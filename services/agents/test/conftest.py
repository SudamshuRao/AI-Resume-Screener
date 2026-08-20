"""
Shared pytest fixtures for the agent-service tests.

Heavy LangChain/LangGraph/ChromaDB/HuggingFace packages are stubbed in
sys.modules before any node module is imported, so the test suite runs
without those packages installed.
"""
import sys
import types
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CHROMA_HOST", "localhost")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")


# ---------------------------------------------------------------------------
# Stub heavy third-party packages so node modules can be imported without
# installing langchain, chromadb, sentence-transformers, etc.
# ---------------------------------------------------------------------------

def _make_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


_STUB_MODULES = [
    "google",
    "google.genai",
    "google.genai.types",
    "agents.tools.gemini",
    "langchain_core",
    "langchain_core.messages",
    "langchain_core.callbacks",
    "langgraph",
    "langgraph.graph",
]

for _mod_name in _STUB_MODULES:
    if _mod_name not in sys.modules:
        _make_module(_mod_name)

# stub GeminiClient used in every node
sys.modules["agents.tools.gemini"].GeminiClient = MagicMock  # type: ignore

# langchain_core.messages.HumanMessage / BaseMessage — used in cover_letter + state
_lc_messages = sys.modules["langchain_core.messages"]
_lc_messages.HumanMessage = MagicMock   # type: ignore
_lc_messages.BaseMessage = MagicMock    # type: ignore

# langchain_core.callbacks.AsyncCallbackHandler — base class for TokenTracker
sys.modules["langchain_core.callbacks"].AsyncCallbackHandler = object  # type: ignore

# langgraph.graph.StateGraph / END — used in graph.py
# Use MagicMock() instance so StateGraph(AgentState) returns a plain mock,
# not a MagicMock spec'd to AgentState (which would block .add_node etc.)
_lg_graph = sys.modules["langgraph.graph"]
_lg_graph.StateGraph = MagicMock()      # type: ignore
_lg_graph.END = "END"                   # type: ignore


# ---------------------------------------------------------------------------
# Minimal valid pipeline output
# ---------------------------------------------------------------------------
MOCK_PIPELINE_RESULT = {
    "gap_analysis": {
        "match_percentage": 75.0,
        "missing_skills": ["Kubernetes"],
        "matching_skills": ["Python", "FastAPI"],
    },
    "tailored_bullets": ["Led development of REST APIs", "Deployed ML models to production"],
    "cover_letter": "Dear Hiring Manager, I am excited to apply...",
    "interview_qa": [
        {"question": "Tell me about yourself", "answer": "I am a software engineer..."}
    ],
    "ats_score": {"score": 80, "feedback": "Good keyword match"},
    "error": None,
}


@pytest.fixture()
def mock_graph():
    """Patch build_graph so the agent service never touches LangGraph/Ollama."""
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=MOCK_PIPELINE_RESULT)
    with patch("agents.main.build_graph", return_value=mock):
        yield mock


@pytest.fixture()
def client(mock_graph):
    """FastAPI TestClient for the agent service with a mocked graph."""
    from agents.main import app
    with TestClient(app) as c:
        yield c