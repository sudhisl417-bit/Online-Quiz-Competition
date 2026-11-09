"""Per-run application bootstrap.

Why this is a *function* and not module-level code
--------------------------------------------------
Streamlit re-executes ``app.py`` on every interaction, but a module that was
already imported is **not** executed again.  The original ``core.py`` set the
page config, CSS and session defaults at import time, so they only ever ran
once per server process - the second browser tab crashed with
``AttributeError: logged_in`` and the styling vanished after the first rerun.
``init_app`` is therefore called explicitly at the top of every run.
"""

from __future__ import annotations

import copy
import threading

import streamlit as st

from . import config, database
from .ui import inject_theme

# Every key the application keeps in ``st.session_state`` and its default.
SESSION_DEFAULTS = {
    # authentication
    "logged_in": False,
    "user_id": None,
    "username": "",
    "full_name": "",
    "role": "",
    "auth_view": "login",          # login | register | verify
    "prefill_username": "",
    "default_password_warning": False,
    # navigation / messages
    "page": "dashboard",
    "flash": None,
    # exam in progress
    "quiz_active": False,
    "quiz_id": "",
    "quiz_questions": [],
    "q_index": 0,
    "score": 0,
    "question_started": 0.0,
    "quiz_limit": config.DEFAULT_SECONDS_PER_QUESTION,
    "quiz_pass_mark": config.DEFAULT_PASS_MARK,
    "quiz_answers": [],
    # last finished exam
    "result": None,
    "saved": False,
    "celebration_shown": False,
}


_DB_LOCK = threading.Lock()
_INITIALISED_PATHS: set = set()      # module level -> survives Streamlit reruns


def _ensure_database() -> None:
    """Create/upgrade the database once per process (and again if the file vanishes).

    A lock prevents two browser sessions that start at the same moment from
    initialising the database simultaneously.
    """
    path = str(config.DB_PATH)
    if path in _INITIALISED_PATHS and config.DB_PATH.exists():
        return
    with _DB_LOCK:
        if path in _INITIALISED_PATHS and config.DB_PATH.exists():
            return
        database.init_db()
        _INITIALISED_PATHS.add(path)


def init_session_state() -> None:
    """Make sure every session key exists (new browser tabs start empty)."""
    for key, default in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = copy.deepcopy(default)


def init_app() -> None:
    """Call first thing in ``app.py`` on every run."""
    # set_page_config must be the first Streamlit command of the run.
    st.set_page_config(
        page_title=config.APP_NAME,
        page_icon=config.APP_ICON,
        layout="wide",
        initial_sidebar_state="auto",
    )
    _ensure_database()
    init_session_state()
    inject_theme()


def logout() -> None:
    """Forget everything about the signed-in user (usable as ``on_click``)."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session_state()
