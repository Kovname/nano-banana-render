"""
Unified logging module for Nano Banana Render addon.

Usage:
    from .log import logger
    logger.info("Scene validation passed")
    logger.warning("Fallback to alternative method")
    logger.error("Failed to connect to API")
"""

import logging

logger = logging.getLogger("nano_banana")

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[NANODE] %(levelname)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
