"""Shared visual theme: injected CSS + reusable color constants + chart styling helpers."""
import streamlit as st

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
INK = "#1A1A17"
INK_SOFT = "#5C5A52"
INK_FAINT = "#8A887E"
PAPER = "#FBFAF8"
SAND = "#F2F0EB"
LINE = "#E4E1D9"
GREEN = "#1B4D3E"
GREEN_SOFT = "#2E6B57"
GREEN_TINT = "#DCE7E1"
AMBER = "#C08A2D"
CLAY = "#B44C3C"
CLAY_TINT = "#F0DDD8"

# Ordered categorical palette for charts (muted, editorial, distinguishable)
SERIES = ["#1B4D3E", "#C08A2D", "#4A6D8C", "#8C6A4A", "#7A8C4A", "#8C4A6D", "#4A8C7A", "#6A5A8C"]

PLOTLY_FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"


def style_fig(fig, height=360, showlegend=True, legend_top=True):
    """Apply consistent, clean styling to any Plotly figure."""
    fig.update_layout(
        height=height,
        showlegend=showlegend,
        font=dict(family=PLOTLY_FONT, size=13, color=INK_SOFT),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=28 if legend_top else 12, b=8),
        hoverlabel=dict(bgcolor="white", font_size=13, font_family=PLOTLY_FONT,
                        bordercolor=LINE),
        colorway=SERIES,
    )
    if showlegend and legend_top:
        fig.update_layout(legend=dict(
            orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
            font=dict(size=12), bgcolor="rgba(0,0,0,0)",
        ))
    fig.update_xaxes(showgrid=False, zeroline=False, showline=True,
                     linecolor=LINE, tickfont=dict(size=12, color=INK_FAINT))
    fig.update_yaxes(showgrid=True, gridcolor=LINE, zeroline=False,
                     tickfont=dict(size=12, color=INK_FAINT))
    return fig


def inject_theme():
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&display=swap');

    html, body, [class*="css"], .stApp {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        color: {INK};
    }}
    .stApp {{ background: {PAPER}; }}

    /* Headings use the serif display face */
    h1, h2, h3 {{
        font-family: 'Fraunces', Georgia, serif !important;
        color: {INK} !important;
        letter-spacing: -0.01em;
        font-weight: 500 !important;
    }}
    h1 {{ font-size: 1.9rem !important; }}
    h2 {{ font-size: 1.35rem !important; }}
    h3 {{ font-size: 1.1rem !important; }}

    /* Sidebar */
    section[data-testid="stSidebar"] {{
        background: {INK};
        border-right: 1px solid {INK};
    }}
    section[data-testid="stSidebar"] * {{ color: #E9E7E0 !important; }}
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{ color: #FFFFFF !important; }}
    section[data-testid="stSidebar"] .stButton button {{
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.18);
        color: #E9E7E0 !important;
    }}
    section[data-testid="stSidebar"] .stButton button:hover {{
        background: rgba(255,255,255,0.16);
        border-color: rgba(255,255,255,0.3);
    }}
    /* Sidebar nav links */
    section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] span {{
        font-size: 0.92rem;
    }}

    /* Buttons */
    .stButton button {{
        border-radius: 8px;
        font-weight: 500;
        border: 1px solid {LINE};
        transition: all 0.12s ease;
    }}
    .stButton button[kind="primary"],
    .stButton button[kind="primaryFormSubmit"],
    .stFormSubmitButton button[kind="primary"] {{
        background: {GREEN};
        border-color: {GREEN};
        color: #FFFFFF !important;
    }}
    .stButton button[kind="primary"] *,
    .stButton button[kind="primaryFormSubmit"] *,
    .stFormSubmitButton button[kind="primary"] * {{
        color: #FFFFFF !important;
    }}
    .stButton button[kind="primary"]:hover,
    .stButton button[kind="primaryFormSubmit"]:hover,
    .stFormSubmitButton button[kind="primary"]:hover {{
        background: {GREEN_SOFT};
        border-color: {GREEN_SOFT};
        color: #FFFFFF !important;
    }}

    /* Inputs */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    div[data-baseweb="select"] > div {{
        border-radius: 8px !important;
        border-color: {LINE} !important;
    }}

    /* Metric cards */
    div[data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1px solid {LINE};
        border-radius: 16px;
        padding: 1.15rem 1.3rem;
        box-shadow: 0 1px 2px rgba(26,26,23,0.04), 0 1px 3px rgba(26,26,23,0.03);
        transition: box-shadow 0.15s ease, transform 0.15s ease;
        min-height: 118px;
    }}
    div[data-testid="stMetric"]:hover {{
        box-shadow: 0 4px 14px rgba(26,26,23,0.07);
        transform: translateY(-1px);
    }}
    div[data-testid="stMetric"] label {{
        color: {INK_FAINT} !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.07em;
    }}
    div[data-testid="stMetricValue"] {{
        font-family: 'Fraunces', Georgia, serif !important;
        font-weight: 500;
        color: {INK} !important;
        font-size: clamp(1.1rem, 1.7vw, 1.7rem) !important;
        white-space: normal;
        overflow-wrap: anywhere;
        line-height: 1.12;
        margin-top: 0.15rem;
    }}
    div[data-testid="stMetricDelta"] {{
        font-size: 0.78rem !important;
        font-weight: 600 !important;
    }}

    /* Dataframe */
    div[data-testid="stDataFrame"] {{
        border: 1px solid {LINE};
        border-radius: 12px;
    }}

    /* Tabs */
    button[data-baseweb="tab"] {{ font-weight: 500; }}
    div[data-baseweb="tab-highlight"] {{ background: {GREEN} !important; }}

    /* Expander */
    details {{ border: 1px solid {LINE} !important; border-radius: 12px !important; }}
    summary {{ font-weight: 500; }}

    /* Progress bar */
    div[data-testid="stProgress"] div[role="progressbar"] > div {{
        background: {GREEN} !important;
    }}

    /* Hide default menu/footer for a cleaner look */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}

    /* Divider */
    hr {{ border-color: {LINE}; }}
    </style>
    """, unsafe_allow_html=True)


def section_label(text):
    """A small uppercase eyebrow label above a section."""
    st.markdown(
        f"<div style='font-size:0.72rem; font-weight:600; letter-spacing:0.08em; "
        f"text-transform:uppercase; color:{INK_FAINT}; margin:0.2rem 0 0.4rem;'>{text}</div>",
        unsafe_allow_html=True,
    )
