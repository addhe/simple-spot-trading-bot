import time
from src.send_asset_status import send_asset_status

STATUS_INTERVAL = 3600  # 1 jam dalam detik

def status_monitor():
    """Thread terpisah untuk memantau dan mengirim status setiap jam."""
    while True:
        send_asset_status()
        time.sleep(STATUS_INTERVAL)