import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.auth import get_current_user
from api.config import settings
from api.database import get_db
from api.models import AnalysisResult, JobApplication, User
from api.rate_limit import check_user_analysis_limit, check_global_token_budget
from fastapi import Query
from api.schemas import AnalyzeRequest, AnalysisResultResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])

# Agent service calls involve LLM round-trips — allow generous timeout
AGENT_TIMEOUT_SECONDS = 600.0


def _to_json_str(value) -> str | None:
    """Serialize *value* to a JSON string for DB storage, or return None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value  # already serialized
    return json.dumps(value)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=AnalysisResultResponse, status_code=status.HTTP_201_CREATED)
async def trigger_analysis(
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger the multi-agent analysis pipeline for a job application.

    1. Fetches the application from the database.
    2. Calls the agent service (`POST {agent_service_url}/analyze`) with the
       application's job description and resume text.
    3. Persists the returned analysis result in the database.
    4. Updates the application status to **analyzed**.

    The agent service call has a **120-second timeout** to accommodate LLM latency.

    Raises:
    - **404** if the application does not exist.
    - **502** if the agent service returns an error or is unreachable.
    - **500** for unexpected database errors.
    """
    # 0. Rate limit checks (before any LLM work) ------------------------------------
    check_user_analysis_limit(current_user.id, db)
    check_global_token_budget(db)

    # 1. Retrieve the application (must belong to the authenticated user) ----------
    application = (
        db.query(JobApplication)
        .filter(
            JobApplication.id == payload.application_id,
            JobApplication.user_id == current_user.id,
        )
        .first()
    )
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with id={payload.application_id} not found.",
        )

    session_id = str(uuid.uuid4())
    logger.info(
        "Starting analysis session=%s for application id=%d (%s @ %s)",
        session_id,
        application.id,
        application.job_title,
        application.company,
    )

    # 2. Call the agent service --------------------------------------------------
    agent_payload = {
        "application_id": application.id,
        "session_id": session_id,
        "company": application.company,
        "job_title": application.job_title,
        "job_description": application.job_description,
        "resume_text": application.resume_text,
        "user_id": current_user.id,
    }

    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.agent_service_url}/analyze",
                json=agent_payload,
            )
            response.raise_for_status()
            agent_data: dict = response.json()
    except httpx.TimeoutException as exc:
        logger.error("Agent service timed out for session=%s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The agent service did not respond in time. Please retry later.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Agent service returned HTTP %d for session=%s: %s",
            exc.response.status_code,
            session_id,
            exc.response.text,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agent service returned an error. Please retry later.",
        ) from exc
    except httpx.RequestError as exc:
        logger.error("Could not reach agent service for session=%s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach the agent service. Please check the service is running.",
        ) from exc

    # 3. Persist the analysis result ---------------------------------------------
    analysis = AnalysisResult(
        application_id=application.id,
        session_id=session_id,
        match_percentage=agent_data.get("match_percentage"),
        gap_analysis=_to_json_str(agent_data.get("gap_analysis")),
        tailored_bullets=_to_json_str(agent_data.get("tailored_bullets")),
        cover_letter=agent_data.get("cover_letter"),
        input_tokens=agent_data.get("input_tokens", 0),
        output_tokens=agent_data.get("output_tokens", 0),
        interview_qa=_to_json_str(agent_data.get("interview_qa")),
        company_research=_to_json_str(agent_data.get("company_research")),
        created_at=datetime.now(timezone.utc),
    )
    db.add(analysis)

    # 4. Update application status -----------------------------------------------
    application.status = "analyzed"

    try:
        db.commit()
        db.refresh(analysis)
        db.refresh(application)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to persist analysis for session=%s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis completed but could not be saved. Please retry.",
        ) from exc

    logger.info(
        "Analysis saved: id=%d session=%s match=%.1f%% tokens=in:%d/out:%d",
        analysis.id,
        session_id,
        analysis.match_percentage or 0.0,
        analysis.input_tokens or 0,
        analysis.output_tokens or 0,
    )

    return AnalysisResultResponse.model_validate(analysis)


