"""
TEST-04: End-to-end tests for the /analyze pipeline endpoint.

The agent service HTTP call is mocked with respx so no real agent
service or LLM is needed. All DB interactions use the SQLite in-memory
session from conftest.py.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AGENT_RESPONSE = {
    "session_id": "mock-session-abc",
    "gap_analysis": {"match_percentage": 80.0, "missing_skills": ["Kubernetes"]},
    "tailored_bullets": [{"original": "Built APIs", "tailored": "Engineered REST APIs"}],
    "cover_letter": "Dear Hiring Manager...",
    "interview_qa": [{"question": "Tell me about yourself", "type": "behavioral", "model_answer": "..."}],
    "ats_score": {"score": 82, "feedback": "Good match"},
    "match_percentage": 80.0,
}


def _create_app(client):
    r = client.post("/api/v1/applications", json={
        "company": "TechCorp",
        "job_title": "Python Engineer",
        "job_description": "FastAPI, Python, Kubernetes",
        "resume_text": "Jane Doe. Python, FastAPI.",
    })
    assert r.status_code == 201
    return r.json()


def _mock_agent_ok(response_data=None):
    """Return a context manager that patches httpx to return a successful agent response."""
    data = response_data or _AGENT_RESPONSE
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 201
    mock_response.json.return_value = data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    return patch("api.routers.analysis.httpx.AsyncClient", return_value=mock_client)


# ===========================================================================
# POST /api/v1/analyze  — happy path
# ===========================================================================

class TestTriggerAnalysis:
    def test_returns_201_with_analysis_result(self, client):
        app = _create_app(client)
        with _mock_agent_ok():
            r = client.post("/api/v1/analyze", json={"application_id": app["id"]})
        assert r.status_code == 201
        body = r.json()
        assert "session_id" in body
        assert body["ats_score"] == 82   # extracted integer from {"score": 82, ...}
        assert body["match_percentage"] == 80.0

    def test_cover_letter_persisted(self, client):
        app = _create_app(client)
        with _mock_agent_ok():
            r = client.post("/api/v1/analyze", json={"application_id": app["id"]})
        assert r.json()["cover_letter"] == "Dear Hiring Manager..."

    def test_gap_analysis_persisted(self, client):
        app = _create_app(client)
        with _mock_agent_ok():
            r = client.post("/api/v1/analyze", json={"application_id": app["id"]})
        gap = r.json()["gap_analysis"]
        assert gap["match_percentage"] == 80.0
        assert "Kubernetes" in gap["missing_skills"]

    def test_tailored_bullets_persisted(self, client):
        app = _create_app(client)
        with _mock_agent_ok():
            r = client.post("/api/v1/analyze", json={"application_id": app["id"]})
        bullets = r.json()["tailored_bullets"]
        assert len(bullets) == 1
        assert bullets[0]["tailored"] == "Engineered REST APIs"

    def test_application_status_updated_to_analyzed(self, client):
        app = _create_app(client)
        with _mock_agent_ok():
            client.post("/api/v1/analyze", json={"application_id": app["id"]})
        r = client.get(f"/api/v1/applications/{app['id']}")
        assert r.json()["status"] == "analyzed"

    def test_analysis_appears_in_application_detail(self, client):
        app = _create_app(client)
        with _mock_agent_ok():
            client.post("/api/v1/analyze", json={"application_id": app["id"]})
        r = client.get(f"/api/v1/applications/{app['id']}")
        assert len(r.json()["analyses"]) == 1

    def test_multiple_analyses_stored(self, client):
        app = _create_app(client)
        with _mock_agent_ok():
            client.post("/api/v1/analyze", json={"application_id": app["id"]})
        with _mock_agent_ok():
            client.post("/api/v1/analyze", json={"application_id": app["id"]})
        r = client.get(f"/api/v1/applications/{app['id']}")
        assert len(r.json()["analyses"]) == 2


# ===========================================================================
# POST /api/v1/analyze  — error paths
# ===========================================================================

class TestTriggerAnalysisErrors:
    def test_404_for_nonexistent_application(self, client):
        r = client.post("/api/v1/analyze", json={"application_id": 99999})
        assert r.status_code == 404

    def test_502_when_agent_service_unreachable(self, client):
        app = _create_app(client)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("connection refused"))

        with patch("api.routers.analysis.httpx.AsyncClient", return_value=mock_client):
            r = client.post("/api/v1/analyze", json={"application_id": app["id"]})
        assert r.status_code == 502

    def test_504_on_agent_service_timeout(self, client):
        app = _create_app(client)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch("api.routers.analysis.httpx.AsyncClient", return_value=mock_client):
            r = client.post("/api/v1/analyze", json={"application_id": app["id"]})
        assert r.status_code == 504

    def test_502_on_agent_service_http_error(self, client):
        app = _create_app(client)
        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 500
        error_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=error_response)
        )

        with patch("api.routers.analysis.httpx.AsyncClient", return_value=mock_client):
            r = client.post("/api/v1/analyze", json={"application_id": app["id"]})
        assert r.status_code == 502

    def test_missing_application_id_returns_422(self, client):
        r = client.post("/api/v1/analyze", json={})
        assert r.status_code == 422


# ===========================================================================
# GET /api/v1/applications/{id}/analyses
# ===========================================================================

class TestListAnalyses:
    def test_empty_before_any_analysis(self, client):
        app = _create_app(client)
        r = client.get(f"/api/v1/applications/{app['id']}/analyses")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_analysis_after_trigger(self, client):
        app = _create_app(client)
        with _mock_agent_ok():
            client.post("/api/v1/analyze", json={"application_id": app["id"]})
        r = client.get(f"/api/v1/applications/{app['id']}/analyses")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["match_percentage"] == 80.0

    def test_404_for_nonexistent_application(self, client):
        r = client.get("/api/v1/applications/99999/analyses")
        assert r.status_code == 404

    def test_ordered_newest_first(self, client):
        app = _create_app(client)
        with _mock_agent_ok(_AGENT_RESPONSE | {"match_percentage": 70.0}):
            client.post("/api/v1/analyze", json={"application_id": app["id"]})
        with _mock_agent_ok(_AGENT_RESPONSE | {"match_percentage": 85.0}):
            client.post("/api/v1/analyze", json={"application_id": app["id"]})
        r = client.get(f"/api/v1/applications/{app['id']}/analyses")
        results = r.json()
        assert len(results) == 2
        # Newest (85%) should be first
        assert results[0]["match_percentage"] == 85.0