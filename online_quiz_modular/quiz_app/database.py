"""SQLite data-access layer.

Design notes
------------
* Every public function opens its *own* short-lived connection.  The original
  version shared one global connection/cursor between all browser sessions and
  threads, which is not safe because Streamlit runs each session in its own
  thread.
* All SQL is parameterised (no string formatting of user input).
* ``init_db`` is idempotent and **never deletes data**: missing tables and
  columns are added, legacy rows are repaired, nothing is dropped.
* Functions return plain ``dict`` objects (or lists of them) so the UI layer
  does not depend on sqlite3 types.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from . import config
from .security import hash_password
from .utils import new_certificate_id, now_str


class DuplicateUserError(Exception):
    """Raised when a username is already taken (case-insensitive)."""


# ==========================================================================
# Connection helpers
# ==========================================================================
@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, always close."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    with connection() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def fetch_one(sql: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """Run one write statement and return ``lastrowid``."""
    with connection() as conn:
        return conn.execute(sql, params).lastrowid


# ==========================================================================
# Schema creation and migration
# ==========================================================================
_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        username   TEXT UNIQUE,
        password   TEXT,
        role       TEXT DEFAULT 'student',
        full_name  TEXT,
        email      TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS questions (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT,
        a        TEXT,
        b        TEXT,
        c        TEXT,
        d        TEXT,
        answer   TEXT,
        subject  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS results (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        username       TEXT,
        subject        TEXT,
        score          INTEGER,
        total          INTEGER,
        percentage     REAL,
        status         TEXT,
        date           TEXT DEFAULT CURRENT_TIMESTAMP,
        certificate_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """,
]

# Columns that older versions of the database may be missing.
_COLUMN_MIGRATIONS = {
    "users": {
        "role": "TEXT DEFAULT 'student'",
        "full_name": "TEXT",
        "email": "TEXT",
        "created_at": "TEXT",
    },
    "results": {
        "subject": "TEXT DEFAULT 'General'",
        "percentage": "REAL DEFAULT 0",
        "status": "TEXT DEFAULT 'Pending'",
        "date": "TEXT",
        "certificate_id": "TEXT",
    },
}

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_results_username ON results(username)",
    "CREATE INDEX IF NOT EXISTS idx_results_certificate ON results(certificate_id)",
    "CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject)",
]

_DEFAULT_SETTINGS = {
    "seconds_per_question": str(config.DEFAULT_SECONDS_PER_QUESTION),
    "pass_mark": str(config.DEFAULT_PASS_MARK),
    "organization_name": config.DEFAULT_ORGANIZATION,
}


def init_db() -> None:
    """Create / upgrade the database.  Safe to call any number of times."""
    with connection() as conn:
        for ddl in _TABLES:
            conn.execute(ddl)

        # Add columns that are missing from databases created by older versions.
        for table, columns in _COLUMN_MIGRATIONS.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, definition in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

        for ddl in _INDEXES:
            conn.execute(ddl)

        _ensure_default_settings(conn)
        _repair_legacy_results(conn)
        _ensure_admin(conn)
        _seed_sample_questions(conn)
        _backfill_certificate_ids(conn)


def _ensure_default_settings(conn: sqlite3.Connection) -> None:
    for key, value in _DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value))


def _repair_legacy_results(conn: sqlite3.Connection) -> None:
    """Fix rows written before the percentage/status columns existed."""
    conn.execute(
        """UPDATE results SET percentage = score * 100.0 / total
           WHERE total > 0 AND (percentage IS NULL OR percentage = 0) AND score > 0"""
    )
    pass_mark = _setting(conn, "pass_mark", config.DEFAULT_PASS_MARK)
    conn.execute(
        """UPDATE results
           SET status = CASE WHEN COALESCE(percentage, 0) >= ? THEN 'PASS' ELSE 'FAIL' END
           WHERE status IS NULL OR status = '' OR status = 'Pending'""",
        (float(pass_mark),),
    )


def _ensure_admin(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT id FROM users WHERE username=?", (config.DEFAULT_ADMIN_USERNAME,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users(username, password, role, full_name, created_at) VALUES(?,?,?,?,?)",
            (
                config.DEFAULT_ADMIN_USERNAME,
                hash_password(config.DEFAULT_ADMIN_PASSWORD),
                "admin",
                "Administrator",
                now_str(),
            ),
        )


