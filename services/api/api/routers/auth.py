import asyncio
import hmac
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from api.auth import create_access_token, get_current_user, hash_password, verify_password
from api.config import settings
from api.database import get_db
from api.models import User
from api.schemas import GoogleAuthRequest, OTPRequest, OTPVerify, Token, UserCreate, UserResponse

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=Token, status_code=http_status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def register(request: Request, payload: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user account and return a JWT access token.

    Raises **409** if the email is already in use.
    """
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("Registered new user id=%d email=%s", user.id, user.email)
    return Token(access_token=create_access_token(user.id, user.email))


@router.post("/login", response_model=Token)
@limiter.limit("20/minute")
def login(request: Request, payload: UserCreate, db: Session = Depends(get_db)):
    """
    Authenticate with email + password and return a JWT access token.

    Raises **401** for invalid credentials.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info("User id=%d logged in", user.id)
    return Token(access_token=create_access_token(user.id, user.email))


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user


# ---------------------------------------------------------------------------
# OTP-based passwordless auth
# ---------------------------------------------------------------------------

def _hash_otp(otp: str) -> str:
    """HMAC-SHA256 hash using the JWT secret as the key, preventing rainbow-table precomputation."""
    return hmac.new(
        settings.jwt_secret_key.encode(),
        otp.encode(),
        hashlib.sha256,
    ).hexdigest()


@router.post("/otp/request", status_code=http_status.HTTP_200_OK)
@limiter.limit("5/minute")
async def otp_request(request: Request, payload: OTPRequest, db: Session = Depends(get_db)):
    """
    Send a 6-digit OTP to the given email address.

    Creates the user account automatically on first use (passwordless sign-up).
    Always returns 200 so callers can't enumerate registered emails.
    """
    email = payload.email.strip().lower()
    logger.info("OTP_REQUEST: received for email=%s", email)

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email)
        db.add(user)
        db.flush()
        logger.info("OTP_REQUEST: auto-created new user email=%s id=%s", email, user.id)
    else:
        logger.info("OTP_REQUEST: existing user email=%s id=%s", email, user.id)

    otp = f"{secrets.randbelow(1_000_000):06d}"
    user.otp_hash = _hash_otp(otp)
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)
    db.commit()
    logger.info("OTP_REQUEST: OTP generated and saved to DB for email=%s expires=%s", email, user.otp_expires_at)

    logger.info("OTP_REQUEST: OTP ready for screen delivery email=%s", email)
    return {"detail": f"OTP sent to {email}", "otp": otp}


@router.post("/otp/verify", response_model=Token)
@limiter.limit("10/minute")
def otp_verify(request: Request, payload: OTPVerify, db: Session = Depends(get_db)):
    """
    Verify the OTP and return a JWT access token.

    Raises **401** for invalid or expired OTPs.
    """
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    invalid_exc = HTTPException(
        status_code=http_status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired OTP.",
    )

    if user is None or user.otp_hash is None or user.otp_expires_at is None:
        raise invalid_exc

    # Check expiry. otp_expires_at is stored as UTC but PostgreSQL strips tzinfo on
    # retrieval, yielding a naive datetime. We know it was stored as UTC, so we
    # safely reattach UTC tzinfo before comparing with the aware datetime.now().
    expires = user.otp_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        raise invalid_exc

    # Brute-force protection: track failed attempts
    attempts = (user.otp_attempts or 0) + 1
    if user.otp_hash != _hash_otp(payload.otp.strip()):
        user.otp_attempts = attempts
        if attempts >= settings.otp_max_attempts:
            # Invalidate OTP after too many failures
            user.otp_hash = None
            user.otp_expires_at = None
            user.otp_attempts = 0
            db.commit()
            logger.warning("OTP locked out after %d attempts for email=%s", attempts, email)
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many incorrect attempts. Request a new OTP.",
            )
        db.commit()
        raise invalid_exc

    # OTP correct — clear it immediately (one-time use)
    user.otp_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    db.commit()

    logger.info("OTP verified for user id=%d email=%s", user.id, user.email)
    return Token(access_token=create_access_token(user.id, user.email))


@router.post("/google", response_model=Token)
@limiter.limit("20/minute")
def google_auth(request: Request, payload: GoogleAuthRequest, db: Session = Depends(get_db)):
    """
    Authenticate via Google Sign-In.

    Verifies the Google ID token, then either logs in an existing user or
    creates a new account (with a random secure password) and returns a JWT.

    Raises **400** if the token is invalid or GOOGLE_CLIENT_ID is not configured.
    """
    if not settings.google_client_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Google Sign-In is not configured on this server.",
        )

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
        id_info = google_id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as exc:
        logger.warning("Google token verification failed: %s", exc)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid Google credential.",
        ) from exc

    email: str = id_info.get("email", "")
    if not email:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Google token did not contain an email address.",
        )

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        random_password = secrets.token_hex(32)
        user = User(email=email, hashed_password=hash_password(random_password))
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Auto-created user via Google Sign-In id=%d email=%s", user.id, user.email)
    else:
        logger.info("Google Sign-In for existing user id=%d email=%s", user.id, user.email)

    return Token(access_token=create_access_token(user.id, user.email))