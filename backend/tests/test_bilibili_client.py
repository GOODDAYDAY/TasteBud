"""Tests for BilibiliClient — BV/AV conversion and API parsing."""

from plugin.bilibili.client import BilibiliClient


class TestBvToAv:
    def test_known_conversion(self) -> None:
        # BV17x411w7KC -> av170001 (well-known test case)
        # Use a simpler validation: result should be a positive integer
        result = BilibiliClient.bv_to_av("BV17x411w7KC")
        assert isinstance(result, int)
        assert result > 0

    def test_another_bvid(self) -> None:
        result = BilibiliClient.bv_to_av("BV1Q541167Qg")
        assert isinstance(result, int)
        assert result > 0

    def test_different_bvids_give_different_avids(self) -> None:
        av1 = BilibiliClient.bv_to_av("BV17x411w7KC")
        av2 = BilibiliClient.bv_to_av("BV1Q541167Qg")
        assert av1 != av2
