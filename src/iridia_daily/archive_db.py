"""SQLite database operations for research paper archives stored in S3.

This module provides a high-performance, low-cost solution for querying
archived research papers by storing them in a SQLite database file in S3.

Architecture:
    - Single SQLite file (~1-2 MB) stored in S3 at archive/papers.db
    - Lambda downloads DB on cold start, caches in /tmp for warm invocations
    - Provides sub-millisecond queries after initial download
    - Newsletter handler downloads, appends new papers, uploads back to S3

Design Decisions:
    1. SQLite over DynamoDB: 80-100x cheaper, full SQL support
    2. FTS5 for search: Native full-text search without complex LIKE queries
    3. Single file: Simple management, atomic updates
    4. /tmp caching with date check: Fresh data daily, zero extra S3 requests
    5. Last-write-wins: Only one writer (newsletter), no locking needed

Cost Analysis (at 10K requests/day):
    - Storage: 2 MB in S3 = $0.00005/month
    - Downloads: 5% cold start × 10K = 500 downloads = $0.0002/month
    - Total: ~$0.0003/month vs $0.08/month for DynamoDB
"""

import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime

import boto3

from .logger import log_info, log_warning, log_error

# Initialize S3 client at module level for reuse across invocations
s3_client = boto3.client('s3')

# Constants for database management
DB_KEY = 'archive/papers.db'
LOCAL_DB_PATH = '/tmp/papers.db'


def get_db_connection() -> sqlite3.Connection:
    """Get SQLite database connection with daily cache invalidation.

    Downloads database from S3 on cold start or when cache is from a previous
    day. This ensures fresh data after newsletter runs (once daily at 7 AM)
    while maximizing cache benefits during the day.

    Lambda containers are naturally recycled overnight when traffic is low,
    so the first request each day automatically gets a fresh database.
    The date check handles the edge case of constantly-warm Lambda instances.

    Returns:
        sqlite3.Connection: Database connection with row_factory enabled
            for dict-like row access.

    Raises:
        Exception: If database download fails or S3 is unreachable.

    Example:
        >>> conn = get_db_connection()
        >>> cursor = conn.cursor()
        >>> cursor.execute("SELECT COUNT(*) FROM papers")
        >>> count = cursor.fetchone()[0]
    """
    bucket_name = os.environ.get('ARCHIVE_BUCKET_NAME')

    if not bucket_name:
        log_error('archive_bucket_not_configured')
        raise ValueError('ARCHIVE_BUCKET_NAME environment variable not set')

    # Check if cache is from today
    # This ensures fresh data after daily newsletter updates
    cache_date_file = '/tmp/db_cached_date.txt'
    today = datetime.now().date().isoformat()
    
    cache_is_fresh = False
    if Path(LOCAL_DB_PATH).exists() and Path(cache_date_file).exists():
        try:
            with open(cache_date_file, 'r') as f:
                cached_date = f.read().strip()
                if cached_date == today:
                    cache_is_fresh = True
                    log_info('using_cached_database',
                            cached_date=cached_date,
                            path=LOCAL_DB_PATH)
        except Exception as e:
            log_warning('cache_date_check_failed', error=str(e))
    
    # Download fresh copy if cache is stale or doesn't exist
    if not cache_is_fresh:
        reason = 'not_cached' if not Path(LOCAL_DB_PATH).exists() else 'new_day'
        log_info('downloading_database_from_s3',
                 bucket=bucket_name,
                 key=DB_KEY,
                 reason=reason)
        
        try:
            # Download database file from S3 to Lambda's /tmp directory
            s3_client.download_file(bucket_name, DB_KEY, LOCAL_DB_PATH)
            
            # Mark cache as fresh for today
            with open(cache_date_file, 'w') as f:
                f.write(today)
            
            file_size = Path(LOCAL_DB_PATH).stat().st_size
            log_info('database_downloaded_successfully',
                     size_bytes=file_size,
                     size_mb=round(file_size / 1024 / 1024, 2),
                     cached_date=today)

        except s3_client.exceptions.NoSuchKey:
            # Database doesn't exist yet - create new one
            log_warning('database_not_found_initializing_new',
                       bucket=bucket_name,
                       key=DB_KEY)
            initialize_database()

        except Exception as e:
            log_error('database_download_failed',
                     error=str(e),
                     error_type=type(e).__name__)
            raise

    # Open connection with row factory for dict-like access
    # This allows accessing columns by name: row['title'] instead of row[0]
    conn = sqlite3.connect(LOCAL_DB_PATH)
    conn.row_factory = sqlite3.Row

    return conn


