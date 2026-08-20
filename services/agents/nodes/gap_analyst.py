import logging
import re
import traceback
from typing import List, Tuple

from langchain_core.messages import HumanMessage
from agents.tools.gemini import GeminiClient

from agents.state import AgentState
from agents.tools.rag import query_collection

logger = logging.getLogger(__name__)


_NULL_TOKENS = {"null", "none", "n/a", "na", "-", ""}

# Maps JD skill buzzwords → synonyms/equivalents that appear on real resumes.
_SKILL_ALIASES: dict[str, List[str]] = {
    # Web / API
    "backend development":   ["software engineering", "server side", "backend", "api development", "web development"],
    "backend engineer":      ["software engineer", "backend", "server side"],
    "rest apis":             ["restful", "rest api", "http api", "web api", "api integration", "api", "fastapi", "flask", "django"],
    "rest api":              ["restful", "http api", "web api", "api", "fastapi"],
    "webhooks":              ["webhook", "event driven", "callback", "event-driven"],
    "oauth":                 ["oauth2", "authentication", "auth", "authorization"],
    "typescript":            ["ts", "javascript", "js"],
    "microservices":         ["microservice", "service oriented", "soa", "distributed", "docker", "kubernetes", "api"],
    "api development":       ["fastapi", "flask", "django", "rest", "restful", "api", "endpoint"],
    "fastapi":               ["fast api", "python api", "rest api", "api"],

    # AI / ML
    "openai api":            ["openai", "gpt", "chatgpt", "llm api", "language model api"],
    "anthropic api":         ["anthropic", "claude"],
    "prompt engineering":    ["prompt", "llm", "system prompt", "few shot", "chain of thought"],
    "rag":                   ["retrieval augmented", "langchain", "vector", "embeddings", "chromadb", "retrieval"],
    "rag architectures":     ["retrieval augmented", "langchain", "vector database", "embeddings", "chromadb", "rag"],
    "llms":                  ["large language model", "llm", "gpt", "claude", "gemini", "hugging face", "transformers"],
    "llm":                   ["large language model", "gpt", "claude", "gemini", "hugging face", "transformers"],
    "large language models": ["llm", "gpt", "claude", "gemini", "hugging face", "transformers"],
    "llm orchestration":     ["langchain", "langgraph", "llm", "agent", "chain"],
    "agentic frameworks":    ["langchain", "langgraph", "agent", "crewai", "autogen", "agentic"],
    "langchain":             ["lang chain", "llm framework", "langchain", "agent"],
    "langgraph":             ["lang graph", "graph agent", "langgraph"],
    "generative ai":         ["genai", "gen ai", "llm", "gpt", "diffusion", "generative", "large language"],
    "gen ai":                ["generative ai", "llm", "gpt", "large language model"],
    "machine learning":      ["ml", "sklearn", "scikit", "xgboost", "pytorch", "tensorflow", "model"],
    "deep learning":         ["neural network", "cnn", "rnn", "transformer", "pytorch", "tensorflow", "keras"],
    "nlp":                   ["natural language", "text", "spacy", "nltk", "transformers", "language model"],
    "mlops":                 ["model deployment", "model serving", "ml pipeline", "kubeflow", "mlflow", "model ops"],
    "vector databases":      ["chromadb", "pinecone", "weaviate", "faiss", "vector store", "embeddings"],
    "model context protocol": ["mcp", "model context", "tool protocol"],
    "mcp":                   ["model context protocol", "tool use", "function calling"],

    # Cloud / Infrastructure
    "cloud":                 ["aws", "gcp", "azure", "cloud provider", "cloud native"],
    "cloud-native":          ["aws", "gcp", "azure", "docker", "kubernetes", "microservices"],
    "aws":                   ["amazon web services", "sagemaker", "ec2", "s3", "lambda", "bedrock"],
    "gcp":                   ["google cloud", "google cloud platform", "bigquery", "vertex"],
    "azure":                 ["microsoft azure", "azure ml"],
    "docker":                ["container", "containerize", "dockerfile", "docker compose"],
    "kubernetes":            ["k8s", "container orchestration", "helm", "kubectl"],
    "ci/cd":                 ["continuous integration", "continuous deployment", "github actions", "jenkins", "cicd"],
    "ci cd":                 ["continuous integration", "continuous deployment", "github actions", "jenkins"],
    "serverless":            ["lambda", "cloud functions", "faas", "serverless framework"],
    "cloud infrastructure":  ["aws", "gcp", "azure", "cloud", "docker", "kubernetes"],
    "service deployment":    ["deployment", "deploy", "docker", "kubernetes", "ci cd", "production"],

    # Voice / Audio
    "stt":                   ["speech to text", "speech recognition", "asr", "whisper"],
    "tts":                   ["text to speech", "speech synthesis", "elevenlabs"],
    "voice ai":              ["conversational ai", "voice assistant", "speech", "vapi", "retell"],
    "telephony":             ["twilio", "phone", "call", "voice"],
    "function calling":      ["function calling", "tool calling", "tool use", "tools"],
    "conversation state":    ["conversation history", "context management", "dialogue", "chat history"],
    "real time audio":       ["audio processing", "real time", "streaming", "latency"],
    "latency management":    ["real time", "low latency", "performance", "optimization"],
    "barge in handling":     ["interruption", "real time", "audio pipeline"],

    # Data
    "sql":                   ["postgresql", "mysql", "sqlite", "postgres", "database", "query", "relational"],
    "nosql":                 ["mongodb", "dynamodb", "cassandra", "redis", "non-relational"],
    "etl":                   ["data pipeline", "data engineering", "airflow", "spark", "pyspark"],
    "data engineering":      ["etl", "pipeline", "spark", "pyspark", "airflow", "data pipeline"],

    # General / Soft
    "api documentation":     ["api", "rest", "documentation", "swagger", "openapi"],
    "full stack":            ["frontend", "backend", "software engineer", "full-stack"],
    "crm integration":       ["crm", "api integration", "salesforce", "hubspot", "integration"],
    "problem solving":       ["analytical", "debugging", "troubleshooting", "critical thinking"],
    "communication":         ["stakeholder", "presentation", "documentation", "collaboration"],
}


