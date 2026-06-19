"""
Structured JSON logging for the Loan Eligibility AI Agent.
Every log line is a JSON object containing trace_id, level, agent, and message.
Logs are written to both a JSONL file and stdout.
"""

import logging
import os
import sys
from pythonjsonlogger import jsonlogger

from config import LOG_DIR, LOG_FILE


def setup_logging() -> None:
    """
    Configure the root logger to output structured JSON.
    Call this once at application startup (app.py calls it).
    """
    # Ensure the log directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

    # JSON formatter — every field becomes a top-level JSON key
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={
            "levelname": "level",
            "asctime": "timestamp",
            "name": "logger",
        },
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicate output on Streamlit reload
    root_logger.handlers.clear()

    # File handler: write to JSONL file
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Stream handler: print to stdout (visible in terminal)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