def initialize_database() -> None:
    """Create new SQLite database with optimized schema and indexes.

    Schema Design:
        - papers table: Main storage with indexed columns
        - papers_fts: FTS5 virtual table for full-text search
        - Indexes on date DESC (sorting) and topic (filtering)

    Why FTS5:
        FTS5 provides orders of magnitude faster text search than LIKE:
        - LIKE '%term%': O(n) scan of all rows
        - FTS5: O(log n) indexed lookup
        - Supports phrase queries, prefix matching, relevance ranking

    This function is called automatically if database doesn't exist in S3.

    Raises:
        Exception: If database creation or S3 upload fails.
    """
    log_info('initializing_new_database')

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cursor = conn.cursor()

    # Main papers table with all paper metadata
    # pmid is primary key (unique PubMed identifier)
    cursor.execute("""
        CREATE TABLE papers (
            pmid TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            journal TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Index on date for efficient sorting (newest first is most common query)
    # DESC order means index can be used directly for ORDER BY date DESC
    cursor.execute(
        "CREATE INDEX idx_date ON papers(date DESC)"
    )

    # Index on topic for efficient filtering by category
    cursor.execute(
        "CREATE INDEX idx_topic ON papers(topic)"
    )

    # FTS5 virtual table for full-text search across title, summary, journal
    # Why separate table: FTS5 uses specialized storage format for performance
    # Content parameter links to main table for automatic sync
    cursor.execute("""
        CREATE VIRTUAL TABLE papers_fts USING fts5(
            title,
            summary,
            journal,
            content=papers,
            content_rowid=rowid
        )
    """)

    # Triggers to keep FTS table in sync with main papers table
    # These ensure FTS index updates automatically on INSERT/UPDATE/DELETE
    cursor.execute("""
        CREATE TRIGGER papers_fts_insert AFTER INSERT ON papers BEGIN
            INSERT INTO papers_fts(rowid, title, summary, journal)
            VALUES (new.rowid, new.title, new.summary, new.journal);
        END
    """)

    cursor.execute("""
        CREATE TRIGGER papers_fts_delete AFTER DELETE ON papers BEGIN
            DELETE FROM papers_fts WHERE rowid = old.rowid;
        END
    """)

    cursor.execute("""
        CREATE TRIGGER papers_fts_update AFTER UPDATE ON papers BEGIN
            DELETE FROM papers_fts WHERE rowid = old.rowid;
            INSERT INTO papers_fts(rowid, title, summary, journal)
            VALUES (new.rowid, new.title, new.summary, new.journal);
        END
    """)

    conn.commit()
    conn.close()

    log_info('database_schema_created')

    # Upload new empty database to S3
    upload_database_to_s3()


def upload_database_to_s3() -> None:
    """Upload local database file to S3.

    Called by newsletter handler after adding new papers.
    Uses atomic upload - if upload fails, S3 still has previous version.

    Raises:
        Exception: If S3 upload fails.
    """
    bucket_name = os.environ.get('ARCHIVE_BUCKET_NAME')

    if not bucket_name:
        log_error('archive_bucket_not_configured')
        raise ValueError('ARCHIVE_BUCKET_NAME environment variable not set')

    try:
        file_size = Path(LOCAL_DB_PATH).stat().st_size

        log_info('uploading_database_to_s3',
                 bucket=bucket_name,
                 key=DB_KEY,
                 size_bytes=file_size,
                 size_mb=round(file_size / 1024 / 1024, 2))

        # Upload with metadata for debugging and monitoring
        s3_client.upload_file(
            LOCAL_DB_PATH,
            bucket_name,
            DB_KEY,
            ExtraArgs={
                'ContentType': 'application/x-sqlite3',
                'Metadata': {
                    'uploaded_at': str(file_size),
                    'file_size_bytes': str(file_size)
                }
            }
        )

        log_info('database_uploaded_successfully')

    except Exception as e:
        log_error('database_upload_failed',
                 error=str(e),
                 error_type=type(e).__name__)
        raise


def add_papers(papers: List[Dict], summaries_by_pmid: Dict[str, str],
               pmid_to_topic: Dict[str, str]) -> int:
    """Add new papers to database in batch operation.

    This is the primary write operation, called once daily by newsletter
    handler. Uses INSERT OR REPLACE to handle duplicate pmids gracefully.

    Design Decision - INSERT OR REPLACE vs INSERT OR IGNORE:
        - REPLACE: Updates paper if pmid exists (handles corrections)
        - Better for data quality if PubMed metadata improves
        - Minimal overhead since pmid collisions are rare

    Args:
        papers: List of paper dictionaries from PubMed.
        summaries_by_pmid: Mapping of PMID to generated summary text.
        pmid_to_topic: Mapping of PMID to topic category.

    Returns:
        int: Number of papers successfully inserted/updated.

    Raises:
        Exception: If database operations fail.

    Example:
        >>> papers = [{'pmid': '12345', 'title': 'Study', ...}]
        >>> summaries = {'12345': 'Summary text'}
        >>> topics = {'12345': 'neuroscience'}
        >>> count = add_papers(papers, summaries, topics)
        >>> print(f"Added {count} papers")
    """
    if not papers:
        log_warning('no_papers_to_add')
        return 0

    conn = get_db_connection()
    cursor = conn.cursor()

    # Use ISO date format for consistent sorting and comparison
    # YYYY-MM-DD format works correctly with string comparison in SQLite
    date_str = datetime.now().strftime('%Y-%m-%d')

    inserted_count = 0

    try:
        # Batch insert for efficiency - single transaction for all papers
        for paper in papers:
            pmid = paper.get('pmid')

            if not pmid or pmid not in summaries_by_pmid:
                log_warning('skipping_paper_missing_data', pmid=pmid)
                continue

            # INSERT OR REPLACE handles duplicates gracefully
            # If pmid exists, row is replaced; otherwise, new row inserted
            cursor.execute("""
                INSERT OR REPLACE INTO papers
                (pmid, topic, date, title, summary, journal, url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                pmid,
                pmid_to_topic.get(pmid, 'default'),
                date_str,
                paper.get('title', ''),
                summaries_by_pmid[pmid],
                paper.get('journal', ''),
                paper.get('url', '')
            ))

            inserted_count += 1

        # Commit all inserts as single transaction for atomicity
        conn.commit()

        log_info('papers_added_to_database',
                 count=inserted_count,
                 date=date_str)

        return inserted_count

    except Exception as e:
        # Rollback on error to maintain database consistency
        conn.rollback()
        log_error('add_papers_failed',
                 error=str(e),
                 error_type=type(e).__name__)
        raise

    finally:
        conn.close()


