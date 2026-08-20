import io
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi import status as http_status
from pydantic import BaseModel

from api.auth import get_current_user
from api.models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["resume"])

_MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB


class ResumeTextResponse(BaseModel):
    text: str
    pages: int


@router.post("/resume/extract", response_model=ResumeTextResponse)
async def extract_resume_text(
    file: UploadFile = File(..., description="PDF resume file (max 5 MB)"),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a PDF resume and extract its plain text.

    Returns the extracted text and page count. The text can then be passed
    directly to `POST /api/v1/applications` as the `resume_text` field.

    Raises **400** if the file is not a PDF or exceeds 5 MB.
    Raises **422** if the PDF cannot be parsed.
    """
    logger.info(
        "Resume upload received: filename=%r content_type=%r user=%d",
        file.filename,
        file.content_type,
        current_user.id,
    )

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        logger.warning(
            "Rejected non-PDF upload: filename=%r content_type=%r user=%d",
            file.filename,
            file.content_type,
            current_user.id,
        )
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted.",
        )

    raw = await file.read()

    if len(raw) > _MAX_PDF_BYTES:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds the 5 MB limit ({len(raw) // 1024} KB received).",
        )

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        pages = len(reader.pages)

        # Try layout-aware extraction first (preserves columns/spacing better),
        # fall back to plain extraction per page if layout mode fails.
        text_parts = []
        for page in reader.pages:
            extracted = ""
            try:
                extracted = page.extract_text(extraction_mode="layout") or ""
            except Exception:
                pass
            if not extracted.strip():
                extracted = page.extract_text() or ""
            if extracted.strip():
                text_parts.append(extracted)

        text = "\n\n".join(text_parts).strip()
    except Exception as exc:
        logger.warning("PDF parse failed for user=%d: %s", current_user.id, exc)
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not parse the PDF. Please ensure it is a valid, text-based PDF.",
        ) from exc

    if not text:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text could be extracted. The PDF may be image-only or use embedded fonts — please paste your resume text manually.",
        )

    logger.info(
        "Extracted %d chars from %d-page PDF for user=%d",
        len(text),
        pages,
        current_user.id,
    )
    return ResumeTextResponse(text=text, pages=pages)