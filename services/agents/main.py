import asyncio
import json
import logging
import os
import time
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

# Import config first so env vars are available before LangChain loads
from agents.config import settings                      # noqa: E402

# Propagate LangSmith vars explicitly so LangChain picks them up even when
# the values come from pydantic-settings rather than raw os.environ.
if settings.langchain_tracing_v2.lower() == "true":
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    if settings.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key

from agents.graph import build_graph                    # noqa: E402
from agents.nodes.supervisor import PIPELINE_ORDER      # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
_logger = logging.getLogger(__name__)
_logger.info(
    "LangSmith tracing: %s (project=%s)",
    settings.langchain_tracing_v2,
    settings.langchain_project,
)

app = FastAPI(
    title="HireIQ Agent Service",
    description=(
        "Multi-agent career intelligence pipeline powered by LangGraph + Claude. "
        "Accepts a resume and job description, runs specialized AI agents, and returns "
        "gap analysis, tailored resume bullets, a cover letter, interview Q&A, and an ATS score."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Build the graph once at startup to avoid repeated compilation overhead.
graph = build_graph()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    resume_text: str
    job_description: str
    user_id: int = 1


class AnalyzeResponse(BaseModel):
    session_id: str
    gap_analysis: dict
    tailored_bullets: list
    cover_letter: str
    interview_qa: list
    ats_score: dict
    match_percentage: float
    company_research: dict = {}
    input_tokens: int = 0
    output_tokens: int = 0


class CoachRequest(BaseModel):
    question: str
    resume_text: str
    job_description: str
    gap_analysis: dict = {}
    tailored_bullets: list = []
    cover_letter: str = ""
    interview_qa: list = []
    ats_score: dict = {}


class CoachResponse(BaseModel):
    answer: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "agent-service"}


class CompanyPreviewRequest(BaseModel):
    company: str = ""
    job_description: str


@app.post("/company-preview")
async def company_preview(req: CompanyPreviewRequest):
    """Quick company research from the job description — runs independently of the full pipeline."""
    _logger.info("company_preview: company=%r jd_len=%d", req.company, len(req.job_description))
    from agents.nodes.company_researcher import company_researcher_node
    state = {
        "job_description": req.job_description,
        "jd_parsed": {"company": req.company},
        "resume_text": "", "resume_parsed": None, "gap_analysis": None,
        "tailored_bullets": None, "cover_letter": None, "interview_qa": None,
        "ats_score": None, "company_research": None, "next_agent": "",
        "completed_agents": [], "messages": [], "error": None,
        "user_id": 0, "session_id": "preview",
    }
    result = company_researcher_node(state)
    if result.get("error"):
        _logger.error("company_preview: researcher failed: %s", result["error"][:300])
        raise HTTPException(status_code=500, detail=result["error"])
    research = result.get("company_research") or {}
    _logger.info("company_preview: completed company_name=%r", research.get("company_name"))
    return research


@app.post("/coach", response_model=CoachResponse)
async def coach(req: CoachRequest):
    """Answer a follow-up career coaching question using the full analysis context.

    Accepts a free-form question and all analysis outputs from a completed pipeline
    run. Returns a concise, actionable answer grounded in the candidate's specific
    resume and target job.
    """
    _logger.info(
        "coach: question=%r resume_len=%d jd_len=%d",
        req.question[:120],
        len(req.resume_text),
        len(req.job_description),
    )
    import json as _json
    from agents.tools.gemini import GeminiClient
    from langchain_core.messages import HumanMessage

    llm = GeminiClient(temperature=0.5)

    system_context = (
        "You are an expert career coach helping a job candidate prepare for their application. "
        "You have access to the candidate's resume, the target job description, and a full "
        "AI-generated analysis of how well the candidate matches the role.\n\n"
        f"RESUME:\n{req.resume_text}\n\n"
        f"JOB DESCRIPTION:\n{req.job_description}\n\n"
        f"GAP ANALYSIS:\n{_json.dumps(req.gap_analysis, indent=2)}\n\n"
        f"TAILORED BULLETS:\n{_json.dumps(req.tailored_bullets, indent=2)}\n\n"
        f"COVER LETTER:\n{req.cover_letter}\n\n"
        f"INTERVIEW Q&A:\n{_json.dumps(req.interview_qa, indent=2)}\n\n"
        f"ATS SCORE:\n{_json.dumps(req.ats_score, indent=2)}\n\n"
        "Answer the candidate's question below. Be specific, practical, and concise."
    )

    prompt = f"{system_context}\n\nCANDIDATE QUESTION: {req.question}"

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        answer = response.content.strip()
        _logger.info("coach: answered successfully answer_len=%d", len(answer))
        return CoachResponse(answer=answer)
    except Exception as exc:
        _logger.error("coach: LLM call failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Coach failed: {str(exc)}",
        )


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """Run the full HireIQ multi-agent pipeline and return all outputs.

    The pipeline executes agents in this order:
        resume_parser -> jd_analyst -> gap_analyst -> resume_tailor ->
        cover_letter -> interview_coach -> ats_scorer
    """
    session_id = str(uuid.uuid4())
    _logger.info(
        "analyze: starting session=%s user_id=%s resume_len=%d jd_len=%d",
        session_id,
        req.user_id,
        len(req.resume_text),
        len(req.job_description),
    )
    t_start = time.monotonic()

    initial_state = {
        "resume_text": req.resume_text,
        "job_description": req.job_description,
        "user_id": req.user_id,
        "session_id": session_id,
        "resume_parsed": None,
        "jd_parsed": None,
        "company_research": None,
        "gap_analysis": None,
        "tailored_bullets": None,
        "cover_letter": None,
        "interview_qa": None,
        "ats_score": None,
        "next_agent": "",
        "completed_agents": [],
        "messages": [],
        "error": None,
        "input_tokens": 0,
        "output_tokens": 0,
    }

    try:
        async with asyncio.timeout(660):  # 11-minute hard ceiling
            result = await graph.ainvoke(initial_state)
    except asyncio.TimeoutError:
        _logger.error("analyze: pipeline timed out [session=%s]", session_id)
        raise HTTPException(status_code=504, detail="Analysis timed out. Please retry.")
    except Exception as exc:
        _logger.error("analyze: pipeline exception [session=%s]: %s", session_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Agent pipeline failed. Please retry.")

    elapsed = time.monotonic() - t_start

    # Propagate any agent-level errors as a 500.
    if result.get("error"):
        _logger.error(
            "analyze: agent error [session=%s] after %.1fs: %s",
            session_id,
            elapsed,
            str(result["error"])[:300],
        )
        raise HTTPException(status_code=500, detail="An agent error occurred. Please retry.")

    # Safely extract outputs, falling back to empty structures if an agent
    # did not produce a result (e.g., due to a handled exception).
    gap_analysis = result.get("gap_analysis") or {}
    tailored_bullets = result.get("tailored_bullets") or []
    cover_letter = result.get("cover_letter") or ""
    interview_qa = result.get("interview_qa") or []
    ats_score = result.get("ats_score") or {}
    company_research = result.get("company_research") or {}
    match_percentage = float(gap_analysis.get("match_percentage", 0.0))

    _logger.info(
        "analyze: completed [session=%s] in %.1fs "
        "match=%.1f%% bullets=%d qa=%d ats=%s tokens=in:%d/out:%d",
        session_id,
        elapsed,
        match_percentage,
        len(tailored_bullets),
        len(interview_qa),
        ats_score.get("score"),
        result.get("input_tokens", 0),
        result.get("output_tokens", 0),
    )

    return AnalyzeResponse(
        session_id=session_id,
        gap_analysis=gap_analysis,
        tailored_bullets=tailored_bullets,
        cover_letter=cover_letter,
        interview_qa=interview_qa,
        ats_score=ats_score,
        company_research=company_research,
        match_percentage=match_percentage,
        input_tokens=result.get("input_tokens", 0),
        output_tokens=result.get("output_tokens", 0),
    )


# ---------------------------------------------------------------------------
# SSE streaming endpoint
# ---------------------------------------------------------------------------

# Agent names in pipeline order — single source of truth is supervisor.PIPELINE_ORDER
_PIPELINE_AGENTS = PIPELINE_ORDER


@app.post("/analyze/stream")
async def analyze_stream(req: AnalyzeRequest):
    """Run the full pipeline and stream agent-completion events via SSE.

    Each event has the format:
        data: {"agent": "<name>", "status": "completed", "step": N, "total": 7}

    A final event signals pipeline completion:
        data: {"agent": "pipeline", "status": "done", "result": {...}}

    The client should listen with EventSource or fetch + ReadableStream.
    """
    session_id = str(uuid.uuid4())

    initial_state = {
        "resume_text": req.resume_text,
        "job_description": req.job_description,
        "user_id": req.user_id,
        "session_id": session_id,
        "resume_parsed": None,
        "jd_parsed": None,
        "company_research": None,
        "gap_analysis": None,
        "tailored_bullets": None,
        "cover_letter": None,
        "interview_qa": None,
        "ats_score": None,
        "next_agent": "",
        "completed_agents": [],
        "messages": [],
        "error": None,
    }

    async def _event_generator():
        try:
            final_state: dict = {}
            prev_completed: set = set()

            async with asyncio.timeout(660):
                # stream_mode="values" yields the full state after each node completes,
                # giving real-time progress as each agent finishes its LLM call.
                async for state_snapshot in graph.astream(initial_state, stream_mode="values"):
                    if not isinstance(state_snapshot, dict):
                        continue
                    final_state = state_snapshot

                    current_completed = set(state_snapshot.get("completed_agents") or [])
                    for agent_name in (current_completed - prev_completed):
                        if agent_name in _PIPELINE_AGENTS:
                            step = _PIPELINE_AGENTS.index(agent_name) + 1
                            payload = json.dumps({
                                "agent": agent_name,
                                "status": "completed",
                                "step": step,
                                "total": len(_PIPELINE_AGENTS),
                            })
                            yield f"data: {payload}\n\n"
                    prev_completed = current_completed

            # Emit the final done event with full results so the API service
            # can persist them without a second pipeline call.
            gap_analysis = final_state.get("gap_analysis") or {}
            result_payload = json.dumps({
                "agent": "pipeline",
                "status": "done",
                "session_id": session_id,
                "match_percentage": float(gap_analysis.get("match_percentage", 0.0)),
                "result": {
                    "gap_analysis": final_state.get("gap_analysis"),
                    "tailored_bullets": final_state.get("tailored_bullets"),
                    "cover_letter": final_state.get("cover_letter"),
                    "interview_qa": final_state.get("interview_qa"),
                    "ats_score": final_state.get("ats_score"),
                    "company_research": final_state.get("company_research"),
                    "input_tokens": final_state.get("input_tokens", 0),
                    "output_tokens": final_state.get("output_tokens", 0),
                },
                "error": final_state.get("error"),
            })
            yield f"data: {result_payload}\n\n"

        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'agent': 'pipeline', 'status': 'error', 'detail': 'Pipeline timed out.'})}\n\n"
        except Exception as exc:
            _logger.error("stream: pipeline error [session=%s]: %s", session_id, exc)
            yield f"data: {json.dumps({'agent': 'pipeline', 'status': 'error', 'detail': 'Pipeline error. Please retry.'})}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Entry point for direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "agents.main:app",
        host="0.0.0.0",
        port=int(os.getenv("AGENT_SERVICE_PORT", "8001")),
        reload=True,
    )