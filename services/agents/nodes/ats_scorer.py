"""
Deterministic ATS scorer — no LLM hallucination.

Scores the resume against the JD using real keyword frequency analysis
and formatting heuristics, the same way actual ATS systems work.

Score breakdown (total 100):
  - Keyword coverage    : 50 pts  (what % of JD keywords appear in resume)
  - Required skill hit  : 30 pts  (what % of required skills are present)
  - Formatting quality  : 20 pts  (formatting red-flag deductions)
"""
import logging
import re
import traceback
from typing import List

from agents.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def _token_set(text: str) -> set[str]:
    """All meaningful words (3+ chars) from a block of text."""
    return {w for w in _normalize(text).split() if len(w) >= 3}


def _keyword_hit(keyword: str, resume_text: str) -> bool:
    """True if every significant word in the keyword appears in the resume."""
    norm_kw = _normalize(keyword)
    norm_resume = _normalize(resume_text)
    # Full phrase match first
    if norm_kw in norm_resume:
        return True
    # All significant words must appear
    words = [w for w in norm_kw.split() if len(w) >= 4]
    return bool(words) and all(w in norm_resume for w in words)


# ATS formatting red-flag patterns
_FORMAT_CHECKS = [
    (r"\|",                     "Pipe characters may confuse ATS parsers — use plain text tables or lists"),
    (r"[\u2022\u2023\u25e6\u2043\u2219]",
                                "Non-standard bullet characters (•, ‣, ◦) — use plain hyphens or asterisks"),
    (r"(header|footer)",        "Headers/footers risk being ignored by some ATS parsers"),
    (r"\t{2,}",                 "Multiple tabs detected — use single spaces for alignment"),
    (r"[^\x00-\x7F]{3,}",      "Non-ASCII characters may not parse correctly in some ATS systems"),
]

_POSITIVE_SIGNALS = [
    (r"\b(summary|objective|profile)\b",  "Professional summary section detected — good for ATS context"),
    (r"\b(experience|work history)\b",     "Dedicated experience section — ATS-friendly structure"),
    (r"\b(education|degree|gpa)\b",        "Education section present — required by most ATS"),
    (r"\b(skill|skills|technologies)\b",   "Skills section present — boosts keyword matching"),
    (r"\b(github|linkedin|portfolio)\b",   "Professional links included — adds credibility"),
]


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

def ats_scorer_node(state: AgentState) -> AgentState:
    """Deterministic ATS compatibility score — keyword frequency + formatting heuristics."""
    session_id = state.get("session_id", "?")
    logger.info("ats_scorer_node: starting [session=%s]", session_id)
    try:
        resume_text = state.get("resume_text", "") or ""
        jd_parsed = state.get("jd_parsed") or {}
        resume_parsed = state.get("resume_parsed") or {}
        gap_analysis = state.get("gap_analysis") or {}

        jd_keywords: List[str] = [
            k for k in (jd_parsed.get("keywords") or [])
            if isinstance(k, str) and k.strip()
        ]
        jd_required: List[str] = [
            s for s in (jd_parsed.get("required_skills") or [])
            if isinstance(s, str) and s.strip()
        ]
        resume_skills: List[str] = [
            s for s in (resume_parsed.get("skills") or [])
            if isinstance(s, str) and s.strip()
        ]

        # --- 1. Keyword coverage (50 pts) ---
        kw_hits = [k for k in jd_keywords if _keyword_hit(k, resume_text)]
        kw_misses = [k for k in jd_keywords if not _keyword_hit(k, resume_text)]
        kw_score = round((len(kw_hits) / len(jd_keywords) * 50) if jd_keywords else 50)

        # --- 2. Required skill coverage (30 pts) ---
        # Re-use matching_skills from gap_analysis if available (avoids re-running matching logic)
        matching_skills: List[str] = gap_analysis.get("matching_skills") or []
        partial_skills: List[str] = gap_analysis.get("partial_matches") or []

        if jd_required:
            required_hit = len([s for s in jd_required if s in matching_skills])
            required_partial = len([s for s in jd_required if s in partial_skills])
            skill_score = round((required_hit + 0.5 * required_partial) / len(jd_required) * 30)
        else:
            skill_score = 25  # no required skills listed = neutral

        # --- 3. Formatting quality (20 pts) ---
        format_deductions: List[str] = []
        format_score = 20
        norm_resume = resume_text.lower()

        for pattern, tip in _FORMAT_CHECKS:
            if re.search(pattern, norm_resume, re.IGNORECASE):
                format_score -= 4
                format_deductions.append(tip)

        # Positive signals — recover up to 2 pts back if already deducted
        positive_notes: List[str] = []
        for pattern, note in _POSITIVE_SIGNALS:
            if re.search(pattern, norm_resume, re.IGNORECASE):
                positive_notes.append(note)

        format_score = max(0, min(20, format_score))

        # --- Final score ---
        total_score = kw_score + skill_score + format_score

        # --- Actionable tips ---
        formatting_suggestions: List[str] = []
        if format_deductions:
            formatting_suggestions.extend(format_deductions[:3])
        if not formatting_suggestions:
            formatting_suggestions.append("Resume formatting looks clean — no major ATS red flags detected.")
        if len(kw_misses) > 0:
            formatting_suggestions.append(
                f"Add these missing keywords naturally: {', '.join(kw_misses[:5])}"
            )

        # --- Overall assessment ---
        if total_score >= 80:
            tier = "Strong ATS match"
        elif total_score >= 60:
            tier = "Moderate ATS match"
        elif total_score >= 40:
            tier = "Weak ATS match"
        else:
            tier = "Poor ATS match"

        overall_assessment = (
            f"{tier} — {total_score}/100. "
            f"Keyword coverage: {len(kw_hits)}/{len(jd_keywords)} JD keywords found. "
            f"Required skills: {skill_score}/30 pts. "
            f"Formatting: {format_score}/20 pts."
        )

        score_dict = {
            "score": total_score,
            "keyword_matches": kw_hits,
            "keyword_misses": kw_misses,
            "formatting_suggestions": formatting_suggestions,
            "overall_assessment": overall_assessment,
            # Score breakdown for transparency
            "score_breakdown": {
                "keyword_coverage": kw_score,
                "skill_coverage": skill_score,
                "formatting": format_score,
            },
        }

        logger.info(
            "ats_scorer_node: done [session=%s] score=%d (kw=%d skill=%d fmt=%d) "
            "kw_hits=%d/%d",
            session_id,
            total_score, kw_score, skill_score, format_score,
            len(kw_hits), len(jd_keywords),
        )
        return {
            **state,
            "ats_score": score_dict,
            "completed_agents": state.get("completed_agents", []) + ["ats_scorer"],
        }

    except Exception as exc:
        error_msg = f"ats_scorer_node error: {traceback.format_exc()}"
        logger.error("ats_scorer_node: FAILED [session=%s]: %s", session_id, exc, exc_info=True)
        return {
            **state,
            "error": error_msg,
            "completed_agents": state.get("completed_agents", []) + ["ats_scorer"],
        }