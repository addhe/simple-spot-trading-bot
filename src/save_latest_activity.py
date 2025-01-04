# src/save_latest_activity.py
import pickle
import logging

def save_latest_activity(latest_activity: dict) -> None:
    try:
        with open('latest_activity.pkl', 'wb') as f:
            pickle.dump(latest_activity, f)
    except Exception as e:
        logging.error(f"Error saat menyimpan latest_activity.pkl: {e}")
