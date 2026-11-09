"""Authentication pages and account forms.

Public pages (shown before sign-in)
    * ``login_page``               student / admin sign-in
    * ``register_page``            separate student registration
    * ``verify_certificate_page``  check a certificate id

Shared account forms (used after sign-in by the student and admin portals)
    * ``profile_form``
    * ``change_password_form``
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import streamlit as st

from . import config, database, ui
from .security import (
    THROTTLE,
    hash_password,
    is_legacy_hash,
    validate_email,
    validate_full_name,
    validate_password,
    validate_username,
    verify_password,
)
from .utils import esc, pretty_date


# ==========================================================================
# Authentication logic (no layout code)
# ==========================================================================
def authenticate(
    username: str, password: str, role: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Check credentials.  Returns ``(user, None)`` or ``(None, error message)``.

    * Repeated failures lock the login name for a few minutes.
    * The account must have the requested role (a student cannot use the admin form).
    * Legacy SHA-256 hashes are upgraded to PBKDF2 for *this user only*.
    """
    username = username.strip()
    key = f"{role}:{username.lower()}"

    wait = THROTTLE.seconds_locked(key)
    if wait:
        return None, f"Too many failed attempts. Please try again in {wait} seconds."

    user = database.get_user_for_login(username)
    valid = bool(
        user and user["role"] == role and verify_password(password, user["password"])
    )
    if not valid:
        THROTTLE.register_failure(key)
        return None, f"Invalid {role} username or password."

    THROTTLE.reset(key)
    if is_legacy_hash(user["password"]):
        database.set_password_hash(user["id"], hash_password(password))
    return user, None


def _start_session(user: Dict[str, Any], password: str) -> None:
    """Store the signed-in user in ``st.session_state``."""
    ss = st.session_state
    ss.logged_in = True
    ss.user_id = user["id"]
    ss.username = user["username"]
    ss.full_name = (user.get("full_name") or "").strip()
    ss.role = user["role"]
    ss.page = "dashboard"
    ss.auth_view = "login"
    ss.prefill_username = ""
    ss.default_password_warning = (
        user["role"] == "admin" and password == config.DEFAULT_ADMIN_PASSWORD
    )


def set_auth_view(view: str) -> None:
    """Switch between the login / register / verify screens (``on_click`` safe)."""
    st.session_state.auth_view = view


def current_user_name() -> str:
    """Name shown in the UI for the signed-in user."""
    return st.session_state.full_name or st.session_state.username


# ==========================================================================
# Login
# ==========================================================================
_HERO = """
<div class="qp-hero">
  <div class="qp-brand"><div class="logo">🎓</div><div>Quiz Portal</div></div>
  <h1>Learn. Take the quiz.<br>Earn your certificate.</h1>
  <p class="lead">A simple, timed online exam platform for students and teachers.</p>
  <div class="qp-feature"><div class="ico">⏱️</div>
    <div><b>Timed questions</b><span>A live countdown keeps every exam fair.</span></div></div>
  <div class="qp-feature"><div class="ico">📊</div>
    <div><b>Instant results</b><span>Scores, history and answer review right after you finish.</span></div></div>
  <div class="qp-feature"><div class="ico">🏆</div>
    <div><b>Leaderboard</b><span>See how you rank against other students.</span></div></div>
  <div class="qp-feature"><div class="ico">📜</div>
    <div><b>PDF certificates</b><span>Download a professional certificate when you pass.</span></div></div>
</div>
"""


def login_page() -> None:
    """Split-screen sign-in page for students and administrators."""
    ui.show_flash()
    left, right = st.columns([1.1, 1], gap="large")

    with left:
        ui.html(_HERO)

    with right:
        ui.html(
            """
            <div class="qp-login-head"><h2>Welcome back 👋</h2>
            <p>Sign in to continue to your quiz portal.</p></div>
            """
        )
        choice = st.radio(
            "Sign in as",
            ["🎓  Student", "🛠️  Admin"],
            horizontal=True,
            key="login_role",
            label_visibility="collapsed",
        )
        role = "admin" if "Admin" in choice else "student"
        is_admin = role == "admin"

        with st.form(f"login_form_{role}"):
            username = st.text_input(
                "Admin ID" if is_admin else "Username",
                value="" if is_admin else st.session_state.prefill_username,
                placeholder="Enter your admin ID" if is_admin else "Enter your username",
            )
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button(
                "Sign in as Admin" if is_admin else "Sign in", type="primary"
            )

        if submitted:
            if not username.strip() or not password:
                st.error("Please enter both your username and password.")
            else:
                user, error = authenticate(username, password, role)
                if error:
                    st.error(error)
                else:
                    _start_session(user, password)
                    st.rerun()

        st.write("")
        if not is_admin:
            st.caption("New student?")
            st.button(
                "✨  Create a student account",
                key="goto_register",
                on_click=set_auth_view,
                args=("register",),
            )
        st.button(
            "🔎  Verify a certificate",
            key="goto_verify",
            on_click=set_auth_view,
            args=("verify",),
        )