def _normalize(text: str) -> str:
    """Lowercase + strip punctuation for comparison."""
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def _skill_match(skill: str, resume_text: str, resume_skills: List[str]) -> str:
    """
    Classify a JD skill against the resume.
    Returns 'match', 'partial', or 'miss'.
    Checks direct text/skill-list matches first, then synonym aliases.
    """
    norm_skill = _normalize(skill)
    norm_resume = _normalize(resume_text)
    norm_skills_list = [_normalize(s) for s in resume_skills]

    # --- Full match: skill phrase appears literally in resume text ---
    if norm_skill in norm_resume:
        return "match"

    # --- Full match: against parsed skills list ---
    for s in norm_skills_list:
        if norm_skill == s or norm_skill in s or s in norm_skill:
            return "match"

    # --- Alias match: check known synonyms against resume text and skills list ---
    aliases = _SKILL_ALIASES.get(norm_skill, [])
    for alias in aliases:
        norm_alias = _normalize(alias)
        if norm_alias in norm_resume:
            return "match"
        for s in norm_skills_list:
            if norm_alias in s or s in norm_alias:
                return "match"

    # --- Partial: a meaningful word (4+ chars) from the skill appears in resume text ---
    words = [w for w in norm_skill.split() if len(w) >= 4]
    if words and any(w in norm_resume for w in words):
        return "partial"

    # --- Partial: any alias word appears in resume text ---
    for alias in aliases:
        alias_words = [w for w in _normalize(alias).split() if len(w) >= 4]
        if alias_words and any(w in norm_resume for w in alias_words):
            return "partial"

    return "miss"


_FORMAT_CHECKS: List[Tuple[str, str]] = [
    (r"\|",                  "Pipe characters may confuse ATS parsers — use plain text instead of tables"),
    (r"\t{2,}",              "Multiple tabs detected — use single spaces for alignment"),
    (r"[^\x00-\x7F]{3,}",   "Non-ASCII characters may not parse correctly in some ATS systems"),
]


def _formatting_tips(resume_text: str) -> List[str]:
    tips = []
    for pattern, tip in _FORMAT_CHECKS:
        if re.search(pattern, resume_text):
            tips.append(tip)
    if not tips:
        tips.append("Resume formatting looks clean — no major ATS red flags detected.")
    return tips


