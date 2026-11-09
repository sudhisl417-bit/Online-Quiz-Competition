"""Central configuration for the Online Quiz Application.

Everything that might reasonably be tuned lives here so the rest of the code
base contains no "magic" values.
"""

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Application identity
# --------------------------------------------------------------------------
APP_NAME = "Online Quiz Portal"
APP_ICON = "🎓"

# --------------------------------------------------------------------------
# Database location
# --------------------------------------------------------------------------
# The database file sits in the project folder (next to app.py) so it is the
# same file no matter which directory the app is started from.  Set the
# QUIZ_DB_PATH environment variable to use a different file.
ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("QUIZ_DB_PATH", ROOT_DIR / "quiz_database.db"))

# --------------------------------------------------------------------------
# Default administrator (created automatically if missing)
# --------------------------------------------------------------------------
DEFAULT_ADMIN_USERNAME = "ansh"
DEFAULT_ADMIN_PASSWORD = "12345678"

# --------------------------------------------------------------------------
# Quiz defaults (admins can change these on the Settings page)
# --------------------------------------------------------------------------
DEFAULT_SECONDS_PER_QUESTION = 30
DEFAULT_PASS_MARK = 50
DEFAULT_ORGANIZATION = "Online Quiz Application"
OPTION_LETTERS = ("A", "B", "C", "D")

# --------------------------------------------------------------------------
# Account rules
# --------------------------------------------------------------------------
MIN_PASSWORD_LENGTH = 6
MAX_FAILED_LOGINS = 5          # failed attempts before a temporary lock
LOCKOUT_SECONDS = 300          # how long the lock lasts

# --------------------------------------------------------------------------
# Sample questions inserted into a brand-new database
# (question, A, B, C, D, correct letter, subject)
# --------------------------------------------------------------------------
SAMPLE_QUESTIONS = [
    # ---- the original sample questions --------------------------------
    ("Which language is used in AI?", "HTML", "Python", "CSS", "XML", "B", "Python"),
    ("What is the Python file extension?", ".html", ".java", ".py", ".css", "C", "Python"),
    ("Which function displays output?", "input()", "print()", "show()", "display()", "B", "Python"),
    ("Which data type stores True or False?", "String", "Integer", "Boolean", "Float", "C", "Python"),
    ("Which language is used for web styling?", "Python", "Java", "CSS", "SQL", "C", "Web"),
    ("Which language is used for database queries?", "HTML", "SQL", "CSS", "XML", "B", "Database"),
    ("Which keyword creates a class in Python?", "function", "class", "define", "object", "B", "Python"),
    ("Which language is known for Android development?", "Java", "HTML", "CSS", "SQL", "A", "Java"),
    ("Which symbol starts a comment in Python?", "//", "#", "/*", "$", "B", "Python"),
    # ---- extra questions so every subject has enough to practise with ----
    ("Which tag defines a hyperlink in HTML?", "<link>", "<a>", "<href>", "<url>", "B", "Web"),
    ("Which language adds interactivity to web pages?", "JavaScript", "SQL", "XML", "YAML", "A", "Web"),
    ("What does HTML stand for?", "Hyper Text Markup Language", "High Tech Modern Language",
     "Hyperlinks and Text Markup Language", "Home Tool Markup Language", "A", "Web"),
    ("Which SQL statement removes rows from a table?", "REMOVE", "DROP ROW", "DELETE", "CUT", "C", "Database"),
    ("Which SQL clause filters records?", "WHERE", "ORDER BY", "GROUP", "LIMIT", "A", "Database"),
    ("Which key uniquely identifies a row in a table?", "Foreign key", "Primary key", "Index key", "Sort key", "B", "Database"),
    ("Which keyword is used to inherit a class in Java?", "implements", "inherits", "extends", "super", "C", "Java"),
    ("Which method is the entry point of a Java program?", "start()", "run()", "init()", "main()", "D", "Java"),
    ("Which Java keyword prevents a class from being subclassed?", "static", "final", "private", "abstract", "B", "Java"),
]
