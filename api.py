"""FastAPI Backend for AI Code Reviewer.

Exposes REST endpoints to run static analysis and LLM reviews on raw Python
code or public GitHub files.
"""

from typing import Any, Dict, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from static_analyzer import run_static_analysis
from llm_reviewer import run_llm_review
from merger import merge_reviews
from github_fetcher import fetch_github_file

# Load environment variables from .env
load_dotenv()

app = FastAPI(
    title="AI Code Reviewer API",
    description="Backend API combining static analysis and Groq LLM reasoning to review Python code.",
    version="1.0.0",
)

# 3. Add CORS middleware allowing all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request schema
class ReviewRequest(BaseModel):
    code: Optional[str] = Field(
        default=None,
        description="Raw Python source code to review.",
        example="def add(a, b):\n    return a + b",
    )
    github_url: Optional[str] = Field(
        default=None,
        description="Public GitHub file URL to fetch and review.",
        example="https://github.com/psf/requests/blob/main/src/requests/__version__.py",
    )


# 4. GET /health sanity check endpoint
@app.get("/health", summary="Health check", tags=["System"])
async def health() -> Dict[str, str]:
    """Return health status of the service."""
    return {"status": "ok"}


# 1 & 2. POST /review endpoint
@app.post(
    "/review",
    summary="Run full code review pipeline",
    response_model=Dict[str, Any],
    tags=["Review"],
)
async def review_code(payload: ReviewRequest) -> Dict[str, Any]:
    """Execute the 3-stage code review pipeline (Static Analysis -> LLM Review -> Merge).
    
    Accepts either raw Python code in `code` OR a public GitHub file URL in `github_url`.
    Exactly one of the two must be provided.
    """
    code = (payload.code or "").strip()
    url = (payload.github_url or "").strip()

    # Validate that exactly one of the two options is provided
    if (code and url) or (not code and not url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid request. Exactly one of 'code' or 'github_url' must be provided. "
                f"Received: code={'provided' if code else 'empty'}, github_url={'provided' if url else 'empty'}."
            ),
        )

    # If GitHub URL is provided, fetch code using existing helper
    if url:
        try:
            code_to_review = fetch_github_file(url)
        except FileNotFoundError as fnf_err:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(fnf_err),
            ) from fnf_err
        except ValueError as val_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(val_err),
            ) from val_err
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch file from GitHub: {exc}",
            ) from exc
    else:
        code_to_review = code

    if not code_to_review.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The provided code content is empty.",
        )

    # Run the 3-stage review pipeline
    try:
        # Step 1: Static Analysis (Pylint, Flake8, Bandit, Radon)
        static_results = run_static_analysis(code_to_review)

        # Step 2: Groq LLM Review
        llm_results = run_llm_review(code_to_review, static_results)

        # Step 3: Merge & Deduplicate
        report = merge_reviews(static_results, llm_results)

        return report

    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(val_err),
        ) from val_err
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review pipeline execution failed: {exc}",
        ) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
