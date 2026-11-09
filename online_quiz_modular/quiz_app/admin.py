"""Admin portal: dashboard, question management, students, results and settings."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st

from . import config, database, ui
from .auth import change_password_form, current_user_name
from .core import logout
from .security import hash_password, validate_password
from .utils import esc, pretty_date

ADMIN_PAGES = [
    ("dashboard", "🏠  Dashboard"),
    ("questions", "❓  Questions"),
    ("students", "👥  Students"),
    ("results", "📋  Results"),
    ("settings", "⚙️  Settings"),
]

NEW_SUBJECT = "➕ New subject…"
CSV_COLUMNS = ["subject", "question", "a", "b", "c", "d", "answer"]
CSV_TEMPLATE = (
    "subject,question,a,b,c,d,answer\n"
    "Python,Which function displays output?,input(),print(),show(),display(),B\n"
)


# ==========================================================================
# Dashboard
# ==========================================================================
def admin_dashboard() -> None:
    ui.page_header("Admin Dashboard", "Everything happening in your quiz portal.", "🛠️")
    ui.show_flash()

    if st.session_state.default_password_warning:
        st.warning(
            "You are still using the default administrator password. "
            "Please change it on the Settings page."
        )
        st.button("Go to Settings", key="dash_go_settings", on_click=ui.go_to, args=("settings",))

    stats = database.overall_stats()
    ui.stat_row(
        [
            {"label": "Students", "value": stats["students"], "icon": "👥", "tone": "indigo"},
            {"label": "Questions", "value": stats["questions"], "icon": "❓", "tone": "violet",
             "hint": f"{stats['subjects']} subjects"},
            {"label": "Exams taken", "value": stats["attempts"], "icon": "📝", "tone": "sky"},
        ]
    )
    st.write("")
    ui.stat_row(
        [
            {"label": "Exams passed", "value": stats["passed"], "icon": "✅", "tone": "green"},
            {"label": "Pass rate", "value": f"{stats['pass_rate']:.1f}%", "icon": "🎯", "tone": "amber"},
            {"label": "Average score", "value": f"{stats['average']:.1f}%", "icon": "📊", "tone": "red"},
        ]
    )
    st.write("")

    performance = database.subject_performance()
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### 📊 Average score by subject")
        if performance:
            frame = pd.DataFrame(performance)
            st.bar_chart(frame.set_index("subject")[["average"]].rename(columns={"average": "Average %"}))
        else:
            ui.empty_state("📊", "No student results yet", "Charts appear after the first exam.")
    with right:
        st.markdown("#### 🏆 Top students")
        top = database.leaderboard(limit=5)
        if top:
            for rank, row in enumerate(top, start=1):
                ui.html(
                    f"""
                    <div class="qp-recent"><div><b>#{rank} {esc(row["username"])}</b>
                    <div class="sub">{row["attempts"]} attempt(s)</div></div>
                    <b>{row["best"]:.1f}%</b></div>
                    """
                )
        else:
            st.caption("No results yet.")

    st.markdown("#### 🕘 Recent exams")
    recent = database.get_results(limit=10)
    if recent:
        ui.table(_results_frame(recent), column_config=_RESULT_COLUMNS)
    else:
        st.caption("Nothing to show yet.")


# ==========================================================================
# Questions
# ==========================================================================
def questions_page() -> None:
    """Tabbed page grouping everything about questions."""
    ui.page_header("Question Bank", "Add, edit, import and remove questions.", "❓")
    ui.show_flash()
    tab_add, tab_manage, tab_import = st.tabs(["➕ Add question", "🗂️ Manage questions", "📥 Import CSV"])
    with tab_add:
        add_question_page()
    with tab_manage:
        manage_questions_page()
    with tab_import:
        import_questions_page()


def add_question_page() -> None:
    """Form for a single new question."""
    existing = [s["subject"] for s in database.list_subjects()]

    # The subject picker is outside the form so choosing "New subject" can
    # reveal a text box immediately.
    choice = st.selectbox("Subject", existing + [NEW_SUBJECT])
    new_subject = ""
    if choice == NEW_SUBJECT:
        new_subject = st.text_input("New subject name", placeholder="Example: Python", key="add_new_subject")

    with st.form("add_question", clear_on_submit=True):
        question = st.text_area("Question")
        col1, col2 = st.columns(2)
        option_a = col1.text_input("Option A")
        option_b = col2.text_input("Option B")
        option_c = col1.text_input("Option C")
        option_d = col2.text_input("Option D")
        answer = st.selectbox("Correct answer", list(config.OPTION_LETTERS))
        submitted = st.form_submit_button("➕  Save question", type="primary")

    if submitted:
        subject = new_subject.strip() if choice == NEW_SUBJECT else choice
        error = _validate_question(subject, question, [option_a, option_b, option_c, option_d])
        if error:
            st.error(error)
            return
        database.add_question(subject, question, option_a, option_b, option_c, option_d, answer)
        st.success(f"Question added to “{subject}”.")
        st.toast("Question saved", icon="✅")


def _validate_question(subject: str, question: str, options: List[str]) -> str:
    """Return an error message or an empty string."""
    if not subject.strip() or not question.strip() or not all(o.strip() for o in options):
        return "Please fill all fields (subject, question and all four options)."
    if len({o.strip().lower() for o in options}) < 4:
        return "The four answer options must all be different."
    return ""


def manage_questions_page() -> None:
    """Browse, edit and delete questions."""
    subjects = [s["subject"] for s in database.list_subjects()]
    col1, col2 = st.columns([1, 2])
    subject = col1.selectbox("Filter by subject", ["All subjects"] + subjects)
    search = col2.text_input("Search question text", key="mq_search")

    rows = database.list_questions(None if subject == "All subjects" else subject, search)
    if not rows:
        ui.empty_state("🗂️", "No questions found", "Add a question or change the filters.")
        return

    frame = pd.DataFrame(rows).rename(
        columns={"id": "ID", "subject": "Subject", "question": "Question", "answer": "Answer",
                 "a": "A", "b": "B", "c": "C", "d": "D"}
    )[["ID", "Subject", "Question", "A", "B", "C", "D", "Answer"]]
    ui.table(frame, height=300)
    st.caption(f"{len(rows)} question(s) shown.")

    st.markdown("#### ✏️ Edit or delete a question")
    by_id = {row["id"]: row for row in rows}
    question_id = st.selectbox(
        "Select a question",
        list(by_id),
        format_func=lambda qid: f"#{qid} · {by_id[qid]['subject']} · {by_id[qid]['question'][:70]}",
    )
    current = by_id[question_id]

    with st.form(f"edit_question_{question_id}"):
        new_subject = st.text_input("Subject", value=current["subject"], key=f"eq_subject_{question_id}")
        new_question = st.text_area("Question", value=current["question"], key=f"eq_question_{question_id}")
        col1, col2 = st.columns(2)
        new_a = col1.text_input("Option A", value=current["a"], key=f"eq_a_{question_id}")
        new_b = col2.text_input("Option B", value=current["b"], key=f"eq_b_{question_id}")
        new_c = col1.text_input("Option C", value=current["c"], key=f"eq_c_{question_id}")
        new_d = col2.text_input("Option D", value=current["d"], key=f"eq_d_{question_id}")
        letters = list(config.OPTION_LETTERS)
        current_answer = (current["answer"] or "A").strip().upper()
        new_answer = st.selectbox(
            "Correct answer",
            letters,
            index=letters.index(current_answer) if current_answer in letters else 0,
            key=f"eq_answer_{question_id}",
        )
        saved = st.form_submit_button("💾  Save changes", type="primary")

    if saved:
        error = _validate_question(new_subject, new_question, [new_a, new_b, new_c, new_d])
        if error:
            st.error(error)
        else:
            database.update_question(
                question_id, new_subject, new_question, new_a, new_b, new_c, new_d, new_answer
            )
            ui.flash("success", f"Question #{question_id} updated.")
            st.rerun()

    with st.expander("🗑️ Delete this question"):
        confirmed = st.checkbox(
            "Yes, delete this question permanently", key=f"confirm_delete_question_{question_id}"
        )
        if st.button("Delete question", key=f"delete_question_{question_id}", disabled=not confirmed):
            database.delete_question(question_id)
            ui.flash("success", "Question deleted successfully.")
            st.rerun()


def _parse_question_csv(upload: Any) -> Tuple[List[Dict[str, str]], List[str]]:
    """Read an uploaded CSV; return ``(valid rows, error messages)``."""
    upload.seek(0)          # the same file object is re-read on every rerun
    try:
        frame = pd.read_csv(upload, dtype=str, encoding="utf-8-sig").fillna("")
    except UnicodeDecodeError:
        upload.seek(0)
        frame = pd.read_csv(upload, dtype=str, encoding="latin-1").fillna("")
    except Exception as exc:  # noqa: BLE001 - show any parse problem to the admin
        return [], [f"Could not read the file: {exc}"]

    frame.columns = [str(c).strip().lower() for c in frame.columns]
    missing = [c for c in CSV_COLUMNS if c not in frame.columns]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}. Download the template to see the format."]

    valid: List[Dict[str, str]] = []
    errors: List[str] = []
    for position, record in enumerate(frame[CSV_COLUMNS].to_dict("records"), start=2):
        row = {key: str(value).strip() for key, value in record.items()}
        row["answer"] = row["answer"].upper()
        if not all(row[c] for c in CSV_COLUMNS):
            errors.append(f"Row {position}: a required value is empty.")
        elif row["answer"] not in config.OPTION_LETTERS:
            errors.append(f"Row {position}: answer must be A, B, C or D.")
        else:
            valid.append(row)
    return valid, errors


def import_questions_page() -> None:
    """Bulk-add questions from a CSV file."""
    st.write("Add many questions at once. Required columns: "
             "`subject, question, a, b, c, d, answer` (answer is A, B, C or D).")
    st.download_button(
        "⬇️  Download CSV template", CSV_TEMPLATE, "questions_template.csv", "text/csv",
        key="download_template",
    )

    counter = st.session_state.get("import_counter", 0)
    upload = st.file_uploader("Upload a CSV file", type=["csv"], key=f"import_upload_{counter}")
    if upload is None:
        return

    valid, errors = _parse_question_csv(upload)
    for message in errors[:10]:
        st.warning(message)
    if len(errors) > 10:
        st.caption(f"…and {len(errors) - 10} more problem(s).")
    if not valid:
        return

    st.success(f"{len(valid)} valid question(s) ready to import.")
    ui.table(pd.DataFrame(valid)[CSV_COLUMNS].head(20))
    if st.button(f"📥  Import {len(valid)} question(s)", key="do_import", type="primary"):
        added = database.add_questions_bulk(valid)
        st.session_state["import_counter"] = counter + 1      # resets the uploader
        ui.flash("success", f"Imported {added} question(s).")
        st.rerun()


# ==========================================================================
# Students
# ==========================================================================
def students_page() -> None:
    ui.page_header("Students", "Registered students and their activity.", "👥")
    ui.show_flash()

    students = database.list_students()
    if not students:
        ui.empty_state("👥", "No students registered yet", "Students can register from the sign-in page.")
        return

    frame = pd.DataFrame(
        [
            {
                "Username": s["username"],
                "Full name": s["full_name"] or "",
                "E-mail": s["email"] or "",
                "Joined": pretty_date(s["created_at"]),
                "Exams": s["attempts"],
                "Average (%)": s["average"],
                "Best (%)": s["best"],
            }
            for s in students
        ]
    )
    ui.table(
        frame,
        column_config={
            "Average (%)": st.column_config.NumberColumn(format="%.2f"),
            "Best (%)": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    by_id = {s["id"]: s for s in students}
    label = lambda sid: f"{by_id[sid]['username']} ({by_id[sid]['full_name'] or 'no name'})"  # noqa: E731

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("#### 🔑 Reset a student's password")
        with st.form("reset_password", clear_on_submit=True):
            student_id = st.selectbox("Student to reset", list(by_id), format_func=label)
            new_password = st.text_input("New password", type="password")
            submitted = st.form_submit_button("Reset password", type="primary")
        if submitted:
            error = validate_password(new_password)
            if error:
                st.error(error)
            else:
                database.set_password_hash(student_id, hash_password(new_password))
                st.success(f"Password reset for {by_id[student_id]['username']}.")

    with right:
        st.markdown("#### 🗑️ Delete a student")
        student_id = st.selectbox("Student to delete", list(by_id), format_func=label)
        st.caption("This also deletes the student's exam results.")
        confirmed = st.checkbox("I understand this cannot be undone", key=f"confirm_delete_student_{student_id}")
        if st.button("Delete student", key=f"delete_student_{student_id}", disabled=not confirmed):
            database.delete_student(student_id)
            ui.flash("success", f"Deleted student {by_id[student_id]['username']}.")
            st.rerun()


# ==========================================================================
# Results
# ==========================================================================
_RESULT_COLUMNS = {
    "Percentage (%)": st.column_config.NumberColumn(format="%.2f"),
}


def _results_frame(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Student": r["username"],
                "Subject": r["subject"],
                "Score": r["score"],
                "Total": r["total"],
                "Percentage (%)": float(r["percentage"] or 0),
                "Status": r["status"],
                "Date": pretty_date(r["date"], with_time=True),
            }
            for r in rows
        ]
    )


def all_results_page() -> None:
    ui.page_header("Student Results", "Filter, review and export every exam result.", "📋")

    subjects = [s["subject"] for s in database.list_subjects()]
    col1, col2, col3 = st.columns(3)
    subject = col1.selectbox("Subject", ["All subjects"] + subjects)
    status = col2.selectbox("Status", ["All", "PASS", "FAIL"])
    search = col3.text_input("Student contains", key="res_search")

    rows = database.get_results(
        subject=None if subject == "All subjects" else subject,
        status=None if status == "All" else status,
        search=search,
    )
    if not rows:
        ui.empty_state("📋", "No student results available", "Try changing the filters.")
        return

    frame = _results_frame(rows)
    ui.table(frame, column_config=_RESULT_COLUMNS)
    st.caption(f"{len(rows)} result(s).")
    st.download_button(
        "📥  Download results CSV",
        data=frame.to_csv(index=False),
        file_name="student_results.csv",
        mime="text/csv",
        key="download_results",
    )


# ==========================================================================
# Settings
# ==========================================================================
def settings_page() -> None:
    ui.page_header("Settings", "Exam rules, certificates and your own password.", "⚙️")
    ui.show_flash()
    current = database.get_settings()

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("#### 🎛️ Exam settings")
        with st.form("exam_settings"):
            seconds = st.number_input(
                "Seconds per question", min_value=5, max_value=600, value=int(current["seconds_per_question"]), step=5
            )
            pass_mark = st.number_input(
                "Pass mark (%)", min_value=1, max_value=100, value=int(current["pass_mark"]), step=1
            )
            organization = st.text_input(
                "Organisation name (printed on certificates)", value=current["organization"], max_chars=60
            )
            submitted = st.form_submit_button("Save settings", type="primary")
        if submitted:
            database.save_settings(int(seconds), int(pass_mark), organization)
            ui.flash("success", "Settings saved. They apply to exams started from now on.")
            st.rerun()
    with right:
        st.markdown(f"#### 🔑 Change password ({current_user_name()})")
        change_password_form("admin")


# ==========================================================================
# Portal router
# ==========================================================================
_PAGE_FUNCTIONS = {
    "dashboard": admin_dashboard,
    "questions": questions_page,
    "students": students_page,
    "results": all_results_page,
    "settings": settings_page,
}


def admin_portal() -> None:
    """Sidebar + the selected admin page."""
    ss = st.session_state
    if ss.page not in _PAGE_FUNCTIONS:
        ss.page = "dashboard"
    ui.render_sidebar(ADMIN_PAGES, current_user_name(), "admin", logout)
    _PAGE_FUNCTIONS[ss.page]()
