"""Visual theme and reusable UI components.

Everything that decides how the application *looks* lives in this module:
the global CSS, stat cards, badges, banners, tables and the sidebar.

Important: ``inject_theme`` must run on **every** script run (Streamlit
rebuilds the page each time), so ``core.init_app`` calls it at the top of
``app.py``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import streamlit as st

from .utils import esc, initials

# ==========================================================================
# Global CSS
# ==========================================================================
THEME_CSS = """
<style>
:root{
  --qp-primary:#4f46e5; --qp-primary-dark:#4338ca; --qp-violet:#7c3aed;
  --qp-text:#1e293b; --qp-muted:#64748b; --qp-border:#e2e8f0;
  --qp-bg:#f4f6fb; --qp-card:#ffffff;
  --qp-green:#16a34a; --qp-red:#dc2626; --qp-amber:#f59e0b;
}
html{color-scheme:light;}
.stApp{background:var(--qp-bg);color:var(--qp-text);}
[data-testid="stHeader"]{background:transparent;}
footer{visibility:hidden;}
.block-container{padding-top:2rem;padding-bottom:3rem;max-width:1200px;}
h1,h2,h3,h4{color:var(--qp-text);letter-spacing:-0.01em;}
[data-testid="stMarkdownContainer"],[data-testid="stWidgetLabel"] p,
[data-testid="stCaptionContainer"]{color:var(--qp-text);}
[data-testid="stCaptionContainer"]{color:var(--qp-muted);}

/* ---------- buttons ---------- */
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{
  width:100%;min-height:44px;border-radius:12px;font-weight:600;
  border:1px solid var(--qp-border);background:#fff;color:var(--qp-text);
  transition:all .15s ease;}
.stButton>button:hover,.stDownloadButton>button:hover,
[data-testid="stFormSubmitButton"]>button:hover{
  border-color:var(--qp-primary);color:var(--qp-primary);
  box-shadow:0 6px 16px rgba(79,70,229,.15);}
.stButton>button[kind^="primary"],.stDownloadButton>button[kind^="primary"],
[data-testid="stFormSubmitButton"]>button[kind^="primary"],
.stButton>button[data-testid^="stBaseButton-primary"],
.stDownloadButton>button[data-testid^="stBaseButton-primary"],
[data-testid="stFormSubmitButton"]>button[data-testid^="stBaseButton-primary"]{
  background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;border:none;}
