"""Streamlit Web UI for AI Code Reviewer.

Provides an interactive, polished interface to review Python code via direct pasting
or by fetching public files directly from GitHub.
"""

import os
import streamlit as st
from dotenv import load_dotenv

from static_analyzer import run_static_analysis
from llm_reviewer import run_llm_review, get_groq_api_key
from merger import merge_reviews
from github_fetcher import fetch_github_file

# Load environment variables from .env
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="AI Code Reviewer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# 1. Custom CSS Theme & Typography Injection
# -----------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
/* Import Google Fonts: Inter and JetBrains Mono */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* Global Font & Theme overrides */
html, body, [class*="css"], [class*="st-"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

code, pre, .font-mono {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Base App Background */
.stApp {
    background-color: #0B0F19;
    color: #E2E8F0;
}

/* Sidebar Styling */
section[data-testid="stSidebar"] {
    background-color: #111827;
    border-right: 1px solid rgba(255, 255, 255, 0.07);
}

/* Hero Header Banner */
.hero-banner {
    background: linear-gradient(135deg, rgba(14, 165, 233, 0.12) 0%, rgba(6, 182, 212, 0.05) 50%, rgba(30, 41, 59, 0.6) 100%);
    border: 1px solid rgba(14, 165, 233, 0.25);
    border-radius: 16px;
    padding: 24px 30px;
    margin-bottom: 24px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    position: relative;
    overflow: hidden;
}
.hero-badge {
    display: inline-flex;
    align-items: center;
    background: rgba(14, 165, 233, 0.18);
    color: #38BDF8;
    border: 1px solid rgba(14, 165, 233, 0.4);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 10px;
}
.hero-title {
    font-size: 2.1rem;
    font-weight: 700;
    color: #F8FAFC;
    margin: 0 0 6px 0;
    letter-spacing: -0.5px;
}
.hero-subtitle {
    font-size: 0.95rem;
    color: #94A3B8;
    margin: 0;
    max-width: 780px;
}

/* Prominent Primary Run Button */
div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0EA5E9 0%, #06B6D4 100%) !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    font-size: 1.02rem !important;
    padding: 0.65rem 1.6rem !important;
    border: none !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 16px rgba(14, 165, 233, 0.38) !important;
    transition: all 0.2s ease-in-out !important;
    cursor: pointer !important;
    width: 100% !important;
}
div.stButton > button[kind="primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 24px rgba(14, 165, 233, 0.55) !important;
    filter: brightness(1.08) !important;
}

/* Metric Cards Styling */
.metric-card {
    background: #161E2E;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 20px 22px;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25);
    transition: transform 0.15s ease, border-color 0.15s ease;
}
.metric-card:hover {
    border-color: rgba(14, 165, 233, 0.4);
    transform: translateY(-2px);
}
.metric-label {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #94A3B8;
    margin-bottom: 8px;
}
.metric-value {
    font-size: 2.2rem;
    font-weight: 700;
    line-height: 1.1;
    margin-bottom: 6px;
    font-family: 'JetBrains Mono', monospace;
}
.metric-sub {
    font-size: 1.1rem;
    color: #64748B;
    font-weight: 500;
}
.metric-hint {
    font-size: 0.78rem;
    font-weight: 500;
}

/* Quick Tips / Info Card */
.tips-card {
    background: #111827;
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 14px;
    padding: 20px 22px;
    height: 100%;
}
.tips-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: #F8FAFC;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.tips-item {
    font-size: 0.82rem;
    color: #94A3B8;
    margin-bottom: 10px;
    line-height: 1.45;
}
.tips-item strong {
    color: #E2E8F0;
}

/* Custom Issue Expanders */
div[data-testid="stExpander"] {
    background-color: #161E2E !important;
    border: 1px solid rgba(255, 255, 255, 0.07) !important;
    border-radius: 12px !important;
    margin-bottom: 12px !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2) !important;
    transition: border-color 0.15s ease !important;
}
div[data-testid="stExpander"]:hover {
    border-color: rgba(14, 165, 233, 0.35) !important;
}

