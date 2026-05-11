"""
storage.py — Simple JSON-based persistent storage for user profiles.

Schema per user_id:
{
    "name":         str,
    "diet":         "regular" | "vegetarian" | "vegan",
    "allergens":    [str, ...],
    "liked_dishes": [str, ...],   # last 20 extracted dish names
    "conversation": [             # last 6 messages for context window
        {"role": "user"|"assistant", "content": str},
        ...
    ]
}
"""

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class UserStorage:
    """Thread-safe, file-backed key-value store keyed by Telegram user_id."""

    _DEFAULT_PROFILE: dict = {
        "name": "",
        "diet": "regular",
        "allergens": [],
        "liked_dishes": [],
        "conversation": [],
    }

    def __init__(self, path: str = "users.json") -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    # ── Private ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info("Loaded %d user profiles from %s", len(self._data), self._path)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load storage (%s); starting fresh.", exc)
                self._data = {}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.error("Could not save storage: %s", exc)

    def _key(self, user_id: int) -> str:
        return str(user_id)

    # ── Public API ─────────────────────────────────────────────────────────────

    def ensure(self, user_id: int, name: str = "") -> None:
        """Create a default profile for user_id if one doesn't exist yet."""
        key = self._key(user_id)
        with self._lock:
            if key not in self._data:
                profile = dict(self._DEFAULT_PROFILE)
                profile["name"] = name
                self._data[key] = profile
                self._save()
                logger.info("Created profile for user %s (%s)", user_id, name)

    def get(self, user_id: int) -> dict:
        """Return a copy of the user's profile (creates a default one if missing)."""
        key = self._key(user_id)
        with self._lock:
            if key not in self._data:
                self._data[key] = dict(self._DEFAULT_PROFILE)
            return dict(self._data[key])

    def update(self, user_id: int, fields: dict[str, Any]) -> None:
        """Merge *fields* into the user's profile and persist to disk."""
        key = self._key(user_id)
        with self._lock:
            if key not in self._data:
                self._data[key] = dict(self._DEFAULT_PROFILE)
            self._data[key].update(fields)
            self._save()

    def all_users(self) -> list[dict]:
        """Return a list of all user profiles (copies)."""
        with self._lock:
            return [dict(v) for v in self._data.values()]