.stButton>button[kind^="primary"]:hover,.stDownloadButton>button[kind^="primary"]:hover,
[data-testid="stFormSubmitButton"]>button[kind^="primary"]:hover,
.stButton>button[data-testid^="stBaseButton-primary"]:hover,
.stDownloadButton>button[data-testid^="stBaseButton-primary"]:hover,
[data-testid="stFormSubmitButton"]>button[data-testid^="stBaseButton-primary"]:hover{
  color:#fff;filter:brightness(1.08);}
.stButton>button:disabled{opacity:.55;}
.stButton>button p,.stDownloadButton>button p,
[data-testid="stFormSubmitButton"]>button p{color:inherit;}

/* ---------- inputs, forms, tabs, radios ---------- */
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{border-radius:10px;}
[data-testid="stForm"]{background:#fff;border:1px solid var(--qp-border);border-radius:18px;
  padding:1.4rem 1.4rem .8rem;box-shadow:0 10px 30px rgba(30,27,75,.06);}
button[role="tab"]{font-weight:600;}
[data-testid="stMetric"]{background:#fff;border:1px solid var(--qp-border);
  border-radius:14px;padding:14px 16px;}
div[role="radiogroup"]{gap:.35rem;}
label[data-baseweb="radio"]{background:#fff;border:1.5px solid var(--qp-border);
  border-radius:12px;padding:.65rem 1rem;margin:0;transition:all .15s ease;}
label[data-baseweb="radio"]:hover{border-color:var(--qp-primary);background:#f5f3ff;}
label[data-baseweb="radio"]:has(input:checked){border-color:var(--qp-primary);background:#eef2ff;}
[data-testid="stExpander"]{background:#fff;border-radius:12px;}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{background:linear-gradient(190deg,#1e1b4b 0%,#312e81 60%,#4338ca 100%);}
[data-testid="stSidebar"] *{color:#e0e7ff;}
[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.18);}
[data-testid="stSidebar"] .stButton>button{
  justify-content:flex-start;text-align:left;background:transparent;border:1px solid transparent;
  color:#c7d2fe;box-shadow:none;}
[data-testid="stSidebar"] .stButton>button:hover{background:rgba(255,255,255,.10);
  border-color:rgba(255,255,255,.18);color:#fff;transform:none;box-shadow:none;}
[data-testid="stSidebar"] .stButton>button[kind="primary"],
[data-testid="stSidebar"] .stButton>button[data-testid="stBaseButton-primary"]{
  background:rgba(255,255,255,.17);color:#fff;box-shadow:inset 3px 0 0 #a5b4fc;border:none;}
[data-testid="stSidebar"] .stButton>button p{color:inherit;}
.qp-brand{display:flex;align-items:center;gap:.7rem;font-weight:800;font-size:1.15rem;
  color:#fff;margin:.2rem 0 1rem;}
.qp-brand .logo{width:38px;height:38px;border-radius:11px;display:flex;align-items:center;
  justify-content:center;background:rgba(255,255,255,.18);font-size:1.3rem;}
.qp-user{display:flex;align-items:center;gap:.75rem;padding:.8rem;border-radius:14px;
  background:rgba(255,255,255,.10);margin-bottom:1rem;}
.qp-avatar{width:42px;height:42px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-weight:700;background:linear-gradient(135deg,#a78bfa,#6366f1);color:#fff;}
.qp-user .name{font-weight:700;color:#fff;line-height:1.2;}
.qp-user .role{font-size:.78rem;color:#c7d2fe;text-transform:uppercase;letter-spacing:.06em;}

/* ---------- page header ---------- */
.qp-page-head{display:flex;align-items:center;gap:1rem;margin:0 0 1.4rem;}
.qp-page-icon{width:54px;height:54px;border-radius:16px;display:flex;align-items:center;
  justify-content:center;font-size:1.6rem;background:linear-gradient(135deg,#eef2ff,#ede9fe);}
.qp-page-head h1{margin:0;padding:0;font-size:1.75rem;line-height:1.2;}
.qp-page-head p{margin:.15rem 0 0;color:var(--qp-muted);}

/* ---------- login hero ---------- */
.qp-hero{position:relative;overflow:hidden;color:#fff;border-radius:26px;padding:2.6rem 2.4rem;
  min-height:560px;background:linear-gradient(135deg,#312e81 0%,#4f46e5 55%,#7c3aed 100%);
  box-shadow:0 24px 60px rgba(79,70,229,.28);}
.qp-hero:before,.qp-hero:after{content:"";position:absolute;border-radius:50%;
  background:rgba(255,255,255,.08);}
.qp-hero:before{width:340px;height:340px;right:-110px;top:-110px;}
.qp-hero:after{width:260px;height:260px;left:-90px;bottom:-90px;}
.qp-hero *{position:relative;z-index:1;color:#fff;}
.qp-hero h1{font-size:2.35rem;line-height:1.15;margin:2.2rem 0 .8rem;color:#fff;}
.qp-hero p.lead{font-size:1.05rem;opacity:.9;margin-bottom:1.8rem;}
.qp-feature{display:flex;gap:.9rem;align-items:flex-start;margin-bottom:1.1rem;}
.qp-feature .ico{flex:0 0 40px;height:40px;border-radius:12px;display:flex;align-items:center;
  justify-content:center;background:rgba(255,255,255,.16);font-size:1.15rem;}
.qp-feature b{display:block;}
.qp-feature span{opacity:.85;font-size:.92rem;}
.qp-login-head h2{margin:.2rem 0 .2rem;font-size:1.7rem;}
.qp-login-head p{color:var(--qp-muted);margin:0 0 1rem;}

/* ---------- stat cards ---------- */
.qp-stat{background:#fff;border:1px solid var(--qp-border);border-radius:16px;
  padding:1.05rem 1.15rem;display:flex;gap:.9rem;align-items:center;
  box-shadow:0 4px 14px rgba(15,23,42,.04);}
.qp-stat .icon{flex:0 0 46px;height:46px;border-radius:13px;display:flex;align-items:center;
  justify-content:center;font-size:1.35rem;}
.qp-stat .label{font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;color:var(--qp-muted);font-weight:600;}
.qp-stat .value{font-size:1.65rem;font-weight:800;line-height:1.15;color:var(--qp-text);}
.qp-stat .hint{font-size:.78rem;color:var(--qp-muted);}
.tone-indigo .icon{background:#eef2ff;} .tone-green .icon{background:#dcfce7;}
.tone-amber .icon{background:#fef3c7;} .tone-red .icon{background:#fee2e2;}
.tone-sky .icon{background:#e0f2fe;}   .tone-violet .icon{background:#ede9fe;}

/* ---------- badges, banners ---------- */
.qp-badge{display:inline-block;padding:.15rem .65rem;border-radius:99px;font-size:.78rem;font-weight:700;}
.qp-badge.pass{background:#dcfce7;color:#166534;} .qp-badge.fail{background:#fee2e2;color:#991b1b;}
.qp-banner{border-radius:20px;padding:1.8rem 1.5rem;text-align:center;margin:.4rem 0 1.2rem;}
.qp-banner h2{margin:0 0 .3rem;font-size:1.9rem;color:inherit;} .qp-banner p{margin:0;opacity:.92;}
.qp-banner.pass{background:linear-gradient(120deg,#059669,#34d399);color:#fff;
  box-shadow:0 14px 34px rgba(5,150,105,.25);}
.qp-banner.fail{background:#fff1f2;border:2px solid #fb7185;color:#be123c;}

/* ---------- exam ---------- */
.qp-qcard{background:#fff;border:1px solid var(--qp-border);border-radius:20px;padding:1.5rem 1.6rem;
  margin:.8rem 0 1rem;box-shadow:0 8px 24px rgba(15,23,42,.05);}
.qp-qnum{font-size:.78rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--qp-primary);}
.qp-qtext{font-size:1.3rem;font-weight:650;line-height:1.45;margin-top:.35rem;white-space:pre-wrap;
  word-break:break-word;color:var(--qp-text);}
.qp-timer{background:#fff;border:1px solid var(--qp-border);border-radius:16px;padding:.9rem 1.1rem;}
.qp-timer .row{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:.5rem;}
.qp-timer .num{font-size:1.9rem;font-weight:800;font-variant-numeric:tabular-nums;}
.qp-timer .lbl{color:var(--qp-muted);font-size:.85rem;font-weight:600;}
.qp-timer .bar{height:9px;background:#e2e8f0;border-radius:99px;overflow:hidden;}
.qp-timer .fill{height:100%;border-radius:99px;transition:width 1s linear;}
.qp-timer.ok .num{color:var(--qp-green);} .qp-timer.ok .fill{background:var(--qp-green);}
.qp-timer.warn .num{color:#d97706;} .qp-timer.warn .fill{background:var(--qp-amber);}
.qp-timer.danger .num{color:var(--qp-red);} .qp-timer.danger .fill{background:var(--qp-red);}
.qp-subject{display:flex;align-items:center;gap:.8rem;margin-bottom:.3rem;}
.qp-subject .ico{width:46px;height:46px;border-radius:13px;display:flex;align-items:center;
  justify-content:center;font-size:1.4rem;background:#eef2ff;}
.qp-subject .name{font-weight:750;font-size:1.1rem;color:var(--qp-text);}
.qp-subject .meta{font-size:.85rem;color:var(--qp-muted);}
.qp-review{border-left:4px solid var(--qp-border);padding:.55rem .9rem;margin:.5rem 0;
  background:#fff;border-radius:0 10px 10px 0;}
.qp-review.good{border-left-color:var(--qp-green);} .qp-review.bad{border-left-color:var(--qp-red);}
.qp-review .q{font-weight:650;} .qp-review .a{font-size:.88rem;color:var(--qp-muted);}

/* ---------- leaderboard, lists ---------- */
.qp-podium{background:#fff;border:1px solid var(--qp-border);border-radius:18px;padding:1.1rem;
  text-align:center;box-shadow:0 6px 18px rgba(15,23,42,.05);}
.qp-podium .medal{font-size:2.2rem;} .qp-podium .who{font-weight:750;color:var(--qp-text);word-break:break-word;}
.qp-podium .pts{font-size:1.5rem;font-weight:800;color:var(--qp-primary);}
.qp-podium.me{border:2px solid var(--qp-primary);background:#f5f3ff;}
.qp-recent{display:flex;justify-content:space-between;align-items:center;gap:.6rem;
  padding:.65rem .9rem;background:#fff;border:1px solid var(--qp-border);border-radius:12px;margin-bottom:.5rem;}
.qp-recent .sub{color:var(--qp-muted);font-size:.8rem;}
.qp-empty{text-align:center;padding:2.2rem 1rem;border:2px dashed #cbd5e1;border-radius:18px;
  color:var(--qp-muted);background:#fff;}
.qp-empty .big{font-size:2.2rem;} .qp-empty b{display:block;color:var(--qp-text);margin:.2rem 0;}

/* ---------- certificate preview ---------- */
.qp-cert{background:#fffdf7;border:6px double #b8892b;border-radius:14px;padding:6px;
  box-shadow:0 14px 36px rgba(184,137,43,.18);margin:.6rem 0 1rem;}
.qp-cert-inner{border:1.5px solid #1b1f4b;border-radius:8px;padding:1.6rem 1rem;text-align:center;color:#1b1f4b;}
.qp-cert-org{letter-spacing:.3em;font-size:.72rem;font-weight:700;color:#5b6475;text-transform:uppercase;}
.qp-cert-title{font-family:Georgia,'Times New Roman',serif;font-size:2.6rem;font-weight:800;line-height:1.1;margin-top:.3rem;}
.qp-cert-sub{letter-spacing:.45em;color:#b8892b;font-weight:700;font-size:.8rem;}
.qp-cert-line{width:160px;height:2px;margin:.8rem auto;background:#b8892b;}
.qp-cert-small{font-family:Georgia,serif;font-style:italic;color:#5b6475;margin:.3rem 0;}
.qp-cert-name{font-family:Georgia,serif;font-style:italic;font-weight:700;font-size:2.1rem;
  border-bottom:1.5px solid #b8892b;display:inline-block;padding:0 1.5rem .1rem;margin:.2rem 0;word-break:break-word;}
.qp-cert-subject{font-size:1.45rem;font-weight:800;color:#4f46e5;margin:.2rem 0 .8rem;}
.qp-cert-meta{display:flex;justify-content:center;gap:1.8rem;flex-wrap:wrap;font-size:.95rem;}
.qp-cert-meta b{color:#5b6475;font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;margin-right:.35rem;}
.qp-cert-foot{margin-top:1rem;font-size:.78rem;color:#5b6475;}

@media (max-width:900px){
  .qp-hero{min-height:auto;padding:1.8rem 1.4rem;} .qp-hero h1{font-size:1.8rem;margin-top:1.2rem;}
}
</style>
"""


def inject_theme() -> None:
    """Emit the global CSS (call once per script run)."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


# ==========================================================================
# Small helpers
# ==========================================================================
def html(markup: str) -> None:
    """Render trusted HTML.

    Lines are stripped and joined because Markdown treats blank lines and
    4-space indentation inside HTML as code blocks.  Callers must escape any
    user supplied text with ``utils.esc`` first.
    """
    flat = " ".join(line.strip() for line in markup.strip().splitlines() if line.strip())
    st.markdown(flat, unsafe_allow_html=True)


def table(df: pd.DataFrame, **kwargs: Any) -> None:
    """Full-width dataframe that works on old *and* new Streamlit versions.

    Newer releases replaced ``use_container_width=True`` with ``width="stretch"``;
    this tries the new spelling first and falls back to the old one.
    """
    kwargs.setdefault("hide_index", True)
    last_error: Optional[Exception] = None
    for extra in ({"width": "stretch"}, {"use_container_width": True}, {}):
        try:
            st.dataframe(df, **kwargs, **extra)
            return
        except Exception as exc:  # noqa: BLE001 - try the next spelling
            last_error = exc
    raise last_error  # type: ignore[misc]


def flash(kind: str, message: str) -> None:
    """Queue a one-time message that survives the next ``st.rerun()``."""
    st.session_state["flash"] = (kind, message)


def show_flash() -> None:
    """Display (and clear) the queued flash message, if any."""
    item = st.session_state.get("flash")
    if not item:
        return
    st.session_state["flash"] = None
    kind, message = item
    {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(message)


def go_to(page: str) -> None:
    """Switch page; safe to use as a button ``on_click`` callback."""
    st.session_state["page"] = page


# ==========================================================================
# Components
# ==========================================================================
def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    html(
        f"""
        <div class="qp-page-head">
          <div class="qp-page-icon">{esc(icon)}</div>
          <div><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>
        </div>
        """
    )


def stat_card_html(label: str, value: Any, icon: str = "", hint: str = "", tone: str = "indigo") -> str:
    return (
        f'<div class="qp-stat tone-{esc(tone)}"><div class="icon">{esc(icon)}</div>'
        f'<div><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div>'
        f'<div class="hint">{esc(hint)}</div></div></div>'
    )


def stat_row(items: List[Dict[str, Any]]) -> None:
    """A row of stat cards. Each item: label, value, icon, hint, tone."""
    for col, item in zip(st.columns(len(items)), items):
        with col:
            html(stat_card_html(**item))


def badge(status: str) -> str:
    """HTML pill for PASS / FAIL."""
    passed = str(status).upper() == "PASS"
    return f'<span class="qp-badge {"pass" if passed else "fail"}">{"PASS" if passed else "FAIL"}</span>'


def empty_state(icon: str, title: str, text: str = "") -> None:
    html(
        f'<div class="qp-empty"><div class="big">{esc(icon)}</div>'
        f"<b>{esc(title)}</b><div>{esc(text)}</div></div>"
    )


def result_banner(passed: bool, percentage: float, pass_mark: int) -> None:
    if passed:
        html(
            """
            <div class="qp-banner pass"><h2>🎉 Congratulations! You passed!</h2>
            <p>Excellent work - your certificate is ready below.</p></div>
            """
        )
    else:
        html(
            f"""
            <div class="qp-banner fail"><h2>Not passed this time</h2>
            <p>You scored {percentage:.1f}% - you need {pass_mark}% to pass. Practise and try again!</p></div>
            """
        )


# ==========================================================================
# Sidebar navigation
# ==========================================================================
def render_sidebar(
    pages: Iterable[Tuple[str, str]],
    display_name: str,
    role: str,
    on_logout: Callable[[], None],
    locked: bool = False,
) -> None:
    """Brand, user card, navigation buttons and log-out button.

    ``pages`` is a list of ``(page_key, label)``.  When ``locked`` (an exam
    is running) every other page button is disabled.
    """
    current = st.session_state.get("page")
    with st.sidebar:
        html('<div class="qp-brand"><div class="logo">🎓</div><div>Quiz Portal</div></div>')
        html(
            f"""
            <div class="qp-user"><div class="qp-avatar">{esc(initials(display_name))}</div>
            <div><div class="name">{esc(display_name)}</div><div class="role">{esc(role)}</div></div></div>
            """
        )
        if locked:
            st.caption("🔒 Exam in progress - navigation is locked")
        for key, label in pages:
            st.button(
                label,
                key=f"nav_{key}",
                type="primary" if current == key else "secondary",
                disabled=locked and current != key,
                on_click=go_to,
                args=(key,),
            )
        st.divider()
        st.button("🚪  Log out", key="logout_button", on_click=on_logout, disabled=False)
