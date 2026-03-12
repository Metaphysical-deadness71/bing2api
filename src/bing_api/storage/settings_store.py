import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional


class JsonSettingsStore:
    def __init__(self, file_path: str) -> None:
        self.file_path = Path(file_path)
        self._lock = threading.RLock()

    def load(self) -> Dict[str, Any]:
        if not self.file_path.exists():
            return {}
        with self._lock:
            with self.file_path.open("r", encoding="utf-8") as handle:
                return json.load(handle) or {}

    def save(self, payload: Dict[str, Any]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.file_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2)


InMemorySettingsStore = JsonSettingsStore
