import json
from collections import Counter

with open("data/score_cache.json") as f:
    cache = json.load(f)

total = len(cache)
weather_skipped = sum(1 for g in cache if g["factors"]["weather"]["skipped"])
weather_active  = total - weather_skipped

print(f"Total games in cache: {total}")
print(f"Weather skipped: {weather_skipped} ({weather_skipped/total:.1%})")
print(f"Weather active:  {weather_active} ({weather_active/total:.1%})")

# Score distribution for non-skipped games
scores = [g["factors"]["weather"]["score"] 
          for g in cache if not g["factors"]["weather"]["skipped"]]

if scores:
    from collections import Counter
    score_counts = Counter(scores)
    print(f"\nWeather score distribution (active games):")
    for score, count in sorted(score_counts.items()):
        print(f"  score={score:5.1f}  count={count}")
else:
    print("\nNO active weather scores — all games are skipped")

# Sample 5 active weather games to verify
print(f"\nSample active weather games:")
shown = 0
for g in cache:
    if not g["factors"]["weather"]["skipped"] and shown < 5:
        print(f"  {g['home_team']} vs {g['away_team']} {g['game_date']}: "
              f"score={g['factors']['weather']['score']}")
        shown += 1

# Sample 5 skipped to see why
print(f"\nSample skipped weather games:")
shown = 0
for g in cache:
    if g["factors"]["weather"]["skipped"] and shown < 3:
        print(f"  {g['home_team']} vs {g['away_team']} {g['game_date']}: "
              f"factors={g['factors']['weather']}")
        shown += 1