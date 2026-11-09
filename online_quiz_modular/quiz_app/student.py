"""Student portal: dashboard, exam, results, history, leaderboard and profile."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import streamlit as st

from . import database, ui
from .auth import change_password_form, current_user_name, profile_form
from .certificates import show_certificate
from .core import logout
from .quiz import exam_page
from .utils import esc, pretty_date

STUDENT_PAGES = [
    ("dashboard", "🏠  Dashboard"),
    ("exam", "📝  Take Exam"),
    ("results", "📊  My Results"),
    ("history", "📜  History"),
    ("leaderboard", "🏆  Leaderboard"),
    ("profile", "👤  Profile"),
]


# ==========================================================================
# Dashboard
# ==========================================================================
def student_dashboard() -> None:
    ss = st.session_state
    user = ss.username
    first_name = current_user_name().split()[0] if current_user_name() else user

    ui.page_header(f"Welcome back, {first_name}!", "Here is an overview of your progress.", "🏠")
    ui.show_flash()

    stats = database.user_stats(user)
    ui.stat_row(
        [
            {"label": "Exams taken", "value": stats["attempts"], "icon": "📝", "tone": "indigo"},
            {"label": "Average score", "value": f"{stats['average']:.1f}%", "icon": "📊", "tone": "sky"},
            {"label": "Best score", "value": f"{stats['best']:.1f}%", "icon": "🏅", "tone": "amber"},
            {"label": "Exams passed", "value": stats["passed"], "icon": "✅", "tone": "green"},
        ]
    )
    st.write("")

    records = database.get_results(username=user)        # newest first
    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown("#### 📈 My performance")
        if records:
            df = pd.DataFrame(records[::-1])             # oldest first for the chart
            df["Attempt"] = range(1, len(df) + 1)
            tab_trend, tab_subject = st.tabs(["Score per attempt", "Average by subject"])
            with tab_trend:
                st.line_chart(df.rename(columns={"percentage": "Percentage"}).set_index("Attempt")[["Percentage"]])
            with tab_subject:
                st.bar_chart(df.groupby("subject")["percentage"].mean().rename("Average %"))
        else:
            ui.empty_state("🚀", "No exams yet", "Take your first exam to see your progress here.")

    with right:
        st.markdown("#### 🕘 Recent attempts")
        if records:
            for row in records[:5]:
                ui.html(
                    f"""
                    <div class="qp-recent"><div><b>{esc(row["subject"])}</b>
                    <div class="sub">{esc(pretty_date(row["date"]))}</div></div>
                    <div><b>{row["percentage"]:.0f}%</b> {ui.badge(row["status"])}</div></div>
                    """
                )
        else:
            st.caption("Your latest exams will appear here.")

    st.write("")
    st.markdown("#### 📚 Available subjects")
    subjects = database.list_subjects()
    if subjects:
        ui.html(
            " ".join(
                f'<span class="qp-badge pass" style="background:#eef2ff;color:#3730a3;margin:0 .35rem .4rem 0">'
                f'{esc(s["subject"])} · {s["questions"]}</span>'
                for s in subjects
            )
        )
        col, _ = st.columns([1, 3])
        col.button("📝  Go to exams", key="dash_go_exam", type="primary", on_click=ui.go_to, args=("exam",))
    else:
        st.warning("No subjects available yet.")


# ==========================================================================
# Results
# ==========================================================================
def _result_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a database row into the same shape as ``st.session_state.result``."""
    return {
        "id": row["id"],
        "subject": row["subject"],
        "score": row["score"],
        "total": row["total"],
        "percentage": row["percentage"] or 0,
        "status": row["status"],
        "certificate_id": row.get("certificate_id"),
        "date": row["date"],
        "pass_mark": database.get_settings()["pass_mark"],
        "review": None,
    }


