import io
import math
import re
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from features.chat.supported_files import detect_image_format
from util import log
from util.error_codes import INVALID_IMAGE_SIZE
from util.errors import ValidationError

MAX_ITERATIONS = 10
QUALITY = 90
MIN_DIMENSION = 64
TARGET_RATIO_LO = 0.90


def __write_temp_file(content: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(delete = False, suffix = suffix) as tmp:
        tmp.write(content)
        tmp.flush()
        return tmp.name


def resize_file(input_path: str, max_size_bytes: int | None) -> str:
    try:
        if max_size_bytes is None:
            log.i("No size limit provided, no resizing needed")
            return input_path

        original_size = Path(input_path).stat().st_size
        if original_size <= max_size_bytes:
            log.i("Image is within size limit, no resizing needed")
            return input_path

        with Path(input_path).open("rb") as file:
            header = file.read(32)
        if detect_image_format(header) is None:
            log.i("File is not a recognized image, skipping resize")
            return input_path

        with Image.open(input_path) as image:
            original_format = image.format or "PNG"
            log.t(f"Original image: {image.size}, format: {original_format}")

            suffix = Path(input_path).suffix or ".png"
            save_format = original_format if original_format in ["JPEG", "PNG", "WEBP"] else "PNG"

            save_kwargs: dict[str, Any] = {"format": save_format, "optimize": True}
            if save_format != "PNG":
                save_kwargs["quality"] = QUALITY

            original_width, original_height = image.size
            best_under: bytes | None = None
            best_under_diff: float = float("inf")
            best_any: bytes | None = None
            best_any_diff: float = float("inf")

            scale = max(0.1, min(1.0, math.sqrt(max_size_bytes / original_size)))
            lo = 0.1
            hi = 1.0

            for iteration in range(MAX_ITERATIONS):
                new_width = int(original_width * scale)
                new_height = int(original_height * scale)

                if new_width < MIN_DIMENSION or new_height < MIN_DIMENSION:
                    log.w("Image hit minimum dimension during search, using best effort")
                    break

                log.d(f"Binary search iteration {iteration + 1}, scale: {scale:.4f}")

                output = io.BytesIO()
                resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                resized.save(output, **save_kwargs)
                output_size = output.tell()

                output_mb = output_size / 1024 / 1024
                log.t(f"Resized to {resized.size}, size: {output_mb:.2f} MB")

                output.seek(0)
                output_bytes = output.read()

                diff = abs(output_size - max_size_bytes)
                if output_size <= max_size_bytes and diff < best_under_diff:
                    best_under_diff = diff
                    best_under = output_bytes
                if diff < best_any_diff:
                    best_any_diff = diff
                    best_any = output_bytes

                if max_size_bytes * TARGET_RATIO_LO <= output_size <= max_size_bytes:
                    original_mb = original_size / 1024 / 1024
                    log.i(f"Successfully resized image from {original_mb:.2f} MB to {output_mb:.2f} MB")
                    return __write_temp_file(output_bytes, suffix)

                if output_size > max_size_bytes:
                    hi = scale
                else:
                    lo = scale
                scale = (lo + hi) / 2

            log.w("Binary search ended without hitting target band, returning best effort")
            if best_under is not None:
                return __write_temp_file(best_under, suffix)
            if best_any is not None:
                return __write_temp_file(best_any, suffix)
            raise ValidationError(
                f"Could not resize image to acceptable size in {MAX_ITERATIONS} iterations",
                INVALID_IMAGE_SIZE,
            )
    except Exception as e:
        log.e("Failed to resize image", e)
        raise


def normalize_image_size_category(size: str) -> str:
    return re.sub(r"\s+", "", size.lower()).replace("mb", "k").replace("mp", "k").replace("m", "k")


def calculate_image_size_category(file_path: str) -> str:
    """
    Calculate the image size category based on megapixels.

    Args:
        file_path: Path to the image file

    Returns:
        Size category as "1k", "2k", "4k", "8k", or "12k"

    Raises:
        ValueError: If image is larger than 14 megapixels
    """
    try:
        with Image.open(file_path) as image:
            width, height = image.size
            megapixels = (width * height) / 1_000_000

        if megapixels <= 1:
            return "1k"
        elif megapixels <= 2:
            return "2k"
        elif megapixels <= 4:
            return "4k"
        elif megapixels <= 8:
            return "8k"
        elif megapixels <= 14:
            if megapixels > 12:
                log.w(f"Large input image ({megapixels:.2f} MP) is tolerated, counting as 12k")
            return "12k"
        else:
            raise ValidationError(f"Input image too large, maximum 14 megapixels ({megapixels:.2f} MP)", INVALID_IMAGE_SIZE)
    except Exception as e:
        log.e("Failed to calculate image size category", e)
        raise
