"""Merge layer for AI Code Reviewer.

Normalizes issues from static analyzers (Pylint, Flake8, Bandit) and the LLM review,
deduplicates overlapping findings, and produces a unified code review report.
"""

import os
import re
from typing import Any, Dict, List, Optional, Set

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Concept clusters used to identify overlapping issues
CONCEPT_CLUSTERS = {
    "bare_except": {"except", "bare", "bare-except", "swallow", "suppress", "e722", "w0702", "b110"},
    "hardcoded_secret": {"password", "secret", "token", "credential", "hardcoded", "b105", "api_key"},
    "unused_import": {"unused", "import", "imported", "f401", "w0611"},
    "unused_variable": {"unused", "variable", "f841", "w0612"},
    "docstring": {"docstring", "documentation", "c0114", "c0115", "c0116"},
}

STOP_WORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "is", "are", "was", "were", "it", "this", "that", "be", "as", "from",
}


def _normalize_severity(sev: Any) -> str:
    """Ensure severity is one of 'low', 'medium', or 'high'."""
    val = str(sev).lower().strip() if sev else "low"
    return val if val in SEVERITY_ORDER else "low"


def _highest_severity(sev1: str, sev2: str) -> str:
    """Return the more critical of two severity levels."""
    r1 = SEVERITY_ORDER.get(_normalize_severity(sev1), 2)
    r2 = SEVERITY_ORDER.get(_normalize_severity(sev2), 2)
    return sev1 if r1 <= r2 else sev2


def _derive_static_suggestion(msg: str) -> Optional[str]:
    """Derive an actionable suggestion for common static analysis messages."""
    msg_lower = msg.lower()
    if "unused import" in msg_lower or "imported but unused" in msg_lower:
        return "Remove the unused import to keep the module namespace clean."
    if "unused variable" in msg_lower or "assigned to but never used" in msg_lower:
        return "Remove the unused variable or use it in the calculation."
    if "bare 'except'" in msg_lower or "bare-except" in msg_lower or "try, except, pass" in msg_lower:
        return "Specify explicit exception types (e.g. 'except ValueError:') instead of catching all exceptions."
    if "hardcoded password" in msg_lower or "hardcoded" in msg_lower or "b105" in msg_lower:
        return "Move sensitive credentials to environment variables or a secure key vault."
    if "missing" in msg_lower and "docstring" in msg_lower:
        return "Add a descriptive docstring explaining purpose, parameters, and return types."
    if "blank lines" in msg_lower:
        return "Follow PEP8 spacing: separate top-level functions with two blank lines."
    return None


def _extract_tokens(text: str) -> Set[str]:
    """Tokenize text into lowercase alphanumeric words, filtering out stop words."""
    words = re.findall(r"[A-Za-z0-9_-]+", text.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 1}


def _get_matched_concepts(tokens: Set[str]) -> Set[str]:
    """Identify which predefined concept clusters match the given token set."""
    matched = set()
    for concept, keywords in CONCEPT_CLUSTERS.items():
        if tokens & keywords:
            matched.add(concept)
    return matched


def _are_same_underlying_problem(issue_a: Dict[str, Any], issue_b: Dict[str, Any]) -> bool:
    """Determine if two issues on the same line address the same root problem."""
    line_a = issue_a.get("line_number")
    line_b = issue_b.get("line_number")
    
    # Must be on the exact same line
    if line_a is None or line_b is None or line_a != line_b:
        return False

    tokens_a = _extract_tokens(issue_a.get("message", ""))
    tokens_b = _extract_tokens(issue_b.get("message", ""))

    # 1. Concept cluster overlap (e.g. both touch 'bare_except' or 'hardcoded_secret')
    concepts_a = _get_matched_concepts(tokens_a)
    concepts_b = _get_matched_concepts(tokens_b)
    if concepts_a and concepts_b and (concepts_a & concepts_b):
        return True

    # 2. Significant word token overlap
    intersection = tokens_a & tokens_b
    if len(intersection) >= 2:
        return True

    return False


