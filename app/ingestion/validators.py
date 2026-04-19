import zipfile
from io import BytesIO

from app.config import settings
from app.exceptions import ValidationError

_MAX_UNCOMPRESSED_MB = 500  # zip-bomb guard


def validate_zip_file(filename: str, content: bytes) -> None:
    if not filename.lower().endswith(".zip"):
        raise ValidationError("file", f"'{filename}' must have a .zip extension.")

    if not zipfile.is_zipfile(BytesIO(content)):
        raise ValidationError("file", f"'{filename}' is not a valid ZIP archive.")


def extract_txt_files(content: bytes) -> list[tuple[str, bytes]]:
    """Extract all .txt files from a ZIP, returning (filename, bytes) pairs."""
    results: list[tuple[str, bytes]] = []
    total_uncompressed = 0

    with zipfile.ZipFile(BytesIO(content)) as zf:
        for info in zf.infolist():
            # Skip directories and macOS metadata
            if info.is_dir():
                continue
            name = info.filename
            if "__MACOSX" in name or name.startswith("."):
                continue
            if not name.lower().endswith(".txt"):
                continue

            total_uncompressed += info.file_size
            if total_uncompressed / (1024 * 1024) > _MAX_UNCOMPRESSED_MB:
                raise ValidationError(
                    "file",
                    f"Uncompressed content exceeds {_MAX_UNCOMPRESSED_MB}MB limit.",
                )

            bare_name = name.split("/")[-1] or name
            file_bytes = zf.read(info.filename)
            results.append((bare_name, file_bytes))

    return results


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


def validate_batch(file_count: int, total_content: int) -> None:
    if file_count > settings.max_files_per_upload:
        raise ValidationError(
            "files",
            f"Too many files: {file_count}. Maximum is {settings.max_files_per_upload}.",
        )
    total_mb = total_content / (1024 * 1024)
    if total_mb > 200:
        raise ValidationError("files", f"Total batch size {total_mb:.1f}MB exceeds 200MB limit.")
