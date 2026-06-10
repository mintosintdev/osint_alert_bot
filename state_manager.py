"""Управление состоянием (дедупликация)."""
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Ошибка чтения state: {e}")
        return {"seen_ids": []}

    def save(self):
        self.state_file.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def is_seen(self, item_id: str) -> bool:
        return item_id in self.state["seen_ids"]

    def mark_seen(self, item_id: str):
        if not self.is_seen(item_id):
            self.state["seen_ids"].append(item_id)
            # Храним только последние 1000 ID чтобы файл не рос бесконечно
            if len(self.state["seen_ids"]) > 1000:
                self.state["seen_ids"] = self.state["seen_ids"][-1000:]
            self.save()
