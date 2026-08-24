from __future__ import annotations

import re

_IMAGE_ARGUMENT = re.compile(r'IMAGE\(\s*"([^"]+)"', re.IGNORECASE)


def extract_image_url(cell: object) -> str | None:
    if cell is None:
        return None

    text = str(cell).strip()
    if not text:
        return None

    matched = _IMAGE_ARGUMENT.search(text)
    if matched:
        return matched.group(1)

    return text if text.lower().startswith("http") else None
