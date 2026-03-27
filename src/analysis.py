"""
analysis.py - Stats and aggregation functions for NFL analytics
"""

import pandas as pd


def team_record(schedules: pd.DataFrame, season: int, team: str) -> dict:
    """Return win/loss/tie record for a team in a given season."""
    df = schedules[schedules['season'] == season]
    home = df[df['home_team'] == team]
    away = df[df['away_team'] == team]

    wins = (
        (home['result'] > 0).sum() +
        (away['result'] < 0).sum()
    )
    losses = (
        (home['result'] < 0).sum() +
        (away['result'] > 0).sum()
    )
    ties = (
        (home['result'] == 0).sum() +
        (away['result'] == 0).sum()
    )
    return {'team': team, 'season': season, 'W': int(wins), 'L': int(losses), 'T': int(ties)}


def top_passers(weekly: pd.DataFrame, season: int, week: int = None, top_n: int = 10) -> pd.DataFrame:
    """Return top QBs by passing yards for a season (optionally filtered by week)."""
    df = weekly[(weekly['season'] == season) & (weekly['position'] == 'QB')]
    if week is not None:
        df = df[df['week'] == week]
    return (
        df.groupby('player_name')[['passing_yards', 'passing_tds', 'interceptions']]
        .sum()
        .sort_values('passing_yards', ascending=False)
        .head(top_n)
        .reset_index()
    )


def top_rushers(weekly: pd.DataFrame, season: int, top_n: int = 10) -> pd.DataFrame:
    """Return top RBs by rushing yards for a season."""
    df = weekly[(weekly['season'] == season) & (weekly['position'] == 'RB')]
    return (
        df.groupby('player_name')[['rushing_yards', 'rushing_tds']]
        .sum()
        .sort_values('rushing_yards', ascending=False)
        .head(top_n)
        .reset_index()
    )


def top_receivers(weekly: pd.DataFrame, season: int, top_n: int = 10) -> pd.DataFrame:
    """Return top receivers by receiving yards for a season."""
    df = weekly[(weekly['season'] == season) & (weekly['position'].isin(['WR', 'TE', 'RB']))]
    return (
        df.groupby('player_name')[['receiving_yards', 'receiving_tds', 'receptions']]
        .sum()
        .sort_values('receiving_yards', ascending=False)
        .head(top_n)
        .reset_index()
    )


def scoring_offense(schedules: pd.DataFrame, season: int) -> pd.DataFrame:
    """Return average points scored per game by team for a season."""
    df = schedules[schedules['season'] == season]
    home = df[['home_team', 'home_score']].rename(columns={'home_team': 'team', 'home_score': 'points'})
    away = df[['away_team', 'away_score']].rename(columns={'away_team': 'team', 'away_score': 'points'})
    combined = pd.concat([home, away])
    return (
        combined.groupby('team')['points']
        .mean()
        .round(1)
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={'points': 'avg_points_per_game'})
    )
