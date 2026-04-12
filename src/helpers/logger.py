"""
Centralized logging configuration.

Call setup_logging() once at application startup (e.g. in main.py).
All modules continue to use the standard pattern::

    import logging
    log = logging.getLogger(__name__)

To switch backends later (CloudWatch, Sentry, etc.), update only
this module — no caller changes required.
"""

import logging
from logging.handlers import TimedRotatingFileHandler

_configured = False


def setup_logging() -> None:
    """Configure application-wide logging. Idempotent — safe to call more than once."""
    global _configured
    if _configured:
        return
    _configured = True

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            TimedRotatingFileHandler(
                filename="bot.log",
                when="D",
                interval=1,
                backupCount=7,
            ),
        ],
        force=True,
    )