/* Badge Pills */
.badge {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 3px 9px;
    border-radius: 6px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    margin-right: 6px;
}
.badge-high {
    background: rgba(239, 68, 68, 0.16);
    color: #F87171;
    border: 1px solid rgba(239, 68, 68, 0.45);
}
.badge-medium {
    background: rgba(245, 158, 11, 0.16);
    color: #FBBF24;
    border: 1px solid rgba(245, 158, 11, 0.45);
}
.badge-low {
    background: rgba(148, 163, 184, 0.14);
    color: #CBD5E1;
    border: 1px solid rgba(148, 163, 184, 0.35);
}
.badge-cat {
    background: rgba(14, 165, 233, 0.14);
    color: #38BDF8;
    border: 1px solid rgba(14, 165, 233, 0.35);
}
.badge-line {
    background: rgba(255, 255, 255, 0.06);
    color: #E2E8F0;
    border: 1px solid rgba(255, 255, 255, 0.12);
}
.badge-source-both {
    background: rgba(168, 85, 247, 0.18);
    color: #C084FC;
    border: 1px solid rgba(168, 85, 247, 0.45);
}
.badge-source-llm {
    background: rgba(59, 130, 246, 0.18);
    color: #60A5FA;
    border: 1px solid rgba(59, 130, 246, 0.45);
}
.badge-source-static {
    background: rgba(16, 185, 129, 0.18);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.45);
}

