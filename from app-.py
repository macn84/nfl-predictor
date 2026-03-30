from app.prediction.factors.betting_lines import _fetch_odds, _find_spread

# Step 1 - can we reach the API and get data back?
odds = _fetch_odds()
if odds is None:
    print("API call failed - check logs above for the error")
elif len(odds) == 0:
    print("API returned empty list - no games currently available")
else:
    print(f"API returned {len(odds)} games")
    # Step 2 - show the first game so we can see the team name format
    import json
    print(json.dumps(odds[0], indent=2))

# Step 3 - try the match directly
spread = _find_spread(odds or [], "BUF", "KC")
print(f"\nSpread found for BUF vs KC: {spread}")