def _seed_sample_questions(conn: sqlite3.Connection) -> None:
    """Insert the sample questions exactly once for a brand-new database.

    A flag in the settings table remembers that seeding has happened, so
    sample questions do not reappear after an admin deletes them all.
    """
    flag = conn.execute("SELECT value FROM settings WHERE key='samples_seeded'").fetchone()
    if flag:
        return
    count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO questions(question,a,b,c,d,answer,subject) VALUES(?,?,?,?,?,?,?)",
            config.SAMPLE_QUESTIONS,
        )
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('samples_seeded','1')")


def _backfill_certificate_ids(conn: sqlite3.Connection) -> None:
    """Give every passed exam from older versions a certificate id."""
    rows = conn.execute(
        "SELECT id FROM results WHERE status='PASS' AND (certificate_id IS NULL OR certificate_id='')"
    ).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE results SET certificate_id=? WHERE id=?", (new_certificate_id(), row["id"])
        )


# ==========================================================================
# Settings
# ==========================================================================
def _setting(conn: sqlite3.Connection, key: str, default: Any) -> Any:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row and row["value"] not in (None, "") else default


def get_settings() -> Dict[str, Any]:
    """Quiz settings as typed values."""
    with connection() as conn:
        try:
            seconds = int(_setting(conn, "seconds_per_question", config.DEFAULT_SECONDS_PER_QUESTION))
        except ValueError:
            seconds = config.DEFAULT_SECONDS_PER_QUESTION
        try:
            pass_mark = int(float(_setting(conn, "pass_mark", config.DEFAULT_PASS_MARK)))
        except ValueError:
            pass_mark = config.DEFAULT_PASS_MARK
        organization = str(_setting(conn, "organization_name", config.DEFAULT_ORGANIZATION))
    return {"seconds_per_question": seconds, "pass_mark": pass_mark, "organization": organization}


def save_settings(seconds_per_question: int, pass_mark: int, organization: str) -> None:
    values = {
        "seconds_per_question": str(int(seconds_per_question)),
        "pass_mark": str(int(pass_mark)),
        "organization_name": organization.strip() or config.DEFAULT_ORGANIZATION,
    }
    with connection() as conn:
        for key, value in values.items():
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, value))


# ==========================================================================
# Users
# ==========================================================================
def get_user(username: str) -> Optional[Dict[str, Any]]:
    """Exact-match lookup."""
    return fetch_one("SELECT * FROM users WHERE username=?", (username,))


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    return fetch_one("SELECT * FROM users WHERE id=?", (user_id,))


def get_user_for_login(username: str) -> Optional[Dict[str, Any]]:
    """Exact match first; otherwise a case-insensitive match if it is unambiguous."""
    user = get_user(username)
    if user:
        return user
    matches = fetch_all("SELECT * FROM users WHERE lower(username)=lower(?)", (username,))
    return matches[0] if len(matches) == 1 else None


def username_taken(username: str) -> bool:
    return fetch_one("SELECT id FROM users WHERE lower(username)=lower(?)", (username,)) is not None


def create_user(
    username: str,
    password_hash: str,
    role: str = "student",
    full_name: str = "",
    email: str = "",
) -> int:
    """Insert a user; raises :class:`DuplicateUserError` if the name is taken."""
    username = username.strip()
    if username_taken(username):
        raise DuplicateUserError(username)
    try:
        return execute(
            "INSERT INTO users(username, password, role, full_name, email, created_at) VALUES(?,?,?,?,?,?)",
            (username, password_hash, role, full_name.strip(), email.strip(), now_str()),
        )
    except sqlite3.IntegrityError as exc:   # race between check and insert
        raise DuplicateUserError(username) from exc


def set_password_hash(user_id: int, password_hash: str) -> None:
    """Update the password of exactly one user (by id)."""
    execute("UPDATE users SET password=? WHERE id=?", (password_hash, user_id))


def update_profile(user_id: int, full_name: str, email: str) -> None:
    execute(
        "UPDATE users SET full_name=?, email=? WHERE id=?",
        (full_name.strip(), email.strip(), user_id),
    )


