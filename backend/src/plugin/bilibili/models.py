"""Bilibili-specific data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VideoInfo:
    """Bilibili video metadata (internal to the plugin)."""

    bvid: str = ""
    avid: int = 0
    title: str = ""
    url: str = ""
    up_mid: int = 0
    up_name: str = ""


@dataclass
class Cursor:
    """Incremental collection cursor for Bilibili comments."""

    last_rpid: int = 0
    last_page: int = 0
    updated_at: str = ""
