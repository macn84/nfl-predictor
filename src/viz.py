"""
viz.py - Visualization helpers for NFL analytics
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Consistent style
sns.set_theme(style='darkgrid')
FIGSIZE = (12, 6)


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str,
              xlabel: str = None, ylabel: str = None,
              color: str = '#1f4e79', save_as: str = None):
    """Generic horizontal bar chart."""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    sns.barplot(data=df, x=x, y=y, color=color, ax=ax)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel(xlabel or x)
    ax.set_ylabel(ylabel or y)
    plt.tight_layout()
    if save_as:
        path = os.path.join(OUTPUT_DIR, save_as)
        plt.savefig(path, dpi=150)
        print(f"Saved to {path}")
    plt.show()


def top_players_chart(df: pd.DataFrame, player_col: str, stat_col: str,
                      title: str, save_as: str = None):
    """Horizontal bar chart for top player rankings."""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    sns.barplot(data=df, x=stat_col, y=player_col, color='#c8102e', ax=ax)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel(stat_col.replace('_', ' ').title())
    ax.set_ylabel('')
    plt.tight_layout()
    if save_as:
        path = os.path.join(OUTPUT_DIR, save_as)
        plt.savefig(path, dpi=150)
        print(f"Saved to {path}")
    plt.show()


def scoring_offense_chart(df: pd.DataFrame, season: int, save_as: str = None):
    """Bar chart of average points per game by team."""
    top = df.head(16)
    fig, ax = plt.subplots(figsize=FIGSIZE)
    sns.barplot(data=top, x='avg_points_per_game', y='team', palette='Blues_r', ax=ax)
    ax.set_title(f'{season} NFL Scoring Offense (Top 16)', fontsize=14, fontweight='bold')
    ax.set_xlabel('Avg Points Per Game')
    ax.set_ylabel('')
    plt.tight_layout()
    if save_as:
        path = os.path.join(OUTPUT_DIR, save_as)
        plt.savefig(path, dpi=150)
        print(f"Saved to {path}")
    plt.show()
