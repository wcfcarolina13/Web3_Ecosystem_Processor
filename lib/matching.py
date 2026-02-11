"""
Name normalization and similarity matching for ecosystem project comparison.
"""

import re
from difflib import SequenceMatcher
from typing import Optional, Tuple, List

# Suffixes to strip during normalization (merged from all scripts)
STRIP_SUFFIXES = [
    "protocol",
    "finance",
    "labs",
    "wallet",
    "exchange",
    "market",
    "markets",
    "swap",
    "amm",
    "lsd",
    "cdp",
    "cex",
    r"v\d+",  # Version suffixes like V2, V3
]


def normalize_name(name: str) -> str:
    """
    Normalize a project name for comparison.

    Strips common suffixes, lowercases, and removes non-alphanumeric characters.
    Examples:
        "PancakeSwap AMM" -> "pancake"
        "Thala LSD" -> "thala"
        "Aptin Finance V2" -> "aptin"
    """
    name = name.lower()
    suffix_pattern = r"\s*(" + "|".join(STRIP_SUFFIXES) + r")$"
    # Apply suffix removal repeatedly (e.g., "Thala Labs Finance" -> "Thala")
    prev = None
    while prev != name:
        prev = name
        name = re.sub(suffix_pattern, "", name, flags=re.I)
    name = re.sub(r"[^a-z0-9]", "", name)
    return name


def similarity(a: str, b: str) -> float:
    """Calculate string similarity ratio using SequenceMatcher (0.0 to 1.0)."""
    return SequenceMatcher(None, a, b).ratio()


def find_match(
    name: str,
    existing_names: List[str],
    threshold: float = 0.8,
) -> Tuple[Optional[str], float]:
    """
    Find the best match for a name in existing names.

    Returns (matched_name, score) or (None, 0.0).
    Score meanings:
        1.0 = exact match after normalization
        0.9 = one name contains the other
        >threshold = high string similarity
    """
    normalized = normalize_name(name)

    best_match = None
    best_score = 0.0

    for existing in existing_names:
        existing_norm = normalize_name(existing)

        # Exact match after normalization
        if normalized == existing_norm:
            return existing, 1.0

        # Check if one contains the other
        if normalized in existing_norm or existing_norm in normalized:
            if 0.9 > best_score:
                best_match = existing
                best_score = 0.9

        # High similarity
        sim = similarity(normalized, existing_norm)
        if sim > threshold and sim > best_score:
            best_match = existing
            best_score = sim

    if best_match:
        return best_match, best_score

    return None, 0.0
