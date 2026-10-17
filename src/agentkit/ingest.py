"""Extract plain text from documents and URLs for knowledge-base ingestion.

Supported: plain text/markdown/CSV/JSON, HTML (``beautifulsoup4``), PDF (``pypdf``),
DOCX (``python-docx``), and URLs (``httpx``). Parsers are imported lazily so a
missing optional library only affects the format that needs it. Size and scheme
guards come from settings (``ingest_max_bytes`` / ``ingest_allowed_schemes``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentkit.contracts.ingest import DocumentLoader
from agentkit.errors import DependencyMissing, InvalidInput
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DriverKind, IngestDriver
from agentkit.support.manager import Manager

TEXT_SUFFIXES = frozenset({".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".log", ".yaml", ".yml"})
HTML_SUFFIXES = frozenset({".html", ".htm"})
PDF_SUFFIXES = frozenset({".pdf"})
DOCX_SUFFIXES = frozenset({".docx"})
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | HTML_SUFFIXES | PDF_SUFFIXES | DOCX_SUFFIXES


class IngestError(InvalidInput):
    """Raised when a source cannot be ingested (unsupported/oversized/blocked)."""


def _max_bytes(settings: Any) -> int:
    return int(getattr(settings, "ingest_max_bytes", 5_000_000) or 5_000_000)


def guard_size(size: int, settings: Any = None) -> None:
    limit = _max_bytes(settings)
    if size > limit:
        raise IngestError(f"source is {size} bytes, over the {limit}-byte limit")


def html_to_text(markup: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except Exception as exc:  # pragma: no cover - optional dependency
        raise DependencyMissing("beautifulsoup4 is required for HTML ingestion") from exc
    soup = BeautifulSoup(markup, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - optional dependency
        raise DependencyMissing("pypdf is required for PDF ingestion") from exc
    import io

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def docx_to_text(data: bytes) -> str:
    try:
        from docx import Document
    except Exception as exc:  # pragma: no cover - optional dependency
        raise DependencyMissing("python-docx is required for DOCX ingestion") from exc
    import io

    document = Document(io.BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()


def text_from_bytes(data: bytes, suffix: str) -> str:
    """Dispatch raw bytes to the right parser by file suffix."""
    suffix = suffix.lower()
    if suffix in PDF_SUFFIXES:
        return pdf_to_text(data)
    if suffix in DOCX_SUFFIXES:
        return docx_to_text(data)
    decoded = data.decode("utf-8", errors="ignore")
    if suffix in HTML_SUFFIXES:
        return html_to_text(decoded)
    return decoded


def extract_text(path: str | Path, *, settings: Any = None) -> str:
    """Read and extract text from a local file (guarded by size/suffix)."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise IngestError(f"file not found: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise IngestError(f"unsupported file type: {suffix or path.name}")
    guard_size(path.stat().st_size, settings)
    data = path.read_bytes()
    return text_from_bytes(data, suffix)


async def fetch_url(url: str, *, settings: Any = None) -> str:
    """Fetch a URL and extract its text (scheme + size guarded, SSRF-checked)."""
    from urllib.parse import urlsplit

    from agentkit.guardrails import check_egress

    allowed = set(getattr(settings, "ingest_allowed_schemes", ["http", "https"]) or [])
    scheme = urlsplit(url).scheme.lower()
    if scheme not in allowed:
        raise IngestError(f"scheme {scheme!r} is not allowed (allow: {sorted(allowed)})")
    if not check_egress(url):
        raise IngestError(f"refusing to fetch {url!r} (blocked host)")
    import httpx

    timeout = float(getattr(settings, "ingest_timeout", 20.0) or 20.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    suffix = ".html" if "html" in content_type else ".txt"
    text = text_from_bytes(response.content, suffix)
    guard_size(len(text.encode("utf-8")), settings)
    return text


class DefaultDocumentLoader:
    """The default loader: every supported format (text, HTML, PDF, DOCX)."""

    def supports(self, suffix: str) -> bool:
        return (suffix or "").lower() in SUPPORTED_SUFFIXES

    def load(
        self,
        source: str | Path | bytes,
        *,
        suffix: str | None = None,
        settings: Any = None,
    ) -> str:
        if isinstance(source, bytes):
            resolved = (suffix or ".txt").lower()
            guard_size(len(source), settings)
            return text_from_bytes(source, resolved)
        return extract_text(source, settings=settings)


class TextDocumentLoader:
    """A text-only loader (no PDF/DOCX/HTML parsing) for minimal deployments."""

    def supports(self, suffix: str) -> bool:
        return (suffix or "").lower() in TEXT_SUFFIXES

    def load(
        self,
        source: str | Path | bytes,
        *,
        suffix: str | None = None,
        settings: Any = None,
    ) -> str:
        if isinstance(source, bytes):
            guard_size(len(source), settings)
            return source.decode("utf-8", errors="ignore")
        path = Path(source).expanduser()
        if not path.is_file():
            raise IngestError(f"file not found: {path}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            raise IngestError(f"unsupported file type: {path.suffix or path.name}")
        guard_size(path.stat().st_size, settings)
        return path.read_text(encoding="utf-8", errors="ignore")


class IngestManager(Manager):
    """Resolves the configured document loader (``ingest_driver``, default ``default``)."""

    kind = DriverKind.INGEST
    default_driver = IngestDriver.DEFAULT


@register_driver(DriverKind.INGEST, IngestDriver.DEFAULT)
class DefaultLoaderDriver(Driver):
    def build(self) -> DefaultDocumentLoader:
        return DefaultDocumentLoader()
@register_driver(DriverKind.INGEST, IngestDriver.TEXT)
class TextLoaderDriver(Driver):
    def build(self) -> TextDocumentLoader:
        return TextDocumentLoader()
__all__ = [
    "SUPPORTED_SUFFIXES",
    "DefaultDocumentLoader",
    "DocumentLoader",
    "IngestError",
    "IngestManager",
    "TextDocumentLoader",
    "docx_to_text",
    "extract_text",
    "fetch_url",
    "guard_size",
    "html_to_text",
    "pdf_to_text",
    "text_from_bytes",
]
