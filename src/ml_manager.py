import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from typing import Dict, List, Tuple, Optional
import joblib
import os
from datetime import datetime, timedelta
from src.logger import logger
from src.monitoring import metrics

class MLManager:
    def __init__(self, model_dir: str = "models"):
        self.model_dir = model_dir
        self.models: Dict[str, Dict] = {}  # symbol -> {timeframe -> model}
        self.scalers: Dict[str, Dict] = {}  # symbol -> {timeframe -> scaler}
        
        if not os.path.exists(model_dir):
            os.makedirs(model_dir)

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for machine learning"""
        # Technical indicators
        df['rsi'] = df['close'].rolling(window=14).apply(lambda x: pd.Series(x).ta.rsi().iloc[-1])
        df['macd'] = df['close'].rolling(window=26).apply(lambda x: pd.Series(x).ta.macd().iloc[-1])
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = df['close'].rolling(window=20).apply(
            lambda x: pd.Series(x).ta.bbands(length=20, std=2)
        ).T.values
        
        # Volume indicators
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        df['volume_std'] = df['volume'].rolling(window=20).std()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        # Price action features
        df['price_change'] = df['close'].pct_change()
        df['price_volatility'] = df['price_change'].rolling(window=20).std()
        df['high_low_range'] = (df['high'] - df['low']) / df['close']
        
        # Target variable (future returns)
        df['target'] = df['close'].shift(-1) / df['close'] - 1
        
        # Drop NaN values
        df.dropna(inplace=True)
        
        return df

    def train_model(self, symbol: str, timeframe: str, historical_data: pd.DataFrame) -> None:
        """Train a machine learning model for a symbol and timeframe"""
        try:
            # Prepare features
            df = self._prepare_features(historical_data.copy())
            
            # Prepare features and target
            features = ['rsi', 'macd', 'bb_upper', 'bb_middle', 'bb_lower',
                       'volume_sma', 'volume_std', 'volume_ratio',
                       'price_change', 'price_volatility', 'high_low_range']
            
            X = df[features]
            y = (df['target'] > 0).astype(int)  # Binary classification
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train LightGBM model
            model = lgb.LGBMClassifier(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=5,
                num_leaves=32,
                random_state=42
            )
            
            model.fit(
                X_train_scaled,
                y_train,
                eval_set=[(X_test_scaled, y_test)],
                eval_metric='auc',
                early_stopping_rounds=10,
                verbose=False
            )
            
            # Save model and scaler
            if symbol not in self.models:
                self.models[symbol] = {}
                self.scalers[symbol] = {}
            
            self.models[symbol][timeframe] = model
            self.scalers[symbol][timeframe] = scaler
            
            # Save to disk
            model_path = os.path.join(self.model_dir, f"{symbol}_{timeframe}_model.joblib")
            scaler_path = os.path.join(self.model_dir, f"{symbol}_{timeframe}_scaler.joblib")
            
            joblib.dump(model, model_path)
            joblib.dump(scaler, scaler_path)
            
            logger.info(f"Successfully trained model for {symbol} {timeframe}")
            metrics.record_success("model_training", {"symbol": symbol, "timeframe": timeframe})
            
        except Exception as e:
            logger.error(f"Error training model for {symbol} {timeframe}: {str(e)}")
            metrics.record_error("model_training")
            raise

    def predict(self, symbol: str, timeframe: str, current_data: pd.DataFrame) -> Optional[float]:
        """Get prediction for current market conditions"""
        try:
            if symbol not in self.models or timeframe not in self.models[symbol]:
                model_path = os.path.join(self.model_dir, f"{symbol}_{timeframe}_model.joblib")
                scaler_path = os.path.join(self.model_dir, f"{symbol}_{timeframe}_scaler.joblib")
                
                if os.path.exists(model_path) and os.path.exists(scaler_path):
                    self.models.setdefault(symbol, {})[timeframe] = joblib.load(model_path)
                    self.scalers.setdefault(symbol, {})[timeframe] = joblib.load(scaler_path)
                else:
                    logger.warning(f"No model found for {symbol} {timeframe}")
                    return None
            
            # Prepare features
            df = self._prepare_features(current_data.copy())
            features = ['rsi', 'macd', 'bb_upper', 'bb_middle', 'bb_lower',
                       'volume_sma', 'volume_std', 'volume_ratio',
                       'price_change', 'price_volatility', 'high_low_range']
            
            X = df[features].iloc[-1:]
            X_scaled = self.scalers[symbol][timeframe].transform(X)
            
            # Get prediction probability
            prob = self.models[symbol][timeframe].predict_proba(X_scaled)[0][1]
            
            return prob
            
        except Exception as e:
            logger.error(f"Error getting prediction for {symbol} {timeframe}: {str(e)}")
            metrics.record_error("model_prediction")
            return None
