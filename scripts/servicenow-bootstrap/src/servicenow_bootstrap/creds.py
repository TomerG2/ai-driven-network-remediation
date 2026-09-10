"""Read and update the gitignored noc_agent credentials file."""

import json
import os
from typing import Any, Dict

CREDS_FILE = ".servicenow-creds.json"


def load_creds_file() -> Dict[str, Any]:
    """Return creds from ``CREDS_FILE``, or an empty dict if missing."""
    if not os.path.exists(CREDS_FILE):
        return {}
    with open(CREDS_FILE, encoding="utf-8") as f:
        return json.load(f)


def merge_creds_file(updates: Dict[str, Any]) -> None:
    """Merge ``updates`` into ``CREDS_FILE`` with mode 0600."""
    creds = load_creds_file()
    creds.update(updates)
    fd = os.open(CREDS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2)
        f.write("\n")
