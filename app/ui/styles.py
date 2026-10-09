CSS = """
<style>
.block-container { padding-top: 1.2rem; max-width: 980px; }
.tcb-title { font-size: 1.35rem; font-weight: 650; margin-bottom: 0.15rem; }
.tcb-userbox {
  border: 1px solid #c5c9ce; border-radius: 6px; padding: 0.55rem 0.75rem;
  font-size: 0.85rem; background: #fff;
}
.segment-banner {
  background: #f6e28b; border-radius: 6px; padding: 0.9rem 1.1rem;
  text-align: center; margin: 0.4rem 0 1rem 0;
}
.segment-banner .progress { font-size: 0.8rem; color: #5c4b12; margin-bottom: 0.35rem; }
.segment-banner .src { font-size: 1.05rem; font-weight: 600; color: #1f2328; }
.segment-banner .ref { font-size: 1.05rem; font-weight: 600; color: #1f2328; margin-top: 0.15rem; }
.span-preview {
  font-size: 0.95rem; line-height: 1.45; padding: 0.15rem 0 0.4rem 0; color: #1f2328;
}
.span-note { font-size: 0.75rem; color: #9a3412; }
.save-ok { color: #1b7f3a; font-size: 0.85rem; }
.save-busy { color: #9a6700; font-size: 0.85rem; }
.save-fail { color: #b42318; font-size: 0.85rem; }
.status-draft { color: #9a6700; font-weight: 600; }
.status-validated { color: #1b7f3a; font-weight: 600; }
.status-rejected { color: #b42318; font-weight: 600; }
</style>
"""


def inject() -> None:
    import streamlit as st

    st.markdown(CSS, unsafe_allow_html=True)