def query_papers(limit: int = 10, offset: int = 0,
                 topic_filter: Optional[str] = None,
                 search_query: Optional[str] = None,
                 sort_order: str = 'date_desc') -> Tuple[List[Dict], int]:
    """Query papers with pagination, filtering, and full-text search.

    This is the primary read operation for the archive API.
    Uses prepared statements to prevent SQL injection.

    Query Optimization:
        - Indexes on date and topic enable fast filtering
        - FTS5 provides fast full-text search
        - LIMIT/OFFSET allows efficient pagination
        - COUNT query uses covering index (doesn't read rows)

    Args:
        limit: Maximum number of papers to return (1-100).
        offset: Number of papers to skip (for pagination).
        topic_filter: Optional topic to filter by (e.g., 'neuroscience').
        search_query: Optional full-text search query.
        sort_order: Sort order - 'date_desc' or 'date_asc'.

    Returns:
        Tuple of (papers_list, total_count):
            - papers_list: List of paper dicts for current page
            - total_count: Total matching papers (for pagination metadata)

    Raises:
        Exception: If database query fails.

    Example:
        >>> papers, total = query_papers(limit=10, offset=0,
        ...                              topic_filter='neuroscience')
        >>> print(f"Showing 10 of {total} papers")
        >>> for paper in papers:
        ...     print(paper['title'])
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Build WHERE clause dynamically based on filters
    # Using list for clauses ensures proper AND joining
    where_clauses = []
    params = []

    # Topic filter uses indexed column for fast filtering
    if topic_filter:
        where_clauses.append("papers.topic = ?")
        params.append(topic_filter)

    # Full-text search using FTS5 virtual table
    # FTS5 match syntax: "word1 word2" searches for both words
    if search_query:
        # Join papers table with FTS table for combined filtering
        # FTS MATCH is much faster than LIKE for text search
        where_clauses.append("""
            papers.rowid IN (
                SELECT rowid FROM papers_fts
                WHERE papers_fts MATCH ?
            )
        """)
        params.append(search_query)

    # Construct final WHERE clause
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Determine sort direction
    # Using DESC/ASC with indexed column enables index-only scan
    order_direction = "DESC" if sort_order == 'date_desc' else "ASC"

    try:
        # Get total count of matching papers
        # This is needed for frontend pagination (total pages calculation)
        # COUNT(*) with indexed WHERE is very fast
        count_query = f"SELECT COUNT(*) FROM papers WHERE {where_sql}"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        log_info('papers_count_query',
                 total_count=total_count,
                 topic_filter=topic_filter or 'none',
                 search_query=search_query or 'none')

        # Get page of results with LIMIT and OFFSET
        # SQLite optimizes this with indexes - doesn't read skipped rows
        # pmid is a stable secondary sort key — many papers share the same date,
        # and without a tiebreaker SQLite's row order within a date group is
        # undefined and can shift after WAL checkpoints or VACUUM operations.
        papers_query = f"""
            SELECT pmid, topic, date, title, summary, journal, url
            FROM papers
            WHERE {where_sql}
            ORDER BY date {order_direction}, pmid ASC
            LIMIT ? OFFSET ?
        """

        # Append limit and offset to params list
        query_params = params + [limit, offset]
        cursor.execute(papers_query, query_params)

        # Convert Row objects to dicts for JSON serialization
        # Using row_factory=sqlite3.Row enables column name access
        papers = [dict(row) for row in cursor.fetchall()]

        log_info('papers_query_executed',
                 returned=len(papers),
                 total=total_count,
                 limit=limit,
                 offset=offset)

        return papers, total_count

    except Exception as e:
        log_error('query_papers_failed',
                 error=str(e),
                 error_type=type(e).__name__)
        raise

    finally:
        conn.close()


def get_papers_by_date(date_str: str) -> List[Dict]:
    """Get all papers from a specific date.

    Used by /archive/{date} endpoint for fetching specific day's archive.

    Args:
        date_str: Date string in YYYY-MM-DD format.

    Returns:
        List of paper dictionaries for that date, or empty list if none found.

    Example:
        >>> papers = get_papers_by_date('2024-11-07')
        >>> print(f"Found {len(papers)} papers from Nov 7")
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Simple date equality check using index for fast lookup
        cursor.execute("""
            SELECT pmid, topic, date, title, summary, journal, url
            FROM papers
            WHERE date = ?
            ORDER BY topic
        """, (date_str,))

        papers = [dict(row) for row in cursor.fetchall()]

        log_info('papers_retrieved_by_date',
                 date=date_str,
                 count=len(papers))

        return papers

    except Exception as e:
        log_error('get_papers_by_date_failed',
                 date=date_str,
                 error=str(e))
        return []

    finally:
        conn.close()


