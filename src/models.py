"""
models.py - Machine learning helpers for NFL analytics
"""

import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error
from sklearn.preprocessing import StandardScaler


def build_win_predictor(schedules: pd.DataFrame, features: list[str]) -> dict:
    """
    Train a simple win/loss classifier based on schedule features.
    Expects schedules df with a 'result' column (positive = home win).

    Example features: ['spread_line', 'total_line', 'div_game', 'roof', 'surface']
    """
    df = schedules.dropna(subset=features + ['result']).copy()
    df['home_win'] = (df['result'] > 0).astype(int)

    X = pd.get_dummies(df[features])
    y = df['home_win']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"Win predictor accuracy: {acc:.3f}")

    importance = pd.Series(model.feature_importances_, index=X.columns)
    print("\nTop feature importances:")
    print(importance.sort_values(ascending=False).head(10))

    return {'model': model, 'accuracy': acc, 'feature_columns': list(X.columns)}


def build_points_predictor(schedules: pd.DataFrame, features: list[str]) -> dict:
    """
    Train a regressor to predict total points scored in a game.

    Example features: ['spread_line', 'total_line', 'div_game']
    """
    df = schedules.dropna(subset=features + ['home_score', 'away_score']).copy()
    df['total_points'] = df['home_score'] + df['away_score']

    X = pd.get_dummies(df[features])
    y = df['total_points']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train_scaled, y_train)

    preds = model.predict(X_test_scaled)
    mae = mean_absolute_error(y_test, preds)
    print(f"Points predictor MAE: {mae:.2f} points")

    return {'model': model, 'scaler': scaler, 'mae': mae, 'feature_columns': list(X.columns)}
