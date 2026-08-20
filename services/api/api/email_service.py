"""
Sends OTP emails.

Priority order:
  1. Brevo  — free 300/day, no CC, no domain DNS, verified sender email only
  2. Resend — RESEND_API_KEY set (requires verified domain for arbitrary recipients)
  3. SMTP   — local dev only (Railway blocks ports 465/587)
  4. Log only — dev fallback when nothing is configured
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from api.config import settings

logger = logging.getLogger(__name__)


def _sanitize_email(to_email: str) -> str:
    """Reject emails containing CRLF or null bytes to prevent header injection."""
    for ch in ("\n", "\r", "\0"):
        if ch in to_email:
            raise ValueError(f"Invalid email address: contains forbidden character {ch!r}")
    return to_email.strip()


def _build_html(otp: str) -> str:
    return f"""
    <div style="font-family:sans-serif;max-width:480px;margin:40px auto;padding:32px;
                background:#0f172a;border:1px solid #1e3a5f;border-radius:12px">
      <h2 style="color:#38bdf8;margin-top:0;letter-spacing:-0.02em">HireIQ</h2>
      <p style="color:#94a3b8">Use the code below to sign in to your account:</p>
      <div style="font-size:44px;font-weight:800;letter-spacing:12px;
                  color:#f1f5f9;padding:28px 0;text-align:center;
                  background:#1e293b;border-radius:8px;margin:20px 0">{otp}</div>
      <p style="color:#64748b;font-size:14px;line-height:1.6">
        This code expires in <strong style="color:#94a3b8">{settings.otp_expire_minutes} minutes</strong>
        and can only be used once.<br>
        If you didn't request this, you can safely ignore it.
      </p>
    </div>
    """


def _build_plain(otp: str) -> str:
    return (
        f"Your HireIQ sign-in code is: {otp}\n\n"
        f"This code expires in {settings.otp_expire_minutes} minutes and can only be used once.\n"
        "If you didn't request this, you can safely ignore it."
    )


def send_otp_email(to_email: str, otp: str) -> None:
    to_email = _sanitize_email(to_email)
    html  = _build_html(otp)
    plain = _build_plain(otp)

    # ── 1. Brevo (free, no domain DNS, just verified sender email) ───────────
    if settings.brevo_api_key and settings.brevo_from_email:
        try:
            resp = httpx.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": settings.brevo_api_key,
                    "Content-Type": "application/json",
                    "accept": "application/json",
                },
                json={
                    "sender": {
                        "name":  settings.brevo_from_name,
                        "email": settings.brevo_from_email,
                    },
                    "to": [{"email": to_email}],
                    "subject": "Your HireIQ sign-in code",
                    "htmlContent": html,
                    "textContent": plain,
                },
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                logger.info("BREVO: email sent to=%s", to_email)
                return
            logger.error("BREVO: unexpected status %d for to=%s body=%s",
                         resp.status_code, to_email, resp.text)
            raise RuntimeError(f"Brevo returned {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.error("BREVO: FAILED to=%s error=%r — trying next provider", to_email, exc)

    # ── 2. Resend (requires verified domain for arbitrary recipients) ─────────
    if settings.resend_api_key:
        try:
            import resend
            resend.api_key = settings.resend_api_key
            resend.Emails.send({
                "from":    settings.resend_from,
                "to":      [to_email],
                "subject": "Your HireIQ sign-in code",
                "html":    html,
                "text":    plain,
            })
            logger.info("RESEND: email sent to=%s", to_email)
            return
        except Exception as exc:
            logger.error("RESEND: FAILED to=%s error=%r — trying next provider", to_email, exc)

    # ── 3. SMTP ───────────────────────────────────────────────────────────────
    if settings.smtp_user:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your HireIQ sign-in code"
        msg["From"]    = settings.smtp_from or settings.smtp_user
        msg["To"]      = to_email
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html,  "html"))
        try:
            if settings.smtp_port == 465:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as s:
                    s.login(settings.smtp_user, settings.smtp_password)
                    s.sendmail(settings.smtp_user, to_email, msg.as_string())
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
                    s.ehlo(); s.starttls()
                    s.login(settings.smtp_user, settings.smtp_password)
                    s.sendmail(settings.smtp_user, to_email, msg.as_string())
            logger.info("SMTP: email sent to=%s", to_email)
            return
        except Exception as exc:
            logger.error("SMTP: FAILED to=%s error=%r", to_email, exc, exc_info=True)
            raise

    # ── 4. No provider configured — log the OTP so dev flows still work ───────
    logger.warning(
        "No email provider configured — OTP for %s is: %s (expires in %d min)",
        to_email, otp, settings.otp_expire_minutes,
    )
    # Raise so auth.py falls back to returning OTP in the response
    raise RuntimeError("No email provider configured")