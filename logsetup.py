"""One shared logger config: console + rotating file, so every script's run
history (what got added, what failed) survives between cron/manual runs."""
import datetime
import json
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# One JSON line per sync/recheck run - committed to the repo by CI (unlike
# logs/, which is gitignored and only kept as a 30-day workflow artifact) so
# "what changed and when" is readable straight from GitHub, no download needed.
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "sync_history.jsonl")


def get_logger(name):
    logger = logging.getLogger(name)
    if logger.handlers:  # avoid duplicate handlers if called twice
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "medical_rag.log"), maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


def record_event(script, **fields):
    """Append a one-line run summary, e.g.
    record_event("sync", window="2026/08/04..2026/08/07", matched=1532, written=1532, with_full_text=410)"""
    entry = {
        "run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "script": script,
        **fields,
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
