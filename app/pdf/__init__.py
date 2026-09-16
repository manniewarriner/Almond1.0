"""Deterministic, local, branded PDF generation. No cloud, no model inference."""

from __future__ import annotations

from app.pdf.service import PdfResult, create_branded_pdf

__all__ = ["PdfResult", "create_branded_pdf"]
