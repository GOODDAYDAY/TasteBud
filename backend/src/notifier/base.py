"""Base notifier interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Notification:
    """A notification to be sent."""

    channel: str  # "local" (more channels can be added via plugins)
    title: str = ""
    body: str = ""
    sent_at: datetime | None = None
    status: str = "pending"  # "pending" | "sent" | "failed"
    retry_count: int = 0
    metadata: dict[str, str] = field(default_factory=dict)


class BaseNotifier(ABC):
    """Abstract base for notification channels."""

    @abstractmethod
    async def send(self, notification: Notification) -> bool:
        """Send a notification. Returns True on success."""
