"""
test_llm.py - Tests for app.services.llm's LLM response cache helpers.
"""

import json

import pytest

from app.services import llm


@pytest.fixture
def responses_file(tmp_path, monkeypatch):
    """Point the LLM response cache at a scratch file for the duration of the test."""
    monkeypatch.setattr(llm.settings, "cache_dir", str(tmp_path))
    path = tmp_path / "llm_responses.json"
    return path


def _seed(path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


class TestEvictLlmResponse:
    def test_removes_both_modes_for_the_game(self, responses_file):
        _seed(
            responses_file,
            {
                "2026-1-lv-mia-winner": {"verdict": "BOOST", "explain": "stale", "flag": None},
                "2026-1-lv-mia-cover": {"verdict": "FADE", "explain": "stale", "flag": None},
            },
        )

        llm.evict_llm_response(2026, 1, "lv-mia")

        assert llm.load_llm_responses() == {}

    def test_leaves_other_games_untouched(self, responses_file):
        _seed(
            responses_file,
            {
                "2026-1-lv-mia-winner": {"verdict": "BOOST", "explain": "stale", "flag": None},
                "2026-1-kc-buf-winner": {"verdict": "AGREE", "explain": "keep", "flag": None},
            },
        )

        llm.evict_llm_response(2026, 1, "lv-mia")

        remaining = llm.load_llm_responses()
        assert list(remaining.keys()) == ["2026-1-kc-buf-winner"]

    def test_noop_when_nothing_cached(self, responses_file):
        # No file at all yet.
        llm.evict_llm_response(2026, 1, "lv-mia")
        assert llm.load_llm_responses() == {}
        assert not responses_file.exists()

    def test_noop_leaves_unrelated_entry_and_file_untouched(self, responses_file):
        seeded = {"2026-1-kc-buf-winner": {"verdict": "AGREE", "explain": "keep", "flag": None}}
        _seed(responses_file, seeded)

        llm.evict_llm_response(2026, 1, "lv-mia")

        assert llm.load_llm_responses() == seeded
