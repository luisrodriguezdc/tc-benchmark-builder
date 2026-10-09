CSS = """
<style>
:root { --tcb-primary: #3697b3; --tcb-text: #31333f; --tcb-line: rgba(49, 51, 63, 0.2); }
.block-container { padding-top: 1.15rem; padding-bottom: 4.5rem; max-width: 1100px; }
.tcb-title { font-size: 1.35rem; font-weight: 700; margin-bottom: 0.35rem; line-height: 1.3; color: #1f2328; }
.tcb-badge {
  display: inline-block; font-size: 0.68rem; font-weight: 800; letter-spacing: 0.06em;
  text-transform: uppercase; background: #f6e28b; color: #5c4b12; border-radius: 999px;
  padding: 0.12rem 0.45rem; vertical-align: middle; margin-left: 0.15rem;
}
div[data-testid="stPopover"] > button {
  border: 1px solid #c5c9ce !important; border-radius: 999px !important;
  background: #fff !important; font-weight: 600 !important;
  min-height: 36px !important; padding: 0.25rem 0.85rem !important;
}
.tcb-counts { color: #5c616c; font-size: 0.92rem; margin: 0.45rem 0 0.15rem; }
.segment-banner {
  background: #d4eef6; border-radius: 6px; padding: 0.9rem 2.7rem 0.95rem;
  text-align: center; margin: 0.45rem 0 0.85rem;
}
.segment-banner.flagged { background: #fde4ef; box-shadow: inset 0 0 0 1px #f4c2d7; }
.segment-banner .flag-note {
  font-size: 0.8rem; font-weight: 700; color: #9b225d; margin-top: 0.5rem;
}
div.element-container:has(.tcb-banner-marker),
div[data-testid="stElementContainer"]:has(.tcb-banner-marker) {
  position: absolute !important; height: 0 !important; margin: 0 !important;
  padding: 0 !important; overflow: hidden !important;
}
div[class*="st-key-src_err_"] {
  width: 100% !important;
  max-width: 100% !important;
  position: relative !important;
  z-index: 4;
  display: flex !important;
  justify-content: flex-end !important;
  margin: 0.35rem 0 -4.55rem 0 !important;
  height: 2.4rem !important;
}
div[class*="st-key-src_err_"] [data-testid="stButton"] {
  width: auto !important;
  margin-right: 0.7rem;
}
div[class*="st-key-src_err_"] button {
  min-width: 2.35rem; min-height: 2.35rem;
  padding: 0.15rem 0.85rem !important;
  font-weight: 700 !important;
}
div.element-container:has(.tcb-banner-marker.flagged) + div[class*="st-key-src_err_"] button,
div[data-testid="stElementContainer"]:has(.tcb-banner-marker.flagged) + div[class*="st-key-src_err_"] button {
  background: #c45a7a !important;
  color: #fff !important;
  border-color: #9b225d !important;
}
.segment-banner .progress { font-size: 0.8rem; color: #000; margin-bottom: 0.45rem; }
.segment-banner .k {
  font-size: 0.72rem; letter-spacing: 0.05em; text-transform: uppercase;
  color: #000; font-weight: 700; margin-top: 0.35rem;
}
.segment-banner .line { font-size: 1.05rem; font-weight: 600; color: #000; line-height: 1.5; margin: 0.12rem 0 0.2rem; }
.span-preview {
  font-size: 1.05rem; font-weight: 600; line-height: 1.5; text-align: center;
  padding: 0.35rem 0.4rem; color: #000; min-height: 3rem;
}
.span-note { font-size: 0.75rem; color: #9a3412; text-align: center; }
.save-ok { color: #1b7f3a; font-size: 0.85rem; }
.save-busy { color: #9a6700; font-size: 0.85rem; }
.save-fail { color: #b42318; font-size: 0.85rem; }
.status-draft { color: #9a6700; font-weight: 600; }
.status-validated { color: #000; font-weight: 700; }
.status-rejected { color: #000; font-weight: 700; }
.tcb-card-state { font-size: 0.82rem; font-weight: 700; color: #000; }
div.element-container:has(.tcb-mark-minor),
div.element-container:has(.tcb-mark-major),
div.element-container:has(.tcb-mark-type) {
  position: absolute !important; height: 0 !important; margin: 0 !important;
  padding: 0 !important; overflow: hidden !important;
}
.tcb-mark-minor, .tcb-mark-major, .tcb-mark-type { display: none; }
div.element-container:has(.tcb-mark-minor) + div.element-container [data-baseweb="select"] > div {
  background-color: #fff6e0 !important; color: #6b4e00 !important;
  border-radius: 999px !important; border-color: #ead79a !important;
  min-height: 32px !important;
}
div.element-container:has(.tcb-mark-major) + div.element-container [data-baseweb="select"] > div {
  background-color: #fde4ef !important; color: #9b225d !important;
  border-radius: 999px !important; border-color: #f4c2d7 !important;
  min-height: 32px !important;
}
div.element-container:has(.tcb-mark-type) + div.element-container [data-baseweb="select"] > div {
  background-color: #e8f1fb !important; color: #0f3a5f !important;
  border-radius: 999px !important; border-color: #c5d8ee !important;
  min-height: 32px !important;
}
div.element-container:has(.tcb-mark-minor) + div.element-container [data-baseweb="select"] *,
div.element-container:has(.tcb-mark-major) + div.element-container [data-baseweb="select"] *,
div.element-container:has(.tcb-mark-type) + div.element-container [data-baseweb="select"] * {
  font-weight: 700 !important; font-size: 0.78rem !important;
}
.pill {
  display: inline-block; border-radius: 999px; padding: 0.12rem 0.55rem;
  font-size: 0.78rem; font-weight: 700; white-space: nowrap;
}
.pill-wip { background: #fff6e0; color: #6b4e00; }
.pill-new { background: #e8f1fb; color: #0f3a5f; }
.pill-done { background: #e7f6ec; color: #146c36; }
.tcb-table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
.tcb-table th, .tcb-table td {
  text-align: left; padding: 0.48rem 0.4rem;
  border-bottom: 1px solid rgba(49, 51, 63, 0.12); vertical-align: middle;
}
.tcb-table th { font-weight: 700; }
.tcb-caption { color: #5c616c; font-size: 0.8rem; margin: 0.3rem 0; }
.tcb-alert { border-radius: 0.5rem; padding: 0.7rem 0.85rem; margin: 0.45rem 0 0.75rem; }
.tcb-alert.warn { background: #fff6e0; color: #6b4e00; }
.tcb-alert.ok { background: #e7f6ec; color: #146c36; }
div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
  border-radius: 999px; min-height: 30px;
  justify-content: center !important;
  text-align: center !important;
}
div[data-testid="stSelectbox"] [data-baseweb="select"] input {
  text-align: center !important;
}
[data-baseweb="popover"] li[role="option"] {
  justify-content: center !important;
  text-align: center !important;
}
</style>
"""


def inject() -> None:
    import streamlit as st

    st.markdown(CSS, unsafe_allow_html=True)


def status_pill(status: str) -> str:
    kind = "pill-wip" if status == "WIP" else "pill-done" if status == "Completed" else "pill-new"
    return f'<span class="pill {kind}">{status}</span>'
