from typing import TypedDict, Optional, List
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # Inputs
    resume_text: str
    job_description: str
    user_id: int
    session_id: str

    # Intermediate outputs (filled by agents)
    resume_parsed: Optional[dict]       # structured resume data
    jd_parsed: Optional[dict]           # structured JD requirements
    company_research: Optional[dict]    # company insights inferred from JD
    gap_analysis: Optional[dict]        # skill gaps + matches
    tailored_bullets: Optional[list]    # rewritten resume bullets
    cover_letter: Optional[str]         # generated cover letter
    interview_qa: Optional[list]        # Q&A pairs
    # ats_score removed — formatting tips now live inside gap_analysis

    # Routing / control
    next_agent: str                     # supervisor routing field
    completed_agents: List[str]         # track which agents ran
    messages: List[BaseMessage]         # LLM message history
    error: Optional[str]                # error message if any

    # Token usage — accumulated across all nodes
    input_tokens: int
    output_tokens: int