def result_page() -> None:
    ss = st.session_state
    ui.page_header("My Results", "Your latest exam result and certificate.", "📊")
    ui.show_flash()

    fresh = ss.result is not None
    result = ss.result
    if not result:
        latest = database.get_results(username=ss.username, limit=1)
        if not latest:
            ui.empty_state("📝", "No results yet", "Complete an exam to see your result here.")
            st.button("Take an exam", key="res_empty_exam", type="primary", on_click=ui.go_to, args=("exam",))
            return
        result = _result_from_row(latest[0])
        st.caption("Showing your most recent saved attempt.")

    percentage = float(result["percentage"])
    passed = result["status"] == "PASS"
    ui.result_banner(passed, percentage, int(result["pass_mark"]))

    review = result.get("review")
    cards = [
        {"label": "Score", "value": f"{result['score']} / {result['total']}", "icon": "🎯", "tone": "indigo"},
        {"label": "Percentage", "value": f"{percentage:.2f}%", "icon": "📊", "tone": "sky"},
    ]
    if review is not None:
        wrong = sum(1 for r in review if r["selected"] is not None and not r["is_correct"])
        skipped = sum(1 for r in review if r["selected"] is None)
        cards += [
            {"label": "Incorrect", "value": wrong, "icon": "❌", "tone": "red"},
            {"label": "Unanswered", "value": skipped, "icon": "⏭️", "tone": "amber"},
        ]
    else:
        cards += [
            {"label": "Subject", "value": result["subject"], "icon": "📘", "tone": "violet"},
            {"label": "Date", "value": pretty_date(result["date"]), "icon": "📅", "tone": "amber"},
        ]
    ui.stat_row(cards)
    st.progress(min(max(percentage / 100.0, 0.0), 1.0))

    # Celebrate once per fresh result (not on every rerun, not for old attempts).
    if passed and fresh and not ss.celebration_shown:
        st.balloons()
        st.toast("Congratulations! You passed!", icon="🎉")
        ss.celebration_shown = True

    if passed and result.get("certificate_id"):
        st.divider()
        show_certificate(
            result,
            current_user_name(),
            database.get_settings()["organization"],
            key=f"result_{result['id']}",
        )

    if review:
        st.divider()
        with st.expander("🔍 Review your answers", expanded=not passed):
            for number, item in enumerate(review, start=1):
                chosen = item["selected"]
                correct = item["correct_answer"]
                tone = "good" if item["is_correct"] else "bad"
                if chosen is None:
                    your = "No answer" + (" (time ran out)" if item["timed_out"] else "")
                else:
                    your = f"{chosen}. {item['options'].get(chosen, '')}"
                right_answer = ""
                if not item["is_correct"]:
                    right_answer = " &nbsp;•&nbsp; Correct answer: " + esc(
                        f"{correct}. {item['options'].get(correct, '')}"
                    )
                ui.html(
                    f"""
                    <div class="qp-review {tone}"><div class="q">{number}. {esc(item["question"])}</div>
                    <div class="a">Your answer: {esc(your)}{right_answer}</div></div>
                    """
                )

    st.write("")
    col1, col2, _ = st.columns([1, 1, 2])
    col1.button("📝  Take another exam", key="res_again", type="primary", on_click=ui.go_to, args=("exam",))
    col2.button("🏠  Dashboard", key="res_dashboard", on_click=ui.go_to, args=("dashboard",))