def list_students() -> List[Dict[str, Any]]:
    """Students with their exam statistics (for the admin Students page)."""
    return fetch_all(
        """
        SELECT u.id, u.username, u.full_name, u.email, u.created_at,
               COUNT(r.id)                       AS attempts,
               ROUND(COALESCE(AVG(r.percentage), 0), 2) AS average,
               ROUND(COALESCE(MAX(r.percentage), 0), 2) AS best
        FROM users u
        LEFT JOIN results r ON r.username = u.username
        WHERE u.role = 'student'
        GROUP BY u.id
        ORDER BY u.username COLLATE NOCASE
        """
    )


def delete_student(user_id: int) -> bool:
    """Delete a student account together with their results (admins are protected)."""
    user = get_user_by_id(user_id)
    if not user or user["role"] != "student":
        return False
    with connection() as conn:
        conn.execute("DELETE FROM results WHERE username=?", (user["username"],))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    return True


# ==========================================================================
# Questions
# ==========================================================================
def list_subjects() -> List[Dict[str, Any]]:
    """Subjects with the number of questions in each."""
    return fetch_all(
        """SELECT subject, COUNT(*) AS questions FROM questions
           WHERE subject IS NOT NULL AND TRIM(subject) <> ''
           GROUP BY subject ORDER BY subject COLLATE NOCASE"""
    )


def get_exam_questions(subject: str) -> List[Dict[str, Any]]:
    """All questions of a subject in random order."""
    rows = fetch_all(
        """SELECT id, question, a, b, c, d, answer, subject
           FROM questions WHERE subject=? ORDER BY RANDOM()""",
        (subject,),
    )
    for row in rows:
        row["answer"] = (row["answer"] or "").strip().upper()
    return rows


def get_question(question_id: int) -> Optional[Dict[str, Any]]:
    return fetch_one("SELECT * FROM questions WHERE id=?", (question_id,))


def list_questions(subject: Optional[str] = None, search: str = "") -> List[Dict[str, Any]]:
    sql = "SELECT id, subject, question, a, b, c, d, answer FROM questions WHERE 1=1"
    params: List[Any] = []
    if subject:
        sql += " AND subject=?"
        params.append(subject)
    if search.strip():
        sql += " AND question LIKE ?"
        params.append(f"%{search.strip()}%")
    sql += " ORDER BY id"
    return fetch_all(sql, params)


def _canonical_subject(conn: sqlite3.Connection, subject: str) -> str:
    """Reuse the existing spelling/capitalisation of a subject if there is one."""
    subject = " ".join(subject.split())
    row = conn.execute(
        "SELECT subject FROM questions WHERE lower(subject)=lower(?) LIMIT 1", (subject,)
    ).fetchone()
    return row["subject"] if row else subject


def add_question(subject: str, question: str, a: str, b: str, c: str, d: str, answer: str) -> int:
    with connection() as conn:
        subject = _canonical_subject(conn, subject)
        return conn.execute(
            "INSERT INTO questions(question,a,b,c,d,answer,subject) VALUES(?,?,?,?,?,?,?)",
            (question.strip(), a.strip(), b.strip(), c.strip(), d.strip(), answer.upper(), subject),
        ).lastrowid


def add_questions_bulk(rows: Iterable[Dict[str, str]]) -> int:
    """Insert many questions in one transaction; returns how many were added."""
    count = 0
    with connection() as conn:
        for row in rows:
            subject = _canonical_subject(conn, row["subject"])
            conn.execute(
                "INSERT INTO questions(question,a,b,c,d,answer,subject) VALUES(?,?,?,?,?,?,?)",
                (
                    row["question"].strip(), row["a"].strip(), row["b"].strip(),
                    row["c"].strip(), row["d"].strip(), row["answer"].strip().upper(), subject,
                ),
            )
            count += 1
    return count


def update_question(
    question_id: int, subject: str, question: str, a: str, b: str, c: str, d: str, answer: str
) -> None:
    with connection() as conn:
        subject = _canonical_subject(conn, subject)
        conn.execute(
            """UPDATE questions SET question=?, a=?, b=?, c=?, d=?, answer=?, subject=?
               WHERE id=?""",
            (question.strip(), a.strip(), b.strip(), c.strip(), d.strip(), answer.upper(),
             subject, question_id),
        )


