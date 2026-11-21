"""SQLite connection handling and versioned schema migrations.

The schema version is stored in ``PRAGMA user_version``. Every database,
including a brand-new one, goes through the same ordered migrations so that
fresh and upgraded files always end up with an identical schema.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# Schema exactly as created by the CP2 scaffold (version 0). Kept verbatim so
# a fresh database and an existing scaffold database start from the same point.
_LEGACY_QUESTIONS = """CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    ai_answer TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_answer TEXT,
    reviewer TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
)"""


def _migrate_to_v1(db):
    """Add AI status/error, idempotency key, constraints and citations.

    SQLite cannot add CHECK constraints to an existing column, so the table is
    rebuilt (create new -> copy -> drop -> rename) inside one transaction.
    Existing rows were produced by the scaffold placeholder, so they are
    marked ``ai_status='placeholder'``.
    """
    db.execute("""CREATE TABLE questions_v1 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        ai_answer TEXT NOT NULL,
        ai_status TEXT NOT NULL DEFAULT 'placeholder'
            CHECK (ai_status IN ('placeholder', 'ok', 'failed')),
        ai_error TEXT,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'approved')),
        reviewed_answer TEXT,
        reviewer TEXT,
        client_request_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        reviewed_at TEXT
    )""")
    db.execute("""INSERT INTO questions_v1
        (id, question, ai_answer, status, reviewed_answer, reviewer, created_at, reviewed_at)
        SELECT id, question, ai_answer, status, reviewed_answer, reviewer, created_at, reviewed_at
        FROM questions""")
    db.execute("DROP TABLE questions")
    db.execute("ALTER TABLE questions_v1 RENAME TO questions")
    db.execute("CREATE INDEX idx_questions_status ON questions(status, id DESC)")
    db.execute("""CREATE TABLE citations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
        source TEXT NOT NULL,
        snippet TEXT,
        locator TEXT
    )""")
    db.execute("CREATE INDEX idx_citations_question ON citations(question_id)")


def _migrate_to_v2(db):
    """Add an append-only review history.

    ``version`` numbers reviews per question (1, 2, ...) so a future
    "revise approved answer" action needs no schema change. Questions that
    were approved before this table existed get their version-1 entry
    backfilled from the questions row, so every approval has a history.
    """
    db.execute("""CREATE TABLE reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
        version INTEGER NOT NULL CHECK (version >= 1),
        action TEXT NOT NULL CHECK (action IN ('approve')),
        answer TEXT NOT NULL,
        reviewer TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (question_id, version)
    )""")
    db.execute("""INSERT INTO reviews (question_id, version, action, answer, reviewer, created_at)
        SELECT id, 1, 'approve', COALESCE(reviewed_answer, ''), COALESCE(reviewer, 'unknown'),
               COALESCE(reviewed_at, created_at)
        FROM questions WHERE status = 'approved' ORDER BY id""")


# Index i upgrades a database from version i to version i + 1.
MIGRATIONS = [_migrate_to_v1, _migrate_to_v2]
SCHEMA_VERSION = len(MIGRATIONS)


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def _open(self, **kwargs):
        db = sqlite3.connect(self.path, timeout=10, **kwargs)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @contextmanager
    def connect(self):
        """Yield a connection; commit on success, roll back on any exception."""
        db = self._open()
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def migrate(self):
        """Bring the file up to SCHEMA_VERSION. Safe to call concurrently."""
        db = self._open(isolation_level=None)  # explicit transaction control
        try:
            # WAL lets the 5-second newcomer polling read while a mentor writes.
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("BEGIN IMMEDIATE")  # serialise concurrent migrators
            try:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise RuntimeError(
                        f"Database schema v{version} is newer than this code (v{SCHEMA_VERSION})")
                if version == 0:
                    db.execute(_LEGACY_QUESTIONS)
                for step in MIGRATIONS[version:]:
                    step(db)
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        finally:
            db.close()
