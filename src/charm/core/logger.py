import logging
import sys


def setup_logger(name: str = "charm", level: str = "INFO") -> logging.Logger:
    """
    Configures a standard logger that writes to stdout.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level.upper())

    return logger


logger = setup_logger()
