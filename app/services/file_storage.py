from dataclasses import dataclass
from mimetypes import guess_type
from pathlib import Path
from uuid import uuid4

from aiogram import Bot
from aiogram.types import Document, PhotoSize


@dataclass(slots=True)
class StoredFile:
    storage_path: str
    original_filename: str
    telegram_file_id: str
    telegram_file_unique_id: str
    mime_type: str | None
    file_size: int | None


class FileStorage:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    async def save_document(self, bot: Bot, document: Document) -> StoredFile:
        extension = Path(document.file_name or "").suffix
        filename = f"{uuid4().hex}{extension}"
        target_path = self.root_dir / filename
        await bot.download(document, destination=target_path)
        return StoredFile(
            storage_path=str(target_path),
            original_filename=document.file_name or filename,
            telegram_file_id=document.file_id,
            telegram_file_unique_id=document.file_unique_id,
            mime_type=document.mime_type,
            file_size=document.file_size,
        )

    async def save_photo(self, bot: Bot, photo: PhotoSize) -> StoredFile:
        filename = f"{uuid4().hex}.jpg"
        target_path = self.root_dir / filename
        await bot.download(photo, destination=target_path)
        mime_type, _ = guess_type(filename)
        return StoredFile(
            storage_path=str(target_path),
            original_filename=filename,
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            mime_type=mime_type,
            file_size=photo.file_size,
        )
