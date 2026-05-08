import sqlite3
import boto3
import os

# Set your bucket name here
BUCKET_NAME = "iridia-daily-archive-prod"

# Create database
print("Creating database...")
conn = sqlite3.connect('/tmp/papers.db')
cursor = conn.cursor()

# Create table
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

# Create indexes
cursor.execute("CREATE INDEX idx_date ON papers(date DESC)")
cursor.execute("CREATE INDEX idx_topic ON papers(topic)")

# Create FTS table
cursor.execute("""
    CREATE VIRTUAL TABLE papers_fts USING fts5(
        title,
        summary,
        journal,
        content=papers,
        content_rowid=rowid
    )
""")

# Create triggers
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

print("✓ Database created")

# Upload to S3
print("Uploading to S3...")
s3 = boto3.client('s3')
s3.upload_file('/tmp/papers.db', BUCKET_NAME, 'archive/papers.db')
print(f"✓ Uploaded to s3://{BUCKET_NAME}/archive/papers.db")
print("\nDone!")