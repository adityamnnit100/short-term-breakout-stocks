import sqlite3
import pandas as pd
import os
import json
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

        # Append-only setup analysis history
        conn.execute('''CREATE TABLE IF NOT EXISTS setup_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date TEXT,
            ticker TEXT,
            scan_mode TEXT,
            setup_score REAL,
            base_score REAL,
            compression_score REAL,
            volume_score REAL,
            resistance_score REAL,
            structure_score REAL,
            risk_score REAL,
            category TEXT,
            reasons TEXT,
            weaknesses TEXT
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS transition_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date TEXT,
            ticker TEXT,
            scan_mode TEXT,
            transition_score REAL,
            setup_velocity_score REAL,
            rs_acceleration_score REAL,
            volume_transition_score REAL,
            compression_evolution_score REAL,
            resistance_pressure_score REAL,
            price_acceptance_score REAL,
            opportunity_velocity_score REAL,
            category TEXT,
            qualifies INTEGER,
            reasons TEXT,
            weaknesses TEXT,
            metrics TEXT
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS trigger_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date TEXT,
            ticker TEXT,
            scan_mode TEXT,
            trigger_decision TEXT,
            trigger_confidence TEXT,
            trigger_score REAL,
            qualifies INTEGER,
            reasons TEXT,
            weaknesses TEXT,
            module_results TEXT,
            metrics TEXT
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

def append_setup_analysis_rows(rows):
    if not rows:
        return
    init_db()
    payload = [
        (
            row.get("analysis_date"),
            row.get("ticker"),
            row.get("scan_mode"),
            float(row.get("setup_score", 0) or 0),
            float(row.get("base_score", 0) or 0),
            float(row.get("compression_score", 0) or 0),
            float(row.get("volume_score", 0) or 0),
            float(row.get("resistance_score", 0) or 0),
            float(row.get("structure_score", 0) or 0),
            float(row.get("risk_score", 0) or 0),
            row.get("category"),
            json.dumps(row.get("reasons", [])),
            json.dumps(row.get("weaknesses", [])),
        )
        for row in rows
    ]
    with get_connection() as conn:
        conn.executemany(
            '''INSERT INTO setup_analyses (
                analysis_date, ticker, scan_mode, setup_score, base_score, compression_score,
                volume_score, resistance_score, structure_score, risk_score, category, reasons, weaknesses
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            payload,
        )
        conn.commit()

def append_transition_analysis_rows(rows):
    if not rows:
        return
    init_db()
    payload = [
        (
            row.get("analysis_date"),
            row.get("ticker"),
            row.get("scan_mode"),
            float(row.get("transition_score", 0) or 0),
            float(row.get("transition_setup_velocity_score", 0) or 0),
            float(row.get("transition_rs_acceleration_score", 0) or 0),
            float(row.get("transition_volume_transition_score", 0) or 0),
            float(row.get("transition_compression_evolution_score", 0) or 0),
            float(row.get("transition_resistance_pressure_score", 0) or 0),
            float(row.get("transition_price_acceptance_score", 0) or 0),
            float(row.get("transition_opportunity_velocity_score", 0) or 0),
            row.get("transition_category"),
            1 if row.get("transition_qualifies") else 0,
            json.dumps(row.get("transition_reasons", [])),
            json.dumps(row.get("transition_weaknesses", [])),
            json.dumps(row.get("transition_metrics", {})),
        )
        for row in rows
    ]
    with get_connection() as conn:
        conn.executemany(
            '''INSERT INTO transition_analyses (
                analysis_date, ticker, scan_mode, transition_score, setup_velocity_score,
                rs_acceleration_score, volume_transition_score, compression_evolution_score,
                resistance_pressure_score, price_acceptance_score, opportunity_velocity_score,
                category, qualifies, reasons, weaknesses, metrics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            payload,
        )
        conn.commit()

def append_trigger_analysis_rows(rows):
    if not rows:
        return
    init_db()
    payload = [
        (
            row.get("analysis_date"),
            row.get("ticker"),
            row.get("scan_mode"),
            row.get("trigger_decision"),
            row.get("trigger_confidence"),
            float(row.get("trigger_score", 0) or 0),
            1 if row.get("trigger_qualifies") else 0,
            json.dumps(row.get("trigger_reasons", [])),
            json.dumps(row.get("trigger_weaknesses", [])),
            json.dumps(row.get("trigger_module_results", {})),
            json.dumps(row.get("trigger_metrics", {})),
        )
        for row in rows
    ]
    with get_connection() as conn:
        conn.executemany(
            '''INSERT INTO trigger_analyses (
                analysis_date, ticker, scan_mode, trigger_decision, trigger_confidence,
                trigger_score, qualifies, reasons, weaknesses, module_results, metrics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            payload,
        )
        conn.commit()

def remove_risk_position(username, ticker):
    execute_query("DELETE FROM risk_positions WHERE username = ? AND ticker = ?", (username, ticker))
