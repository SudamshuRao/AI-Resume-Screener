import logging
import traceback
from typing import List, Optional

from agents.tools.gemini import GeminiClient
from pydantic import BaseModel, field_validator

from agents.config import settings
from agents.state import AgentState
from agents.tools.rag import index_documents
from agents.tools.structured import invoke_structured

logger = logging.getLogger(__name__)


_NULL_TOKENS = {"null", "none", "n/a", "na", "-", ""}

def _coerce_list(v):
    if isinstance(v, list):
        return [str(x) for x in v if x and str(x).strip().lower() not in _NULL_TOKENS]
    if isinstance(v, dict):
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.split(",")
                if x.strip() and x.strip().lower() not in _NULL_TOKENS]
    return []


class ParsedJD(BaseModel):
    job_title: Optional[str] = None
    company: Optional[str] = None
    required_skills: List[str] = []
    nice_to_have_skills: List[str] = []
    experience_years: Optional[int] = None
    responsibilities: List[str] = []
    keywords: List[str] = []

    @field_validator("required_skills", "nice_to_have_skills", "responsibilities", "keywords", mode="before")
    @classmethod
    def coerce_lists(cls, v):
        return _coerce_list(v)


def jd_analyst_node(state: AgentState) -> AgentState:
    """Parse the job description into structured data and index it in ChromaDB."""
    session_id = state.get("session_id", "?")
    logger.info("jd_analyst_node: starting [session=%s] jd_len=%d", session_id, len(state.get("job_description", "")))
    try:
        llm = GeminiClient(temperature=0, json_mode=True)

        jd_text = state['job_description'][:settings.max_jd_chars]
        prompt = (
            "Extract structured info from this job description.\n\n"
            f"JD:\n{jd_text}\n\n"
            "Skills: short names only (1-4 words, e.g. Python, React, Docker — not full sentences).\n\n"
            "Respond with ONLY a JSON object:\n"
            '{"job_title": "string", "company": "string or null", '
            '"required_skills": ["Python", "React", "short skill names only"], '
            '"nice_to_have_skills": ["short", "skill", "names"], '
            '"experience_years": 0, '
            '"responsibilities": ["list", "of", "strings"], '
            '"keywords": ["list", "of", "strings"]}'
        )

        parsed: ParsedJD = invoke_structured(llm, prompt, ParsedJD)
        jd_dict = parsed.model_dump()

        # Index JD into ChromaDB for later RAG retrieval.
        session_id = state.get("session_id", "unknown")
        chunks = [state["job_description"]]
        ids = [f"jd_{session_id}_0"]
        try:
            index_documents(chunks, ids, collection_name="job_descriptions")
        except Exception as rag_exc:
            logger.warning("jd_analyst_node: RAG indexing skipped [session=%s]: %s", session_id, rag_exc)

        logger.info(
            "jd_analyst_node: done [session=%s] title=%r required_skills=%d",
            session_id,
            jd_dict.get("job_title"),
            len(jd_dict.get("required_skills", [])),
        )
        return {
            **state,
            "jd_parsed": jd_dict,
            "completed_agents": state.get("completed_agents", []) + ["jd_analyst"],
            "input_tokens": state.get("input_tokens", 0) + llm.input_tokens,
            "output_tokens": state.get("output_tokens", 0) + llm.output_tokens,
        }

    except Exception as exc:
        error_msg = f"jd_analyst_node error: {traceback.format_exc()}"
        logger.error("jd_analyst_node: FAILED [session=%s]: %s", session_id, exc, exc_info=True)
        _in = getattr(llm, 'input_tokens', 0) if 'llm' in locals() else 0
        _out = getattr(llm, 'output_tokens', 0) if 'llm' in locals() else 0
        return {
            **state,
            "error": error_msg,
            "completed_agents": state.get("completed_agents", []) + ["jd_analyst"],
            "input_tokens": state.get("input_tokens", 0) + _in,
            "output_tokens": state.get("output_tokens", 0) + _out,
        }