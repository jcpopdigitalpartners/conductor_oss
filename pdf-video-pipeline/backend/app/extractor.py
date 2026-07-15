from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO


@dataclass
class ExtractedPdfContent:
    text: str
    markdown: str
    page_count: int
    scanned_page_ratio: float
    parser_used: str
    fallback_used: bool


def _docling_extract(filename: str, pdf_bytes: bytes) -> ExtractedPdfContent | None:
    try:
        from docling.datamodel.base_models import DocumentStream
        from docling.document_converter import DocumentConverter
    except ImportError:
        return None

    converter = DocumentConverter()
    result = converter.convert(DocumentStream(name=filename, stream=BytesIO(pdf_bytes)))
    document = result.document
    markdown = document.export_to_markdown().strip()
    text = markdown
    if not text:
        return None
    pages = getattr(document, "pages", None)
    page_count = len(pages) if pages is not None else max(1, markdown.count("\n# "))

    return ExtractedPdfContent(
        text=text,
        markdown=markdown,
        page_count=max(1, page_count),
        scanned_page_ratio=0.0 if text.strip() else 1.0,
        parser_used="docling",
        fallback_used=False,
    )


def _pypdf_extract(filename: str, pdf_bytes: bytes) -> ExtractedPdfContent | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    reader = PdfReader(BytesIO(pdf_bytes))
    page_text = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n".join(filter(None, page_text)).strip()

    if not text:
        text = (
            f"{filename} was uploaded for PDF-to-video conversion, but text extraction returned no body text. "
            "Treat this as a scanned or image-heavy document until OCR is configured."
        )

    return ExtractedPdfContent(
        text=text,
        markdown=text,
        page_count=max(1, len(reader.pages)),
        scanned_page_ratio=1.0 if not any(page_text) else 0.0,
        parser_used="pypdf",
        fallback_used=True,
    )


def extract_pdf_content(filename: str, pdf_bytes: bytes) -> ExtractedPdfContent:
    for extractor in (_docling_extract, _pypdf_extract):
        try:
            result = extractor(filename, pdf_bytes)
        except Exception:
            result = None
        if result is not None:
            return result

    fallback_text = (
        f"{filename} was uploaded through the review UI for PDF-to-video conversion. "
        f"The source PDF size is {len(pdf_bytes)} bytes. "
        "No PDF extraction backend is installed yet, so the parser generated a placeholder summary."
    )
    return ExtractedPdfContent(
        text=fallback_text,
        markdown=fallback_text,
        page_count=1,
        scanned_page_ratio=0.0,
        parser_used="placeholder",
        fallback_used=True,
    )
