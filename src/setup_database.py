from src.get_db_connection import get_db_connection

def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tabel transaksi yang sudah ada
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        symbol TEXT,
        type TEXT,
        quantity REAL,
        price REAL
    )
    ''')

    # Tabel baru untuk historical data
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS historical_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        timestamp TEXT,
        open_price REAL,
        high_price REAL,
        low_price REAL,
        close_price REAL,
        volume REAL,
        UNIQUE(symbol, timestamp)
    )
    ''')

    # Index untuk mempercepat query
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_historical_symbol_timestamp
    ON historical_data(symbol, timestamp)
    ''')

    conn.commit()
    conn.close()