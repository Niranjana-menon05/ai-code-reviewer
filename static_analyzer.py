"""Static analysis layer for AI Code Reviewer.

Executes pylint, flake8, bandit, and radon on Python source code
and normalizes results into a unified structure.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List


def _map_pylint_severity(msg_type: str) -> str:
    """Map pylint message type to low/medium/high severity."""
    msg_type = (msg_type or "").lower()
    mapping = {
        "fatal": "high",
        "error": "high",
        "warning": "medium",
        "refactor": "low",
        "convention": "low",
        "info": "low",
    }
    return mapping.get(msg_type, "low")


def _map_flake8_severity(code: str) -> str:
    """Map flake8 error code to low/medium/high severity."""
    code = (code or "").upper()
    # E9xx (syntax/IO errors), F82x/F83x (undefined names)
    if code.startswith("E9") or code.startswith("F82") or code.startswith("F83"):
        return "high"
    # Pyflakes logic warnings, F841 unused variables, E722 bare except
    if code.startswith("F") or code.startswith("E7"):
        return "medium"
    # General PEP8 styling/whitespace issues (E1xx, E2xx, E3xx, E5xx, Wxxx)
    return "low"


def _map_bandit_severity(severity: str) -> str:
    """Map bandit severity to low/medium/high severity."""
    severity = (severity or "").lower()
    if severity in ("low", "medium", "high"):
        return severity
    return "low"


def _run_pylint(filepath: str) -> List[Dict[str, Any]]:
    """Run pylint on the target file and return parsed issues."""
    cmd = [sys.executable, "-m", "pylint", filepath, "--output-format=json"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    
    issues: List[Dict[str, Any]] = []
    output = res.stdout.strip()
    if not output:
        return issues
        
    try:
        data = json.loads(output)
        if isinstance(data, list):
            for item in data:
                line_no = item.get("line")
                symbol = item.get("symbol", "")
                raw_msg = item.get("message", "")
                msg = f"[{symbol}] {raw_msg}" if symbol else raw_msg
                severity = _map_pylint_severity(item.get("type", ""))
                
                issues.append({
                    "tool": "pylint",
                    "line_number": int(line_no) if line_no is not None else 1,
                    "severity": severity,
                    "message": msg,
                })
    except json.JSONDecodeError:
        pass
        
    return issues


def _run_flake8(filepath: str) -> List[Dict[str, Any]]:
    """Run flake8 on the target file and return parsed issues."""
    cmd = [sys.executable, "-m", "flake8", filepath]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    
    issues: List[Dict[str, Any]] = []
    output = res.stdout.strip()
    if not output:
        return issues
        
    # Flake8 output format: <filepath>:<line>:<col>: <code> <message>
    pattern = re.compile(r":(\d+):(?:\d+):\s*([A-Za-z0-9]+)\s*(.*)$")
    
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        match = pattern.search(line)
        if match:
            line_no = int(match.group(1))
            code = match.group(2)
            msg_text = match.group(3).strip()
            severity = _map_flake8_severity(code)
            
            issues.append({
                "tool": "flake8",
                "line_number": line_no,
                "severity": severity,
                "message": f"{code} {msg_text}",
            })
            
    return issues


def _run_bandit(filepath: str) -> List[Dict[str, Any]]:
    """Run bandit on the target file and return parsed security issues."""
    cmd = [sys.executable, "-m", "bandit", "-f", "json", "-q", filepath]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    
    issues: List[Dict[str, Any]] = []
    output = res.stdout.strip()
    if not output:
        return issues
        
    try:
        data = json.loads(output)
        results = data.get("results", [])
        for item in results:
            line_no = item.get("line_number")
            test_id = item.get("test_id", "")
            raw_text = item.get("issue_text", "")
            msg = f"[{test_id}] {raw_text}" if test_id else raw_text
            severity = _map_bandit_severity(item.get("issue_severity", "low"))
            
            issues.append({
                "tool": "bandit",
                "line_number": int(line_no) if line_no is not None else 1,
                "severity": severity,
                "message": msg,
            })
    except json.JSONDecodeError:
        pass
        
    return issues


def _run_radon(filepath: str) -> float:
    """Run radon cyclomatic complexity analysis and return the average complexity score."""
    cmd = [sys.executable, "-m", "radon", "cc", filepath, "-j", "-s"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    
    output = res.stdout.strip()
    if not output:
        return 1.0
        
    try:
        data = json.loads(output)
        complexities: List[int] = []
        
        # Format is {filepath: [block1, block2, ...]} or {filepath: {"error": ...}}
        for _, blocks in data.items():
            if isinstance(blocks, list):
                for block in blocks:
                    if isinstance(block, dict) and "complexity" in block:
                        complexities.append(block["complexity"])
                        for closure in block.get("closures", []):
                            if isinstance(closure, dict) and "complexity" in closure:
                                complexities.append(closure["complexity"])
                                
        if complexities:
            return round(sum(complexities) / len(complexities), 2)
    except json.JSONDecodeError:
        pass
        
    # Baseline complexity of linear/flat code with no analyzed blocks
    return 1.0


def run_static_analysis(code: str, filename: str = "temp.py") -> Dict[str, Any]:
    """Analyze Python code using pylint, flake8, bandit, and radon.
    
    Args:
        code: Python source code as a string.
        filename: Optional filename to use in the temporary directory.
        
    Returns:
        A dictionary containing:
        - "issues": List of dictionaries with keys "tool", "line_number", "severity", "message"
        - "complexity_score": Average cyclomatic complexity score (float)
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        filepath = os.path.join(temp_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
            
        pylint_issues = _run_pylint(filepath)
        flake8_issues = _run_flake8(filepath)
        bandit_issues = _run_bandit(filepath)
        complexity_score = _run_radon(filepath)
        
    combined_issues = pylint_issues + flake8_issues + bandit_issues
    # Sort issues primarily by line number and secondarily by tool name
    combined_issues.sort(key=lambda item: (item.get("line_number", 0), item.get("tool", "")))
    
    return {
        "issues": combined_issues,
        "complexity_score": complexity_score,
    }


if __name__ == "__main__":
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

    print("Running static analysis on sample code...")
    result = run_static_analysis(sample_code)
    
    print("\n" + "=" * 60)
    print(f"STATIC ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Cyclomatic Complexity Score: {result['complexity_score']}")
    print(f"Total Issues Detected: {len(result['issues'])}")
    print("-" * 60)
    
    for idx, issue in enumerate(result["issues"], 1):
        print(
            f"{idx:2d}. [{issue['tool'].upper()}] "
            f"Line {issue['line_number']:2d} | "
            f"Severity: {issue['severity'].upper():6s} | "
            f"{issue['message']}"
        )
    print("=" * 60)
