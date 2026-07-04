from pathlib import Path
from urllib.parse import urlparse

# Support is based on popularity and support in AI models

KNOWN_IMAGE_FORMATS = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "tif": "image/tiff",
}

OPAQUE_IMAGE_FORMATS = {"jpg", "jpeg"}

SUPPORTED_AUDIO_FORMATS = {
    "mp3": "audio/mpeg",
    "mp4": "video/mp4",
    "mpeg": "video/mpeg",
    "mpga": "audio/mpeg",
    "m4a": "audio/mp4",
    "wav": "audio/wav",
    "webm": "video/webm",
}

# File extension -> Audio format
EXTENSION_FORMAT_MAP = {
    **{ext: ext for ext in SUPPORTED_AUDIO_FORMATS.keys()},
    "oga": "ogg",
    "ogg": "ogg",
}

# Formats we know how to convert from
CONVERTIBLE_AUDIO_FORMATS = {
    "oga": "audio/ogg",
    "ogg": "audio/ogg",
}

KNOWN_AUDIO_FORMATS = SUPPORTED_AUDIO_FORMATS | CONVERTIBLE_AUDIO_FORMATS

TARGET_AUDIO_FORMAT = "wav"

KNOWN_DOCS_FORMATS = {
    # binary document formats
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # plain-text and markup formats
    "txt": "text/plain",
    "md": "text/markdown",
    "log": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "xml": "application/xml",
    "html": "text/html",
    "yaml": "application/yaml",
    "yml": "application/yaml",
    # source-code and web formats
    "js": "text/javascript",
    "ts": "application/typescript",
    "jsx": "text/javascript",
    "tsx": "application/typescript",
    "css": "text/css",
    "scss": "text/plain",
    "py": "text/x-python",
    "java": "text/x-java-source",
    "c": "text/x-c",
    "h": "text/x-c",
    "cpp": "text/x-c++",
    "hpp": "text/x-c++",
    "go": "text/plain",
    "rs": "text/plain",
    "rb": "text/x-ruby",
    "php": "application/x-php",
    "sh": "application/x-sh",
    "bash": "application/x-sh",
    "zsh": "application/x-sh",
    "swift": "text/plain",
    "kt": "text/plain",
}

KNOWN_FILE_FORMATS = KNOWN_IMAGE_FORMATS | KNOWN_AUDIO_FORMATS | KNOWN_DOCS_FORMATS


def resolve_file_type(
    mime_type: str | None = None,
    extension: str | None = None,
    uri: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Extracts mime type and extension using the available file information.
    Prioritizes the given values over the dynamically resolved ones.

    Returns:
        tuple[str | None, str | None]: (mime_type, extension)
    """

    # 1. try to resolve extension first
    resolved_extension: str | None = extension
    if not resolved_extension and mime_type:
        # only mime type is given, try to resolve extension from it
        resolved_extension = __extension_for_mime_type(mime_type)
    if not resolved_extension:
        # mime type is not given or could not be resolved, try to resolve extension from URI
        resolved_extension = __extension_from_uri(uri)

    # 2. try to resolve mime type next
    resolved_mime_type: str | None = mime_type
    if not resolved_mime_type:
        # try to resolve mime type from extension
        resolved_mime_type = __mime_type_for_extension(resolved_extension)

    # 3. return whatever we have at this point
    return resolved_mime_type, resolved_extension


def is_supported_mime_type(mime_type: str | None) -> bool:
    return bool(mime_type and mime_type in KNOWN_FILE_FORMATS.values())


def is_supported_extension(extension: str | None) -> bool:
    mime_type, _ = resolve_file_type(extension = extension)
    return mime_type is not None


def __extension_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    suffix = Path(urlparse(uri).path).suffix
    if not suffix:
        return None
    return suffix.removeprefix(".").lower()


def __extension_for_mime_type(mime_type: str | None) -> str | None:
    if not mime_type:
        return None
    return next((
        known_extension
        for known_extension, known_mime_type in KNOWN_FILE_FORMATS.items()
        if known_mime_type == mime_type
    ), None)


def __mime_type_for_extension(extension: str | None) -> str | None:
    if not extension:
        return None
    return KNOWN_FILE_FORMATS.get(extension.lower())
