"""Tests for archive_db query layer.

Focuses on correctness of pagination, filtering, sorting, and total_count
accuracy — the properties that directly affect what the frontend renders.
"""

import sqlite3
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Create a real SQLite database with the production schema."""
    path = str(tmp_path / 'papers.db')
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

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
    cursor.execute("CREATE INDEX idx_date ON papers(date DESC)")
    cursor.execute("CREATE INDEX idx_topic ON papers(topic)")
    cursor.execute("""
        CREATE VIRTUAL TABLE papers_fts USING fts5(
            title, summary, journal,
            content=papers,
            content_rowid=rowid
        )
    """)
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
    return path


def _insert_papers(db_path, papers):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for p in papers:
        cursor.execute(
            "INSERT INTO papers (pmid, topic, date, title, summary, journal, url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p['pmid'], p['topic'], p['date'], p['title'],
             p['summary'], p.get('journal', ''), p.get('url', ''))
        )
    conn.commit()
    conn.close()


def _make_papers(count, topic='neuroscience', date='2025-01-01',
                 title_prefix='Paper', summary_prefix='Summary'):
    return [
        {
            'pmid': f'pmid{i:04d}',
            'topic': topic,
            'date': date,
            'title': f'{title_prefix} {i}',
            'summary': f'{summary_prefix} {i}',
            'journal': f'Journal {i}',
            'url': f'https://example.com/{i}'
        }
        for i in range(count)
    ]


@pytest.fixture
def patched_db(db_path):
    """Patch get_db_connection so query_papers uses the test database."""
    def _make_conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    with patch('iridia_daily.archive_db.get_db_connection', side_effect=_make_conn):
        yield db_path


# ---------------------------------------------------------------------------
# Ordering stability
# ---------------------------------------------------------------------------

class TestOrderingStability:
    """Papers with the same date must be ordered deterministically."""

    def test_same_date_order_is_stable_across_calls(self, patched_db):
        """Calling query_papers twice with the same args returns identical results."""
        from iridia_daily.archive_db import query_papers

        _insert_papers(patched_db, _make_papers(10, date='2025-01-01'))

        papers_a, _ = query_papers(limit=10, offset=0)
        papers_b, _ = query_papers(limit=10, offset=0)

        assert [p['pmid'] for p in papers_a] == [p['pmid'] for p in papers_b]

    def test_same_date_pagination_has_no_duplicate_papers(self, patched_db):
        """No paper appears on two pages when all papers share the same date."""
        from iridia_daily.archive_db import query_papers

        _insert_papers(patched_db, _make_papers(25, date='2025-01-01'))

        page1, _ = query_papers(limit=10, offset=0)
        page2, _ = query_papers(limit=10, offset=10)
        page3, _ = query_papers(limit=10, offset=20)

        all_pmids = (
            [p['pmid'] for p in page1]
            + [p['pmid'] for p in page2]
            + [p['pmid'] for p in page3]
        )

        assert len(all_pmids) == len(set(all_pmids)), \
            "Duplicate papers found across pages"

    def test_same_date_pagination_covers_all_papers(self, patched_db):
        """Paginating through all pages returns every paper exactly once."""
        from iridia_daily.archive_db import query_papers

        papers = _make_papers(25, date='2025-01-01')
        _insert_papers(patched_db, papers)
        expected_pmids = {p['pmid'] for p in papers}

        collected = []
        for page in range(3):
            results, _ = query_papers(limit=10, offset=page * 10)
            collected.extend(p['pmid'] for p in results)

        assert set(collected) == expected_pmids, \
            "Some papers were skipped or duplicated during pagination"


# ---------------------------------------------------------------------------
# Total count accuracy
# ---------------------------------------------------------------------------

class TestTotalCount:
    """total_count must reflect the filtered result set, not the whole table."""

    def test_total_count_matches_table_size_unfiltered(self, patched_db):
        from iridia_daily.archive_db import query_papers

        _insert_papers(patched_db, _make_papers(15))
        _, total = query_papers(limit=5, offset=0)

        assert total == 15

    def test_total_count_is_same_on_every_page(self, patched_db):
        """total_count should not decrease as offset increases."""
        from iridia_daily.archive_db import query_papers

        _insert_papers(patched_db, _make_papers(20))

        _, total_page1 = query_papers(limit=5, offset=0)
        _, total_page2 = query_papers(limit=5, offset=5)
        _, total_page3 = query_papers(limit=5, offset=10)

        assert total_page1 == total_page2 == total_page3 == 20

    def test_total_count_reflects_topic_filter(self, patched_db):
        from iridia_daily.archive_db import query_papers

        _insert_papers(patched_db, _make_papers(10, topic='neuroscience'))
        _insert_papers(patched_db, [
            {**p, 'pmid': f'space{p["pmid"]}', 'topic': 'space'}
            for p in _make_papers(5, topic='space')
        ])

        _, total = query_papers(limit=10, offset=0, topic_filter='neuroscience')

        assert total == 10

    def test_total_count_reflects_search_filter(self, patched_db):
        from iridia_daily.archive_db import query_papers

        papers = _make_papers(5)
        papers[0]['title'] = 'Quantum entanglement in neural tissue'
        papers[0]['summary'] = 'A study of quantum effects'
        _insert_papers(patched_db, papers)

        _, total = query_papers(limit=10, offset=0, search_query='quantum')

        assert total == 1

    def test_total_count_with_combined_topic_and_search(self, patched_db):
        from iridia_daily.archive_db import query_papers

        neuro_papers = _make_papers(5, topic='neuroscience')
        neuro_papers[0]['title'] = 'CRISPR gene editing in neural cells'
        neuro_papers[0]['summary'] = 'CRISPR applications in brain research'

        space_papers = [
            {**p, 'pmid': f'sp{p["pmid"]}', 'topic': 'space',
             'title': 'CRISPR in microgravity', 'summary': 'CRISPR study'}
            for p in _make_papers(2, topic='space')
        ]

        _insert_papers(patched_db, neuro_papers + space_papers)

        _, total = query_papers(
            limit=10, offset=0,
            topic_filter='neuroscience',
            search_query='CRISPR'
        )

        assert total == 1

    def test_total_count_when_offset_exceeds_results(self, patched_db):
        """total_count stays accurate even when the page itself is empty."""
        from iridia_daily.archive_db import query_papers

        _insert_papers(patched_db, _make_papers(5))
        papers, total = query_papers(limit=10, offset=100)

        assert papers == []
        assert total == 5


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

class TestFiltering:
    def test_topic_filter_excludes_other_topics(self, patched_db):
        from iridia_daily.archive_db import query_papers

        _insert_papers(patched_db, _make_papers(5, topic='neuroscience'))
        _insert_papers(patched_db, [
            {**p, 'pmid': f'sp{p["pmid"]}', 'topic': 'space'}
            for p in _make_papers(5, topic='space')
        ])

        papers, _ = query_papers(limit=20, offset=0, topic_filter='neuroscience')

        assert all(p['topic'] == 'neuroscience' for p in papers)

    def test_search_returns_matching_papers(self, patched_db):
        from iridia_daily.archive_db import query_papers

        papers = _make_papers(5)
        papers[2]['title'] = 'Dopamine receptor binding kinetics'
        papers[2]['summary'] = 'Study of dopamine in the striatum'
        _insert_papers(patched_db, papers)

        results, _ = query_papers(limit=10, offset=0, search_query='dopamine')

        assert len(results) == 1
        assert results[0]['pmid'] == papers[2]['pmid']

    def test_empty_search_returns_all_papers(self, patched_db):
        from iridia_daily.archive_db import query_papers

        _insert_papers(patched_db, _make_papers(7))
        papers, total = query_papers(limit=20, offset=0, search_query=None)

        assert total == 7

    def test_no_filter_returns_all_topics(self, patched_db):
        from iridia_daily.archive_db import query_papers

        _insert_papers(patched_db, _make_papers(3, topic='neuroscience'))
        _insert_papers(patched_db, [
            {**p, 'pmid': f'sp{p["pmid"]}', 'topic': 'space'}
            for p in _make_papers(3, topic='space')
        ])

        papers, total = query_papers(limit=20, offset=0)

        assert total == 6
        topics = {p['topic'] for p in papers}
        assert 'neuroscience' in topics
        assert 'space' in topics


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

class TestSorting:
    def test_date_desc_returns_newest_first(self, patched_db):
        from iridia_daily.archive_db import query_papers

        papers = [
            {**_make_papers(1)[0], 'pmid': 'old', 'date': '2024-01-01'},
            {**_make_papers(1)[0], 'pmid': 'mid', 'date': '2025-01-01'},
            {**_make_papers(1)[0], 'pmid': 'new', 'date': '2025-06-01'},
        ]
        _insert_papers(patched_db, papers)

        results, _ = query_papers(limit=10, offset=0, sort_order='date_desc')
        dates = [r['date'] for r in results]

        assert dates == sorted(dates, reverse=True)

    def test_date_asc_returns_oldest_first(self, patched_db):
        from iridia_daily.archive_db import query_papers

        papers = [
            {**_make_papers(1)[0], 'pmid': 'old', 'date': '2024-01-01'},
            {**_make_papers(1)[0], 'pmid': 'mid', 'date': '2025-01-01'},
            {**_make_papers(1)[0], 'pmid': 'new', 'date': '2025-06-01'},
        ]
        _insert_papers(patched_db, papers)

        results, _ = query_papers(limit=10, offset=0, sort_order='date_asc')
        dates = [r['date'] for r in results]

        assert dates == sorted(dates)

    def test_date_desc_and_asc_are_inverses(self, patched_db):
        from iridia_daily.archive_db import query_papers

        papers = [
            {**_make_papers(1)[0], 'pmid': f'p{i}', 'date': f'2025-0{i+1}-01'}
            for i in range(5)
        ]
        _insert_papers(patched_db, papers)

        desc, _ = query_papers(limit=10, offset=0, sort_order='date_desc')
        asc, _ = query_papers(limit=10, offset=0, sort_order='date_asc')

        assert [p['pmid'] for p in desc] == [p['pmid'] for p in reversed(asc)]
