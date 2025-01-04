# src/load_latest_activity.py
import pickle
import logging

def load_latest_activity() -> dict:
    try:
        with open('latest_activity.pkl', 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        logging.warning("File latest_activity.pkl tidak ditemukan, menggunakan default.")
        return {
            'buy': False,
            'sell': False,
            'symbol': '',
            'quantity': 0,
            'price': 0,
            'estimasi_profit': 0,
            'stop_loss': 0,
            'take_profit': 0
        }
    except Exception as e:
        logging.error(f"Error saat membaca latest_activity.pkl: {e}")
        return {
            'buy': False,
            'sell': False,
            'symbol': '',
            'quantity': 0,
            'price': 0,
            'estimasi_profit': 0,
            'stop_loss': 0,
            'take_profit': 0
        }
