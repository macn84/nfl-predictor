"""
test_llm_facts.py - Tests for the redesigned LLM pipeline: nfl.com injury
parsing, the code-built facts block, response validation and hash-based cache
invalidation. The Anthropic client is always mocked.
"""

import json

import pytest

from app.data import injuries
from app.services import game_facts, llm

# Trimmed copy of the real nfl.com markup (one team table per sub-title).
_HTML = """
<div class="d3-o-section-sub-title"><span>Packers</span></div>
<table><thead><tr><th>Player</th><th>Position</th><th>Injuries</th><th>Practice Status</th><th>Game Status</th></tr></thead>
<tbody>
<tr><td scope="row"><a href="/p/1"> Jordan Love </a></td><td>QB</td><td>Knee</td><td>Did Not Participate In Practice</td><td>Out</td></tr>
<tr><td scope="row"><a href="/p/2"> Some Guard </a></td><td>G</td><td></td><td>Full Participation in Practice</td><td></td></tr>
</tbody></table>
<div class="d3-o-section-sub-title"><span>Lions</span></div>
<table><tbody>
<tr><td><a> D.J. Reed </a></td><td>CB</td><td>Foot</td><td>Limited Participation in Practice</td><td>Questionable</td></tr>
</tbody></table>
"""  # noqa: E501 - fixture mirrors real nfl.com markup


def _game(**over):
    g = {
        "game_id": "gb-det", "season": 2026, "week": 2, "gameday": "2026-09-20",
        "home_team": "GB", "away_team": "DET",
        "predicted_winner": "GB", "winner_confidence": 70.0,
        "predicted_cover": "GB", "cover_confidence": 63.0,
        "spread": 4.5,  # engine convention: positive = home favoured
        "predicted_margin": 7.0,
    }
    g.update(over)
    return g


class TestInjuryParser:
    def test_parses_rows_with_team_abbreviations(self):
        rows = injuries.parse_injury_page(_HTML)
        assert len(rows) == 3
        assert rows[0] == {
            "team": "GB", "player": "Jordan Love", "position": "QB", "injury": "Knee",
            "practice_status": "Did Not Participate In Practice", "game_status": "Out",
        }
        assert rows[2]["team"] == "DET" and rows[2]["player"] == "D.J. Reed"

    def test_unrecognised_page_returns_no_rows(self):
        assert injuries.parse_injury_page("<html><body>nothing</body></html>") == []


class TestFormatLine:
    def test_matches_ui_sign_convention(self):
        # UI: home line = -spread. spread 4.5 => GB -4.5, DET +4.5.
        assert game_facts.format_line("GB", 4.5, home_team="GB") == "GB -4.5"
        assert game_facts.format_line("DET", 4.5, home_team="GB") == "DET +4.5"

    def test_pickem_zero_is_not_dropped(self):
        assert game_facts.format_line("GB", 0.0, home_team="GB") == "GB PK"

    def test_no_line(self):
        assert game_facts.format_line("GB", None, home_team="GB") == "no line"


class TestBuildGameFacts:
    def test_line_and_qb_flag(self):
        report = {"rows": injuries.parse_injury_page(_HTML), "fetched_at": "t"}
        facts = game_facts.build_game_facts(
            _game(), report, {"GB": "Jordan Love", "DET": "Jared Goff"}
        )
        assert facts["line_text"] == "GB -4.5"
        assert "LINE SHOWN TO USER: GB -4.5 / DET +4.5" in facts["text"]
        assert facts["has_injury_data"]
        assert facts["flags"] == ["GB QB Jordan Love is listed Out"]
        assert "jordan love" in facts["allowed_names"]
        # Full-participation, no-status players are omitted.
        assert "Some Guard" not in facts["text"]

    def test_missing_team_means_no_injury_data(self):
        report = {"rows": [r for r in injuries.parse_injury_page(_HTML) if r["team"] == "GB"]}
        facts = game_facts.build_game_facts(_game(), report, {})
        assert not facts["has_injury_data"]
        assert "INJURY REPORT: unavailable" in facts["text"]

    def test_hash_changes_when_line_changes(self):
        report = {"rows": injuries.parse_injury_page(_HTML)}
        a = game_facts.build_game_facts(_game(spread=4.5), report, {})
        b = game_facts.build_game_facts(_game(spread=3.5), report, {})
        assert a["hash"] != b["hash"]


