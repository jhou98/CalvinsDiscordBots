"""
Tests for helpers/logger.py — centralized logging configuration.
"""

import logging

from src.helpers.logger import setup_logging


class TestSetupLogging:
    def test_idempotent(self):
        """Calling setup_logging multiple times does not add duplicate handlers."""
        root = logging.getLogger()
        setup_logging()
        count_after_first = len(root.handlers)
        setup_logging()
        assert len(root.handlers) == count_after_first

    def test_configures_root_logger(self):
        setup_logging()
        root = logging.getLogger()
        assert root.level <= logging.INFO
        assert len(root.handlers) > 0

    def test_module_loggers_work(self):
        """Modules using getLogger(__name__) should inherit the configuration."""
        setup_logging()
        log = logging.getLogger("src.cogs.test_module")
        assert log.getEffectiveLevel() <= logging.INFO
