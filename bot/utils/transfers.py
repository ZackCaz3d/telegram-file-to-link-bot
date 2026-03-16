import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Transfer:
    id: str
    filename: str
    file_size: int
    user_id: int
    direction: str  # "download" or "upload"
    started_at: float = field(default_factory=time.time)
    current_bytes: int = 0
    total_bytes: int = 0
    stage: str = "queued"  # queued, downloading, uploading, complete, failed

    @property
    def progress(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return self.current_bytes / self.total_bytes

    def to_dict(self) -> dict:
        elapsed = time.time() - self.started_at
        speed = self.current_bytes / elapsed if elapsed > 0 else 0
        return {
            "id": self.id,
            "filename": self.filename,
            "file_size": self.file_size,
            "user_id": self.user_id,
            "direction": self.direction,
            "started_at": self.started_at,
            "current_bytes": self.current_bytes,
            "total_bytes": self.total_bytes,
            "progress": round(self.progress * 100, 1),
            "stage": self.stage,
            "elapsed": round(elapsed, 1),
            "speed_bps": round(speed),
        }


class TransferTracker:
    def __init__(self):
        self._active: dict[str, Transfer] = {}
        self._history: list[dict] = []

    def start(self, transfer_id: str, filename: str, file_size: int,
              user_id: int, direction: str) -> Transfer:
        t = Transfer(
            id=transfer_id,
            filename=filename,
            file_size=file_size,
            user_id=user_id,
            direction=direction,
            total_bytes=file_size,
        )
        self._active[transfer_id] = t
        return t

    def update(self, transfer_id: str, current_bytes: int, stage: str = None):
        if transfer_id in self._active:
            self._active[transfer_id].current_bytes = current_bytes
            if stage:
                self._active[transfer_id].stage = stage

    def complete(self, transfer_id: str, stage: str = "complete"):
        if transfer_id in self._active:
            t = self._active.pop(transfer_id)
            t.stage = stage
            entry = t.to_dict()
            self._history.insert(0, entry)
            self._history = self._history[:50]

    def get_active(self) -> list[dict]:
        return [t.to_dict() for t in self._active.values()]

    def get_history(self) -> list[dict]:
        return self._history[:20]


tracker = TransferTracker()
