# src/load_historical_data.py
import pickle
import logging

def load_historical_data() -> list:
    try:
        with open('historical_data.pkl', 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        logging.warning("File historical_data.pkl tidak ditemukan, menggunakan default.")
        return []
    except Exception as e:
        logging.error(f"Error saat membaca historical_data.pkl: {e}")
        return []