def get_database_stats() -> Dict:
    """Get database statistics for monitoring and debugging.

    Returns:
        Dictionary containing:
            - total_papers: Total number of papers in database
            - earliest_date: Earliest paper date
            - latest_date: Latest paper date
            - topics: Dictionary of topic counts
            - db_size_bytes: Database file size

    Example:
        >>> stats = get_database_stats()
        >>> print(f"Database has {stats['total_papers']} papers")
        >>> print(f"Size: {stats['db_size_mb']} MB")
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM papers")
        total_papers = cursor.fetchone()[0]

        # Get date range
        cursor.execute("SELECT MIN(date), MAX(date) FROM papers")
        earliest_date, latest_date = cursor.fetchone()

        # Get topic distribution
        cursor.execute("""
            SELECT topic, COUNT(*) as count
            FROM papers
            GROUP BY topic
            ORDER BY count DESC
        """)
        topics = {row['topic']: row['count'] for row in cursor.fetchall()}

        # Get file size
        db_size = Path(LOCAL_DB_PATH).stat().st_size

        stats = {
            'total_papers': total_papers,
            'earliest_date': earliest_date,
            'latest_date': latest_date,
            'topics': topics,
            'db_size_bytes': db_size,
            'db_size_mb': round(db_size / 1024 / 1024, 2)
        }

        log_info('database_stats', **stats)

        return stats

    except Exception as e:
        log_error('get_stats_failed', error=str(e))
        return {}

    finally:
        conn.close()