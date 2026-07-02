import io
import tempfile

from PIL import Image

BLACK_BACKGROUND = (0, 0, 0, 255)


def __write_temp_file(content: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(delete = False, suffix = suffix) as tmp:
        tmp.write(content)
        tmp.flush()
        return tmp.name


def image_has_transparency(input_path: str) -> bool:
    with Image.open(input_path) as image:
        return __image_has_transparency(image)


def flatten_transparency_over_black(input_path: str) -> str:
    with Image.open(input_path) as image:
        if not __image_has_transparency(image):
            return input_path

        rgba_image = image.convert("RGBA")
        background = Image.new("RGBA", rgba_image.size, BLACK_BACKGROUND)
        background.alpha_composite(rgba_image)

        output = io.BytesIO()
        background.convert("RGB").save(output, format = "PNG", optimize = True)
        output.seek(0)
        return __write_temp_file(output.read(), ".png")


def __image_has_transparency(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA"):
        alpha = image.getchannel("A")
        return alpha.getextrema()[0] < 255
    if image.info.get("transparency") is not None:
        alpha = image.convert("RGBA").getchannel("A")
        return alpha.getextrema()[0] < 255
    return False
