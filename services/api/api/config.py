from pydantic_settings import BaseSettings
from pydantic import field_validator


_INSECURE_DEFAULTS = {"change-me-in-production", "secret", "changeme", ""}


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@db:5432/hireiq"
    agent_service_url: str = "http://agent-service:8001"
    environment: str = "development"
    # Allowed CORS origins (comma-separated). Defaults to localhost for dev.
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    # Google OAuth
    google_client_id: str = ""
    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    # Brevo (free 300/day, no CC, no domain DNS — verify one sender email only)
    brevo_api_key: str = ""
    brevo_from_email: str = ""   # sender email you verified in Brevo dashboard
    brevo_from_name: str = "HireIQ"
    # Resend API (alternative — requires verified domain for sending to arbitrary users)
    resend_api_key: str = ""
    resend_from: str = "HireIQ <onboarding@resend.dev>"
    # SMTP / OTP email (fallback when no API key is set)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    otp_expire_minutes: int = 10
    # OTP brute-force protection
    otp_max_attempts: int = 5
    # Rate limiting
    max_analyses_per_user_per_day: int = 3
    daily_token_budget: int = 90000
    max_coach_messages_per_user_per_day: int = 5

    class Config:
        env_file = ".env"

    @field_validator("jwt_secret_key", mode="before")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if not v or v.strip() in _INSECURE_DEFAULTS or len(v.strip()) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be set to a random string of at least 32 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()