def _normalize_static_issue(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw static analysis issue to the common schema."""
    tool = str(item.get("tool", "static")).lower()
    raw_msg = item.get("message", "")
    
    # Map static tools: bandit -> security, pylint/flake8 -> style
    category = "security" if tool == "bandit" else "style"
    severity = _normalize_severity(item.get("severity", "low"))
    suggestion = _derive_static_suggestion(raw_msg)

    return {
        "line_number": item.get("line_number"),
        "severity": severity,
        "category": category,
        "source": "static",
        "message": f"[{tool.upper()}] {raw_msg}",
        "suggestion": suggestion,
        "_raw_tool": tool,
        "_raw_message": raw_msg,
    }


def _normalize_llm_issue(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw LLM review issue to the common schema."""
    valid_categories = {"bug", "security", "style", "performance", "design"}
    raw_cat = str(item.get("category", "design")).lower()
    category = raw_cat if raw_cat in valid_categories else "design"
    severity = _normalize_severity(item.get("severity", "medium"))
    
    line = item.get("line_number")
    if line is not None:
        try:
            line = int(line)
        except (ValueError, TypeError):
            line = None

    return {
        "line_number": line,
        "severity": severity,
        "category": category,
        "source": "llm",
        "message": str(item.get("message", "")).strip(),
        "suggestion": str(item.get("suggestion", "")).strip() or None,
    }


def merge_reviews(static_results: Dict[str, Any], llm_results: Dict[str, Any]) -> Dict[str, Any]:
    """Merge and deduplicate static analysis issues with LLM review issues.
    
    Args:
        static_results: Dict from run_static_analysis containing 'issues' and 'complexity_score'.
        llm_results: Dict from run_llm_review containing 'summary', 'quality_score', 'issues'.
        
    Returns:
        Consolidated report dictionary adhering to the specified schema.
    """
    raw_static = static_results.get("issues", [])
    raw_llm = llm_results.get("issues", [])

    norm_static = [_normalize_static_issue(i) for i in raw_static]
    norm_llm = [_normalize_llm_issue(i) for i in raw_llm]

    merged_issues: List[Dict[str, Any]] = []
    used_static_indices: Set[int] = set()

    # Step 1: Match LLM issues against static issues on the same line & problem
    for llm_issue in norm_llm:
        matching_static_tools: List[str] = []
        highest_sev = llm_issue["severity"]

        for idx, static_issue in enumerate(norm_static):
            if idx in used_static_indices:
                continue

            # Compare underlying problem between static issue and LLM issue
            comp_static = {"line_number": static_issue["line_number"], "message": static_issue["_raw_message"]}
            comp_llm = {"line_number": llm_issue["line_number"], "message": llm_issue["message"]}
            
            if _are_same_underlying_problem(comp_static, comp_llm):
                used_static_indices.add(idx)
                matching_static_tools.append(static_issue["_raw_tool"].upper())
                highest_sev = _highest_severity(highest_sev, static_issue["severity"])

        if matching_static_tools:
            tools_str = ", ".join(sorted(set(matching_static_tools)))
            merged_issues.append({
                "line_number": llm_issue["line_number"],
                "severity": highest_sev,
                "category": llm_issue["category"],
                "source": "both",
                "message": f"{llm_issue['message']} (Confirmed by static analysis: {tools_str})",
                "suggestion": llm_issue["suggestion"],
            })
        else:
            merged_issues.append({
                "line_number": llm_issue["line_number"],
                "severity": llm_issue["severity"],
                "category": llm_issue["category"],
                "source": "llm",
                "message": llm_issue["message"],
                "suggestion": llm_issue["suggestion"],
            })

    # Step 2: Consolidate remaining static issues (merging multi-tool static duplicates on same line)
    remaining_static: List[Dict[str, Any]] = []
    for idx, static_issue in enumerate(norm_static):
        if idx in used_static_indices:
            continue

        # Check if this static issue duplicates an already added remaining static issue
        found_static_dup = False
        for existing in remaining_static:
            comp_a = {"line_number": existing["line_number"], "message": existing["_raw_message"]}
            comp_b = {"line_number": static_issue["line_number"], "message": static_issue["_raw_message"]}
            if _are_same_underlying_problem(comp_a, comp_b):
                found_static_dup = True
                existing["severity"] = _highest_severity(existing["severity"], static_issue["severity"])
                # Append tool name if not present
                current_tool = static_issue["_raw_tool"].upper()
                if current_tool not in existing["message"]:
                    existing["message"] += f", [{current_tool}]"
                break

        if not found_static_dup:
            clean_item = {
                "line_number": static_issue["line_number"],
                "severity": static_issue["severity"],
                "category": static_issue["category"],
                "source": "static",
                "message": static_issue["message"],
                "suggestion": static_issue["suggestion"],
                "_raw_message": static_issue["_raw_message"],
            }
            remaining_static.append(clean_item)

    # Clean internal helper keys before adding
    for item in remaining_static:
        item.pop("_raw_message", None)
        merged_issues.append(item)

    # Step 3: Sort by severity (high -> medium -> low) then by line number
    def _sort_key(issue: Dict[str, Any]) -> tuple:
        sev_rank = SEVERITY_ORDER.get(issue.get("severity", "low"), 2)
        line = issue.get("line_number")
        # Numbered lines appear in order, general/None lines appear at the end
        line_rank = (0, line) if line is not None else (1, 0)
        return (sev_rank, line_rank)

    merged_issues.sort(key=_sort_key)

    return {
        "summary": llm_results.get("summary", ""),
        "quality_score": llm_results.get("quality_score", 0),
        "complexity_score": static_results.get("complexity_score", 1.0),
        "total_issues": len(merged_issues),
        "issues": merged_issues,
    }


if __name__ == "__main__":
    import json
    from static_analyzer import run_static_analysis
    from llm_reviewer import run_llm_review

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

    print("=" * 70)
    print("STEP 1: Running Static Analysis...")
    static_results = run_static_analysis(sample_code)
    print(f"-> Captured {len(static_results['issues'])} static issues, CC: {static_results['complexity_score']}")

    print("\nSTEP 2: Running LLM Review via Groq...")
    llm_results = run_llm_review(sample_code, static_results)
    print(f"-> LLM Review complete. Quality Score: {llm_results.get('quality_score')}/10")

    print("\nSTEP 3: Merging & Deduplicating Reviews...")
    final_report = merge_reviews(static_results, llm_results)

    print("\n" + "=" * 70)
    print("FINAL CONSOLIDATED CODE REVIEW REPORT")
    print("=" * 70)
    print(f"Summary:           {final_report['summary']}")
    print(f"Quality Score:     {final_report['quality_score']}/10")
    print(f"Complexity Score:  {final_report['complexity_score']}")
    print(f"Total Issues:      {final_report['total_issues']}")
    print("-" * 70)

    for idx, issue in enumerate(final_report["issues"], 1):
        line_str = f"Line {issue['line_number']:2d}" if issue["line_number"] is not None else "General"
        source_tag = f"[{issue['source'].upper()}]"
        sev_tag = f"[{issue['severity'].upper():6s}]"
        cat_tag = f"[{issue['category'].upper():11s}]"
        
        print(f"{idx:2d}. {source_tag:8s} {sev_tag} {cat_tag} {line_str}")
        print(f"    Issue:      {issue['message']}")
        if issue["suggestion"]:
            print(f"    Suggestion: {issue['suggestion']}")
        print()
    print("=" * 70)
