"""One shared logger config: console + rotating file, so every script's run
history (what got added, what failed) survives between cron/manual runs."""
import datetime
import json
import logging
import os

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Generate a single timestamp for the entire run so all loggers and events share the same files
RUN_TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# JSON history is now dynamically generated in record_event


def get_logger(name):
    logger = logging.getLogger(name)
    if logger.handlers:  # avoid duplicate handlers if called twice
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = logging.FileHandler(
        os.path.join(LOG_DIR, f"medical_rag_{RUN_TIMESTAMP}.log"), encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


def record_event(event_type, **kwargs):
    """Append a structured event to a single metrics log file for the project.
    On GitHub Actions, this single file gets committed to track history."""
    history_file = os.path.join(LOG_DIR, "sync_history.jsonl")
    event = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "run_id": RUN_TIMESTAMP,
        "event": event_type,
        **kwargs
    }
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event
