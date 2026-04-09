"""Entry point for <repo-name>."""

import logging

from src.config import load_config

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the application."""
    config = load_config()
    logger.info("Starting %s", config.get("APP_ENV", "development"))
    # TODO: replace with your application logic


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    main()
