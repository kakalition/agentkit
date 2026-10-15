from __future__ import annotations

import pytest

from agentkit.config import AgentSettings
from agentkit.ingest import (
    IngestError,
    docx_to_text,
    extract_text,
    fetch_url,
    guard_size,
    html_to_text,
    pdf_to_text,
    text_from_bytes,
)
from agentkit.knowledge import KnowledgeBase
from agentkit.runtime import build_runtime


def test_html_to_text_strips_markup_and_scripts():
    text = html_to_text(
        "<html><head><style>x{}</style><script>alert(1)</script></head>"
        "<body><h1>Title</h1><p>Hello   world</p></body></html>"
    )
    assert "Title" in text and "Hello world" in text
    assert "alert" not in text and "x{}" not in text


def test_extract_text_txt_and_unsupported(tmp_path):
    md = tmp_path / "note.md"
    md.write_text("# Heading\n\nbody text", encoding="utf-8")
    assert "body text" in extract_text(md)

    html = tmp_path / "page.html"
    html.write_text("<p>hi <b>there</b></p>", encoding="utf-8")
    assert extract_text(html) == "hi there"

    binary = tmp_path / "thing.bin"
    binary.write_bytes(b"\x00\x01")
    with pytest.raises(IngestError):
        extract_text(binary)


def test_size_guard(tmp_path):
    settings = AgentSettings(owner_id="o", agent_home=tmp_path, ingest_max_bytes=4)
    big = tmp_path / "big.txt"
    big.write_text("way too long", encoding="utf-8")
    with pytest.raises(IngestError):
        extract_text(big, settings=settings)
    with pytest.raises(IngestError):
        guard_size(10, settings)


def test_docx_roundtrip(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Hello from docx")
    path = tmp_path / "doc.docx"
    document.save(path)
    assert "Hello from docx" in extract_text(path)
    assert "Hello from docx" in docx_to_text(path.read_bytes())


def test_pdf_parser_handles_bytes():
    pypdf = pytest.importorskip("pypdf")
    import io

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    # a blank page extracts to empty text without raising
    assert pdf_to_text(buffer.getvalue()) == ""
    assert text_from_bytes(buffer.getvalue(), ".pdf") == ""


async def test_fetch_url_scheme_guard(tmp_path):
    settings = AgentSettings(owner_id="o", agent_home=tmp_path, ingest_allowed_schemes=["http"])
    with pytest.raises(IngestError):
        await fetch_url("ftp://example.com/file", settings=settings)


async def test_knowledge_add_file_and_url_guard(tmp_path):
    settings = AgentSettings(owner_id="o", agent_home=tmp_path, memory_embedding_backend="hash")
    build_runtime(settings)
    kb = KnowledgeBase.from_settings(settings)

    doc = tmp_path / "doc.txt"
    doc.write_text("Mochi is a grey cat.", encoding="utf-8")
    assert await kb.add_file(doc) >= 1
    assert any(source.endswith("doc.txt") for source in await kb.sources())

    with pytest.raises(IngestError):
        await kb.add_url("ftp://example.com")
