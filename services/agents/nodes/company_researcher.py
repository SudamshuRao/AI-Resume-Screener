import logging
import traceback
from typing import List

from agents.tools.gemini import GeminiClient
from pydantic import BaseModel

from agents.state import AgentState
from agents.tools.structured import invoke_structured

logger = logging.getLogger(__name__)


_NULL_TOKENS = {"null", "none", "n/a", "na", "-", ""}


class CompanyResearch(BaseModel):
    company_name: str = ""
    what_they_do: str = ""           # 2-3 sentences about what the company does
    recent_projects: List[str] = []  # recent/current initiatives inferred from JD
    culture_notes: str = ""          # 1-2 sentences on culture/values inferred from JD
    why_apply: str = ""              # 1-2 sentences on why this is a good opportunity


def company_researcher_node(state: AgentState) -> AgentState:
    """Infer company insights from the job description using the LLM."""
    session_id = state.get("session_id", "?")
    logger.info("company_researcher_node: starting [session=%s]", session_id)
    try:
        jd_parsed = state.get("jd_parsed") or {}
        company = jd_parsed.get("company") or ""
        title = jd_parsed.get("job_title", "")
        skills = jd_parsed.get("required_skills", [])[:10]
        resp = jd_parsed.get("responsibilities", [])[:5]

        llm = GeminiClient(temperature=0.5, json_mode=True)

        prompt = (
            "Infer company insights from this parsed job info.\n\n"
            f"Company: {company}\nRole: {title}\nRequired skills: {skills}\nResponsibilities: {resp}\n\n"
            "Respond with ONLY a JSON object:\n"
            '{"company_name": "string", "what_they_do": "2-3 sentences", "recent_projects": ["3-5 short phrases"], '
            '"culture_notes": "1-2 sentences", "why_apply": "1-2 sentences"}'
        )

        research: CompanyResearch = invoke_structured(llm, prompt, CompanyResearch)

        # Filter null-like tokens from recent_projects
        cleaned_projects = [
            p for p in research.recent_projects
            if isinstance(p, str) and p.strip().lower() not in _NULL_TOKENS
        ]
        research_dict = research.model_dump()
        research_dict["recent_projects"] = cleaned_projects

        logger.info(
            "company_researcher_node: done [session=%s] company=%r projects=%d",
            session_id,
            research_dict.get("company_name"),
            len(research_dict.get("recent_projects", [])),
        )
        return {
            **state,
            "company_research": research_dict,
            "completed_agents": state.get("completed_agents", []) + ["company_researcher"],
            "input_tokens": state.get("input_tokens", 0) + llm.input_tokens,
            "output_tokens": state.get("output_tokens", 0) + llm.output_tokens,
        }

    except Exception as exc:
        error_msg = f"company_researcher_node error: {traceback.format_exc()}"
        logger.error("company_researcher_node: FAILED [session=%s]: %s", session_id, exc, exc_info=True)
        _in = getattr(llm, 'input_tokens', 0) if 'llm' in locals() else 0
        _out = getattr(llm, 'output_tokens', 0) if 'llm' in locals() else 0
        return {
            **state,
            "error": error_msg,
            "completed_agents": state.get("completed_agents", []) + ["company_researcher"],
            "input_tokens": state.get("input_tokens", 0) + _in,
            "output_tokens": state.get("output_tokens", 0) + _out,
        }