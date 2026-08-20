from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from api.database import Base


class User(Base):
    """Registered user account."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # OTP-based authentication
    otp_hash = Column(String, nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    otp_attempts = Column(Integer, default=0, nullable=False)

    applications = relationship("JobApplication", back_populates="user", cascade="all, delete-orphan")


class JobApplication(Base):
    """Represents a single job application submitted by a user."""

    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company = Column(String, nullable=False)
    job_title = Column(String, nullable=False)
    job_description = Column(Text, nullable=False)
    resume_text = Column(Text, nullable=False)
    # Lifecycle: pending → analyzed → applied → rejected | offered
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    analyses = relationship("AnalysisResult", back_populates="application", cascade="all, delete-orphan")
    user = relationship("User", back_populates="applications")


class AnalysisResult(Base):
    """Stores the multi-agent analysis output for a job application."""

    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("job_applications.id"), nullable=False)
    session_id = Column(String, nullable=False)
    ats_score = Column(Integer)
    match_percentage = Column(Float)
    gap_analysis = Column(Text)       # stored as JSON string
    tailored_bullets = Column(Text)   # stored as JSON string
    cover_letter = Column(Text)
    interview_qa = Column(Text)       # stored as JSON string
    ats_details = Column(Text)        # full ATS dict stored as JSON string
    company_research = Column(Text)   # stored as JSON string
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    application = relationship("JobApplication", back_populates="analyses")


class CoachLog(Base):
    """Tracks per-user coach (LLM follow-up) calls for rate limiting."""

    __tablename__ = "coach_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))