def delete_question(question_id: int) -> None:
    execute("DELETE FROM questions WHERE id=?", (question_id,))


# ==========================================================================
# Results
# ==========================================================================
def save_result(
    username: str,
    subject: str,
    score: int,
    total: int,
    percentage: float,
    status: str,
    certificate_id: Optional[str],
    date: Optional[str] = None,
) -> int:
    """Store one finished exam and return its row id."""
    return execute(
        """INSERT INTO results
           (username, subject, score, total, percentage, status, date, certificate_id)
           VALUES(?,?,?,?,?,?,?,?)""",
        (username, subject, score, total, round(percentage, 2), status,
         date or now_str(), certificate_id),
    )


def get_result(result_id: int) -> Optional[Dict[str, Any]]:
    return fetch_one("SELECT * FROM results WHERE id=?", (result_id,))


def get_results(
    username: Optional[str] = None,
    subject: Optional[str] = None,
    status: Optional[str] = None,
    search: str = "",
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Flexible result query, newest first."""
    sql = """SELECT id, username, subject, score, total, percentage, status, date, certificate_id
             FROM results WHERE 1=1"""
    params: List[Any] = []
    if username:
        sql += " AND username=?"
        params.append(username)
    if subject:
        sql += " AND subject=?"
        params.append(subject)
    if status:
        sql += " AND status=?"
        params.append(status)
    if search.strip():
        sql += " AND username LIKE ?"
        params.append(f"%{search.strip()}%")
    sql += " ORDER BY id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return fetch_all(sql, params)


def user_stats(username: str) -> Dict[str, Any]:
    return fetch_one(
        """SELECT COUNT(*) AS attempts,
                  COALESCE(AVG(percentage), 0) AS average,
                  COALESCE(MAX(percentage), 0) AS best,
                  COALESCE(SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END), 0) AS passed
           FROM results WHERE username=?""",
        (username,),
    ) or {"attempts": 0, "average": 0, "best": 0, "passed": 0}


def overall_stats() -> Dict[str, Any]:
    """Headline numbers for the admin dashboard."""
    with connection() as conn:
        students = conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0]
        questions = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        subjects = conn.execute(
            "SELECT COUNT(DISTINCT subject) FROM questions WHERE subject IS NOT NULL"
        ).fetchone()[0]
        attempts = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        passed = conn.execute("SELECT COUNT(*) FROM results WHERE status='PASS'").fetchone()[0]
        average = conn.execute("SELECT COALESCE(AVG(percentage),0) FROM results").fetchone()[0]
    return {
        "students": students,
        "questions": questions,
        "subjects": subjects,
        "attempts": attempts,
        "passed": passed,
        "pass_rate": (passed / attempts * 100.0) if attempts else 0.0,
        "average": average,
    }


def subject_performance() -> List[Dict[str, Any]]:
    return fetch_all(
        """SELECT subject, COUNT(*) AS attempts,
                  ROUND(AVG(percentage), 2) AS average,
                  SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END) AS passed
           FROM results GROUP BY subject ORDER BY subject COLLATE NOCASE"""
    )


def leaderboard(subject: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Best percentage per student (ties: fewer attempts first, then name)."""
    sql = """SELECT username,
                    ROUND(MAX(percentage), 2) AS best,
                    COUNT(*) AS attempts,
                    SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END) AS passed
             FROM results"""
    params: List[Any] = []
    if subject:
        sql += " WHERE subject=?"
        params.append(subject)
    sql += " GROUP BY username ORDER BY best DESC, attempts ASC, username COLLATE NOCASE LIMIT ?"
    params.append(int(limit))
    return fetch_all(sql, params)


def find_certificate(certificate_id: str) -> Optional[Dict[str, Any]]:
    """Look up a passed exam by certificate id (for the public verification page)."""
    return fetch_one(
        """SELECT r.id, r.username, r.subject, r.score, r.total, r.percentage,
                  r.status, r.date, r.certificate_id, u.full_name
           FROM results r LEFT JOIN users u ON u.username = r.username
           WHERE upper(r.certificate_id) = upper(?) AND r.status = 'PASS'""",
        (certificate_id.strip(),),
    )
