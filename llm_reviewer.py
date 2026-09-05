"""LLM Reviewer layer for AI Code Reviewer.

Sends code and static analysis context to the Groq API
and parses the structured review output.
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from groq import Groq, NotFoundError

# Ensure Windows terminal prints unicode characters without charmap errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Load environment variables from .env if present
load_dotenv()


def extract_json(text: str) -> Dict[str, Any]:
    """Extract and parse a JSON object from LLM response text.
    
    Handles markdown code fences (```json ... ```) and stray commentary
    before or after the JSON payload.
    """
    cleaned_text = text.strip()
    
    # 1. Check for markdown code fences: ```json ... ``` or ``` ... ```
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    fence_match = fence_pattern.search(cleaned_text)
    if fence_match:
        content_inside_fence = fence_match.group(1).strip()
        try:
            return json.loads(content_inside_fence)
        except json.JSONDecodeError:
            pass

    # 2. Try parsing the raw text directly
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        pass

    # 3. Locate the outermost curly braces { ... }
    start = cleaned_text.find("{")
    end = cleaned_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned_text[start : end + 1].strip()
        return json.loads(candidate)

    raise ValueError(f"Could not extract a valid JSON object from model response:\n{text[:200]}")


def _build_prompt(code: str, static_issues: List[Dict[str, Any]]) -> str:
    """Construct the user prompt incorporating code and static analysis findings."""
    if static_issues:
        issue_lines = []
        for idx, issue in enumerate(static_issues, 1):
            tool = issue.get("tool", "tool").upper()
            line = issue.get("line_number")
            sev = issue.get("severity", "unknown").upper()
            msg = issue.get("message", "")
            issue_lines.append(f"{idx}. [{tool}] Line {line} | Severity: {sev} | {msg}")
        static_context = "\n".join(issue_lines)
    else:
        static_context = "No issues detected by static analysis."

    return f"""You are an expert senior code reviewer. Analyze the following Python code.

### Python Code:
```python
{code}
```

### Static Analysis Findings (from Pylint, Flake8, Bandit):
{static_context}

### Review Instructions:
1. Provide a comprehensive, high-level code review.
2. CRITICAL: Do NOT simply repeat or re-list the static analysis issues above. Focus primarily on issues that static analysis tools CANNOT catch:
   - Logic bugs, calculation errors, or incorrect control flow
   - Poor naming conventions or misleading variable/function names
   - Architectural or structural flaws
   - Missing edge case handling (e.g. empty inputs, None values, division by zero)
   - Dangerous assumptions or unhandled exceptions
   - You may only mention a static analysis issue if you are confirming and expanding upon why it is especially severe or hazardous in this specific context.