class TestValidateResponse:
    facts = {"allowed_names": {"jordan love", "dj reed"}}

    def _ok(self, **over):
        r = {"verdict": "AGREE", "explain": "", "impact_pts": None, "evidence": []}
        r.update(over)
        return r

    def test_valid_disagree(self):
        r = self._ok(
            verdict="DISAGREE",
            explain="Packers starting QB Jordan Love is out, which the model does not price in.",
            evidence=[{"fact": "Jordan Love Out", "source": "facts"}],
        )
        assert llm.validate_response(r, self.facts) == []

    def test_rejects_stale_player_name(self):
        r = self._ok(explain="Aaron Rodgers gives Green Bay the edge.")
        problems = llm.validate_response(r, self.facts)
        assert any("Aaron" in p for p in problems)

    def test_rejects_injury_report_filler(self):
        r = self._ok(explain="Solid pick, but check the injury report before kickoff.")
        assert llm.validate_response(r, self.facts)

    def test_rejects_restated_line(self):
        r = self._ok(explain="The model correctly picks the home side to cover -3.5.")
        assert any("line" in p for p in llm.validate_response(r, self.facts))

    def test_disagree_requires_evidence(self):
        r = self._ok(verdict="DISAGREE", explain="Jordan Love is out.")
        assert any("evidence" in p for p in llm.validate_response(r, self.facts))

    def test_rejects_old_verdicts(self):
        assert llm.validate_response(self._ok(verdict="FADE"), self.facts)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(llm.settings, "llm_web_search_enabled", False)
    return tmp_path / "llm_responses.json"


def _payload(spread=4.5, rows=True):
    report = {"rows": injuries.parse_injury_page(_HTML) if rows else []}
    g = _game(spread=spread)
    g["facts"] = game_facts.build_game_facts(g, report, {"GB": "Jordan Love", "DET": "Jared Goff"})
    return g


class TestAnalyzeGame:
    def _patch_llm(self, monkeypatch, result, calls):
        monkeypatch.setattr(llm, "_build_prompt", lambda g, m: ("sys", "user"))

        def fake(system, user, tool, *, web_search=False):
            calls.append(user)
            return result

        monkeypatch.setattr(llm, "_call_anthropic_structured", fake)

    def test_no_injury_data_skips_llm(self, store, monkeypatch):
        calls = []
        self._patch_llm(monkeypatch, {}, calls)
        entry = llm.analyze_game(_payload(rows=False))
        assert entry["verdict"] == "NO_DATA" and calls == []

    def test_cache_reused_until_facts_change(self, store, monkeypatch):
        calls = []
        good = {"verdict": "AGREE", "explain": "", "impact_pts": None, "evidence": []}
        self._patch_llm(monkeypatch, good, calls)
        llm.analyze_game(_payload(spread=4.5))
        llm.analyze_game(_payload(spread=4.5))
        assert len(calls) == 1              # same hash -> cached
        llm.analyze_game(_payload(spread=3.5))
        assert len(calls) == 2              # line moved -> regenerated

    def test_hallucinated_response_twice_becomes_neutral_agree(self, store, monkeypatch):
        calls = []
        bad = {"verdict": "DISAGREE", "explain": "Aaron Rodgers is out.",
               "impact_pts": 3, "evidence": [{"fact": "x", "source": "facts"}]}
        self._patch_llm(monkeypatch, bad, calls)
        entry = llm.analyze_game(_payload())
        assert len(calls) == 2              # one retry
        assert entry["verdict"] == "AGREE" and entry["flag"] is None
        assert entry.get("validation_failed")

    def test_disagree_sets_flag_and_persists(self, store, monkeypatch):
        calls = []
        good = {"verdict": "DISAGREE",
                "explain": "Jordan Love is out for Green Bay.",
                "impact_pts": 4.0, "evidence": [{"fact": "Jordan Love Out", "source": "facts"}]}
        self._patch_llm(monkeypatch, good, calls)
        entry = llm.analyze_game(_payload())
        assert entry["flag"] == entry["explain"]
        assert (
            json.loads(store.read_text())["2026-2-gb-det-cover"]["input_hash"]
            == entry["input_hash"]
        )


