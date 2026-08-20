"""
Tests for POST /api/v1/resume/extract  (AI-05)
"""
import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf_bytes(text: str = "Hello, world! This is a test resume.") -> bytes:
    """Return a minimal valid PDF with one text page using pypdf.PdfWriter."""
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, ArrayObject, NumberObject, DictionaryObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestResumeExtract:

    def test_non_pdf_returns_400(self, client):
        """Uploading a non-PDF file returns 400."""
        data = b"this is plain text, not a pdf"
        response = client.post(
            "/api/v1/resume/extract",
            files={"file": ("resume.txt", io.BytesIO(data), "text/plain")},
        )
        assert response.status_code == 400
        assert "PDF" in response.json()["detail"]

    def test_oversized_file_returns_400(self, client):
        """A file exceeding 5 MB returns 400."""
        big = b"%PDF-1.4 " + b"x" * (5 * 1024 * 1024 + 1)
        response = client.post(
            "/api/v1/resume/extract",
            files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")},
        )
        assert response.status_code == 400
        assert "5 MB" in response.json()["detail"]

    def test_image_only_pdf_returns_422(self, client):
        """A PDF with no extractable text returns 422."""
        pdf_bytes = _make_pdf_bytes()

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader):
            response = client.post(
                "/api/v1/resume/extract",
                files={"file": ("image.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            )

        assert response.status_code == 422
        assert "No text" in response.json()["detail"]

    def test_valid_pdf_returns_text_and_pages(self, client):
        """A parseable PDF returns extracted text and page count."""
        pdf_bytes = _make_pdf_bytes()

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "John Doe\nSoftware Engineer\nPython, FastAPI"

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader):
            response = client.post(
                "/api/v1/resume/extract",
                files={"file": ("resume.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["pages"] == 1
        assert "John Doe" in body["text"]

    def test_unauthenticated_returns_401(self):
        """Request without a Bearer token returns 401."""
        with TestClient(app) as c:
            pdf_bytes = _make_pdf_bytes()
            response = c.post(
                "/api/v1/resume/extract",
                files={"file": ("resume.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            )
        assert response.status_code == 401

    def test_missing_file_returns_422(self, client):
        """Omitting the file field returns 422."""
        response = client.post("/api/v1/resume/extract")
        assert response.status_code == 422

    def test_octet_stream_content_type_accepted(self, client):
        """application/octet-stream is allowed as a fallback content-type."""
        pdf_bytes = _make_pdf_bytes()

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Resume content here"

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader):
            response = client.post(
                "/api/v1/resume/extract",
                files={"file": ("resume.pdf", io.BytesIO(pdf_bytes), "application/octet-stream")},
            )

        assert response.status_code == 200
        assert response.json()["pages"] == 1