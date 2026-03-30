from app.prediction.engine import predict
from datetime import date

result = predict(
    home_team="BUF",
    away_team="KC",
    season=2024,
    game_date=date(2024, 12, 1),
)

for f in result.factors:
    print(f"{f.name:20} score={f.score:7.2f}  weight={f.weight:.3f}  skipped={f.supporting_data.get('skipped', False)}")

print(f"\nWinner: {result.predicted_winner}  Confidence: {result.confidence}")