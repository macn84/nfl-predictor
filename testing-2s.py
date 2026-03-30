import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from datetime import date
from app.data.loader import load_schedules
from app.data.spreads import get_spread

# Load validation seasons
print("Loading 2024-2025 schedules...")
schedules = load_schedules([2021, 2022, 2023, 2024, 2025])
val_games = schedules[
    (schedules["season"].isin([2024, 2025])) &
    schedules["result"].notna()
].copy()
print(f"Validation games: {len(val_games)}")

# Load cached scores
with open("data/optimiser_results.json") as f:
    data = json.load(f)

slope = data["meta"]["slope"]
intercept = data["meta"]["intercept"]

# We need the score cache to do this properly
# Check if it exists
cache_path = "data/score_cache.json"
if not os.path.exists(cache_path):
    print("ERROR: score_cache.json not found - run optimise_weights.py --rebuild-cache first")
    sys.exit(1)

with open(cache_path) as f:
    cache = json.load(f)

# Filter cache to validation seasons
val_cache = [g for g in cache if g["season"] in [2024, 2025]]
print(f"Validation games in cache: {len(val_cache)}")

FACTOR_NAMES = ["recent_form", "home_away", "head_to_head", 
                "betting_lines", "coaching_matchup", "weather"]

def evaluate(weight_dict, games, slope, intercept):
    import numpy as np
    w = np.array([weight_dict[f] for f in FACTOR_NAMES])
    
    winner_num = winner_den = 0.0
    cover_num = cover_den = 0.0
    hc_correct = hc_total = 0
    simple_correct = 0

    for g in games:
        scores = np.array([g["factors"][f]["score"] for f in FACTOR_NAMES])
        skipped = np.array([g["factors"][f]["skipped"] for f in FACTOR_NAMES])
        
        eff_w = np.where(skipped, 0.0, w)
        total_w = eff_w.sum()
        if total_w == 0:
            continue
        norm_w = eff_w / total_w
        ws = (scores * norm_w).sum()
        confidence = 50 + abs(ws) / 2
        cw = max(0, confidence - 50) / 50

        predicted_winner = g["home_team"] if ws >= 0 else g["away_team"]
        actual_winner = g["home_team"] if g["actual_margin"] > 0 else g["away_team"]
        correct = predicted_winner == actual_winner

        winner_num += cw * int(correct)
        winner_den += cw
        simple_correct += int(correct)

        if confidence >= 70:
            hc_correct += int(correct)
            hc_total += 1

        if g.get("spread") is not None:
            pred_margin = slope * ws + intercept
            cover_margin = pred_margin - g["spread"]
            pred_cover = g["home_team"] if cover_margin > 0 else g["away_team"]
            actual_cover = g["home_team"] if g["actual_margin"] > g["spread"] else g["away_team"]
            if g["actual_margin"] != g["spread"]:
                cover_num += cw * int(pred_cover == actual_cover)
                cover_den += cw

    return {
        "winner_wscore": winner_num / winner_den if winner_den > 0 else 0,
        "simple_acc": simple_correct / len(games),
        "hc_acc": hc_correct / hc_total if hc_total > 0 else 0,
        "hc_n": hc_total,
        "cover_wscore": cover_num / cover_den if cover_den > 0 else 0,
    }

print("\n=== WINNER TOP 5 — Train vs Validation ===")
for i, r in enumerate(data["top_winner"][:5], 1):
    val = evaluate(r["weights"], val_cache, slope, intercept)
    drop = r["winner_wscore"] - val["winner_wscore"]
    flag = " ⚠ OVERFIT" if drop > 0.05 else ""
    print(f"\nRank {i}: rf={r['weights']['recent_form']} ha={r['weights']['home_away']} "
          f"h2h={r['weights']['head_to_head']} coach={r['weights']['coaching_matchup']} "
          f"wx={r['weights']['weather']}")
    print(f"  Train:  winner={r['winner_wscore']:.4f}  hc={r['winner_hc_acc']:.1%}({r['winner_hc_n']})  acc={r['simple_acc']:.1%}")
    print(f"  Val:    winner={val['winner_wscore']:.4f}  hc={val['hc_acc']:.1%}({val['hc_n']})  acc={val['simple_acc']:.1%}  drop={drop:+.4f}{flag}")

print("\n=== COVER TOP 5 — Train vs Validation ===")
for i, r in enumerate(data["top_cover"][:5], 1):
    val = evaluate(r["weights"], val_cache, slope, intercept)
    drop = r["cover_wscore"] - val["cover_wscore"]
    flag = " ⚠ OVERFIT" if drop > 0.05 else ""
    print(f"\nRank {i}: rf={r['weights']['recent_form']} ha={r['weights']['home_away']} "
          f"h2h={r['weights']['head_to_head']} coach={r['weights']['coaching_matchup']} "
          f"wx={r['weights']['weather']}")
    print(f"  Train:  cover={r['cover_wscore']:.4f}  winner={r['winner_wscore']:.4f}  acc={r['simple_acc']:.1%}")
    print(f"  Val:    cover={val['cover_wscore']:.4f}  winner={val['winner_wscore']:.4f}  acc={val['simple_acc']:.1%}  drop={drop:+.4f}{flag}")