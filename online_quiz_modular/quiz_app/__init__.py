"""Online Quiz Application package.

Module overview
---------------
config        constants and defaults (paths, timer, pass mark, sample data)
utils         small pure helpers (dates, escaping, ids) - no Streamlit
security      password hashing, input validation, login throttling - no Streamlit
database      every SQL statement lives here (SQLite) - no Streamlit
ui            theme (CSS), reusable components, sidebar navigation
core          per-run bootstrap: page config, database init, session state
auth          login, student registration, certificate verification, profile forms
quiz          exam selection, timer, answer handling, saving results
student       student dashboard, results, history, leaderboard, profile
admin         admin dashboard, question/student/result management, settings
certificates  PDF certificate generation and on-screen preview
"""

__version__ = "2.0.0"
