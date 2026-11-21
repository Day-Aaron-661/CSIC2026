"""All SQL lives here; routes never build queries themselves."""
import sqlite3
from datetime import datetime, timezone

_PUBLIC_COLUMNS = ("id, question, ai_answer, ai_status, ai_error, status, "
                   "reviewed_answer, reviewer, created_at, reviewed_at")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class QuestionRepository:
    def __init__(self, database):
        self.database = database

    # ---- reads -------------------------------------------------------------
    def _with_citations(self, db, rows):
        items = [dict(row) for row in rows]
        if not items:
            return items
        by_id = {item["id"]: item for item in items}
        for item in items:
            item["citations"] = []
        marks = ",".join("?" * len(by_id))
        for c in db.execute(
                f"SELECT question_id, source, snippet, locator FROM citations "
                f"WHERE question_id IN ({marks}) ORDER BY id", tuple(by_id)):
            by_id[c["question_id"]]["citations"].append(
                {"source": c["source"], "snippet": c["snippet"], "locator": c["locator"]})
        return items

    def _get(self, db, question_id):
        row = db.execute(f"SELECT {_PUBLIC_COLUMNS} FROM questions WHERE id=?",
                         (question_id,)).fetchone()
        if row is None:
            raise NotFound(question_id)
        return self._with_citations(db, [row])[0]

    def get(self, question_id):
        with self.database.connect() as db:
            return self._get(db, question_id)

    def find_by_request_id(self, client_request_id):
        """Return (question_text, public_item) or None."""
        with self.database.connect() as db:
            row = db.execute("SELECT id, question FROM questions WHERE client_request_id=?",
                             (client_request_id,)).fetchone()
            if row is None:
                return None
            return row["question"], self._get(db, row["id"])

    def list(self, status=None, limit=100):
        sql = f"SELECT {_PUBLIC_COLUMNS} FROM questions"
        params = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.database.connect() as db:
            return self._with_citations(db, db.execute(sql, params).fetchall())

    def search_knowledge(self, q=None, limit=100):
        sql = f"SELECT {_PUBLIC_COLUMNS} FROM questions WHERE status='approved'"
        params = []
        if q:
            pattern = f"%{_escape_like(q)}%"
            sql += (" AND (question LIKE ? ESCAPE '\\' COLLATE NOCASE"
                    " OR reviewed_answer LIKE ? ESCAPE '\\' COLLATE NOCASE)")
            params += [pattern, pattern]
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.database.connect() as db:
            return self._with_citations(db, db.execute(sql, params).fetchall())

    # ---- writes ------------------------------------------------------------
    def create(self, question, result, client_request_id=None):
        """Insert a question with its AI result.

        Raises ``sqlite3.IntegrityError`` if ``client_request_id`` already
        exists (a concurrent duplicate submission); the caller resolves it.
        """
        with self.database.connect() as db:
            cur = db.execute(
                """INSERT INTO questions
                   (question, ai_answer, ai_status, ai_error, client_request_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (question, result.answer, result.status, result.error,
                 client_request_id, now_iso()))
            question_id = cur.lastrowid
            db.executemany(
                "INSERT INTO citations (question_id, source, snippet, locator) VALUES (?, ?, ?, ?)",
                [(question_id, c.source.strip(), c.snippet, c.locator) for c in result.citations])
            return self._get(db, question_id)

    def approve(self, question_id, answer, reviewer):
        with self.database.connect() as db:
            cur = db.execute(
                """UPDATE questions SET status='approved', reviewed_answer=?,
                   reviewer=?, reviewed_at=? WHERE id=? AND status='pending'""",
                (answer, reviewer, now_iso(), question_id))
            if cur.rowcount == 0:
                exists = db.execute("SELECT 1 FROM questions WHERE id=?", (question_id,)).fetchone()
                raise NotFound(question_id) if exists is None else Conflict(question_id)
            return self._get(db, question_id)


IntegrityError = sqlite3.IntegrityError
