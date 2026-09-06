"""Protected attachment storage abstraction for RecordGuard.

The API stores opaque object keys, never filesystem paths. The local backend is
for development/staging; production can replace it with an object-store adapter.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import uuid

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx", ".txt"}

class StorageError(RuntimeError):
    pass

class LocalObjectStorage:
    def __init__(self, root: str | None = None):
        self.root = Path(root or os.getenv("RECORDGUARD_OBJECT_ROOT", Path(__file__).resolve().parent / "attachments")).resolve()

    def _safe_path(self, object_key: str) -> Path:
        key = str(object_key or "").replace("\\", "/")
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise StorageError("Invalid object key.")
        return path

    def put_file(self, source_path: str, organization_id, patient_id, original_name: str) -> tuple[str, str]:
        source = Path(source_path)
        if not source.is_file():
            raise StorageError("Attachment file was not found.")
        ext = source.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise StorageError("Unsupported attachment type.")
        safe_name = Path(original_name or source.name).name
        if safe_name in {"", ".", ".."}:
            raise StorageError("Invalid attachment name.")
        object_key = f"{organization_id}/{patient_id}/{uuid.uuid4().hex}{ext}"
        target = self._safe_path(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return object_key, safe_name

    def open(self, object_key: str):
        path = self._safe_path(object_key)
        if not path.is_file():
            raise FileNotFoundError("Attachment not found.")
        return path.open("rb")

    def delete(self, object_key: str) -> None:
        path = self._safe_path(object_key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
