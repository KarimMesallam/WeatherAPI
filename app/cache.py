import json
import os
import tempfile
import time
import logging
from typing import Any, Dict, Optional

from app.config import CACHE_FILE, POLL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self) -> None:
        self._data: Optional[Dict[str, Any]] = None
        self._last_updated: float = 0.0
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not os.path.exists(CACHE_FILE):
            logger.info("No cache file found at %s", CACHE_FILE)
            return
        try:
            with open(CACHE_FILE, "r") as f:
                stored = json.load(f)
            self._data = stored.get("data")
            self._last_updated = stored.get("last_updated", 0.0)
            age = time.time() - self._last_updated
            logger.info(
                "Loaded cache from disk (age: %.0f seconds)", age
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load cache from disk: %s", exc)

    def _save_to_disk(self) -> None:
        stored = {
            "data": self._data,
            "last_updated": self._last_updated,
        }
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(CACHE_FILE), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(stored, f)
                os.replace(tmp_path, CACHE_FILE)
            except Exception:
                os.unlink(tmp_path)
                raise
            logger.debug("Cache saved to disk")
        except OSError as exc:
            logger.warning("Failed to save cache to disk: %s", exc)

    def update(self, data: Dict[str, Any]) -> None:
        self._data = data
        self._last_updated = time.time()
        self._save_to_disk()

    @property
    def has_data(self) -> bool:
        return self._data is not None

    @property
    def needs_refresh(self) -> bool:
        if not self.has_data:
            return True
        return self.get_age_seconds() > POLL_INTERVAL_SECONDS

    def get_age_seconds(self) -> float:
        if self._last_updated == 0.0:
            return float("inf")
        return time.time() - self._last_updated

    def get_response(self) -> Optional[Dict[str, Any]]:
        if self._data is None:
            return None
        return {
            **self._data,
            "age": int(self.get_age_seconds()),
        }
