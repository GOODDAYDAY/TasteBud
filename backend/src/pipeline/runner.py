"""Pipeline runner — orchestrates Collect → Analyze → Notify via plugins."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import structlog

from analyzer.comment.analyzer import CommentAnalyzer
from analyzer.comment.analyzer import LLMConfig as AnalyzerLLMConfig
from analyzer.comment.models import CommentAnalysisResult
from core.comment import CommentBatch
from notifier.base import BaseNotifier, Notification
from pipeline.base import BasePlugin, load_plugin
from pipeline.models import NotifierConfig, PipelineConfig, PipelineRun

log = structlog.get_logger()


class PipelineRunner:
    """Execute a pipeline: per-video Collect → Save → Analyze → Notify."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    async def run(self, config: PipelineConfig) -> PipelineRun:
        """Run a single pipeline. Each video independently walks the full flow."""
        run = PipelineRun(
            pipeline_name=config.name,
            started_at=datetime.now(timezone.utc),
        )

        try:
            plugin = load_plugin(config.collector.type)
            platform_dir = self._base_dir / config.collector.type

            # 0. Ensure auth
            if not await plugin.ensure_auth(config):
                run.status = "error"
                run.error = "Authentication failed or cancelled"
                run.finished_at = datetime.now(timezone.utc)
                return run

            # Per-video full pipeline: Collect → Save → Analyze → Notify
            print(f"  Collecting & analyzing per video...")

            async for batch in plugin.collect(config, platform_dir):
                # 1. Save batch + cursor
                self._save_batch(plugin, batch, platform_dir)
                plugin.save_cursor(batch, platform_dir)
                run.new_comments += len(batch.comments)

                # 2. Analyze this batch immediately
                print(f"  Analyzing {len(batch.comments)} comments from [{batch.target_id}]...")
                try:
                    result = await self._analyze(config, batch)
                    self._save_analysis(result, platform_dir, batch)
                    run.pain_points_found += len(result.pain_points)
                    print(f"  Found {len(result.pain_points)} pain point(s).")

                    # 3. Notify
                    sent = await self._notify(config, plugin, result)
                    run.notifications_sent += sent
                    if sent > 0:
                        print(f"  Saved {sent} notification(s).")
                except Exception as e:
                    print(f"  Analysis/notify failed for [{batch.target_id}]: {e}")

            if run.new_comments == 0:
                run.status = "collected"
                print(f"  No new comments found.")
            else:
                run.status = "notified" if run.notifications_sent > 0 else "analyzed"
                print(
                    f"  Done: {run.new_comments} comments, {run.pain_points_found} pain points, {run.notifications_sent} notifications.")

            run.finished_at = datetime.now(timezone.utc)

        except Exception as e:
            run.status = "error"
            run.error = str(e)
            run.finished_at = datetime.now(timezone.utc)
            print(f"  ERROR: {e}")

        return run

    # -- Analyze --

    async def _analyze(
            self,
            config: PipelineConfig,
            batch: CommentBatch,
    ) -> CommentAnalysisResult:
        """Run AI analysis on a single batch of comments."""
        llm_cfg = config.analyzer.llm
        api_token = self._resolve_token(llm_cfg)

        analyzer = CommentAnalyzer(
            AnalyzerLLMConfig(
                provider=llm_cfg.provider,
                model=llm_cfg.model,
                base_url=llm_cfg.base_url,
                api_token=api_token,
                max_comments=llm_cfg.max_comments,
            )
        )

        return await analyzer.analyze(
            batch.comments,
            pipeline_name=config.name,
            target_id=batch.target_id,
            target_title=batch.target_title or batch.target_id,
        )

    @staticmethod
    def _resolve_token(llm_cfg: object) -> str:
        """Resolve API token from file path or environment variable."""
        # File takes priority
        if llm_cfg.api_token_path:
            token_path = Path(llm_cfg.api_token_path).expanduser()
            if token_path.exists():
                return token_path.read_text(encoding="utf-8").strip()
            print(f"  WARNING: Token file not found: {token_path}")
        # Fallback to env var
        if llm_cfg.api_token_env:
            return os.environ.get(llm_cfg.api_token_env, "")
        return ""

    # -- Notify --

    async def _notify(
            self,
            config: PipelineConfig,
            plugin: BasePlugin,
            result: CommentAnalysisResult,
    ) -> int:
        """Send notifications for analysis result. Returns count sent."""
        title, body = plugin.render_notification(result)
        sent = 0

        for nc in config.notifiers:
            notifier = self._build_notifier(nc)
            if notifier is None:
                continue

            notification = Notification(
                channel=nc.type,
                title=title,
                body=body,
            )
            if await notifier.send(notification):
                sent += 1
                self._log_notification(result, notification)

        return sent

    def _build_notifier(self, nc: NotifierConfig) -> BaseNotifier | None:
        """Build a notifier from config."""
        if nc.type == "local":
            from notifier.local import LocalNotifier

            output_dir = Path(nc.output_dir) if nc.output_dir else self._base_dir / "notifications"
            return LocalNotifier(output_dir)

        log.warning("unknown_notifier_type", type=nc.type)
        return None

    # -- Storage helpers --

    def _save_batch(self, plugin: BasePlugin, batch: CommentBatch, platform_dir: Path) -> None:
        """Save a comment batch to disk using the plugin serializer."""
        ts = batch.fetched_at.strftime("%Y%m%d_%H%M%S")
        path = (
                platform_dir
                / batch.target_type
                / batch.target_id
                / "comments"
                / f"batch_{ts}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        data = plugin.serialize_batch(batch)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  Saved: {path}")

    def _save_analysis(
            self,
            result: CommentAnalysisResult,
            platform_dir: Path,
            batch: CommentBatch,
    ) -> None:
        """Save per-video analysis result alongside the video's data + a copy in unified dir."""
        from dataclasses import asdict

        ts = result.analyzed_at.strftime("%Y%m%d_%H%M%S")
        data = asdict(result)
        data["analyzed_at"] = result.analyzed_at.isoformat()
        content = json.dumps(data, ensure_ascii=False, indent=2)

        # 1. Per-video directory
        per_video_path = (
                platform_dir
                / batch.target_type
                / batch.target_id
                / "analysis"
                / f"result_{ts}.json"
        )
        per_video_path.parent.mkdir(parents=True, exist_ok=True)
        per_video_path.write_text(content, encoding="utf-8")
        print(f"  Analysis saved: {per_video_path}")

        # 2. Unified directory (timestamp_targetId for easy sorting)
        unified_path = (
                platform_dir
                / "analysis"
                / f"{ts}_{batch.target_id}.json"
        )
        unified_path.parent.mkdir(parents=True, exist_ok=True)
        unified_path.write_text(content, encoding="utf-8")

    def _log_notification(
            self, result: CommentAnalysisResult, notification: Notification
    ) -> None:
        """Append notification to log."""
        path = (
                self._base_dir
                / "notifications"
                / "log.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "pipeline": result.pipeline_name,
            "channel": notification.channel,
            "status": notification.status,
            "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
            "pain_points": len(result.pain_points),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
