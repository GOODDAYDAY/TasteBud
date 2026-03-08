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
from analyzer.comment.window import add_pending, get_pending_count, reset_pending, should_analyze
from core.comment import Comment, CommentBatch
from notifier.base import BaseNotifier, Notification
from pipeline.base import BasePlugin, load_plugin
from pipeline.models import NotifierConfig, PipelineConfig, PipelineRun

log = structlog.get_logger()


class PipelineRunner:
    """Execute a pipeline: Collect → (window check) → Analyze → Notify."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    async def run(self, config: PipelineConfig) -> PipelineRun:
        """Run a single pipeline."""
        run = PipelineRun(
            pipeline_name=config.name,
            started_at=datetime.now(timezone.utc),
        )

        try:
            # Load platform plugin
            plugin = load_plugin(config.collector.type)
            platform_dir = self._base_dir / config.collector.type

            # 0. Ensure auth
            if not await plugin.ensure_auth(config):
                run.status = "error"
                run.error = "Authentication failed or cancelled"
                run.finished_at = datetime.now(timezone.utc)
                return run

            # 1. Collect
            print(f"  Collecting comments...")
            batches = await plugin.collect(config, platform_dir)
            all_comments = [c for b in batches for c in b.comments]
            run.new_comments = len(all_comments)

            if not all_comments:
                run.status = "collected"
                run.finished_at = datetime.now(timezone.utc)
                print(f"  No new comments found.")
                return run

            print(f"  Collected {len(all_comments)} new comments from {len(batches)} target(s).")

            # 2. Update pending counts and save comments
            for batch in batches:
                self._save_batch(plugin, batch, platform_dir)
                add_pending(
                    platform_dir,
                    batch.target_type,
                    batch.target_id,
                    len(batch.comments),
                )

            # 3. Check analysis window for each target
            analysis_results: list[CommentAnalysisResult] = []
            for batch in batches:
                threshold = config.analyzer.window_size
                if should_analyze(
                        platform_dir,
                        batch.target_type,
                        batch.target_id,
                        threshold,
                ):
                    # Load all pending comments for this target
                    pending = self._load_pending_comments(
                        plugin, batch.target_type, batch.target_id, platform_dir
                    )
                    if pending:
                        print(f"  Window reached ({len(pending)}>={threshold}), analyzing [{batch.target_id}]...")
                        result = await self._analyze(config, pending, batch)
                        analysis_results.append(result)
                        self._save_analysis(batch.target_type, batch.target_id, result, platform_dir)
                        reset_pending(
                            platform_dir, batch.target_type, batch.target_id
                        )
                        print(f"  Found {len(result.pain_points)} pain point(s).")
                else:
                    total = get_pending_count(platform_dir, batch.target_type, batch.target_id)
                    print(f"  [{batch.target_id}] pending: {total}/{threshold} (not enough for analysis)")

            if not analysis_results:
                run.status = "collected"
                run.finished_at = datetime.now(timezone.utc)
                return run

            # 4. Notify
            total_pain = sum(len(r.pain_points) for r in analysis_results)
            run.pain_points_found = total_pain

            sent = 0
            for result in analysis_results:
                sent += await self._notify(config, plugin, result)
            run.notifications_sent = sent

            if sent > 0:
                print(f"  Saved {sent} notification(s).")

            run.status = "notified" if sent > 0 else "analyzed"
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
            comments: list[Comment],
            batch: CommentBatch,
    ) -> CommentAnalysisResult:
        """Run AI analysis."""
        llm_cfg = config.analyzer.llm
        api_token = os.environ.get(llm_cfg.api_token_env, "") if llm_cfg.api_token_env else ""

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
            comments,
            pipeline_name=config.name,
            target_id=batch.target_id,
            target_title=batch.target_title,
        )

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

    def _load_pending_comments(
            self, plugin: BasePlugin, target_type: str, target_id: str, platform_dir: Path
    ) -> list[Comment]:
        """Load all unanalyzed comment batches for a target."""
        comments_dir = platform_dir / target_type / target_id / "comments"
        if not comments_dir.exists():
            return []

        all_comments: list[Comment] = []
        for batch_file in sorted(comments_dir.glob("batch_*.json")):
            data = json.loads(batch_file.read_text(encoding="utf-8"))
            all_comments.extend(plugin.deserialize_comments(data))

        return all_comments

    def _save_analysis(
            self,
            target_type: str,
            target_id: str,
            result: CommentAnalysisResult,
            platform_dir: Path,
    ) -> None:
        """Save analysis result to disk."""
        from dataclasses import asdict

        ts = result.analyzed_at.strftime("%Y%m%d_%H%M%S")
        path = (
                platform_dir
                / target_type
                / target_id
                / "analysis"
                / f"result_{ts}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        data = asdict(result)
        data["analyzed_at"] = result.analyzed_at.isoformat()
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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
