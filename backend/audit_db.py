import sqlite3
try:
    conn = sqlite3.connect('siews.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    print(f"Tables: {cursor.fetchall()}")
    
    cursor.execute("SELECT COUNT(*) FROM alerts")
    print(f"Total Alerts: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 3")
    rows = cursor.fetchall()
    for row in rows:
        print(f"Alert: {row}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
