from undercover.bot.message_utils import Photo, as_photo
from undercover.media.card_renderer import CARD_SUFFIX


def card_photo(image: bytes | str, name: str) -> Photo:
    return as_photo(image, f"{name}.{CARD_SUFFIX}")
