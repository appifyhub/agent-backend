CARD_OUTER_PAD = 24  # transparent shadow margin around card
CARD_CORNER_RADIUS = 40
CARD_INNER_PAD = 54  # padding inside the card
CARD_SECTION_GAP = 28  # vertical gap between header / body / photos / footer
PHOTO_CORNER_RADIUS = 36
PHOTO_GAP = 4  # gap between stacked photos
AVATAR_SIZE = 64
AVATAR_GAP = 16  # gap between avatar and name column
LOGO_SIZE = 32
LOGO_CIRCLE_R = 26
PLATFORM_ICON_SIZE = 12
HEADER_HEIGHT = AVATAR_SIZE + CARD_INNER_PAD
DIVIDER_OPACITY = 0.2
FOOTER_OPACITY = 0.45
FONT_SIZE_NAME = 22
FONT_SIZE_DATE = 16
FONT_SIZE_BODY = 26
FONT_SIZE_FOOTER = 16
LINE_HEIGHT_BODY = 32  # pixels per line in body text
DROP_SHADOW_BLUR = 10
DROP_SHADOW_DY = 6
DROP_SHADOW_OPACITY = 0.30


def card_width_from_text(text: str) -> int:
    length = len(text)
    if length <= 500:
        return 800
    if length <= 1000:
        return 1000
    return 1200
