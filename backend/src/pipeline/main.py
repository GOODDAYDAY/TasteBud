"""Pipeline CLI entry point.

Usage:
    python -m pipeline                     # list + run all enabled pipelines
    python -m pipeline --dir ./pipelines   # specify pipelines directory
    python -m pipeline --list              # list only, don't run
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import sys
from pathlib import Path

import structlog

from pipeline.config import find_pipeline_configs, load_pipeline_config
from pipeline.runner import PipelineRunner

log = structlog.get_logger()

# Fix Windows console encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _configure_logging() -> None:
    """Configure structlog for clean CLI output (warnings and errors only, no colors)."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    )


DEFAULT_PIPELINES_DIR = Path(__file__).resolve().parents[3] / "pipelines"
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "downloads" / "pipeline-data"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TasteBud Pipeline Runner")
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_PIPELINES_DIR,
        help="Directory containing pipeline YAML configs (default: pipelines/)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Base directory for pipeline data storage",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="List all pipelines and exit",
    )
    return parser.parse_args(argv)


def list_pipelines(pipelines_dir: Path) -> None:
    """Print all pipeline configs and their enabled status."""
    config_files = find_pipeline_configs(pipelines_dir)
    if not config_files:
        print(f"No pipeline configs found in {pipelines_dir}")
        return

    print(f"\nPipelines in {pipelines_dir}:\n")
    print(f"  {'Name':<30} {'Enabled':<10} {'Type':<10} {'File'}")
    print(f"  {'-' * 30} {'-' * 10} {'-' * 10} {'-' * 20}")
    for path in config_files:
        try:
            config = load_pipeline_config(path)
            status = "ON" if config.enabled else "OFF"
            ctype = config.collector.type
            print(f"  {config.name:<30} {status:<10} {ctype:<10} {path.name}")
        except Exception as e:
            print(f"  {'(error)':<30} {'?':<10} {'?':<10} {path.name}  -- {e}")


async def run_all(pipelines_dir: Path, data_dir: Path) -> int:
    """List pipelines, check auth, then run all enabled ones. Returns exit code."""
    config_files = find_pipeline_configs(pipelines_dir)
    if not config_files:
        print(f"No pipeline configs found in {pipelines_dir}")
        return 1

    # 1. Load all configs
    configs = []
    for path in config_files:
        try:
            config = load_pipeline_config(path)
            configs.append(config)
        except Exception as e:
            log.error("config_load_failed", file=str(path), error=str(e))

    enabled = [c for c in configs if c.enabled]
    skipped = [c for c in configs if not c.enabled]

    # 2. Show overview
    print(f"\n  Found {len(configs)} pipeline(s): {len(enabled)} enabled, {len(skipped)} disabled")
    for c in enabled:
        print(f"    [ON]  {c.name}  ({c.collector.type}/{c.collector.mode} -> {c.collector.target})")
    for c in skipped:
        print(f"    [OFF] {c.name}")

    if not enabled:
        print("\n  No enabled pipelines to run.")
        return 0

    # 3. Run each pipeline (auth check happens inside runner via plugin.ensure_auth)
    print(f"\n  Data directory: {data_dir}")
    print(f"  Running {len(enabled)} pipeline(s)...\n")

    runner = PipelineRunner(base_dir=data_dir)
    errors = 0

    for config in enabled:
        print(f"  --- [{config.name}] ---")
        result = await runner.run(config)

        if result.status == "error":
            print(f"  Result: ERROR - {result.error}\n")
            errors += 1
        else:
            parts = [f"status={result.status}"]
            if result.new_comments:
                parts.append(f"new_comments={result.new_comments}")
            if result.pain_points_found:
                parts.append(f"pain_points={result.pain_points_found}")
            if result.notifications_sent:
                parts.append(f"notifications={result.notifications_sent}")
            print(f"  Result: {', '.join(parts)}\n")

    print(f"Finished. {len(enabled) - errors}/{len(enabled)} succeeded.")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> None:
    _configure_logging()
    args = parse_args(argv)

    if args.list_only:
        list_pipelines(args.dir)
        return

    exit_code = asyncio.run(run_all(args.dir, args.data_dir))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
