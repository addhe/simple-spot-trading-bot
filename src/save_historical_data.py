# src/save_historical_data.py
import pickle
import logging

def save_historical_data(historical_data: list) -> None:
    try:
        with open('historical_data.pkl', 'wb') as f:
            pickle.dump(historical_data, f)
    except Exception as e:
        logging.error(f"Error saat menyimpan historical_data.pkl: {e}")
