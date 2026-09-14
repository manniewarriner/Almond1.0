"""Deterministic input/output policy for the general-chat surface."""

from __future__ import annotations

import re
import unicodedata

from app.errors import ContentPolicyError

_NSFW_TERMS = (
    "adult content",
    "erotic",
    "fetish",
    "genital",
    "nude",
    "nudity",
    "onlyfans",
    "porn",
    "pornographic",
    "sexual",
    "xxx",
)
_NSFW_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in _NSFW_TERMS) + r")\b",
    re.IGNORECASE,
)

SAFE_REFUSAL = "I can't help with sexually explicit or NSFW content."


def contains_nsfw(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return _NSFW_PATTERN.search(normalized) is not None


def enforce_safe_input(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise ContentPolicyError("Enter a message.")
    if contains_nsfw(cleaned):
        raise ContentPolicyError(SAFE_REFUSAL)
    return cleaned


def filter_safe_output(text: str) -> str:
    return SAFE_REFUSAL if contains_nsfw(text) else text.strip()
