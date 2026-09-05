"""GitHub file fetcher for AI Code Reviewer.

Converts GitHub blob URLs into raw.githubusercontent.com URLs and fetches
file contents using the requests library.
"""

import re
import warnings
from urllib.parse import urlparse
import requests


def convert_github_url_to_raw(url: str) -> str:
    """Convert a GitHub web URL to a raw.githubusercontent.com URL.
    
    Examples:
        https://github.com/psf/requests/blob/main/src/requests/__version__.py
        -> https://raw.githubusercontent.com/psf/requests/main/src/requests/__version__.py
    """
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("URL cannot be empty.")

    parsed = urlparse(clean_url)
    hostname = (parsed.hostname or "").lower()

    # Already a raw URL
    if hostname == "raw.githubusercontent.com":
        return clean_url

    # Check for github.com blob/raw URLs
    if hostname in ("github.com", "www.github.com"):
        pattern = r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?:blob|raw)/(?P<rest>.+)$"
        match = re.match(pattern, parsed.path)
        if match:
            owner = match.group("owner")
            repo = match.group("repo")
            rest = match.group("rest")
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}"
        
        # If user provided a repo root or tree folder URL
        if "/tree/" in parsed.path:
            raise ValueError(
                "The provided GitHub URL points to a folder or directory tree, not a file. "
                "Please provide a link to a specific file (e.g., https://github.com/user/repo/blob/main/file.py)."
            )
        raise ValueError(
            "Invalid GitHub file URL format. Expected format: "
            "https://github.com/<owner>/<repo>/blob/<branch>/<path_to_file>"
        )

    raise ValueError(
        f"Unsupported URL domain '{hostname}'. Please provide a valid github.com or raw.githubusercontent.com URL."
    )


def fetch_github_file(url: str, timeout: int = 15) -> str:
    """Fetch raw code from a GitHub file URL.
    
    Args:
        url: GitHub web file URL or raw content URL.
        timeout: Request timeout in seconds.
        
    Returns:
        The content of the file as a string.
        
    Raises:
        ValueError: If the URL format is invalid.
        FileNotFoundError: If the file returns HTTP 404.
        RuntimeError: For other HTTP errors or network connection failures.
    """
    raw_url = convert_github_url_to_raw(url)

    # Check file extension and warn if not a Python file
    parsed_path = urlparse(raw_url).path
    if not parsed_path.lower().endswith(".py"):
        warnings.warn(
            f"The file '{parsed_path}' does not have a '.py' extension. "
            "Static analysis tools may produce limited results for non-Python files.",
            UserWarning,
            stacklevel=2,
        )

    try:
        response = requests.get(raw_url, timeout=timeout)
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Connection timed out while fetching from GitHub ({raw_url}).") from None
    except requests.exceptions.RequestException as err:
        raise RuntimeError(f"Network error while connecting to GitHub: {err}") from None

    if response.status_code == 200:
        return response.text
    elif response.status_code == 404:
        raise FileNotFoundError(
            f"File not found on GitHub (HTTP 404). "
            f"Please verify that the repository is public and that the branch and path are correct: {url}"
        )
    elif response.status_code == 403:
        raise RuntimeError(
            "Access to GitHub was forbidden (HTTP 403). "
            "This could be due to GitHub rate limiting or attempting to access a private repository."
        )
    else:
        raise RuntimeError(
            f"GitHub returned HTTP status {response.status_code} when fetching {raw_url}."
        )


if __name__ == "__main__":
    # Test with a real public file from the PSF requests repository
    test_blob_url = "https://github.com/psf/requests/blob/main/src/requests/__version__.py"
    print(f"Testing GitHub fetcher with public URL:\n{test_blob_url}\n")
    
    try:
        content = fetch_github_file(test_blob_url)
        print("-> Fetch successful!")
        print("-> First 200 characters of fetched content:")
        print("-" * 50)
        print(content[:200])
        print("-" * 50)
    except Exception as e:
        print(f"Fetch failed: {e}")
