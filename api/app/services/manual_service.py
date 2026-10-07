import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.errors import AppError
from app.models import Manual
from app.repositories.manual_repository import ManualRepository
from app.services.extraction import SUPPORTED, extract, normalize


class ManualService:
    def __init__(self, repo: ManualRepository, settings: Settings):
        self.repo, self.settings = repo, settings

    def create_from_text(self, text: str) -> Manual:
        text = normalize(text)
        if not text:
            raise AppError(422, "empty_text", "Text is empty or whitespace only.")
        return self._save("text", None, None, text)

    def create_from_file(self, filename: str, data: bytes) -> Manual:
        name = Path(filename.replace("\\", "/")).name
        kind = SUPPORTED.get(Path(name).suffix.lower())
        if kind is None:
            raise AppError(415, "unsupported_file_type", "Unsupported file type. Allowed: .pdf, .docx, .md, .txt.")
        if len(data) > self.settings.max_upload_bytes:
            raise AppError(413, "file_too_large", f"File exceeds the {self.settings.max_upload_bytes // (1024 * 1024)} MB limit.")
        text = extract(kind, data)  # raises before anything is written
        manual_id = str(uuid.uuid4())
        folder = self.settings.storage_dir / "manuals" / manual_id
        folder.mkdir(parents=True)
        path = folder / name
        path.write_bytes(data)
        return self._save(kind, name, str(path), text, manual_id)

    def get(self, manual_id: str) -> Manual:
        m = self.repo.get(manual_id)
        if m is None:
            raise AppError(404, "manual_not_found", "Manual not found.")
        return m

    def _save(self, kind, filename, file_path, text, manual_id=None) -> Manual:
        return self.repo.add(Manual(
            id=manual_id or str(uuid.uuid4()), source_type=kind, original_filename=filename,
            file_path=file_path, text=text,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
