def relative_luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = rgb
    return (0.299 * red + 0.587 * green + 0.114 * blue) / 255
