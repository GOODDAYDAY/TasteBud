"""Tests for sieve storage helpers in collector/storage.py."""

import json
from pathlib import Path

from collector.storage import find_sieved, load_sieve_file, save_sieve_file

CAT = "manga"


class TestSieveFileStorage:
    def test_save_and_load(self, tmp_path: Path) -> None:
        data = {"layer1": {"passed": True, "score": 0.8, "threshold": 0.5}}
        save_sieve_file(CAT, "ehentai", "123", data, base_dir=tmp_path)
        loaded = load_sieve_file(CAT, "ehentai", "123", base_dir=tmp_path)
        assert loaded is not None
        assert loaded["layer1"]["passed"] is True
        assert loaded["layer1"]["score"] == 0.8

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        assert load_sieve_file(CAT, "ehentai", "999", base_dir=tmp_path) is None

    def test_overwrite(self, tmp_path: Path) -> None:
        data1 = {"layer1": {"passed": True, "score": 0.5, "threshold": 0.3}}
        save_sieve_file(CAT, "ehentai", "123", data1, base_dir=tmp_path)

        data2 = {
            "layer1": {"passed": True, "score": 0.5, "threshold": 0.3},
            "layer2": {"passed": False, "score": 0.1, "threshold": 0.3},
        }
        save_sieve_file(CAT, "ehentai", "123", data2, base_dir=tmp_path)

        loaded = load_sieve_file(CAT, "ehentai", "123", base_dir=tmp_path)
        assert loaded is not None
        assert "layer2" in loaded
        assert loaded["layer2"]["passed"] is False


class TestFindSieved:
    def _create_item_with_sieve(
        self, tmp_path: Path, sid: str, sieve_data: dict
    ) -> None:
        """Helper to create a minimal item directory with data.json and sieve.json."""
        idir = tmp_path / CAT / "ehentai" / sid
        idir.mkdir(parents=True)
        # data.json is needed for find_items to discover the item
        (idir / "data.json").write_text(
            json.dumps({"source": "ehentai", "source_id": sid, "tags": []}),
            encoding="utf-8",
        )
        (idir / "sieve.json").write_text(
            json.dumps(sieve_data), encoding="utf-8"
        )

    def test_find_passed_layer1(self, tmp_path: Path) -> None:
        self._create_item_with_sieve(tmp_path, "1", {
            "layer1": {"passed": True, "score": 0.8, "threshold": 0.5},
        })
        self._create_item_with_sieve(tmp_path, "2", {
            "layer1": {"passed": False, "score": 0.2, "threshold": 0.5},
        })
        self._create_item_with_sieve(tmp_path, "3", {
            "layer1": {"passed": True, "score": 0.6, "threshold": 0.5},
        })

        passed = find_sieved(CAT, 1, True, base_dir=tmp_path)
        assert len(passed) == 2
        sids = {p.name for p in passed}
        assert sids == {"1", "3"}

    def test_find_failed_layer1(self, tmp_path: Path) -> None:
        self._create_item_with_sieve(tmp_path, "1", {
            "layer1": {"passed": True, "score": 0.8, "threshold": 0.5},
        })
        self._create_item_with_sieve(tmp_path, "2", {
            "layer1": {"passed": False, "score": 0.2, "threshold": 0.5},
        })

        failed = find_sieved(CAT, 1, False, base_dir=tmp_path)
        assert len(failed) == 1
        assert failed[0].name == "2"

    def test_find_passed_layer2(self, tmp_path: Path) -> None:
        self._create_item_with_sieve(tmp_path, "1", {
            "layer1": {"passed": True, "score": 0.8, "threshold": 0.5},
            "layer2": {"passed": True, "score": 0.7, "threshold": 0.3},
        })
        self._create_item_with_sieve(tmp_path, "2", {
            "layer1": {"passed": True, "score": 0.6, "threshold": 0.5},
            "layer2": {"passed": False, "score": 0.1, "threshold": 0.3},
        })

        passed = find_sieved(CAT, 2, True, base_dir=tmp_path)
        assert len(passed) == 1
        assert passed[0].name == "1"

    def test_find_with_no_sieve(self, tmp_path: Path) -> None:
        """Items without sieve.json are not returned."""
        idir = tmp_path / CAT / "ehentai" / "1"
        idir.mkdir(parents=True)
        (idir / "data.json").write_text('{"source":"ehentai","source_id":"1","tags":[]}')

        result = find_sieved(CAT, 1, True, base_dir=tmp_path)
        assert result == []

    def test_empty_category(self, tmp_path: Path) -> None:
        result = find_sieved(CAT, 1, True, base_dir=tmp_path)
        assert result == []
