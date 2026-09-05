# 🔍 AI Code Reviewer

An automated hybrid code review platform combining deterministic static analyzers with Groq-powered LLM reasoning.

> **Live Demo:** https://ai-code-reviewer-lhm4anyq8hvf2cg4rzwsqs.streamlit.app/
> **Screenshot:** [add after deploying]

---

## 🚀 How It Works

Most automated review tools fall into one of two extremes:
- **Linters**: Fast and deterministic, but blind to architecture, business logic, and semantic bugs.
- **LLMs**: Context-aware and intelligent, but slow, token-expensive, and prone to wasting time on basic PEP8 formatting or hallucinating line numbers.

**AI Code Reviewer** bridges both worlds in a 3-stage hybrid pipeline:

```text
Code Input -> Static Analysis (pylint/flake8/bandit/radon) -> LLM Review (Groq/Llama 3.3) -> Merge & Deduplicate -> Report
```

1. **Static Analysis Layer (`static_analyzer.py`)**:
   Runs **Pylint**, **Flake8**, **Bandit**, and **Radon** simultaneously in a sandboxed temporary environment. It extracts style violations, PEP8 issues, known security vulnerabilities, and calculates a baseline cyclomatic complexity score.
2. **LLM Review Layer (`llm_reviewer.py`)**:
   Passes the source code along with the verified static findings to Groq (`groq/compound` / Llama models). Instructed to skip basic formatting rules already caught, the LLM focuses its reasoning power on hidden logic bugs, unhandled edge cases, misleading naming, and architectural flaws.
3. **Merge & Deduplicate Layer (`merger.py`)**:
   Normalizes all findings into a unified schema. If a static tool and the LLM flag the same problem on the same line (such as a hardcoded secret or a bare `except:`), the system collapses them into a single issue tagged `[BOTH]`, elevates it to the highest severity, and prioritizes findings from **HIGH** to **LOW**.

---

## ✨ Features

- **📝 Paste Code Mode**: Paste raw Python snippets directly into the web interface for instant review.
- **🔗 GitHub File Review**: Enter any public GitHub file URL (e.g., `https://github.com/user/repo/blob/main/app.py`) to fetch and review code directly via GitHub's raw CDN.
- **🛡️ Multi-Engine Static Analysis**:
  - **Pylint**: Syntax, coding standards, and common anti-patterns.
  - **Flake8**: Strict PEP8 style and unused variable/import checks.
  - **Bandit**: Security vulnerabilities and credential leak detection.
  - **Radon**: Cyclomatic complexity scoring.
- **🧠 Semantic AI Reasoning**: Context-aware recommendations and concrete code fix suggestions.
- **🎯 Intelligent De-duplication**: Prevents redundant noise by merging overlapping linter and AI warnings.
- **📊 Interactive Metrics**: High-level Quality Score (1–10), Complexity Score, total issue counts, and color-coded expandable problem cards.

---

## 🛠️ Tech Stack

- **UI & Dashboard**: [Streamlit](https://streamlit.io/)
- **LLM Acceleration**: [Groq Python SDK](https://console.groq.com/) (`groq/compound`, Llama models)
- **Static Analysis Suite**:
  - [Pylint](https://pylint.org/)
  - [Flake8](https://flake8.pycqa.org/)
  - [Bandit](https://bandit.readthedocs.io/)
  - [Radon](https://radon.readthedocs.io/)
- **HTTP / Fetching**: [Requests](https://requests.readthedocs.io/)
- **Environment Management**: [python-dotenv](https://github.com/theskumar/python-dotenv)

---

## 💻 Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/ai-code-reviewer.git
cd ai-code-reviewer
```

### 2. Install Dependencies
Make sure you have Python 3.10 or higher installed:
```bash
pip install -r requirements.txt
```

### 3. Configure Your Groq API Key
1. Obtain a free Groq API key from the [Groq Console](https://console.groq.com/keys).
2. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
3. Open `.env` and insert your key:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   ```
   *(Alternatively, set the environment variable in your terminal: `export GROQ_API_KEY="your_groq_api_key_here"` on macOS/Linux or `$env:GROQ_API_KEY="your_groq_api_key_here"` on PowerShell).*

### 4. Run the Streamlit Application
```bash
streamlit run app.py
```
Open your browser and navigate to `http://localhost:8501`.

---

## ☁️ Deployment (Streamlit Community Cloud)

When deploying to [Streamlit Community Cloud](https://share.streamlit.io/):
1. Push your repository to GitHub (ensure `.env` is ignored by `.gitignore`).
2. Connect your GitHub repository in the Streamlit Cloud dashboard.
3. In **Advanced Settings** &rarr; **Secrets**, add:
   ```toml
   GROQ_API_KEY = "your_groq_api_key_here"
   ```
4. Click **Deploy**. The app will automatically read the secret key and launch!
