import json
import logging
import traceback

from agents.tools.gemini import GeminiClient
from langchain_core.messages import HumanMessage

from agents.state import AgentState

logger = logging.getLogger(__name__)


def cover_letter_node(state: AgentState) -> AgentState:
    """Generate a professional, personalized 3-paragraph cover letter."""
    session_id = state.get("session_id", "?")
    logger.info("cover_letter_node: starting [session=%s]", session_id)
    try:
        resume_parsed = state.get("resume_parsed") or {}
        jd_parsed = state.get("jd_parsed") or {}
        gap_analysis = state.get("gap_analysis") or {}

        candidate_name = resume_parsed.get("name", "the candidate")
        job_title = jd_parsed.get("job_title", "the position")
        company = jd_parsed.get("company") or "your company"
        matching_skills = gap_analysis.get("matching_skills", [])

        llm = GeminiClient(temperature=0.7)

        candidate_slim = {
            "name": candidate_name,
            "skills": resume_parsed.get("skills", [])[:10],
            "experience": [{"title": e.get("title"), "company": e.get("company")} for e in resume_parsed.get("experience", [])[:3]],
        }
        jd_slim = {"title": job_title, "company": company, "required": jd_parsed.get("required_skills", [])[:8]}

        prompt = (
            f"Write a professional 3-paragraph cover letter for {candidate_name} applying to '{job_title}' at {company}.\n\n"
            f"CANDIDATE: {json.dumps(candidate_slim)}\nJD: {json.dumps(jd_slim)}\nMATCHES: {matching_skills[:8]}\n\n"
            "Rules:\n"
            "- Start Para 1 with 'I am excited to apply...' or similar — NEVER start with 'My name is'.\n"
            "- Para 1: express specific enthusiasm for the role and company.\n"
            "- Para 2: highlight 2-3 concrete matching skills/experiences tied to the JD requirements.\n"
            "- Para 3: confident closing with a call to action.\n"
            "- Do NOT include a salutation line (Dear Hiring Manager) or signature block — body text only.\n"
            "Return ONLY the 3 paragraphs of cover letter body text."
        )

        message = HumanMessage(content=prompt)
        response = llm.invoke([message])
        cover_letter_text = response.content.strip()

        logger.info(
            "cover_letter_node: done [session=%s] cover_letter_len=%d",
            session_id,
            len(cover_letter_text),
        )
        return {
            **state,
            "cover_letter": cover_letter_text,
            "completed_agents": state.get("completed_agents", []) + ["cover_letter"],
            "input_tokens": state.get("input_tokens", 0) + llm.input_tokens,
            "output_tokens": state.get("output_tokens", 0) + llm.output_tokens,
        }

    except Exception as exc:
        error_msg = f"cover_letter_node error: {traceback.format_exc()}"
        logger.error("cover_letter_node: FAILED [session=%s]: %s", session_id, exc, exc_info=True)
        _in = getattr(llm, 'input_tokens', 0) if 'llm' in locals() else 0
        _out = getattr(llm, 'output_tokens', 0) if 'llm' in locals() else 0
        return {
            **state,
            "error": error_msg,
            "completed_agents": state.get("completed_agents", []) + ["cover_letter"],
            "input_tokens": state.get("input_tokens", 0) + _in,
            "output_tokens": state.get("output_tokens", 0) + _out,
        }