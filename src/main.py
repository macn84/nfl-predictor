"""
main.py - Example script tying all modules together
"""

from src.fetch import load_schedules, load_weekly_stats
from src.analysis import top_passers, top_rushers, scoring_offense
from src.viz import top_players_chart, scoring_offense_chart

SEASONS = [2023, 2024]

# --- Load data ---
schedules = load_schedules(SEASONS)
weekly = load_weekly_stats(SEASONS)

# --- Analysis ---
passers = top_passers(weekly, season=2024, top_n=10)
print("\nTop 10 Passers - 2024:")
print(passers.to_string(index=False))

rushers = top_rushers(weekly, season=2024, top_n=10)
print("\nTop 10 Rushers - 2024:")
print(rushers.to_string(index=False))

offense = scoring_offense(schedules, season=2024)
print("\nScoring Offense - 2024:")
print(offense.head(10).to_string(index=False))

# --- Visualizations ---
top_players_chart(passers, player_col='player_name', stat_col='passing_yards',
                  title='Top 10 Passers by Yards - 2024',
                  save_as='top_passers_2024.png')

scoring_offense_chart(offense, season=2024,
                      save_as='scoring_offense_2024.png')
