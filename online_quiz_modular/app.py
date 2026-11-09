"""Online Quiz Application - entry point.

Run with:    python -m streamlit run app.py

This file only decides *which screen to show*; all logic lives in the
``quiz_app`` package.  It is executed again by Streamlit on every
interaction, which is why ``init_app()`` is called here each time.
"""

import streamlit as st

from quiz_app.admin import admin_portal
from quiz_app.auth import auth_router
from quiz_app.core import init_app
from quiz_app.student import student_portal

# Page config + database + session defaults + CSS (must run on every rerun).
init_app()

if not st.session_state.logged_in:
    auth_router()                     # login / register / verify certificate
elif st.session_state.role == "admin":
    admin_portal()
else:
    student_portal()
