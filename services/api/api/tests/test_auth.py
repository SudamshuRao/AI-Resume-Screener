"""
AUTH-02 tests: register and login endpoints.
"""
import pytest


class TestRegister:
    def test_register_returns_token(self, client):
        r = client.post("/api/v1/register", json={"email": "new@example.com", "password": "secret123"})
        assert r.status_code == 201
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_register_duplicate_email_returns_409(self, client):
        client.post("/api/v1/register", json={"email": "dup@example.com", "password": "pass1"})
        r = client.post("/api/v1/register", json={"email": "dup@example.com", "password": "pass2"})
        assert r.status_code == 409

    def test_register_missing_email_returns_422(self, client):
        r = client.post("/api/v1/register", json={"password": "secret123"})
        assert r.status_code == 422

    def test_register_missing_password_returns_422(self, client):
        r = client.post("/api/v1/register", json={"email": "x@example.com"})
        assert r.status_code == 422


class TestLogin:
    def test_login_valid_credentials_returns_token(self, client):
        client.post("/api/v1/register", json={"email": "user@example.com", "password": "mypassword"})
        r = client.post("/api/v1/login", json={"email": "user@example.com", "password": "mypassword"})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password_returns_401(self, client):
        client.post("/api/v1/register", json={"email": "user2@example.com", "password": "correct"})
        r = client.post("/api/v1/login", json={"email": "user2@example.com", "password": "wrong"})
        assert r.status_code == 401

    def test_login_nonexistent_email_returns_401(self, client):
        r = client.post("/api/v1/login", json={"email": "nobody@example.com", "password": "pass"})
        assert r.status_code == 401

    def test_login_token_is_valid_jwt(self, client):
        from jose import jwt
        from api.config import settings
        client.post("/api/v1/register", json={"email": "jwt@example.com", "password": "pass"})
        r = client.post("/api/v1/login", json={"email": "jwt@example.com", "password": "pass"})
        token = r.json()["access_token"]
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["email"] == "jwt@example.com"
        assert "sub" in payload
        assert "exp" in payload