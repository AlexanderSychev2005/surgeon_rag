import datetime
import json
import logging
import os
from typing import Any

LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
os.makedirs(LOG_DIR, exist_ok=True)

RUN_TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = logging.FileHandler(
        os.path.join(LOG_DIR, f"medical_rag_{RUN_TIMESTAMP}.log"), encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


def record_event(event_type: str, **kwargs: Any) -> dict[str, Any]:
    history_file = os.path.join(LOG_DIR, "sync_history.jsonl")
    event = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "run_id": RUN_TIMESTAMP,
        "event": event_type,
        **kwargs,
    }
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event
