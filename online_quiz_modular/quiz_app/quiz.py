"""Exam flow: subject selection, countdown timer, answering and saving results.

How the exam works
------------------
* ``start_quiz`` loads the subject's questions (random order) and snapshots
  the current settings (seconds per question, pass mark).
* ``quiz_page`` shows one question at a time with a live countdown.
* The countdown is a ``st.fragment`` that refreshes itself every second, so
  the whole page is *not* re-run constantly.  When it reaches zero it asks
  Streamlit for one full rerun; at the very top of ``quiz_page`` the expired
  question is then submitted automatically (with whatever was selected).
* ``finish_quiz`` saves the result to SQLite, stores a result dictionary in
  the session and sends the student to the Results page.
"""

from __future__ import annotations

import math
import time
import uuid
from typing import Any, Dict, Optional

import streamlit as st

from . import database, ui
from .config import OPTION_LETTERS
from .utils import esc, esc_br, md_escape, new_certificate_id, now_str, percentage_of


# ==========================================================================
# State changes (plain functions - safe to call from buttons' on_click)
# ==========================================================================
def start_quiz(subject: str) -> bool:
    """Begin an exam.  Returns ``False`` if the subject has no questions."""
    questions = database.get_exam_questions(subject)
    if not questions:
        return False

    settings = database.get_settings()
    ss = st.session_state
    ss.quiz_questions = questions
    ss.quiz_id = uuid.uuid4().hex          # makes every attempt's widget keys unique
    ss.q_index = 0
    ss.score = 0
    ss.quiz_answers = []
    ss.quiz_limit = settings["seconds_per_question"]
    ss.quiz_pass_mark = settings["pass_mark"]
    ss.question_started = time.time()
    ss.result = None
    ss.saved = False
    ss.celebration_shown = False
    ss.quiz_active = True
    ss.page = "exam"
    return True


def submit_answer(expected_index: int, selected: Optional[str], timed_out: bool = False) -> None:
    """Record the answer for question ``expected_index`` and move on.

    ``expected_index`` guards against double submission: if a click and the
    timeout race each other, only the first one is counted.
    """
    ss = st.session_state
    if not ss.quiz_active or ss.q_index != expected_index:
        return

    question = ss.quiz_questions[expected_index]
    is_correct = selected is not None and selected == question["answer"]
    if is_correct:
        ss.score += 1

    ss.quiz_answers.append(
        {
            "question": question["question"],
            "options": {letter: question[letter.lower()] for letter in OPTION_LETTERS},
            "selected": selected,
            "correct_answer": question["answer"],
            "is_correct": is_correct,
            "timed_out": timed_out and selected is None,
        }
    )

    if expected_index + 1 < len(ss.quiz_questions):
        ss.q_index += 1
        ss.question_started = time.time()
    else:
        finish_quiz()


def on_next(index: int, answer_key: str) -> None:
    """Callback of the Next / Submit button."""
    submit_answer(index, st.session_state.get(answer_key))


def finish_quiz() -> None:
    """Save the result, build the result summary and open the Results page."""
    ss = st.session_state
    if ss.saved:
        return

    total = len(ss.quiz_questions)
    score = ss.score
    percentage = percentage_of(score, total)
    passed = percentage >= ss.quiz_pass_mark
    status = "PASS" if passed else "FAIL"
    subject = ss.quiz_questions[0]["subject"]
    certificate_id = new_certificate_id() if passed else None
    finished_at = now_str()

    result_id = database.save_result(
        ss.username, subject, score, total, percentage, status, certificate_id, finished_at
    )

    ss.result = {
        "id": result_id,
        "subject": subject,
        "score": score,
        "total": total,
        "percentage": round(percentage, 2),
        "status": status,
        "certificate_id": certificate_id,
        "date": finished_at,
        "pass_mark": ss.quiz_pass_mark,
        "review": list(ss.quiz_answers),     # answer-by-answer review (this session only)
    }
    ss.saved = True
    ss.celebration_shown = False
    ss.quiz_active = False
    ss.page = "results"


def quit_quiz() -> None:
    """Abandon the running exam without saving anything."""
    ss = st.session_state
    ss.quiz_active = False
    ss.quiz_questions = []
    ss.quiz_answers = []
    ss.q_index = 0
    ss.score = 0
    ui.flash("info", "Exam cancelled. No result was saved.")


# ==========================================================================
# Pages
# ==========================================================================
def exam_page() -> None:
    """Entry point of the *Take Exam* page."""
    if st.session_state.quiz_active:
        quiz_page()
    else:
        exam_selection_page()


