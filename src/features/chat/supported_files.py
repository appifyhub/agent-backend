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
    # Binary document formats
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # Plain-text and markup formats
    "txt": "text/plain",
    "md": "text/markdown",
    "log": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "xml": "application/xml",
    "html": "text/html",
    "yaml": "application/yaml",
    "yml": "application/yaml",
    # Source-code and web formats
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
