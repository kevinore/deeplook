from app.config import settings
from app.exceptions import ValidationError


def validate_upload_file(filename: str, content: bytes) -> None:
    if not filename.lower().endswith(".txt"):
        raise ValidationError("file", f"'{filename}' must have a .txt extension.")

    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise ValidationError(
            "file",
            f"'{filename}' is {size_mb:.1f}MB, exceeding the {settings.max_upload_size_mb}MB limit.",
        )

    for encoding in ("utf-8", "latin-1"):
        try:
            content.decode(encoding)
            return
        except (UnicodeDecodeError, ValueError):
            continue

    raise ValidationError("file", f"'{filename}' could not be decoded as UTF-8 or Latin-1.")


def validate_batch(files: list, total_content: int) -> None:
    if len(files) > settings.max_files_per_upload:
        raise ValidationError(
            "files",
            f"Too many files: {len(files)}. Maximum is {settings.max_files_per_upload}.",
        )
    total_mb = total_content / (1024 * 1024)
    if total_mb > 200:
        raise ValidationError("files", f"Total batch size {total_mb:.1f}MB exceeds 200MB limit.")