@router.post("/analyze/stream")
async def trigger_analysis_stream(
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run the multi-agent pipeline and stream real-time agent-completion events via SSE.

    Progress events: {"agent": "<name>", "status": "completed", "step": N, "total": 8}
    Final event:     {"agent": "pipeline", "status": "saved", "application_id": N}
    Error event:     {"agent": "pipeline", "status": "error", "detail": "..."}
    """
    # Rate limit checks (before any LLM work) --------------------------------------
    check_user_analysis_limit(current_user.id, db)
    check_global_token_budget(db)

    application = (
        db.query(JobApplication)
        .filter(
            JobApplication.id == payload.application_id,
            JobApplication.user_id == current_user.id,
        )
        .first()
    )
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with id={payload.application_id} not found.",
        )

    session_id = str(uuid.uuid4())
    agent_payload = {
        "resume_text": application.resume_text,
        "job_description": application.job_description,
        "user_id": current_user.id,
    }

    async def event_generator():
        try:
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT_SECONDS) as client:
                async with client.stream(
                    "POST",
                    f"{settings.agent_service_url}/analyze/stream",
                    json=agent_payload,
                ) as resp:
                    buffer = ""
                    async for text_chunk in resp.aiter_text():
                        buffer += text_chunk
                        while "\n\n" in buffer:
                            event_block, buffer = buffer.split("\n\n", 1)
                            for line in event_block.split("\n"):
                                if not line.startswith("data: "):
                                    continue
                                data_str = line[6:].strip()
                                try:
                                    event = json.loads(data_str)
                                except Exception:
                                    yield f"data: {data_str}\n\n"
                                    continue

                                if event.get("status") == "done":
                                    result = event.get("result") or {}
                                    if not isinstance(result, dict) or not result:
                                        logger.warning(
                                            "Stream done event has empty/invalid result for session=%s — skipping DB insert",
                                            session_id,
                                        )
                                    else:
                                        analysis = AnalysisResult(
                                            application_id=application.id,
                                            session_id=session_id,
                                            match_percentage=result.get("match_percentage"),
                                            gap_analysis=_to_json_str(result.get("gap_analysis")),
                                            tailored_bullets=_to_json_str(result.get("tailored_bullets")),
                                            cover_letter=result.get("cover_letter"),
                                            input_tokens=result.get("input_tokens", 0),
                                            output_tokens=result.get("output_tokens", 0),
                                            interview_qa=_to_json_str(result.get("interview_qa")),
                                            company_research=_to_json_str(result.get("company_research")),
                                            created_at=datetime.now(timezone.utc),
                                        )
                                        db.add(analysis)
                                        application.status = "analyzed"
                                        try:
                                            db.commit()
                                            db.refresh(analysis)
                                            logger.info(
                                                "Stream analysis saved: id=%d session=%s match=%.1f%%",
                                                analysis.id, session_id, analysis.match_percentage or 0.0,
                                            )
                                        except Exception as db_exc:
                                            db.rollback()
                                            logger.error("Failed to save stream analysis: %s", db_exc)

                                    yield f"data: {json.dumps({'agent': 'pipeline', 'status': 'saved', 'application_id': application.id})}\n\n"
                                else:
                                    yield f"data: {data_str}\n\n"

        except Exception as exc:
            logger.error("Stream proxy error session=%s: %s", session_id, exc)
            yield f"data: {json.dumps({'agent': 'pipeline', 'status': 'error', 'detail': 'Pipeline error. Please retry.'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/applications/{application_id}/analyses", response_model=list[AnalysisResultResponse])
def list_analyses(
    application_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all analysis results for a given job application, ordered newest first.

    Raises **404** if no application with the given id exists.
    """
    application = (
        db.query(JobApplication)
        .filter(JobApplication.id == application_id, JobApplication.user_id == current_user.id)
        .first()
    )
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with id={application_id} not found.",
        )

    analyses = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.application_id == application_id)
        .order_by(AnalysisResult.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    logger.info("Listed %d analyses for application id=%d", len(analyses), application_id)
    return [AnalysisResultResponse.model_validate(a) for a in analyses]