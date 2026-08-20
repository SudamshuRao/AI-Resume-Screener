import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from api.auth import get_current_user
from api.database import get_db
from api.models import AnalysisResult, JobApplication, User
from api.schemas import (
    JobApplicationCreate,
    JobApplicationDetail,
    JobApplicationResponse,
    ResumeUpdate,
    StatusUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["applications"])

# Valid status values for the application lifecycle
VALID_STATUSES = {"pending", "analyzed", "applied", "rejected", "offered"}


def _latest_analysis(application: JobApplication) -> Optional[AnalysisResult]:
    """Return the most recent AnalysisResult for *application*, or None."""
    if not application.analyses:
        return None
    return max(application.analyses, key=lambda a: a.created_at)


def _get_owned_or_404(db: Session, application_id: int, user_id: int) -> JobApplication:
    """Return the application if it exists and belongs to user_id, else raise 404."""
    application = (
        db.query(JobApplication)
        .filter(JobApplication.id == application_id, JobApplication.user_id == user_id)
        .first()
    )
    if not application:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Application with id={application_id} not found.",
        )
    return application


def _enrich_response(application: JobApplication) -> dict:
    """
    Build a dict suitable for JobApplicationResponse, injecting ats_score
    and match_percentage from the latest analysis when available.
    """
    latest = _latest_analysis(application)
    data = {
        "id": application.id,
        "company": application.company,
        "job_title": application.job_title,
        "status": application.status,
        "created_at": application.created_at,
        "ats_score": latest.ats_score if latest else None,
        "match_percentage": latest.match_percentage if latest else None,
    }
    return data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/applications", response_model=list[JobApplicationResponse])
def list_applications(
    status: Optional[str] = Query(default=None, description="Filter by application status"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all job applications with optional status filtering and pagination.

    - **status**: one of pending / analyzed / applied / rejected / offered
    - **limit**: page size (1–100, default 20)
    - **offset**: records to skip for pagination
    """
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}",
        )

    query = db.query(JobApplication).filter(JobApplication.user_id == current_user.id)
    if status:
        query = query.filter(JobApplication.status == status)

    applications = query.order_by(JobApplication.created_at.desc()).offset(offset).limit(limit).all()
    logger.info("Listed %d applications (status=%s, limit=%d, offset=%d)", len(applications), status, limit, offset)

    return [JobApplicationResponse(**_enrich_response(app)) for app in applications]


@router.post("/applications", response_model=JobApplicationResponse, status_code=http_status.HTTP_201_CREATED)
def create_application(
    payload: JobApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new job application.

    The application is stored with status **pending** and no analysis results yet.
    Call `POST /api/v1/analyze` afterwards to trigger the agent pipeline.
    """
    application = JobApplication(**payload.model_dump(), user_id=current_user.id)
    db.add(application)
    try:
        db.commit()
        db.refresh(application)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to create application: %s", exc)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save the application. Please try again.",
        ) from exc

    logger.info("Created application id=%d for company='%s'", application.id, application.company)
    return JobApplicationResponse(**_enrich_response(application))


@router.get("/applications/{application_id}", response_model=JobApplicationDetail)
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve full details of a single job application, including all analysis results.

    Raises **404** if no application with the given id exists.
    """
    application = _get_owned_or_404(db, application_id, current_user.id)

    latest = _latest_analysis(application)
    return JobApplicationDetail(
        **_enrich_response(application),
        job_description=application.job_description,
        resume_text=application.resume_text,
        analyses=application.analyses,
    )


@router.patch("/applications/{application_id}/status", response_model=JobApplicationResponse)
def update_application_status(
    application_id: int,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update the lifecycle status of a job application.

    Valid status values: **pending**, **analyzed**, **applied**, **rejected**, **offered**.
    Raises **404** if the application does not exist and **422** for invalid status values.
    """
    if payload.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{payload.status}'. Must be one of: {sorted(VALID_STATUSES)}",
        )

    application = _get_owned_or_404(db, application_id, current_user.id)

    application.status = payload.status
    try:
        db.commit()
        db.refresh(application)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to update status for application id=%d: %s", application_id, exc)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update the application status. Please try again.",
        ) from exc

    logger.info("Updated application id=%d status to '%s'", application_id, payload.status)
    return JobApplicationResponse(**_enrich_response(application))


@router.patch("/applications/{application_id}/resume", response_model=JobApplicationResponse)
def update_resume_text(
    application_id: int,
    payload: ResumeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the resume text on an existing application (e.g. before re-analyzing)."""
    application = _get_owned_or_404(db, application_id, current_user.id)
    resume_text = payload.resume_text.strip()
    if not resume_text:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="resume_text is required.")
    try:
        application.resume_text = resume_text
        db.commit()
        db.refresh(application)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to update resume for application id=%d: %s", application_id, exc)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update resume.") from exc
    logger.info("Updated resume text for application id=%d (%d chars)", application_id, len(resume_text))
    return JobApplicationResponse(**_enrich_response(application))


@router.delete("/applications/{application_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_application(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Permanently delete a job application and all its associated analysis results.

    Raises **404** if no application with the given id exists.
    Returns **204 No Content** on success.
    """
    application = _get_owned_or_404(db, application_id, current_user.id)

    try:
        db.delete(application)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to delete application id=%d: %s", application_id, exc)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete the application. Please try again.",
        ) from exc

    logger.info("Deleted application id=%d", application_id)