# ==========================================================================
# History
# ==========================================================================
def history_page() -> None:
    ss = st.session_state
    ui.page_header("My Exam History", "Every exam you have taken.", "📜")

    records = database.get_results(username=ss.username)
    if not records:
        ui.empty_state("📜", "No examination history found", "Your finished exams will be listed here.")
        return

    subjects = ["All subjects"] + sorted({r["subject"] for r in records if r["subject"]})
    chosen = st.selectbox("Filter by subject", subjects)
    shown = [r for r in records if chosen == "All subjects" or r["subject"] == chosen]

    df = pd.DataFrame(
        [
            {
                "Date": pretty_date(r["date"], with_time=True),
                "Subject": r["subject"],
                "Score": f"{r['score']} / {r['total']}",
                "Percentage (%)": float(r["percentage"] or 0),
                "Status": r["status"],
            }
            for r in shown
        ]
    )
    ui.table(df, column_config={"Percentage (%)": st.column_config.NumberColumn(format="%.2f")})

    # Re-download certificates of earlier passed exams.
    passed = [r for r in shown if r["status"] == "PASS" and r.get("certificate_id")]
    st.divider()
    st.markdown("#### 📜 Download a certificate")
    if not passed:
        st.caption("Pass an exam to earn a certificate.")
        return
    by_id = {r["id"]: r for r in passed}
    selected_id = st.selectbox(
        "Choose a passed exam",
        list(by_id),
        format_func=lambda rid: (
            f"{by_id[rid]['subject']} — {by_id[rid]['percentage']:.1f}% — "
            f"{pretty_date(by_id[rid]['date'])}"
        ),
    )
    show_certificate(
        _result_from_row(by_id[selected_id]),
        current_user_name(),
        database.get_settings()["organization"],
        key=f"history_{selected_id}",
    )


# ==========================================================================
# Leaderboard
# ==========================================================================
def leaderboard_page() -> None:
    ss = st.session_state
    ui.page_header("Leaderboard", "Top students ranked by their best score.", "🏆")

    subjects = ["All subjects"] + [s["subject"] for s in database.list_subjects()]
    chosen = st.selectbox("Subject", subjects)
    everyone = database.leaderboard(None if chosen == "All subjects" else chosen, limit=1000)
    if not everyone:
        ui.empty_state("🏆", "No results available", "Be the first to take an exam!")
        return

    top = everyone[:10]
    medals = ["🥇", "🥈", "🥉"]
    columns = st.columns(min(3, len(top)))
    for column, row, medal in zip(columns, top, medals):
        mine = " me" if row["username"] == ss.username else ""
        with column:
            ui.html(
                f"""
                <div class="qp-podium{mine}"><div class="medal">{medal}</div>
                <div class="who">{esc(row["username"])}</div>
                <div class="pts">{row["best"]:.1f}%</div></div>
                """
            )
    st.write("")

    df = pd.DataFrame(
        [
            {
                "Rank": rank,
                "Student": row["username"] + ("  (you)" if row["username"] == ss.username else ""),
                "Best (%)": float(row["best"]),
                "Attempts": row["attempts"],
                "Passed": int(row["passed"] or 0),
            }
            for rank, row in enumerate(top, start=1)
        ]
    )
    ui.table(df, column_config={"Best (%)": st.column_config.NumberColumn(format="%.2f")})

    position = next((i for i, r in enumerate(everyone, 1) if r["username"] == ss.username), None)
    if position:
        st.caption(f"Your position: **#{position}** of {len(everyone)} students.")
    else:
        st.caption("Take an exam to appear on the leaderboard.")


# ==========================================================================
# Profile
# ==========================================================================
def profile_page() -> None:
    ui.page_header("My Profile", "Update your details and password.", "👤")
    ui.show_flash()
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("#### Account details")
        profile_form()
    with right:
        st.markdown("#### Change password")
        change_password_form("student")


# ==========================================================================
# Portal router
# ==========================================================================
_PAGE_FUNCTIONS = {
    "dashboard": student_dashboard,
    "exam": exam_page,
    "results": result_page,
    "history": history_page,
    "leaderboard": leaderboard_page,
    "profile": profile_page,
}


def student_portal() -> None:
    """Sidebar + the selected student page."""
    ss = st.session_state
    if ss.quiz_active:
        ss.page = "exam"                    # an exam in progress cannot be left
    elif ss.page not in _PAGE_FUNCTIONS:
        ss.page = "dashboard"

    ui.render_sidebar(
        STUDENT_PAGES, current_user_name(), "student", logout, locked=ss.quiz_active
    )
    _PAGE_FUNCTIONS[ss.page]()
