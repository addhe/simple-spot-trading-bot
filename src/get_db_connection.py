import sqlite3

def get_db_connection():
    """Thread-safe database connection"""
    return sqlite3.connect('table_transactions.db')