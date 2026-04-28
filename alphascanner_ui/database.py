import sqlite3
import pandas as pd
import os
from datetime import datetime
from pathlib import Path

DB_PATH = os.environ.get(
    "ALPHASCANNER_USER_DB", "alphascanner_data.db"
)

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database schema."""
    with get_connection() as conn:
        # Notes Table
        conn.execute('''CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY, username TEXT, title TEXT, content TEXT, date TEXT
        )''')
        
        # Trade Journal Table
        conn.execute('''CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ticker TEXT, entry_date TEXT, 
            entry_price REAL, exit_date TEXT, exit_price REAL, quantity INTEGER, 
            pattern TEXT, notes TEXT, pnl REAL, status TEXT
        )''')
        
        # Portfolios & Holdings (Relational)
        conn.execute('''CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, name TEXT,
            UNIQUE(username, name)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id INTEGER, 
            ticker TEXT, quantity INTEGER, avg_price REAL, 
            date_added TEXT, date_updated TEXT,
            FOREIGN KEY(portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
        )''')
        
        # Watchlist Table
        conn.execute('''CREATE TABLE IF NOT EXISTS watchlist (
            username TEXT, category TEXT, ticker TEXT, PRIMARY KEY(username, category, ticker)
        )''')
        
        # Risk Positions Table
        conn.execute('''CREATE TABLE IF NOT EXISTS risk_positions (
            username TEXT, ticker TEXT, entry REAL, stop REAL, shares INTEGER, 
            risk_amount REAL, total_value REAL, date_added TEXT, PRIMARY KEY(username, ticker)
        )''')

def execute_query(query, params=(), is_select=False):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if is_select:
            return cursor.fetchall()
        conn.commit()

# Specific DAO helpers to simplify Tab logic
def get_all_notes(username):
    res = execute_query("SELECT * FROM notes WHERE username = ? ORDER BY date DESC", (username,), is_select=True)
    return [dict(row) for row in res]

def save_note(username, note_id, title, content):
    dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    execute_query("INSERT OR REPLACE INTO notes (id, username, title, content, date) VALUES (?, ?, ?, ?, ?)", 
                  (note_id, username, title, content, dt))

def delete_note(username, note_id):
    execute_query("DELETE FROM notes WHERE id = ? AND username = ?", (note_id, username))

def get_journal(username):
    res = execute_query("SELECT * FROM journal WHERE username = ? ORDER BY entry_date DESC", (username,), is_select=True)
    return [dict(row) for row in res]

def add_journal_entry(username, data):
    execute_query('''INSERT INTO journal (username, ticker, entry_date, entry_price, exit_date, exit_price, quantity, pattern, notes, pnl, status) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                  (username, data['ticker'], data['entry_date'], data['entry'], data['exit_date'], 
                   data['exit'], data['qty'], data['pattern'], data['notes'], data['pnl'], data['status']))

def get_portfolios_with_holdings(username):
    p_rows = execute_query("SELECT * FROM portfolios WHERE username = ?", (username,), is_select=True)
    portfolios = []
    for p in p_rows:
        h_rows = execute_query("SELECT * FROM holdings WHERE portfolio_id = ?", (p['id'],), is_select=True)
        portfolios.append({
            "id": p['id'],
            "name": p['name'],
            "holdings": [dict(h) for h in h_rows]
        })
    return portfolios

def add_holding(portfolio_id, ticker, qty, price):
    dt = datetime.now().strftime("%Y-%m-%d")
    # Upsert logic
    existing = execute_query("SELECT id FROM holdings WHERE portfolio_id = ? AND ticker = ?", (portfolio_id, ticker), is_select=True)
    if existing:
        execute_query("UPDATE holdings SET quantity = ?, avg_price = ?, date_updated = ? WHERE id = ?", 
                      (qty, price, dt, existing[0]['id']))
    else:
        execute_query("INSERT INTO holdings (portfolio_id, ticker, quantity, avg_price, date_added, date_updated) VALUES (?, ?, ?, ?, ?, ?)", 
                      (portfolio_id, ticker, qty, price, dt, dt))

def get_watchlist_data(username):
    rows = execute_query("SELECT category, ticker FROM watchlist WHERE username = ?", (username,), is_select=True)
    data = {}
    for r in rows:
        data.setdefault(r['category'], []).append(r['ticker'])
    if not data: data = {"Default": []}
    return data

def add_watchlist_ticker(username, category, ticker):
    execute_query("INSERT OR IGNORE INTO watchlist (username, category, ticker) VALUES (?, ?, ?)", (username, category, ticker))

def remove_watchlist_ticker(username, category, ticker):
    execute_query("DELETE FROM watchlist WHERE username = ? AND category = ? AND ticker = ?", (username, category, ticker))

def get_risk_positions(username):
    res = execute_query("SELECT * FROM risk_positions WHERE username = ?", (username,), is_select=True)
    return [dict(row) for row in res]

def add_risk_position(username, data):
    execute_query('''INSERT OR REPLACE INTO risk_positions (username, ticker, entry, stop, shares, risk_amount, total_value, date_added)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (username, data['ticker'], data['entry'], data['stop'], data['shares'], data['risk_amount'], data['total_value'], data['date_added']))

def remove_risk_position(username, ticker):
    execute_query("DELETE FROM risk_positions WHERE username = ? AND ticker = ?", (username, ticker))
