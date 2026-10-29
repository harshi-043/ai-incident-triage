"""Read a runbook file (Markdown, text or PDF) into plain text. The text is untrusted content: it is only stored and shown."""
from __future__ import annotations

import io
from pathlib import Path

from app.core.config import ALLOWED_RUNBOOK_EXTENSIONS
from app.ingestion.pipeline import safe_display_name


class RunbookError(Exception):
    """A problem with an uploaded runbook. Carries an HTTP status and a stable code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


def load_runbook(data: bytes, filename: str | None, *, max_bytes: int) -> tuple[str, str]:
    """Return (clean file name, text). Raises RunbookError for unsupported, empty, oversized or unreadable files."""
    name = safe_display_name(filename)  # strips any folder part, so a name like ../../x.md cannot point elsewhere
    extension = Path(name).suffix.lower()
    if extension not in ALLOWED_RUNBOOK_EXTENSIONS:
        raise RunbookError(415, "unsupported_runbook_type", f"Runbooks must be one of: {', '.join(ALLOWED_RUNBOOK_EXTENSIONS)}.")
    if not data:
        raise RunbookError(422, "empty_file", "The file is empty.")
    if len(data) > max_bytes:
        raise RunbookError(413, "file_too_large", f"The file is larger than {max_bytes // (1024 * 1024)} MB.")

    if extension == ".pdf":
        text = _pdf_text(data)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")  # never fails; wrong characters are better than a rejected file
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    if not text.strip():
        raise RunbookError(422, "no_text", "No readable text was found in the file.")
    return name, text


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - pypdf is in requirements.txt
        raise RunbookError(501, "pdf_unavailable", "PDF support needs the 'pypdf' package.") from None
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise RunbookError(422, "pdf_encrypted", "Encrypted PDFs are not supported.")
        pages = [(page.extract_text() or "") for page in reader.pages[:200]]  # cap the pages read
    except RunbookError:
        raise
    except Exception:  # a corrupt file can raise many kinds of errors
        raise RunbookError(422, "pdf_unreadable", "The PDF could not be read.") from None
    return "\n\n".join(p.strip() for p in pages if p.strip())


def title_from_text(text: str, filename: str) -> str:
    """Use the first Markdown heading as the title, otherwise the file name."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title[:300]
    return Path(filename).stem.replace("-", " ").replace("_", " ").title()[:300]