3. Respond ONLY with a valid JSON object. Do not include markdown code fences (```json), conversational pleasantries, or prose outside the JSON object.

### Required JSON Schema:
{{
  "summary": "2-3 sentence overall assessment",
  "quality_score": <int 1-10>,
  "issues": [
    {{
      "line_number": <int or null>,
      "severity": "low" | "medium" | "high",
      "category": "bug" | "security" | "style" | "performance" | "design",
      "message": "what's wrong",
      "suggestion": "how to fix it"
    }}
  ]
}}
"""


def _invoke_completion(client: Groq, model: str, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
    """Invoke chat completion with fallback for unavailable models."""
    fallback_models = ["groq/compound", "groq/compound-mini", "openai/gpt-oss-120b"]
    models_to_try = [model] + [m for m in fallback_models if m != model]
    
    last_error = None
    for target_model in models_to_try:
        try:
            response = client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
            )
            if target_model != model:
                print(f"[Notice] Model '{model}' not accessible. Automatically using available model '{target_model}'.")
            return response.choices[0].message.content or ""
        except NotFoundError as err:
            last_error = err
            continue
        except Exception as err:
            # If rate limit or other error, try next fallback
            last_error = err
            continue

    if last_error:
        raise last_error
    raise RuntimeError("No Groq model could be reached.")


def get_groq_api_key(provided_key: Optional[str] = None) -> Optional[str]:
    """Resolve the Groq API key from provided argument, st.secrets, or environment variables.
    
    Checks in this order:
    1. Direct argument (provided_key)
    2. Streamlit Cloud Secrets (st.secrets["GROQ_API_KEY"])
    3. Environment variable (os.getenv("GROQ_API_KEY"))
    """
    if provided_key and str(provided_key).strip():
        return str(provided_key).strip()

    # 1. Try Streamlit Cloud secrets (used when deployed on Streamlit Community Cloud)
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets:
            secret_val = str(st.secrets["GROQ_API_KEY"]).strip()
            if secret_val:
                return secret_val
    except Exception:
        pass

    # 2. Try environment variable / local .env
    env_val = os.getenv("GROQ_API_KEY")
    if env_val and env_val.strip():
        return env_val.strip()

    return None


def run_llm_review(
    code: str,
    static_results: Dict[str, Any],
    api_key: Optional[str] = None,
    model: str = "groq/compound",
) -> Dict[str, Any]:
    """Review Python code using the Groq LLM API, augmented with static analysis context.
    
    Args:
        code: The Python source code to review.
        static_results: The dictionary returned by run_static_analysis() containing 'issues'.
        api_key: Optional Groq API key. If omitted, reads from st.secrets or GROQ_API_KEY.
        model: Groq model identifier (defaults to 'groq/compound', with automatic fallback).
        
    Returns:
        A dictionary conforming to the required review schema:
        - "summary": str
        - "quality_score": int (1-10)
        - "issues": list of issue dicts
    """
    key = get_groq_api_key(api_key)
    if not key:
        raise ValueError(
            "GROQ_API_KEY is not set. "
            "Please set GROQ_API_KEY in Streamlit Secrets, your environment, or in a .env file."
        )

    # Support model override via environment variable if set
    selected_model = os.getenv("GROQ_MODEL", model)

    client = Groq(api_key=key)
    static_issues = static_results.get("issues", [])
    user_prompt = _build_prompt(code, static_issues)
    
    system_prompt = (
        "You are an expert Python code reviewer. You always return strictly valid JSON matching "
        "the requested schema without any markdown formatting, preamble, or commentary."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # First attempt to call the LLM
    raw_response = _invoke_completion(client, selected_model, messages, temperature=0.2)

    try:
        return extract_json(raw_response)
    except Exception as parse_err:
        # Retry once with a stricter reminder prompt
        print(f"[Warning] Initial JSON parse failed ({parse_err}). Retrying with stricter instructions...")
        retry_messages = messages + [
            {"role": "assistant", "content": raw_response},
            {
                "role": "user",
                "content": (
                    "CRITICAL ERROR: Your previous response could not be parsed as valid JSON. "
                    "Return ONLY a single, valid raw JSON object matching the schema. "
                    "Do NOT use markdown code blocks (no ```json or ```). "
                    "Do NOT include any introduction, explanations, or trailing commentary."
                ),
            },
        ]
        
        retry_content = _invoke_completion(client, selected_model, retry_messages, temperature=0.0)
        return extract_json(retry_content)


if __name__ == "__main__":
    from static_analyzer import run_static_analysis

    sample_code = '''import os
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

    print("Step 1: Running static analysis...")
    static_results = run_static_analysis(sample_code)
    print(f"Static analysis found {len(static_results['issues'])} issues. Complexity score: {static_results['complexity_score']}")

    print("\nStep 2: Running LLM review via Groq...")
    try:
        llm_results = run_llm_review(sample_code, static_results)
        
        print("\n" + "=" * 60)
        print("LLM CODE REVIEW RESULT")
        print("=" * 60)
        print(f"Summary: {llm_results.get('summary')}")
        print(f"Quality Score: {llm_results.get('quality_score')}/10")
        print("-" * 60)
        print(f"LLM-Identified Issues ({len(llm_results.get('issues', []))} found):")
        
        for idx, issue in enumerate(llm_results.get("issues", []), 1):
            line_str = f"Line {issue['line_number']}" if issue.get("line_number") is not None else "General"
            print(
                f"\n{idx}. [{issue.get('category', 'general').upper()}] {line_str} | "
                f"Severity: {issue.get('severity', 'low').upper()}"
            )
            print(f"   Problem:    {issue.get('message')}")
            print(f"   Suggestion: {issue.get('suggestion')}")
        print("=" * 60)

    except ValueError as e:
        print(f"\n[Configuration Notice]: {e}")
        print("To run the LLM review, please set your Groq API key:")
        print("  Windows PowerShell: $env:GROQ_API_KEY=\"your_key_here\"")
        print("  Windows CMD:        set GROQ_API_KEY=your_key_here")
        print("  Or add GROQ_API_KEY=your_key_here to a .env file in the workspace.")
