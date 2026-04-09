"""Configuration loader — reads environment variables from .env."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).parent.parent / ".env"


def load_config() -> dict[str, str]:
    """Load configuration from environment variables.

    Reads from a .env file if present, then falls back to the
    process environment. Values in the process environment take
    precedence over .env values.

    Returns:
        Dictionary of all environment variables as strings.
    """
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE)
        logger.debug("Loaded environment from %s", _ENV_FILE)
    else:
        logger.debug("No .env file found at %s — using process environment", _ENV_FILE)

    return dict(os.environ)