/* Custom left-bordered card for issue content */
.issue-card {
    padding: 12px 16px;
    border-radius: 0 10px 10px 0;
    margin-top: 6px;
    margin-bottom: 8px;
    background: rgba(255, 255, 255, 0.02);
}
.issue-card-high {
    border-left: 4px solid #EF4444;
}
.issue-card-medium {
    border-left: 4px solid #F59E0B;
}
.issue-card-low {
    border-left: 4px solid #64748B;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Header Hero Area
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="hero-banner">
        <div class="hero-badge">⚡ Automated Code Intelligence</div>
        <h1 class="hero-title">AI Code Reviewer</h1>
        <p class="hero-subtitle">
            Combines deterministic static analyzers (Pylint, Flake8, Bandit, Radon) with
            Groq-accelerated LLM reasoning to catch syntax, security, and deep logic flaws in seconds.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Sidebar: Settings & System Architecture
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("ℹ️ Architecture")
    st.markdown(
        """
        **The 3-Stage Review Process:**

        1. **Static Analysis Layer**:
           Runs `Pylint`, `Flake8`, `Bandit`, and `Radon` in a temporary sandbox to catch styling, known CVEs, and cyclomatic complexity.
        
        2. **Groq LLM Reasoning Layer**:
           Passes code and linter findings to Groq (`groq/compound`). Focuses on logic bugs, misleading naming, and edge cases.
        
        3. **Merge & Deduplicate Layer**:
           Normalizes findings, collapses identical findings on the same line into a unified `[BOTH]` tag, and prioritizes by severity.
        """
    )
    
    st.divider()
    st.subheader("⚙️ API Configuration")
    detected_key = get_groq_api_key()
    if detected_key:
        masked_key = detected_key[:6] + "..." + detected_key[-4:] if len(detected_key) > 10 else "***"
        st.success(f"Groq Key active: `{masked_key}`")
        custom_key = st.text_input("Override API Key (optional):", type="password", placeholder="gsk_...")
    else:
        st.warning("No key found in secrets or `.env`.")
        custom_key = st.text_input("Enter Groq API Key:", type="password", placeholder="gsk_...")

# -----------------------------------------------------------------------------
# 2. Side-by-Side Layout: Input Area + Quick Tips Panel
# -----------------------------------------------------------------------------
DEFAULT_SAMPLE_CODE = '''import os
import sys

def authenticate_and_calculate(user_role, values):
    hardcoded_token = "admin_secret_token_98765"
    total = 0
    try:
        if user_role == "admin":
            for val in values:
                if val > 0:
                    total += val
                else:
                    total -= val
        else:
            total = sum(values)
    except:
        pass
    return total
'''

DEFAULT_GITHUB_URL = "https://github.com/psf/requests/blob/main/src/requests/__version__.py"

col_input, col_tips = st.columns([7, 3], gap="large")

with col_input:
    input_mode = st.radio(
        "Input Method:",
        options=["Paste Code", "GitHub URL"],
        horizontal=True,
    )

    if input_mode == "Paste Code":
        code_input = st.text_area(
            "Python Source Code:",
            value=DEFAULT_SAMPLE_CODE,
            height=260,
            help="Paste standard Python code here.",
        )
        github_url = ""
    else:
        github_url = st.text_input(
            "Public GitHub File URL:",
            value=DEFAULT_GITHUB_URL,
            placeholder="https://github.com/owner/repo/blob/main/path/to/file.py",
            help="Paste a direct link to any public file on GitHub.",
        )
        code_input = ""

    run_btn = st.button("🚀 Run Comprehensive Review", type="primary", use_container_width=True)

with col_tips:
    st.markdown(
        """
        <div class="tips-card">
            <div class="tips-title">💡 How to Get Best Results</div>
            <div class="tips-item">
                <strong>• Paste Real Snippets:</strong> Include full functions or modules for accurate cyclomatic complexity scoring.
            </div>
            <div class="tips-item">
                <strong>• Public GitHub Files:</strong> Point directly to a file on any branch (e.g. <code>blob/main/file.py</code>).
            </div>
            <div class="tips-item">
                <strong>• Groq Model:</strong> Defaults to <code>groq/compound</code> for near-instant inference and deep reasoning.
            </div>
            <div class="tips-item">
                <strong>• Deduplication:</strong> Identical issues flagged by both linters and AI are merged into a single <code>[BOTH]</code> card.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# 3. Execution Pipeline with Polished Multi-Step Loading State
# -----------------------------------------------------------------------------
if run_btn:
    active_api_key = get_groq_api_key(custom_key)
    if not active_api_key:
        st.error(
            "🔑 **GROQ_API_KEY is not set!**\n\n"
            "To run the LLM review layer, please either:\n"
            "1. Enter your Groq API key in the sidebar under **API Configuration**.\n"
            "2. Add `GROQ_API_KEY = \"your_key\"` to your Streamlit Cloud Secrets.\n"
            "3. Add `GROQ_API_KEY=your_key` to a `.env` file in the project folder."
        )
        st.stop()

    code_to_review = ""

    # Fetch from GitHub if selected
    if input_mode == "GitHub URL":
        clean_url = github_url.strip()
        if not clean_url:
            st.warning("⚠️ Please provide a valid GitHub file URL.")
            st.stop()

        with st.spinner("Connecting to GitHub CDN..."):
            try:
                code_to_review = fetch_github_file(clean_url)
            except FileNotFoundError as fnf_err:
                st.error(f"❌ {fnf_err}")
                st.stop()
            except ValueError as val_err:
                st.error(f"❌ {val_err}")
                st.stop()
            except Exception as gen_err:
                st.error(f"❌ Failed to retrieve file from GitHub: {gen_err}")
                st.stop()

        if not clean_url.split("?")[0].lower().endswith(".py"):
            st.warning(
                "⚠️ **Non-Python File Notice:** The selected file does not have a `.py` extension. "
                "Static analysis tools will run, but may report fewer issues."
            )
    else:
        code_to_review = code_input

    if not code_to_review.strip():
        st.warning("⚠️ The provided code is empty. Please supply valid code to review.")
        st.stop()

    # Polished multi-step progress state
    with st.status("🚀 Review in Progress...", expanded=True) as status_box:
        try:
            # Step 1: Static Analysis
            st.write("🔍 **Phase 1:** Running static analysis (Pylint, Flake8, Bandit, Radon)...")
            static_results = run_static_analysis(code_to_review)

            # Step 2: LLM Review
            st.write("🧠 **Phase 2:** Consulting Groq LLM for deep logic, security, and edge-case analysis...")
            llm_results = run_llm_review(code_to_review, static_results, api_key=active_api_key)

            # Step 3: Merge & Deduplicate
            st.write("⚡ **Phase 3:** Merging results and eliminating duplicate findings...")
            report = merge_reviews(static_results, llm_results)

            status_box.update(label="✅ Analysis Complete!", state="complete", expanded=False)

        except Exception as err:
            status_box.update(label="❌ Review Failed", state="error", expanded=True)
            st.error(f"An error occurred during the review pipeline: {err}")
            st.stop()

    # Display read-only source preview
    with st.expander("📄 View Reviewed Source Code", expanded=False):
        st.code(code_to_review, language="python", line_numbers=True)

    # -------------------------------------------------------------------------
    # 4. Results Display: Styled Metric Cards
    # -------------------------------------------------------------------------
    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    # Calculate dynamic colors based on values
    qs = report.get("quality_score", 0)
    if qs > 7:
        qs_color = "#10B981"  # Emerald green
        qs_hint = "Solid Code Health"
    elif qs >= 4:
        qs_color = "#F59E0B"  # Amber / orange
        qs_hint = "Needs Moderate Refactoring"
    else:
        qs_color = "#EF4444"  # Red
        qs_hint = "Critical Flaws Detected"

    comp = report.get("complexity_score", 1.0)
    if comp <= 5.0:
        comp_color = "#10B981"
        comp_hint = "Low / Highly Maintainable"
    elif comp <= 10.0:
        comp_color = "#F59E0B"
        comp_hint = "Moderate Complexity"
    else:
        comp_color = "#EF4444"
        comp_hint = "High Branching Complexity"

    tot = report.get("total_issues", 0)
    tot_color = "#10B981" if tot == 0 else ("#F59E0B" if tot <= 5 else "#EF4444")
    tot_hint = "Clean Build" if tot == 0 else f"{tot} items to address"

    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Quality Score</div>
                <div class="metric-value" style="color: {qs_color};">{qs}<span class="metric-sub"> / 10</span></div>
                <div class="metric-hint" style="color: {qs_color};">{qs_hint}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Complexity Score</div>
                <div class="metric-value" style="color: {comp_color};">{comp}</div>
                <div class="metric-hint" style="color: {comp_color};">{comp_hint}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Total Issues</div>
                <div class="metric-value" style="color: {tot_color};">{tot}</div>
                <div class="metric-hint" style="color: {tot_color};">{tot_hint}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

    # Executive Summary Section
    st.subheader("📋 Executive Summary")
    st.info(report["summary"])

    # Issue List Section
    st.subheader(f"⚠️ Findings ({report['total_issues']})")

    if not report["issues"]:
        st.balloons()
        st.success("🎉 No issues identified! Code is clean, secure, and ready for production.")
    else:
        sev_icons = {
            "high": "🔴",
            "medium": "🟠",
            "low": "⚪",
        }

        for idx, issue in enumerate(report["issues"], 1):
            sev = issue.get("severity", "low").lower()
            cat = issue.get("category", "general").upper()
            line = issue.get("line_number")
            line_str = f"Line {line}" if line is not None else "General"
            source = issue.get("source", "static").lower()
            icon = sev_icons.get(sev, "⚪")

            # Expander header with icon
            title = f"{icon} [{sev.upper()}] {cat} — {line_str}: {issue['message'][:80]}..."

            with st.expander(title, expanded=(sev == "high")):
                # Badge pill elements row
                st.markdown(
                    f"""
                    <div style="margin-bottom: 10px;">
                        <span class="badge badge-{sev}">{sev}</span>
                        <span class="badge badge-cat">{cat}</span>
                        <span class="badge badge-line">{line_str}</span>
                        <span class="badge badge-source-{source}">Origin: {source}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Color-accented card body
                st.markdown(
                    f"""
                    <div class="issue-card issue-card-{sev}">
                        <div style="font-size: 0.95rem; color: #F8FAFC; margin-bottom: 6px;">
                            <strong>Problem:</strong> {issue['message']}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if issue.get("suggestion"):
                    st.markdown(f"💡 **Actionable Suggestion:** {issue['suggestion']}")
