import streamlit as st


def apply_theme() -> None:
    st.markdown("""
    <style>
    :root { --ink:#17202a; --muted:#667085; --line:#dfe3e8; --paper:#f6f7f8; --navy:#153a5b; --red:#b42318; --amber:#b54708; --green:#027a48; }
    .stApp { background:var(--paper); color:var(--ink); }
    #MainMenu, footer, header { visibility:hidden; }
    .block-container { max-width:1480px; padding:1rem 2.2rem 3rem; }
    h1,h2,h3 { color:var(--ink); font-family:Arial, sans-serif; letter-spacing:-.025em; }
    h1 { font-size:2rem !important; margin-bottom:.1rem !important; }
    h2 { font-size:1.25rem !important; margin-top:1.8rem !important; border-top:1px solid var(--line); padding-top:1rem; }
    [data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:2px; padding:.65rem .8rem; }
    [data-testid="stMetricLabel"] { color:var(--muted); font-size:.74rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }
    [data-testid="stMetricValue"] { font-variant-numeric:tabular-nums; color:var(--ink); }
    .storm-header { border-bottom:2px solid var(--navy); display:flex; align-items:end; justify-content:space-between; padding:0 0 .55rem; margin-bottom:.45rem; }
    .storm-wordmark { font-size:1.25rem; font-weight:800; letter-spacing:.12em; color:var(--navy); }
    .storm-meta { color:var(--muted); font-size:.82rem; text-align:right; line-height:1.5; }
    .finding { background:#fff; border-left:3px solid var(--navy); padding:.75rem .85rem; min-height:92px; }
    .finding-risk { border-left-color:var(--red); } .finding-watch { border-left-color:var(--amber); } .finding-strength { border-left-color:var(--green); }
    .finding-label { font-size:.68rem; font-weight:800; letter-spacing:.09em; color:var(--muted); margin-bottom:.35rem; }
    .finding-text { font-size:.92rem; color:var(--ink); line-height:1.35; }
    .channel-row { background:#fff; border-top:1px solid var(--line); padding:.65rem .85rem; margin:0; }
    .channel-name { color:var(--navy); font-size:.92rem; font-weight:800; }
    .section-note { color:var(--muted); font-size:.83rem; }
    .stButton>button { border-radius:6px; border-color:#cbd3dc; color:var(--ink); background:#fff; }
    [data-testid="stRadio"] > div { gap:.2rem; border-bottom:1px solid var(--line); padding-bottom:.3rem; }
    [data-testid="stRadio"] label { padding:.32rem .75rem; border-radius:2px; font-size:.82rem; font-weight:700; color:var(--muted); }
    [data-testid="stRadio"] label:has(input:checked) { background:var(--navy); color:#fff; }
    [data-testid="stRadio"] input { display:none; }
    .business-block { background:#fff; border-top:3px solid var(--navy); padding:.85rem 1rem .7rem; min-height:146px; }
    .block-title { font-size:.73rem; letter-spacing:.1em; font-weight:800; color:var(--navy); margin-bottom:.7rem; }
    .metric-pairs { display:grid; grid-template-columns:1fr 1fr; gap:.4rem 1.4rem; }
    .metric-pair { display:flex; justify-content:space-between; gap:.6rem; border-bottom:1px solid #eef0f2; font-size:.82rem; padding-bottom:.2rem; }
    .metric-pair span,.block-note { color:var(--muted); }.metric-pair strong { font-variant-numeric:tabular-nums; }
    .block-note { margin-top:.55rem; font-size:.75rem; }
    .matrix-head,.matrix-row { display:grid; grid-template-columns:1.3fr .9fr 1.3fr .9fr .7fr; align-items:center; gap:.8rem; padding:.5rem .7rem; }
    .matrix-head { color:var(--muted); font-size:.7rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; border-bottom:1px solid var(--line); }
    .matrix-row { background:#fff; border-bottom:1px solid var(--line); font-size:.84rem; }.matrix-row b { color:var(--navy); }.matrix-row span { font-variant-numeric:tabular-nums; }
    .micro { display:inline-block; width:58px; height:5px; background:#e7ebee; margin-right:.35rem; vertical-align:middle; }.micro em { display:block; height:100%; background:var(--navy); }
    .conclusion { display:grid; grid-template-columns:110px 1fr; gap:.75rem; background:#fff; border-left:3px solid var(--navy); padding:.55rem .75rem; margin:.28rem 0; font-size:.86rem; }.conclusion b { color:var(--navy); font-size:.72rem; letter-spacing:.06em; }
    [data-testid="stDataFrame"] { border:1px solid var(--line); }
    </style>
    """, unsafe_allow_html=True)
