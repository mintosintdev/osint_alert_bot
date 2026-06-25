import json
import os
from pathlib import Path

class StateManager:
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.seen_ids = set()

    async def load(self):
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r') as f:
                    data = json.load(f)
                    self.seen_ids = set(data.get("seen_ids", []))
            except:
                self.seen_ids = set()

    async def save(self):
        with open(self.filepath, 'w') as f:
            json.dump({"seen_ids": list(self.seen_ids)}, f)

    def is_seen(self, item_id: str) -> bool:
        return item_id in self.seen_ids

    def mark_seen(self, item_id: str):
        self.seen_ids.add(item_id)
