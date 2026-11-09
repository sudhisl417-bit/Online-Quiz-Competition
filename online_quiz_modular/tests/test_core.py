"""Unit tests for the framework-independent layers.

Run from the project folder:

    python -m unittest discover -s tests -v

These tests use a throw-away SQLite file and never touch quiz_database.db.
"""

import hashlib
import pathlib
import sqlite3
import sys
import tempfile
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:                                   # the logic tests do not need a running Streamlit
    import streamlit  # noqa: F401
except ImportError:
    sys.modules["streamlit"] = types.ModuleType("streamlit")

from quiz_app import config, database as db, security, utils      # noqa: E402
from quiz_app.certificates import generate_certificate_pdf          # noqa: E402


class TempDatabaseCase(unittest.TestCase):
    """Each test gets its own empty database file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_path = config.DB_PATH
        config.DB_PATH = pathlib.Path(self._tmp.name) / "test.db"

    def tearDown(self):
        config.DB_PATH = self._old_path
        self._tmp.cleanup()


class SecurityTests(unittest.TestCase):
    def test_hash_and_verify(self):
        stored = security.hash_password("secret1")
        self.assertTrue(stored.startswith("pbkdf2$"))
        self.assertTrue(security.verify_password("secret1", stored))
        self.assertFalse(security.verify_password("wrong", stored))
        self.assertNotEqual(stored, security.hash_password("secret1"))   # random salt

    def test_legacy_sha256_hash_is_accepted(self):
        legacy = hashlib.sha256(b"oldpw").hexdigest()
        self.assertTrue(security.is_legacy_hash(legacy))
        self.assertTrue(security.verify_password("oldpw", legacy))
        self.assertFalse(security.verify_password("nope", legacy))

    def test_garbage_hashes_do_not_crash(self):
        for bad in (None, "", "pbkdf2$zz$zz", "pbkdf2$", "é"):
            self.assertFalse(security.verify_password("x", bad))

    def test_validators(self):
        self.assertIsNone(security.validate_username("asha_nair"))
        self.assertIsNotNone(security.validate_username("a b"))
        self.assertIsNotNone(security.validate_username("ab"))
        self.assertIsNone(security.validate_email(""))
        self.assertIsNotNone(security.validate_email("nope"))
        self.assertIsNotNone(security.validate_password("abc"))
        self.assertIsNotNone(security.validate_password("abcdef", "abcxyz"))
        self.assertIsNone(security.validate_password("abcdef", "abcdef"))

    def test_throttle_locks_and_resets(self):
        throttle = security.LoginThrottle(3, 60)
        for _ in range(3):
            throttle.register_failure("u")
        self.assertGreater(throttle.seconds_locked("u"), 0)
        throttle.reset("u")
        self.assertEqual(throttle.seconds_locked("u"), 0)


class UtilsTests(unittest.TestCase):
    def test_helpers(self):
        self.assertEqual(utils.initials("Asha Nair"), "AN")
        self.assertEqual(utils.initials("ansh"), "AN")
        self.assertEqual(utils.percentage_of(1, 0), 0.0)
        self.assertEqual(utils.grade_label(95), "Distinction")
        self.assertEqual(utils.grade_label(80), "Merit")
        self.assertEqual(utils.grade_label(60), "Pass")
        self.assertEqual(utils.esc("<b>&"), "&lt;b&gt;&amp;")
        self.assertEqual(utils.md_escape("*a*_b_"), r"\*a\*\_b\_")
        self.assertEqual(utils.pretty_date("2026-11-06 14:05:00"), "06 November 2026")
        self.assertEqual(utils.pretty_date(None), "—")


class DatabaseTests(TempDatabaseCase):
    def test_fresh_database_has_admin_samples_and_settings(self):
        db.init_db()
        db.init_db()                                          # idempotent
        self.assertEqual(db.get_user("ansh")["role"], "admin")
        self.assertTrue(security.verify_password("12345678", db.get_user("ansh")["password"]))
        subjects = {s["subject"] for s in db.list_subjects()}
        self.assertEqual(subjects, {"Python", "Web", "Database", "Java"})
        self.assertEqual(db.get_settings()["seconds_per_question"], 30)

    def test_samples_do_not_reappear_after_deleting_everything(self):
        db.init_db()
        for q in db.list_questions():
            db.delete_question(q["id"])
        db.init_db()
        self.assertEqual(db.list_questions(), [])

    def test_legacy_database_is_migrated_without_data_loss(self):
        conn = sqlite3.connect(config.DB_PATH)
        conn.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT);
            CREATE TABLE questions (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT,
                a TEXT, b TEXT, c TEXT, d TEXT, answer TEXT, subject TEXT);
            CREATE TABLE results (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT,
                score INTEGER, total INTEGER);
            """
        )
        conn.execute("INSERT INTO users(username,password) VALUES('olduser',?)",
                     (hashlib.sha256(b"secret1").hexdigest(),))
        conn.execute("INSERT INTO questions(question,a,b,c,d,answer,subject) "
                     "VALUES('Q?','1','2','3','4','B','Custom')")
        conn.execute("INSERT INTO results(username,score,total) VALUES('olduser',8,10)")
        conn.execute("INSERT INTO results(username,score,total) VALUES('olduser',2,10)")
        conn.commit()
        conn.close()

        db.init_db()

        self.assertEqual(db.get_user("olduser")["role"], "student")
        self.assertEqual([q["subject"] for q in db.list_questions()], ["Custom"])  # no samples injected
        rows = {r["score"]: r for r in db.get_results(username="olduser")}
        self.assertEqual(rows[8]["status"], "PASS")
        self.assertAlmostEqual(rows[8]["percentage"], 80.0)
        self.assertTrue(rows[8]["certificate_id"].startswith("QUIZ-"))
        self.assertEqual(rows[2]["status"], "FAIL")

    def test_users(self):
        db.init_db()
        uid = db.create_user("Asha", security.hash_password("pw12345"), "student", "Asha Nair", "a@b.co")
        with self.assertRaises(db.DuplicateUserError):
            db.create_user("asha", "x")                       # case-insensitive
        self.assertEqual(db.get_user_for_login("ASHA")["id"], uid)
        db.update_profile(uid, "New Name", "")
        self.assertEqual(db.get_user_by_id(uid)["full_name"], "New Name")
        self.assertFalse(db.delete_student(db.get_user("ansh")["id"]))   # admin protected

    def test_password_update_touches_only_one_user(self):
        db.init_db()
        legacy = hashlib.sha256(b"same").hexdigest()
        a = db.create_user("a_user", legacy)
        b = db.create_user("b_user", legacy)
        db.set_password_hash(a, security.hash_password("same"))
        self.assertTrue(security.is_legacy_hash(db.get_user_by_id(b)["password"]))

    def test_questions_crud_and_subject_canonicalisation(self):
        db.init_db()
        qid = db.add_question("python  basics", "Q", "a", "b", "c", "d", "a")
        db.add_question("Python Basics", "Q2", "a", "b", "c", "d", "b")
        self.assertEqual(len(db.list_questions(subject="python basics")), 2)   # same subject, one spelling
        self.assertEqual({s["subject"] for s in db.list_subjects()}, {"Python", "Web", "Database", "Java", "python basics"})
        db.update_question(qid, "python basics", "Edited", "1", "2", "3", "4", "d")
        self.assertEqual(db.get_question(qid)["answer"], "D")
        self.assertEqual(db.add_questions_bulk([
            {"subject": "Go", "question": "q", "a": "1", "b": "2", "c": "3", "d": "4", "answer": "c"}]), 1)

    def test_results_leaderboard_and_certificate_lookup(self):
        db.init_db()
        uid = db.create_user("asha", security.hash_password("pw12345"), "student", "Asha Nair", "")
        db.save_result("asha", "Python", 8, 9, 88.888, "PASS", "QUIZ-AAAA111111")
        db.save_result("asha", "Python", 3, 9, 33.33, "FAIL", None)
        db.save_result("zed", "Web", 9, 9, 100, "PASS", "QUIZ-CCCC333333")
        board = db.leaderboard()
        self.assertEqual([r["username"] for r in board], ["zed", "asha"])
        self.assertEqual(db.leaderboard("Python")[0]["username"], "asha")
        stats = db.user_stats("asha")
        self.assertEqual((stats["attempts"], stats["passed"]), (2, 1))
        self.assertEqual(db.find_certificate("quiz-aaaa111111")["full_name"], "Asha Nair")
        self.assertIsNone(db.find_certificate("QUIZ-NOPE"))
        overall = db.overall_stats()
        self.assertEqual((overall["attempts"], overall["passed"]), (3, 2))
        self.assertTrue(db.delete_student(uid))
        self.assertEqual(db.get_results(username="asha"), [])

    def test_settings_round_trip(self):
        db.init_db()
        db.save_settings(45, 60, "  Kerala Academy ")
        self.assertEqual(
            db.get_settings(),
            {"seconds_per_question": 45, "pass_mark": 60, "organization": "Kerala Academy"},
        )


class CertificateTests(unittest.TestCase):
    RESULT = {"subject": "Python", "score": 8, "total": 9, "percentage": 88.89,
              "date": "2026-11-06 14:05:00", "certificate_id": "QUIZ-3F9A1C07BD"}

    def test_pdf_is_generated(self):
        pdf = generate_certificate_pdf(self.RESULT, "Asha Nair", "Online Quiz Application")
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 3000)

    def test_unusual_input_does_not_crash(self):
        long_subject = dict(self.RESULT, subject="X" * 200)
        pdf = generate_certificate_pdf(long_subject, "അൻഷ് " + "N" * 100, "Org " * 40)
        self.assertTrue(pdf.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
