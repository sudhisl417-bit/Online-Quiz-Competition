# 🎓 Online Quiz Portal (Streamlit + SQLite)

A modular, timed online exam application with student and admin portals,
leaderboard, answer review and professional PDF certificates.

## Quick start in VS Code

1. **Extract** the ZIP and open the `online_quiz_modular` folder in VS Code
   (*File → Open Folder…*). Make sure you open the folder that contains `app.py`.
2. Open the integrated terminal (*Terminal → New Terminal*). It must be inside that folder.
3. **Create a virtual environment** (recommended; needs Python 3.9 or newer):

   ```powershell
   # Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   ```bash
   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```
   If PowerShell blocks the activation script, run
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `cmd`
   and `.venv\Scripts\activate.bat`.
   In VS Code choose the `.venv` interpreter via *Ctrl+Shift+P → Python: Select Interpreter*.
4. **Install the dependencies**:

   ```bash
   python -m pip install -r requirements.txt
   ```
5. **Start the app**:

   ```bash
   python -m streamlit run app.py
   ```
   Your browser opens at <http://localhost:8501>. If it does not, open that address yourself.
   Stop the server with `Ctrl+C`. To use another port:
   `python -m streamlit run app.py --server.port 8502`.

### Default administrator

| Admin ID | Password   |
|----------|------------|
| `ansh`   | `12345678` |

Sign in through the **Admin** option on the login page, then change the
password under **Settings → Change password** (the dashboard reminds you until you do).

### Keeping your existing data

The database is the single file `quiz_database.db` in the project folder and is
created automatically on first start. **To keep your old students, questions and
results, copy your existing `quiz_database.db` into this folder before the first run.**
It is upgraded in place and nothing is deleted:

* new columns are added (`full_name`, `email`, `created_at`, `certificate_id`) and a `settings` table is created;
* old results that lack a percentage / status are repaired, and every previously
  passed exam receives a certificate ID so its certificate can be downloaded again;
* old SHA-256 password hashes keep working and are upgraded to PBKDF2 when that student next signs in.

Use another file with the environment variable `QUIZ_DB_PATH`
(e.g. `set QUIZ_DB_PATH=D:\data\quiz.db` on Windows `cmd`).

## Features

**Everyone**
* Modern split-screen login (Student / Admin), **separate student registration page**
  (full name, username, optional e-mail, password), login throttling (5 failures → 5 min lock)
* **Verify a certificate** by its ID, no login needed

**Students**
* Dashboard with statistics, progress chart and recent attempts
* Subject cards → timed exam: one question at a time, **live countdown with colour bar**,
  automatic submit when time runs out, progress bar, quit option
* Results page: score, correct / incorrect / unanswered, **answer-by-answer review**, pass/fail banner
* **PDF certificate** for passed exams, also re-downloadable later from History
* History with subject filter, leaderboard (overall or per subject, podium, your rank), profile and password change

**Admins**
* Dashboard: students, questions, exams, pass rate, average score, chart per subject, top students, recent exams
* Questions: add, **edit**, delete (with confirmation), search/filter, **bulk CSV import** with validation
* Students: list with statistics, reset password, delete student
* Results: filter by subject / status / student, **export CSV**
* Settings: seconds per question, pass mark, organisation name on certificates, own password

## Project structure

```text
online_quiz_modular/
├── app.py                 entry point – chooses login / student / admin screen
├── requirements.txt
├── README.md
├── .streamlit/config.toml light theme used by the custom CSS
├── quiz_app/
│   ├── config.py          constants, defaults, sample questions
│   ├── utils.py           pure helpers (dates, escaping, ids)           – no Streamlit
│   ├── security.py        hashing, validation, login throttle           – no Streamlit
│   ├── database.py        every SQL statement, migrations (SQLite)      – no Streamlit
│   ├── ui.py              CSS theme, stat cards, tables, sidebar
│   ├── core.py            per-run bootstrap: page config, DB init, session state
│   ├── auth.py            login, registration, verification, profile forms
│   ├── quiz.py            exam selection, timer, answers, saving results
│   ├── student.py         student pages + portal router
│   ├── admin.py           admin pages + portal router
│   └── certificates.py    PDF generation + on-screen preview
└── tests/
    ├── test_core.py       unit tests (database, migration, security, PDF)
    └── test_app_smoke.py  runs the real app with Streamlit's AppTest
```

## Tests

```bash
python -m unittest discover -s tests -v
```

`test_core.py` needs nothing but the packages above. `test_app_smoke.py`
drives the real Streamlit app (login page, a second session, admin sign-in).

## What was fixed compared with the original

**Crashes**
* `auth.py` used `sqlite3`, `hash_password` and `verify_password` without importing them → every login/registration raised `NameError`.
* `quiz.py` used `uuid` and `datetime` without importing them → finishing an exam raised `NameError`.
* `core.py` ran page config, CSS and session defaults at *import* time. Python imports a module only once, so the second browser tab crashed (`AttributeError: logged_in`) and the styling vanished after the first interaction. This is now `init_app()`, called on every run.

**Database**
* One global connection/cursor was shared by all users and threads; every operation now uses its own short-lived connection.
* The legacy-password upgrade rewrote *every* user with the same hash; it now updates only the signing-in user.
* Sample questions re-appeared whenever an admin deleted all questions; they are now seeded once.
* Timestamps mixed UTC and local time; new results use local time.

**Behaviour**
* The exam sat inside a tab, so after submitting you had to find the Results tab yourself and could wander off mid-exam. Navigation is now a sidebar: finishing opens *My Results* automatically and navigation is locked during an exam.
* The timer re-ran the whole page every second (`streamlit-autorefresh`); it is now a self-updating `st.fragment`, and that dependency is gone.
* Certificates read the name from the session and could only be downloaded immediately after the exam. They are now generated from stored data.
* Question and option text was rendered as Markdown/HTML; it is now escaped, so text like `*args` or `<b>` displays literally and cannot inject markup.

## Limitations and notes

* **Refreshing the browser (F5) signs you out**, and an exam in progress is lost; Streamlit keeps session data in the open tab only.
* Certificates use the PDF standard fonts, which only contain Western (Latin) characters. Other scripts print as `?`; ask students to enter their name in English letters.
* Streamlit 1.37 or newer is required (`st.fragment`). If a future Streamlit release changes widget markup, only the CSS in `quiz_app/ui.py` may need small tweaks; the logic is unaffected.
* This is a single-server app intended for classrooms and small deployments, not a high-security proctored exam system.

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named streamlit` | Activate the virtual environment, then `python -m pip install -r requirements.txt`. |
| `python` not found on Windows | Use `py -m venv .venv`, then `py -m streamlit run app.py`. |
| `No module named quiz_app` | Start the command from the folder that contains `app.py`. |
| Port already in use | `python -m streamlit run app.py --server.port 8502`. |
| Forgot the admin password | Delete the `ansh` row from the `users` table (or delete the database file if it holds no data you need) and restart; the default admin is re-created. |
