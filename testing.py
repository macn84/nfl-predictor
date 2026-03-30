import json
from datetime import date

# Load the results
with open("data/optimiser_results.json") as f:
    data = json.load(f)

print("=== WINNER TOP 5 — Training vs (need validation) ===")
for i, r in enumerate(data["top_winner"][:5], 1):
    w = r["weights"]
    print(f"\nRank {i}:")
    print(f"  Weights: rf={w['recent_form']} ha={w['home_away']} h2h={w['head_to_head']} "
          f"bl={w['betting_lines']} coach={w['coaching_matchup']} wx={w['weather']}")
    print(f"  Train winner_wscore={r['winner_wscore']:.4f}  hc_acc={r['winner_hc_acc']:.1%}  hc_n={r['winner_hc_n']}")
    print(f"  Train simple_acc={r['simple_acc']:.1%}")

print("\n=== COVER TOP 5 ===")
for i, r in enumerate(data["top_cover"][:5], 1):
    w = r["weights"]
    print(f"\nRank {i}:")
    print(f"  Weights: rf={w['recent_form']} ha={w['home_away']} h2h={w['head_to_head']} "
          f"bl={w['betting_lines']} coach={w['coaching_matchup']} wx={w['weather']}")
    print(f"  Train cover_wscore={r['cover_wscore']:.4f}  winner_wscore={r['winner_wscore']:.4f}")
    print(f"  Train simple_acc={r['simple_acc']:.1%}")