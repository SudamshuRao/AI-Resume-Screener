"""
TEST-03: Integration tests for API CRUD endpoints.

Uses the SQLite in-memory DB + TestClient fixtures from conftest.py.
No real PostgreSQL or agent service is required.
"""
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _app_payload(**overrides):
    base = {
        "company": "Acme Corp",
        "job_title": "Python Engineer",
        "job_description": "Build APIs with FastAPI and Python.",
        "resume_text": "Jane Doe. Skills: Python, FastAPI.",
    }
    base.update(overrides)
    return base


def _create(client, **overrides):
    """POST /applications and return the JSON response."""
    r = client.post("/api/v1/applications", json=_app_payload(**overrides))
    assert r.status_code == 201
    return r.json()


# ===========================================================================
# POST /api/v1/applications
# ===========================================================================

class TestCreateApplication:
    def test_creates_with_valid_payload(self, client):
        r = client.post("/api/v1/applications", json=_app_payload())
        assert r.status_code == 201
        body = r.json()
        assert body["company"] == "Acme Corp"
        assert body["job_title"] == "Python Engineer"
        assert body["status"] == "pending"
        assert body["id"] is not None

    def test_returns_none_scores_before_analysis(self, client):
        body = _create(client)
        assert body["ats_score"] is None
        assert body["match_percentage"] is None

    def test_missing_required_field_returns_422(self, client):
        payload = _app_payload()
        del payload["company"]
        r = client.post("/api/v1/applications", json=payload)
        assert r.status_code == 422

    def test_each_application_gets_unique_id(self, client):
        a = _create(client, company="Alpha")
        b = _create(client, company="Beta")
        assert a["id"] != b["id"]


# ===========================================================================
# GET /api/v1/applications
# ===========================================================================

class TestListApplications:
    def test_returns_empty_list_initially(self, client):
        r = client.get("/api/v1/applications")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_created_application(self, client):
        _create(client)
        r = client.get("/api/v1/applications")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_pagination_limit(self, client):
        for i in range(5):
            _create(client, company=f"Company {i}")
        r = client.get("/api/v1/applications?limit=3")
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_pagination_offset(self, client):
        for i in range(4):
            _create(client, company=f"Co {i}")
        r = client.get("/api/v1/applications?limit=10&offset=2")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_filter_by_status_pending(self, client):
        _create(client, company="Alpha")
        _create(client, company="Beta")
        r = client.get("/api/v1/applications?status=pending")
        assert r.status_code == 200
        for item in r.json():
            assert item["status"] == "pending"

    def test_filter_by_invalid_status_returns_422(self, client):
        r = client.get("/api/v1/applications?status=banana")
        assert r.status_code == 422


# ===========================================================================
# GET /api/v1/applications/{id}
# ===========================================================================

class TestGetApplication:
    def test_returns_full_detail(self, client):
        created = _create(client)
        r = client.get(f"/api/v1/applications/{created['id']}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == created["id"]
        assert "job_description" in body
        assert "resume_text" in body
        assert "analyses" in body

    def test_404_for_nonexistent_id(self, client):
        r = client.get("/api/v1/applications/99999")
        assert r.status_code == 404

    def test_analyses_empty_before_analysis(self, client):
        created = _create(client)
        r = client.get(f"/api/v1/applications/{created['id']}")
        assert r.json()["analyses"] == []


# ===========================================================================
# PATCH /api/v1/applications/{id}/status
# ===========================================================================

class TestUpdateStatus:
    def test_updates_to_valid_status(self, client):
        created = _create(client)
        r = client.patch(
            f"/api/v1/applications/{created['id']}/status",
            json={"status": "applied"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "applied"

    @pytest.mark.parametrize("status", ["pending", "analyzed", "applied", "rejected", "offered"])
    def test_all_valid_statuses_accepted(self, client, status):
        created = _create(client)
        r = client.patch(
            f"/api/v1/applications/{created['id']}/status",
            json={"status": status},
        )
        assert r.status_code == 200
        assert r.json()["status"] == status

    def test_invalid_status_returns_422(self, client):
        created = _create(client)
        r = client.patch(
            f"/api/v1/applications/{created['id']}/status",
            json={"status": "flying"},
        )
        assert r.status_code == 422

    def test_404_for_nonexistent_id(self, client):
        r = client.patch(
            "/api/v1/applications/99999/status",
            json={"status": "applied"},
        )
        assert r.status_code == 404


# ===========================================================================
# DELETE /api/v1/applications/{id}
# ===========================================================================

class TestDeleteApplication:
    def test_delete_returns_204(self, client):
        created = _create(client)
        r = client.delete(f"/api/v1/applications/{created['id']}")
        assert r.status_code == 204

    def test_deleted_application_not_found(self, client):
        created = _create(client)
        client.delete(f"/api/v1/applications/{created['id']}")
        r = client.get(f"/api/v1/applications/{created['id']}")
        assert r.status_code == 404

    def test_deleted_application_not_in_list(self, client):
        created = _create(client)
        client.delete(f"/api/v1/applications/{created['id']}")
        r = client.get("/api/v1/applications")
        ids = [a["id"] for a in r.json()]
        assert created["id"] not in ids

    def test_404_for_nonexistent_id(self, client):
        r = client.delete("/api/v1/applications/99999")
        assert r.status_code == 404


# ===========================================================================
# Health check
# ===========================================================================

# ===========================================================================
# Ownership scoping — user A cannot see/mutate user B's applications
# ===========================================================================

class TestOwnershipScoping:
    def _client_for_new_user(self, client, email):
        """Register a second user and return a client authenticated as that user."""
        from fastapi.testclient import TestClient
        from api.main import app
        from api.auth import create_access_token
        from api.database import get_db

        # Register via the existing client (shares the same db_session)
        r = client.post("/api/v1/register", json={"email": email, "password": "pw"})
        assert r.status_code == 201
        # Decode to get the new user's id from the token
        from jose import jwt
        from api.config import settings
        payload = jwt.decode(r.json()["access_token"], settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        new_token = create_access_token(int(payload["sub"]), email)
        return new_token

    def test_user_cannot_see_other_users_applications(self, client, db_session):
        # User 1 (default test client) creates an application
        _create(client)
        # User 2 registers and lists — should see nothing
        from api.main import app
        from api.database import get_db
        from fastapi.testclient import TestClient
        new_token = self._client_for_new_user(client, "user2@example.com")

        def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override
        with TestClient(app, headers={"Authorization": f"Bearer {new_token}"}) as c2:
            r = c2.get("/api/v1/applications")
        app.dependency_overrides.clear()

        assert r.status_code == 200
        assert r.json() == []

    def test_user_cannot_delete_other_users_application(self, client, db_session):
        created = _create(client)
        new_token = self._client_for_new_user(client, "user3@example.com")

        from api.main import app
        from api.database import get_db
        from fastapi.testclient import TestClient

        def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override
        with TestClient(app, headers={"Authorization": f"Bearer {new_token}"}) as c2:
            r = c2.delete(f"/api/v1/applications/{created['id']}")
        app.dependency_overrides.clear()

        assert r.status_code == 404


class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"