class TestValidatorFalsePositives:
    facts = {"allowed_names": {"michael penix", "tua tagovailoa"}}

    def _r(self, explain, evidence=None):
        return {
            "verdict": "AGREE",
            "explain": explain,
            "impact_pts": None,
            "evidence": evidence or [],
        }

    def test_name_suffix_and_position_plural_are_not_flagged(self):
        r = self._r("Michael Penix Jr. is Out and both QBs are hurt.")
        assert llm.validate_response(r, self.facts) == []

    def test_name_from_web_search_text_is_allowed(self):
        r = self._r("Kirk Cousins starts for Atlanta.")
        assert llm.validate_response(r, self.facts)
        assert (
            llm.validate_response(r, self.facts, search_text="Falcons: Kirk Cousins to start")
            == []
        )


class TestTokenGate:
    def test_unflagged_game_makes_no_llm_call(self, tmp_path, monkeypatch):
        monkeypatch.setattr(llm.settings, "cache_dir", str(tmp_path))
        calls = []
        monkeypatch.setattr(llm, "_call_anthropic_structured", lambda *a, **k: calls.append(1))
        # Only a Questionable CB (no QB issue, <4 out): no flags.
        rows = [r for r in injuries.parse_injury_page(_HTML) if r["position"] != "QB"]
        g = _game()
        g["facts"] = game_facts.build_game_facts(g, {"rows": rows}, {})
        assert g["facts"]["flags"] == []
        entry = llm.analyze_game(g)
        assert calls == [] and entry["verdict"] == "AGREE"

    def test_facts_omit_full_participation_and_practice_text_when_status_set(self):
        report = {"rows": injuries.parse_injury_page(_HTML)}
        text = game_facts.build_game_facts(_game(), report, {})["text"]
        assert "Some Guard" not in text
        # QB Love has a game status, so practice text dropped
        assert "Did Not Participate" not in text


class TestAgreeIsSilent:
    def test_possessive_team_name_not_flagged(self):
        r = {"verdict": "DISAGREE", "explain": "Green Bay's QB Jordan Love is out.",
             "impact_pts": 3, "evidence": [{"fact": "x", "source": "facts"}]}
        assert llm.validate_response(r, {"allowed_names": {"jordan love"}}) == []

    def test_agree_prose_is_discarded_without_retry(self, tmp_path, monkeypatch):
        monkeypatch.setattr(llm.settings, "llm_web_search_enabled", False)
        calls = []
        chatty = {"verdict": "AGREE", "explain": "Aaron Rodgers is fine.", "impact_pts": -2,
                  "evidence": [{"fact": "x", "source": "facts"}]}
        monkeypatch.setattr(
            llm, "_call_anthropic_structured", lambda *a, **k: calls.append(1) or chatty
        )
        out = llm._generate("s", "u", "cover", {"allowed_names": set()})
        assert len(calls) == 1
        assert out == {"verdict": "AGREE", "explain": "", "impact_pts": None, "evidence": []}


class TestFirstNameBeforeSurname:
    def test_first_name_ok_when_only_surname_supplied(self):
        # No injury row for Love here: only the abbreviated assumed-QB name "J.Love".
        facts = game_facts.build_game_facts(_game(), {"rows": []}, {"GB": "J.Love"})
        r = {"verdict": "DISAGREE", "explain": "Jordan Love is the concern for Green Bay.",
             "impact_pts": 2, "evidence": [{"fact": "x", "source": "facts"}]}
        assert llm.validate_response(r, facts) == []
