"""Streamlit Web UI for AI Code Reviewer.

Provides an interactive interface to review Python code via direct pasting
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
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 1. Page Title and Subtitle
st.title("🔍 AI Code Reviewer")
st.caption("A hybrid code review system combining deterministic static analyzers with Groq-powered LLM reasoning.")

# 6. Sidebar: "How this works"
with st.sidebar:
    st.header("ℹ️ How This Works")
    st.markdown(
        """
        This reviewer employs a **3-stage hybrid pipeline**:

        1. **Static Analysis Layer**:
           Runs `Pylint`, `Flake8`, `Bandit`, and `Radon` simultaneously on a temporary file to detect syntax errors, PEP8 style issues, known security vulnerabilities, and cyclomatic complexity.
        
        2. **LLM Review Layer**:
           Passes the raw code **and** static findings to Groq (`groq/compound`). The LLM is instructed to skip basic linting rules and focus on deeper logic flaws, architecture, and edge cases.
        
        3. **Merge & Deduplicate Layer**:
           Standardizes both feeds into a common schema, merges overlapping issues on the same line into a unified `[BOTH]` tag, and ranks them by severity.
        """
    )
    
    st.divider()
    st.subheader("⚙️ API Configuration")
    detected_key = get_groq_api_key()
    if detected_key:
        masked_key = detected_key[:6] + "..." + detected_key[-4:] if len(detected_key) > 10 else "***"
        st.success(f"Groq API Key detected: `{masked_key}`")
        custom_key = st.text_input("Override API Key (optional):", type="password", placeholder="gsk_...")
    else:
        st.warning("No `GROQ_API_KEY` found in Streamlit secrets or environment.")
        custom_key = st.text_input("Enter Groq API Key:", type="password", placeholder="gsk_...")

# 2. Input Mode Toggle: Paste Code vs GitHub URL
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

input_mode = st.radio(
    "Choose Input Method:",
    options=["Paste Code", "GitHub URL"],
    horizontal=True,
)

if input_mode == "Paste Code":
    code_input = st.text_area(
        "Paste Python Code to Review:",
        value=DEFAULT_SAMPLE_CODE,
        height=280,
        help="Enter standard Python code here.",
    )
    github_url = ""
else:
    github_url = st.text_input(
        "Enter Public GitHub File URL:",
        value=DEFAULT_GITHUB_URL,
        placeholder="https://github.com/owner/repo/blob/main/path/to/file.py",
        help="Paste a link to any public file on GitHub.",
    )
    code_input = ""

col_btn, _ = st.columns([1, 4])
with col_btn:
    run_btn = st.button("🚀 Run Review", type="primary", use_container_width=True)

# 3, 4 & 5. Pipeline execution and display
if run_btn:
    active_api_key = get_groq_api_key(custom_key)
    if not active_api_key:
        st.error(
            "🔑 **GROQ_API_KEY is not set!**\n\n"
            "To run the LLM review layer, please either:\n"
            "1. Enter your Groq API key in the sidebar under **API Configuration**.\n"
            "2. Add `GROQ_API_KEY = \"gsk_...\"` to your Streamlit Cloud Secrets (if deployed).\n"
            "3. Add `GROQ_API_KEY=gsk_...` to a `.env` file in the project folder.\n"
            "4. Set the environment variable in your terminal: `$env:GROQ_API_KEY='gsk_...'`."
        )
        st.stop()

    code_to_review = ""

    # Fetch from GitHub if selected
    if input_mode == "GitHub URL":
        clean_url = github_url.strip()
        if not clean_url:
            st.warning("⚠️ Please provide a valid GitHub file URL.")
            st.stop()

        with st.spinner("Fetching file from GitHub..."):
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

        # Check for non-Python file warning
        if not clean_url.split("?")[0].lower().endswith(".py"):
            st.warning(
                "⚠️ **Non-Python File Notice:** The selected file does not have a `.py` extension. "
                "Static analysis tools (Pylint, Flake8, Bandit, Radon) will run, but might flag fewer issues."
            )
    else:
        code_to_review = code_input

    if not code_to_review.strip():
        st.warning("⚠️ The provided code is empty. Please provide code to review.")
        st.stop()

    # Run the full review pipeline
    with st.spinner("Running full review pipeline (Static Analysis ➔ Groq LLM Review ➔ Merge)..."):
        try:
            # Step 1: Static Analysis
            static_results = run_static_analysis(code_to_review)
            
            # Step 2: LLM Review
            llm_results = run_llm_review(code_to_review, static_results, api_key=active_api_key)
            
            # Step 3: Merge & Deduplicate
            report = merge_reviews(static_results, llm_results)

        except Exception as err:
            st.error(f"❌ An error occurred during the review pipeline: {err}")
            st.stop()

    st.success("✅ Analysis Complete!")

    # Display fetched / reviewed code (collapsed by default)
    with st.expander("📄 View Reviewed Code", expanded=False):
        st.code(code_to_review, language="python", line_numbers=True)

    # 4. Display Metric Cards Top Section
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric(label="Quality Score", value=f"{report['quality_score']} / 10")
    with m2:
        st.metric(label="Complexity Score", value=f"{report['complexity_score']}")
    with m3:
        st.metric(label="Total Issues", value=f"{report['total_issues']}")

    st.divider()

    # Summary Text Section
    st.subheader("📋 Executive Summary")
    st.info(report["summary"])

    # Issue List Section
    st.subheader(f"⚠️ Issues Identified ({report['total_issues']})")

    if not report["issues"]:
        st.balloons()
        st.success("🎉 No issues identified! Code looks clean and ready for production.")
    else:
        sev_icons = {
            "high": "🔴",
            "medium": "🟠",
            "low": "⚪",
        }
        source_badges = {
            "both": "violet",
            "llm": "blue",
            "static": "green",
        }

        for idx, issue in enumerate(report["issues"], 1):
            sev = issue.get("severity", "low").lower()
            cat = issue.get("category", "general").upper()
            line = issue.get("line_number")
            line_str = f"Line {line}" if line is not None else "General"
            source = issue.get("source", "static").lower()
            icon = sev_icons.get(sev, "⚪")

            # Expander header
            title = f"{icon} [{sev.upper()}] {cat} — {line_str}: {issue['message'][:75]}..."

            with st.expander(title, expanded=(sev == "high")):
                # Color code issue box based on severity
                if sev == "high":
                    st.error(f"**Problem:** {issue['message']}")
                elif sev == "medium":
                    st.warning(f"**Problem:** {issue['message']}")
                else:
                    st.info(f"**Problem:** {issue['message']}")

                if issue.get("suggestion"):
                    st.markdown(f"💡 **Suggestion:** {issue['suggestion']}")

                # Source badge
                badge_color = source_badges.get(source, "gray")
                st.caption(f"Origin: **:{badge_color}[{source.upper()}]**")
