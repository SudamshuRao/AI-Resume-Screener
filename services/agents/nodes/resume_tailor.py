import json
import logging
import traceback
from typing import List

from agents.tools.gemini import GeminiClient
from pydantic import BaseModel

from agents.state import AgentState
from agents.tools.structured import invoke_structured

logger = logging.getLogger(__name__)


class TailoredBullet(BaseModel):
    original: str
    tailored: str
    reasoning: str


class TailoredBullets(BaseModel):
    bullets: List[TailoredBullet]


def resume_tailor_node(state: AgentState) -> AgentState:
    """Rewrite the top 5 most relevant resume bullet points to match the JD keywords."""
    session_id = state.get("session_id", "?")
    logger.info("resume_tailor_node: starting [session=%s]", session_id)
    try:
        resume_parsed = state.get("resume_parsed") or {}
        jd_parsed = state.get("jd_parsed") or {}
        gap_analysis = state.get("gap_analysis") or {}

        all_bullets: List[str] = []
        for exp in resume_parsed.get("experience", []):
            bullets = exp.get("bullets", [])
            if isinstance(bullets, list):
                all_bullets.extend([str(b) for b in bullets])

        if not all_bullets:
            return {
                **state,
                "tailored_bullets": [],
                "completed_agents": state.get("completed_agents", []) + ["resume_tailor"],
            }

        # Show up to 8 bullets for strong matches, fewer for weak ones.
        # Cap at len(all_bullets) so we never ask for more than exist.
        gap_pct = float((gap_analysis or {}).get("match_percentage", 0))
        if gap_pct >= 60:
            n_bullets = min(len(all_bullets), 8)
        elif gap_pct >= 30:
            n_bullets = min(len(all_bullets), 5)
        else:
            n_bullets = min(len(all_bullets), 3)

        llm = GeminiClient(temperature=0.3, json_mode=True)

        jd_slim = {"title": jd_parsed.get("job_title"), "required": jd_parsed.get("required_skills", [])[:12], "keywords": jd_parsed.get("keywords", [])[:10]}
        gap_slim = {"missing": gap_analysis.get("missing_skills", [])[:8], "matching": gap_analysis.get("matching_skills", [])[:8]}
        prompt = (
            f"Rewrite the {n_bullets} most relevant resume bullets to match this job.\n\n"
            f"BULLETS:\n{json.dumps(all_bullets[:12])}\n\n"
            f"JD:\n{json.dumps(jd_slim)}\n\n"
            f"GAPS:\n{json.dumps(gap_slim)}\n\n"
            f"Return exactly {n_bullets} bullets. Use strong action verbs and JD keywords.\n\n"
            "Respond with ONLY: "
            '{"bullets": [{"original": "string", "tailored": "string", "reasoning": "string"}]}'
        )

        result: TailoredBullets = invoke_structured(llm, prompt, TailoredBullets)
        # Drop any bullets the LLM returned with empty/null fields (happens when
        # the resume has fewer bullets than requested).
        _null = {"", "null", "none", "n/a"}
        tailored_list = [
            b.model_dump() for b in result.bullets
            if b.original.strip().lower() not in _null
            and b.tailored.strip().lower() not in _null
        ]

        logger.info(
            "resume_tailor_node: done [session=%s] bullets_returned=%d",
            session_id,
            len(tailored_list),
        )
        return {
            **state,
            "tailored_bullets": tailored_list,
            "completed_agents": state.get("completed_agents", []) + ["resume_tailor"],
            "input_tokens": state.get("input_tokens", 0) + llm.input_tokens,
            "output_tokens": state.get("output_tokens", 0) + llm.output_tokens,
        }

    except Exception as exc:
        error_msg = f"resume_tailor_node error: {traceback.format_exc()}"
        logger.error("resume_tailor_node: FAILED [session=%s]: %s", session_id, exc, exc_info=True)
        _in = getattr(llm, 'input_tokens', 0) if 'llm' in locals() else 0
        _out = getattr(llm, 'output_tokens', 0) if 'llm' in locals() else 0
        return {
            **state,
            "error": error_msg,
            "completed_agents": state.get("completed_agents", []) + ["resume_tailor"],
            "input_tokens": state.get("input_tokens", 0) + _in,
            "output_tokens": state.get("output_tokens", 0) + _out,
        }