def gap_analyst_node(state: AgentState) -> AgentState:
    """Perform a gap analysis between the parsed resume and the parsed JD."""
    session_id = state.get("session_id", "?")
    logger.info("gap_analyst_node: starting [session=%s]", session_id)
    try:
        resume_parsed = state.get("resume_parsed") or {}
        jd_parsed = state.get("jd_parsed") or {}
        resume_text = state.get("resume_text", "")

        resume_skills: List[str] = [
            s for s in (resume_parsed.get("skills") or [])
            if isinstance(s, str) and s.strip().lower() not in _NULL_TOKENS
        ]

        # All required skills from the JD (deduplicated)
        jd_required: List[str] = [
            s for s in (jd_parsed.get("required_skills") or [])
            if isinstance(s, str) and s.strip().lower() not in _NULL_TOKENS
        ]
        jd_nice: List[str] = [
            s for s in (jd_parsed.get("nice_to_have_skills") or [])
            if isinstance(s, str) and s.strip().lower() not in _NULL_TOKENS
        ]
        all_jd_skills = list(dict.fromkeys(jd_required + jd_nice))  # preserve order, dedup

        # --- Deterministic classification ---
        matching_skills: List[str] = []
        missing_skills: List[str] = []
        partial_matches: List[str] = []

        for skill in all_jd_skills:
            result = _skill_match(skill, resume_text, resume_skills)
            if result == "match":
                matching_skills.append(skill)
            elif result == "partial":
                partial_matches.append(skill)
            else:
                missing_skills.append(skill)

        # --- Weighted match percentage ---
        # Required skills count 2x more than nice-to-haves for a more accurate picture.
        req_set = set(s.lower() for s in jd_required)

        def _weight(skill: str) -> float:
            return 2.0 if skill.lower() in req_set else 1.0

        total_weight = sum(_weight(s) for s in all_jd_skills)
        match_weight = sum(_weight(s) for s in matching_skills)
        partial_weight = sum(_weight(s) * 0.5 for s in partial_matches)

        if total_weight > 0:
            match_pct = round((match_weight + partial_weight) / total_weight * 100, 1)
        else:
            match_pct = 0.0

        # --- LLM only for the summary text ---
        rag_context = ""
        try:
            job_title = jd_parsed.get("job_title", "")
            if job_title:
                chunks = query_collection(query=job_title, collection_name="resumes", n_results=3)
                if chunks:
                    rag_context = "\n\nAdditional resume context:\n" + "\n---\n".join(chunks)
        except Exception:
            pass

        llm = GeminiClient(temperature=0)

        summary_prompt = (
            f"The candidate matches {match_pct}% of the job requirements.\n"
            f"Matching skills ({len(matching_skills)}): {', '.join(matching_skills[:8]) or 'none'}\n"
            f"Missing skills ({len(missing_skills)}): {', '.join(missing_skills[:8]) or 'none'}\n"
            f"Partial matches ({len(partial_matches)}): {', '.join(partial_matches[:5]) or 'none'}\n"
            f"{rag_context}\n\n"
            "Write 2 sentences summarising the candidate's fit for this role. Be direct and specific."
        )

        try:
            resp = llm.invoke([HumanMessage(content=summary_prompt)])
            summary = resp.content.strip()
        except Exception:
            summary = f"Candidate matches {match_pct}% of the job requirements."

        logger.info(
            "gap_analyst_node: done [session=%s] match=%.1f%% matching=%d missing=%d partial=%d",
            session_id,
            match_pct,
            len(matching_skills),
            len(missing_skills),
            len(partial_matches),
        )
        return {
            **state,
            "gap_analysis": {
                "matching_skills": matching_skills,
                "missing_skills": missing_skills,
                "partial_matches": partial_matches,
                "match_percentage": match_pct,
                "summary": summary,
                "formatting_tips": _formatting_tips(resume_text),
            },
            "completed_agents": state.get("completed_agents", []) + ["gap_analyst"],
            "input_tokens": state.get("input_tokens", 0) + llm.input_tokens,
            "output_tokens": state.get("output_tokens", 0) + llm.output_tokens,
        }

    except Exception as exc:
        error_msg = f"gap_analyst_node error: {traceback.format_exc()}"
        logger.error("gap_analyst_node: FAILED [session=%s]: %s", session_id, exc, exc_info=True)
        _in = getattr(llm, 'input_tokens', 0) if 'llm' in locals() else 0
        _out = getattr(llm, 'output_tokens', 0) if 'llm' in locals() else 0
        return {
            **state,
            "error": error_msg,
            "completed_agents": state.get("completed_agents", []) + ["gap_analyst"],
            "input_tokens": state.get("input_tokens", 0) + _in,
            "output_tokens": state.get("output_tokens", 0) + _out,
        }