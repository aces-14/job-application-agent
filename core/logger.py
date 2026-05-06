import logging
import os
from datetime import datetime
from core.config import LOG_LEVEL, LOG_FILE

class SensitiveFilter(logging.Filter):
    SENSITIVE_KEYWORDS = [
        "API_KEY", "SECRET", "TOKEN", "PASSWORD",
        "GROQ", "TAVILY", "gsk_", "tvly-"
    ]

    def filter(self, record):
        msg = str(record.getMessage())
        for keyword in self.SENSITIVE_KEYWORDS:
            if keyword.upper() in msg.upper():
                record.msg = "[REDACTED — sensitive value detected in log]"
                record.args = ()
                return True
        return True

def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(SensitiveFilter())
    logger.addHandler(console)

    # File handler
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.FileHandler(f"logs/{LOG_FILE}")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SensitiveFilter())
    logger.addHandler(file_handler)

    return logger