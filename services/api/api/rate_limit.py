"""
Rate limiting helpers for HireIQ API.

Three layers:
  1. Per-user daily analysis cap   — prevents one user draining all Groq tokens
  2. Global daily token budget     — hard stop before Groq TPD limit is hit
  3. Per-user daily coach cap      — coach calls are LLM-heavy; throttle separately
"""
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.config import settings
from api.models import AnalysisResult, CoachLog, JobApplication


# ---------------------------------------------------------------------------
# Layer 1 — per-user daily analysis cap
# ---------------------------------------------------------------------------

def check_user_analysis_limit(user_id: int, db: Session) -> None:
    today = date.today()
    count = (
        db.query(func.count(AnalysisResult.id))
        .join(JobApplication, AnalysisResult.application_id == JobApplication.id)
        .filter(
            JobApplication.user_id == user_id,
            func.date(AnalysisResult.created_at) == today,
        )
        .scalar()
    ) or 0

    if count >= settings.max_analyses_per_user_per_day:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily analysis limit of {settings.max_analyses_per_user_per_day} reached. "
                "Please try again tomorrow."
            ),
        )


# ---------------------------------------------------------------------------
# Layer 2 — global daily Groq token budget
# ---------------------------------------------------------------------------

def check_global_token_budget(db: Session) -> None:
    today = date.today()
    row = (
        db.query(
            func.coalesce(func.sum(AnalysisResult.input_tokens), 0).label("inp"),
            func.coalesce(func.sum(AnalysisResult.output_tokens), 0).label("out"),
        )
        .filter(func.date(AnalysisResult.created_at) == today)
        .one()
    )
    total = row.inp + row.out

    if total >= settings.daily_token_budget:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "The service has reached its daily AI usage limit. "
                "Please try again tomorrow."
            ),
        )


# ---------------------------------------------------------------------------
# Layer 3 — per-user daily coach cap
# ---------------------------------------------------------------------------

def check_user_coach_limit(user_id: int, db: Session) -> None:
    today = date.today()
    count = (
        db.query(func.count(CoachLog.id))
        .filter(
            CoachLog.user_id == user_id,
            func.date(CoachLog.created_at) == today,
        )
        .scalar()
    ) or 0

    if count >= settings.max_coach_messages_per_user_per_day:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily coaching limit of {settings.max_coach_messages_per_user_per_day} questions reached. "
                "Please try again tomorrow."
            ),
        )


def log_coach_call(user_id: int, db: Session) -> None:
    """Record a successful coach call for rate-limit tracking."""
    db.add(CoachLog(user_id=user_id, created_at=datetime.now(timezone.utc)))
    db.commit()