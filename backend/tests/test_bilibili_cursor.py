"""Tests for Bilibili incremental cursor management."""

from pathlib import Path

from plugin.bilibili.cursor import load_cursor, save_cursor
from plugin.bilibili.models import Cursor


class TestCursor:
    def test_load_empty(self, tmp_path: Path) -> None:
        cursor = load_cursor(tmp_path, "video", "BV123")
        assert cursor.last_rpid == 0
        assert cursor.last_page == 0

    def test_save_and_load(self, tmp_path: Path) -> None:
        cursor = Cursor(last_rpid=12345, last_page=3)
        save_cursor(tmp_path, "video", "BV123", cursor)

        loaded = load_cursor(tmp_path, "video", "BV123")
        assert loaded.last_rpid == 12345
        assert loaded.last_page == 3
        assert loaded.updated_at != ""

    def test_overwrite(self, tmp_path: Path) -> None:
        save_cursor(tmp_path, "video", "BV123", Cursor(last_rpid=100))
        save_cursor(tmp_path, "video", "BV123", Cursor(last_rpid=200))

        loaded = load_cursor(tmp_path, "video", "BV123")
        assert loaded.last_rpid == 200

    def test_isolated_by_target(self, tmp_path: Path) -> None:
        save_cursor(tmp_path, "video", "BV111", Cursor(last_rpid=100))
        save_cursor(tmp_path, "video", "BV222", Cursor(last_rpid=200))

        assert load_cursor(tmp_path, "video", "BV111").last_rpid == 100
        assert load_cursor(tmp_path, "video", "BV222").last_rpid == 200