def exam_selection_page() -> None:
    """Subject cards + exam rules."""
    ui.page_header("Take an Exam", "Pick a subject and test your knowledge.", "📝")
    ui.show_flash()

    settings = database.get_settings()
    subjects = database.list_subjects()
    if not subjects:
        ui.empty_state("📭", "No subjects available yet", "Ask your administrator to add questions.")
        return

    ui.stat_row(
        [
            {"label": "Time per question", "value": f"{settings['seconds_per_question']} s",
             "icon": "⏱️", "tone": "amber"},
            {"label": "Pass mark", "value": f"{settings['pass_mark']}%", "icon": "🎯", "tone": "green"},
            {"label": "Subjects", "value": len(subjects), "icon": "📚", "tone": "indigo"},
        ]
    )
    st.write("")
    st.markdown("#### Choose a subject")

    per_row = 3
    for start in range(0, len(subjects), per_row):
        columns = st.columns(per_row)
        for column, item in zip(columns, subjects[start:start + per_row]):
            subject, count = item["subject"], item["questions"]
            minutes = max(1, math.ceil(count * settings["seconds_per_question"] / 60))
            plural = "" if count == 1 else "s"
            with column:
                with st.container(border=True):
                    ui.html(
                        f"""
                        <div class="qp-subject"><div class="ico">📘</div>
                        <div><div class="name">{esc(subject)}</div>
                        <div class="meta">{count} question{plural} • about {minutes} min</div></div></div>
                        """
                    )
                    if st.button("🚀  Start exam", key=f"start_{subject}", type="primary"):
                        if start_quiz(subject):
                            st.rerun()
                        else:
                            st.error("No questions available for this subject.")

    with st.expander("📋 Exam rules"):
        st.markdown(
            f"- Every question has **{settings['seconds_per_question']} seconds**. "
            "When time runs out your current choice is submitted automatically.\n"
            "- You cannot go back to a previous question.\n"
            "- Unanswered questions score zero.\n"
            f"- You need **{settings['pass_mark']}%** to pass and receive a certificate.\n"
            "- Do not refresh the browser during an exam - the attempt would be lost."
        )


@st.fragment(run_every=1)
def timer_fragment(started: float, limit: int) -> None:
    """Self-refreshing countdown (re-runs only this function every second)."""
    remaining = limit - (time.time() - started)
    if remaining <= 0:
        st.rerun()                       # full rerun -> quiz_page submits the question
    seconds = max(0, math.ceil(remaining))
    share = max(0.0, min(100.0, remaining / limit * 100.0))
    tone = "ok" if share > 50 else "warn" if share > 25 else "danger"
    ui.html(
        f"""
        <div class="qp-timer {tone}"><div class="row"><span class="lbl">⏳ Time left</span>
        <span class="num">{seconds}s</span></div>
        <div class="bar"><div class="fill" style="width:{share:.1f}%"></div></div></div>
        """
    )


def quiz_page() -> None:
    """One question at a time, with timer, options and navigation buttons."""
    ss = st.session_state
    questions = ss.quiz_questions
    index = ss.q_index
    total = len(questions)
    question: Dict[str, Any] = questions[index]
    answer_key = f"answer_{ss.quiz_id}_{index}"

    # -- automatic timeout: must run BEFORE this question's widgets are drawn --
    if time.time() - ss.question_started >= ss.quiz_limit:
        submit_answer(index, ss.get(answer_key), timed_out=True)
        st.rerun()

    ui.page_header(f"{question['subject']} Exam", f"Question {index + 1} of {total}", "📝")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.progress((index + 1) / total)
        st.caption(f"{index} answered • {total - index} remaining (including this one)")
    with right:
        timer_fragment(ss.question_started, ss.quiz_limit)

    ui.html(
        f"""
        <div class="qp-qcard"><div class="qp-qnum">Question {index + 1}</div>
        <div class="qp-qtext">{esc_br(question["question"])}</div></div>
        """
    )

    st.radio(
        "Choose your answer",
        list(OPTION_LETTERS),
        index=None,
        key=answer_key,
        format_func=lambda letter: f"{letter}.  {md_escape(question[letter.lower()])}",
        label_visibility="collapsed",
    )

    st.write("")
    next_col, quit_col = st.columns([3, 1])
    with next_col:
        st.button(
            "Submit exam  ✅" if index == total - 1 else "Next question  →",
            type="primary",
            key=f"next_{ss.quiz_id}_{index}",
            on_click=on_next,
            args=(index, answer_key),
        )
    with quit_col:
        st.button("Quit exam", key=f"quit_{ss.quiz_id}_{index}", on_click=quit_quiz)
    st.caption("Unanswered questions score zero. You cannot return to a previous question.")
