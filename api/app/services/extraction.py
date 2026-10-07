"""Pure functions: bytes -> normalized text. No HTTP, no DB."""
from io import BytesIO

from app.errors import AppError

SUPPORTED = {".pdf": "pdf", ".docx": "docx", ".md": "md", ".txt": "txt"}


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _corrupt() -> AppError:
    return AppError(422, "invalid_request", "The file could not be read; it may be corrupt.")


def _plain(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AppError(422, "invalid_encoding", "The file is not valid UTF-8 text.")


def _docx(data: bytes) -> str:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(BytesIO(data))
        lines: list[str] = []
        for child in doc.element.body.iterchildren():  # keeps document order
            if child.tag.endswith("}p"):
                lines.append(Paragraph(child, doc).text)
            elif child.tag.endswith("}tbl"):
                for row in Table(child, doc).rows:
                    lines.append("\t".join(c.text for c in row.cells))
        return "\n".join(lines)
    except Exception:
        raise _corrupt()


def _pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        raise _corrupt()


def extract(kind: str, data: bytes) -> str:
    raw = {"pdf": _pdf, "docx": _docx}.get(kind, _plain)(data)
    text = normalize(raw)
    if not text:
        raise AppError(422, "no_readable_text", "No readable text found in the file.")
    return text
