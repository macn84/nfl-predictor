import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.prediction.calibration import MARGIN_SLOPE, MARGIN_INTERCEPT
from app.config import settings

FACTOR_NAMES = ["recent_form", "home_away", "head_to_head",
                "betting_lines", "coaching_matchup", "weather"]

with open("data/score_cache.json") as f:
    cache = json.load(f)

games_2022 = [g for g in cache if g["season"] == 2022 and g.get("spread") is not None][:20]
weights = settings.cover_weights

correct = wrong = 0
for g in games_2022:
    w = {k: 0.0 if g["factors"][k]["skipped"] else weights[k] for k in FACTOR_NAMES}
    total = sum(w.values())
    if total == 0:
        continue
    norm = {k: v/total for k,v in w.items()}
    ws = sum(g["factors"][k]["score"] * norm[k] for k in norm)
    pred_margin = MARGIN_SLOPE * ws + MARGIN_INTERCEPT
    spread = g["spread"]
    actual_margin = g["actual_margin"]

    pred_cover = g["home_team"] if pred_margin > spread else g["away_team"]
    actual_cover = g["home_team"] if actual_margin > spread else g["away_team"]
    match = pred_cover == actual_cover

    if match:
        correct += 1
    else:
        wrong += 1

    print(f"{g['home_team']:3s} vs {g['away_team']:3s} "
          f"actual_margin={actual_margin:+.1f} spread={spread:+.1f} "
          f"pred_margin={pred_margin:+.1f} "
          f"pred_cover={pred_cover:3s} actual_cover={actual_cover:3s} "
          f"{'✓' if match else '✗'}")

print(f"\nSample: {correct}/{correct+wrong} = {correct/(correct+wrong):.1%}")