# ==========================================================================
# Registration (separate page)
# ==========================================================================
def register_page() -> None:
    """Student self-registration."""
    _, middle, _ = st.columns([1, 1.7, 1])
    with middle:
        ui.page_header("Create your student account", "It only takes a minute.", "✨")

        with st.form("register_form"):
            full_name = st.text_input(
                "Full name",
                max_chars=60,
                placeholder="As it should appear on your certificate",
                help="Use English letters so the name prints correctly on the PDF certificate.",
            )
            col1, col2 = st.columns(2)
            username = col1.text_input("Username", max_chars=30, placeholder="e.g. asha_nair")
            email = col2.text_input("E-mail (optional)", placeholder="name@example.com")
            col3, col4 = st.columns(2)
            password = col3.text_input("Password", type="password")
            confirm = col4.text_input("Confirm password", type="password")
            st.caption(
                f"Username: 3-30 letters, numbers, dot, dash or underscore. "
                f"Password: at least {config.MIN_PASSWORD_LENGTH} characters."
            )
            submitted = st.form_submit_button("Create account", type="primary")

        if submitted:
            _handle_registration(full_name, username, email, password, confirm)

        st.button(
            "←  Back to sign in",
            key="back_to_login",
            on_click=set_auth_view,
            args=("login",),
        )


def _handle_registration(
    full_name: str, username: str, email: str, password: str, confirm: str
) -> None:
    """Validate the registration form and create the account."""
    username = username.strip()
    reserved = (
        "This username is reserved."
        if username.lower() == config.DEFAULT_ADMIN_USERNAME.lower()
        else None
    )
    error = (
        validate_full_name(full_name)
        or validate_username(username)
        or reserved
        or validate_email(email)
        or validate_password(password, confirm)
    )
    if error:
        st.error(error)
        return

    try:
        database.create_user(
            username, hash_password(password), "student", full_name.strip(), email.strip()
        )
    except database.DuplicateUserError:
        st.error("That username is already taken. Please choose another.")
        return

    ui.flash("success", f"Account created! Sign in as “{username}” to start your first exam.")
    st.session_state.prefill_username = username
    st.session_state.auth_view = "login"
    st.rerun()


# ==========================================================================
# Certificate verification (public)
# ==========================================================================
def verify_certificate_page() -> None:
    """Let anyone check that a certificate id is genuine."""
    _, middle, _ = st.columns([1, 1.7, 1])
    with middle:
        ui.page_header(
            "Verify a certificate", "Enter the certificate ID printed at the bottom of the PDF.", "🔎"
        )
        with st.form("verify_form"):
            cert_id = st.text_input("Certificate ID", placeholder="QUIZ-XXXXXXXXXX")
            submitted = st.form_submit_button("Verify", type="primary")

        if submitted:
            cert = database.find_certificate(cert_id) if cert_id.strip() else None
            if cert:
                st.success("✅ This certificate is valid.")
                ui.html(
                    f"""
                    <div class="qp-recent"><div><b>{esc(cert.get("full_name") or cert["username"])}</b>
                    <div class="sub">{esc(cert["subject"])} • {cert["score"]}/{cert["total"]}
                    ({cert["percentage"]:.2f}%) • issued {esc(pretty_date(cert["date"]))}</div></div>
                    <span class="qp-badge pass">VALID</span></div>
                    """
                )
            else:
                st.error("No certificate with that ID was found.")

        st.button(
            "←  Back to sign in",
            key="back_from_verify",
            on_click=set_auth_view,
            args=("login",),
        )


def auth_router() -> None:
    """Show the correct public page."""
    view = st.session_state.auth_view
    if view == "register":
        register_page()
    elif view == "verify":
        verify_certificate_page()
    else:
        login_page()


# ==========================================================================
# Shared account forms (signed-in users)
# ==========================================================================
def profile_form() -> None:
    """Edit full name and e-mail."""
    user = database.get_user_by_id(st.session_state.user_id)
    if not user:
        st.error("Account not found.")
        return
    with st.form("profile_form"):
        st.text_input("Username", value=user["username"], disabled=True)
        full_name = st.text_input(
            "Full name (printed on certificates)", value=user.get("full_name") or "", max_chars=60
        )
        email = st.text_input("E-mail (optional)", value=user.get("email") or "")
        submitted = st.form_submit_button("Save profile", type="primary")
    if submitted:
        error = validate_full_name(full_name) or validate_email(email)
        if error:
            st.error(error)
            return
        database.update_profile(user["id"], full_name, email)
        st.session_state.full_name = full_name.strip()
        ui.flash("success", "Profile updated.")
        st.rerun()


def change_password_form(key: str = "pw") -> None:
    """Change the signed-in user's own password."""
    with st.form(f"change_password_{key}", clear_on_submit=True):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update password", type="primary")
    if not submitted:
        return

    user = database.get_user_by_id(st.session_state.user_id)
    if not user or not verify_password(current, user["password"]):
        st.error("Your current password is incorrect.")
    elif current == new:
        st.error("The new password must be different from the current one.")
    elif (error := validate_password(new, confirm)):
        st.error(error)
    else:
        database.set_password_hash(user["id"], hash_password(new))
        st.session_state.default_password_warning = False
        st.success("Password updated successfully.")
