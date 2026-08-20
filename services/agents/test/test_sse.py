"""
AI-01 tests: SSE streaming endpoint /analyze/stream

The endpoint runs graph.ainvoke(), then emits one SSE event per completed agent
(in pipeline order) followed by a final "done" event.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ANALYZE_PAYLOAD = {
    "resume_text": "Jane Doe. Python, FastAPI.",
    "job_description": "Python engineer needed.",
    "user_id": 1,
}

_ALL_AGENTS = [
    "resume_parser", "jd_analyst", "company_researcher",
    "gap_analyst", "resume_tailor", "cover_letter", "interview_coach", "ats_scorer",
]

_FINAL_STATE = {
    "completed_agents": _ALL_AGENTS,
    "gap_analysis": {"match_percentage": 75.0, "missing_skills": ["Kubernetes"]},
    "tailored_bullets": [],
    "cover_letter": "Dear Hiring Manager...",
    "interview_qa": [],
    "ats_score": {"score": 75},
    "error": None,
}


class TestAnalyzeStream:
    def _mock_graph(self, final_state=None):
        """Patch agents.main.graph to return a controlled final state from ainvoke."""
        fs = final_state or _FINAL_STATE
        mock = MagicMock()
        mock.ainvoke = AsyncMock(return_value=fs)
        return patch("agents.main.graph", mock)

    def _parse_events(self, response_text: str) -> list:
        """Parse SSE response body into a list of dicts."""
        events = []
        for line in response_text.strip().splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    def test_streams_agent_completion_events(self, mock_graph):
        """Each completed agent should produce one SSE event."""
        from agents.main import app
        from fastapi.testclient import TestClient

        with self._mock_graph():
            with TestClient(app) as c:
                r = c.post("/analyze/stream", json=_ANALYZE_PAYLOAD)

        assert r.status_code == 200
        events = self._parse_events(r.text)
        agent_progress = [e for e in events if e.get("status") == "completed"]
        assert len(agent_progress) == len(_ALL_AGENTS)

    def test_step_and_total_fields_correct(self, mock_graph):
        """Progress events should include correct step and total values."""
        from agents.main import app
        from fastapi.testclient import TestClient

        partial_state = {**_FINAL_STATE, "completed_agents": ["resume_parser"]}
        with self._mock_graph(final_state=partial_state):
            with TestClient(app) as c:
                r = c.post("/analyze/stream", json=_ANALYZE_PAYLOAD)

        events = self._parse_events(r.text)
        progress = [e for e in events if e.get("agent") == "resume_parser"]
        assert len(progress) == 1
        assert progress[0]["step"] == 1
        assert progress[0]["total"] == len(_ALL_AGENTS)

    def test_partial_pipeline_emits_only_completed_agents(self, mock_graph):
        """Only agents listed in completed_agents should appear in SSE output."""
        from agents.main import app
        from fastapi.testclient import TestClient

        partial_state = {**_FINAL_STATE, "completed_agents": ["resume_parser", "jd_analyst"]}
        with self._mock_graph(final_state=partial_state):
            with TestClient(app) as c:
                r = c.post("/analyze/stream", json=_ANALYZE_PAYLOAD)

        events = self._parse_events(r.text)
        progress = [e for e in events if e.get("status") == "completed"]
        assert len(progress) == 2
        agent_names = [e["agent"] for e in progress]
        assert "resume_parser" in agent_names
        assert "jd_analyst" in agent_names
        assert "gap_analyst" not in agent_names

    def test_final_done_event_emitted(self, mock_graph):
        """A final 'done' event must be emitted after all progress events."""
        from agents.main import app
        from fastapi.testclient import TestClient

        with self._mock_graph():
            with TestClient(app) as c:
                r = c.post("/analyze/stream", json=_ANALYZE_PAYLOAD)

        events = self._parse_events(r.text)
        done_events = [e for e in events if e.get("status") == "done"]
        assert len(done_events) == 1
        assert done_events[0]["agent"] == "pipeline"
        assert "session_id" in done_events[0]
        assert done_events[0]["match_percentage"] == 75.0

    def test_content_type_is_event_stream(self, mock_graph):
        """Response Content-Type must be text/event-stream."""
        from agents.main import app
        from fastapi.testclient import TestClient

        with self._mock_graph():
            with TestClient(app) as c:
                r = c.post("/analyze/stream", json=_ANALYZE_PAYLOAD)

        assert "text/event-stream" in r.headers["content-type"]

    def test_empty_completed_agents_emits_only_done(self, mock_graph):
        """If no agents completed (error path), only the done event is emitted."""
        from agents.main import app
        from fastapi.testclient import TestClient

        empty_state = {**_FINAL_STATE, "completed_agents": [], "error": "pipeline failed"}
        with self._mock_graph(final_state=empty_state):
            with TestClient(app) as c:
                r = c.post("/analyze/stream", json=_ANALYZE_PAYLOAD)

        events = self._parse_events(r.text)
        progress = [e for e in events if e.get("status") == "completed"]
        done = [e for e in events if e.get("status") == "done"]
        assert len(progress) == 0
        assert len(done) == 1