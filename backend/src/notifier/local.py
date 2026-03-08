"""Local file notifier — saves notifications as JSON files."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import structlog

from notifier.base import BaseNotifier, Notification

log = structlog.get_logger()


class LocalNotifier(BaseNotifier):
    """Save notifications to local JSON files."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    async def send(self, notification: Notification) -> bool:
        """Write notification to a JSON file."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc)
        filename = f"notification_{ts.strftime('%Y%m%d_%H%M%S')}.json"
        path = self._output_dir / filename

        data = {
            "channel": notification.channel,
            "title": notification.title,
            "body": notification.body,
            "created_at": ts.isoformat(),
        }
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        notification.status = "sent"
        notification.sent_at = ts
        log.info("local_notification_saved", path=str(path))
        return True
