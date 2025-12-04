"""
Aspect Ratio Utilities for Nano Banana Render
Handles smart aspect ratio matching for Google Gemini API
"""

from typing import Tuple
from math import gcd

# Supported aspect ratios by Google Gemini API
SUPPORTED_RATIOS = [
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
]


def _parse_ratio(ratio_str: str) -> Tuple[int, int]:
    """Parse ratio string like '16:9' to tuple (16, 9)"""
    parts = ratio_str.split(":")
    return int(parts[0]), int(parts[1])


def _ratio_to_float(ratio_str: str) -> float:
    """Convert ratio string to float value (width/height)"""
    w, h = _parse_ratio(ratio_str)
    return w / h


def find_closest_ratio(width: int, height: int) -> str:
    """
    Find the closest supported aspect ratio for given dimensions.

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Closest matching ratio string from SUPPORTED_RATIOS (e.g., "16:9")
    """
    if width <= 0 or height <= 0:
        return "1:1"

    current_ratio = width / height

    closest_ratio = "1:1"
    min_diff = float("inf")

    for ratio_str in SUPPORTED_RATIOS:
        ratio_value = _ratio_to_float(ratio_str)
        diff = abs(current_ratio - ratio_value)

        if diff < min_diff:
            min_diff = diff
            closest_ratio = ratio_str

    return closest_ratio


def adjust_resolution_to_ratio(
    width: int, height: int, target_ratio: str
) -> Tuple[int, int]:
    """
    Adjust resolution to exactly match target aspect ratio.
    Keeps the longer edge fixed and adjusts the shorter edge.

    Args:
        width: Current width in pixels
        height: Current height in pixels
        target_ratio: Target ratio string (e.g., "16:9")

    Returns:
        Tuple of (new_width, new_height) that matches target ratio exactly
    """
    ratio_w, ratio_h = _parse_ratio(target_ratio)
    target_ratio_float = ratio_w / ratio_h

    if width >= height:
        # Landscape or square - keep width fixed, adjust height
        new_width = width
        new_height = round(width / target_ratio_float)
    else:
        # Portrait - keep height fixed, adjust width
        new_height = height
        new_width = round(height * target_ratio_float)

    return new_width, new_height


def get_current_ratio_string(width: int, height: int) -> str:
    """
    Get simplified ratio string for current dimensions.
    Uses GCD to simplify the ratio.

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Simplified ratio string (e.g., "16:9")
    """
    if width <= 0 or height <= 0:
        return "1:1"

    divisor = gcd(width, height)
    w_ratio = width // divisor
    h_ratio = height // divisor

    return f"{w_ratio}:{h_ratio}"


def is_ratio_supported(width: int, height: int) -> bool:
    """
    Check if current dimensions match a supported ratio exactly.

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        True if ratio is in SUPPORTED_RATIOS
    """
    current = get_current_ratio_string(width, height)
    return current in SUPPORTED_RATIOS
