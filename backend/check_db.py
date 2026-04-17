import sqlite3
import os

db_path = "siews.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
try:
    cursor.execute("SELECT * FROM persons")
    rows = cursor.fetchall()
    print(f"Persons found: {len(rows)}")
    for r in rows:
        print(r)
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
