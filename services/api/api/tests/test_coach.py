"""
AI-03 tests: POST /api/v1/coach conversational endpoint.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _create_app(client):
    r = client.post("/api/v1/applications", json={
        "company": "TechCorp",
        "job_title": "Python Engineer",
        "job_description": "FastAPI, Python, Kubernetes",
        "resume_text": "Jane Doe. Python, FastAPI.",
    })
    assert r.status_code == 201
    return r.json()


def _mock_agent_analyze():
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "session_id": "abc",
        "gap_analysis": {"match_percentage": 80.0, "missing_skills": ["Kubernetes"]},
        "tailored_bullets": [],
        "cover_letter": "Dear Hiring Manager...",
        "interview_qa": [],
        "ats_score": {"score": 80},
        "match_percentage": 80.0,
        "input_tokens": 100,
        "output_tokens": 200,
    }
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)
    return patch("api.routers.analysis.httpx.AsyncClient", return_value=mock_client)


def _mock_coach_ok(answer="Great question! Here is my advice."):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"answer": answer}
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)
    return patch("api.routers.coach.httpx.AsyncClient", return_value=mock_client)


class TestCoach:
    def _setup(self, client):
        """Create an app, run analysis, return app id."""
        app = _create_app(client)
        with _mock_agent_analyze():
            client.post("/api/v1/analyze", json={"application_id": app["id"]})
        return app["id"]

    def test_returns_answer(self, client):
        app_id = self._setup(client)
        with _mock_coach_ok("Focus on Kubernetes experience."):
            r = client.post("/api/v1/coach", json={
                "application_id": app_id,
                "question": "What should I improve?",
            })
        assert r.status_code == 200
        assert r.json()["answer"] == "Focus on Kubernetes experience."

    def test_404_no_application(self, client):
        r = client.post("/api/v1/coach", json={
            "application_id": 99999,
            "question": "What should I do?",
        })
        assert r.status_code == 404

    def test_404_no_analysis_yet(self, client):
        app = _create_app(client)
        r = client.post("/api/v1/coach", json={
            "application_id": app["id"],
            "question": "Help me",
        })
        assert r.status_code == 404
        assert "analyze" in r.json()["detail"].lower()

    def test_502_agent_unreachable(self, client):
        app_id = self._setup(client)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("down"))
        with patch("api.routers.coach.httpx.AsyncClient", return_value=mock_client):
            r = client.post("/api/v1/coach", json={
                "application_id": app_id,
                "question": "Help",
            })
        assert r.status_code == 502

    def test_504_timeout(self, client):
        app_id = self._setup(client)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with patch("api.routers.coach.httpx.AsyncClient", return_value=mock_client):
            r = client.post("/api/v1/coach", json={
                "application_id": app_id,
                "question": "Help",
            })
        assert r.status_code == 504

    def test_missing_question_returns_422(self, client):
        r = client.post("/api/v1/coach", json={"application_id": 1})
        assert r.status_code == 422