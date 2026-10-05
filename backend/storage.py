from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile


ROOT_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(os.getenv("CMMS_UPLOAD_DIR", str(ROOT_DIR / "uploads"))).resolve()
MAX_PHOTO_SIZE = 10 * 1024 * 1024
MAX_MANUAL_SIZE = 20 * 1024 * 1024


async def save_image(upload: UploadFile | None, category: str) -> tuple[str | None, str | None]:
    if upload is None or not upload.filename:
        return None, None
    data = await upload.read(MAX_PHOTO_SIZE + 1)
    if len(data) > MAX_PHOTO_SIZE:
        raise HTTPException(413, "A imagem excede o limite de 10 MB.")
    if data.startswith(b"\xff\xd8\xff"):
        suffix, mime = ".jpg", "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        suffix, mime = ".png", "image/png"
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        suffix, mime = ".webp", "image/webp"
    else:
        raise HTTPException(415, "Formato de imagem inválido. Envie JPEG, PNG ou WebP.")
    return _write(category, suffix, data), mime


async def save_pdf(upload: UploadFile | None, category: str) -> tuple[str | None, str | None]:
    if upload is None or not upload.filename:
        return None, None
    data = await upload.read(MAX_MANUAL_SIZE + 1)
    if len(data) > MAX_MANUAL_SIZE:
        raise HTTPException(413, "O manual excede o limite de 20 MB.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(415, "O manual enviado não é um PDF válido.")
    return _write(category, ".pdf", data), "application/pdf"


def _write(category: str, suffix: str, data: bytes) -> str:
    if category not in {"calls", "equipment"}:
        raise ValueError("Categoria de arquivo inválida.")
    directory = UPLOAD_DIR / category
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{suffix}"
    (directory / filename).write_bytes(data)
    return filename


def file_path(category: str, filename: str) -> Path:
    if category not in {"calls", "equipment"} or Path(filename).name != filename:
        raise HTTPException(404, "Arquivo não encontrado.")
    path = UPLOAD_DIR / category / filename
    if not path.is_file():
        raise HTTPException(404, "Arquivo não encontrado.")
    return path
