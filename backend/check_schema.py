import sqlite3

db_path = "siews.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_jobs'")
    table_exists = cursor.fetchone()
    print(f"Table exists: {table_exists}")
    
    if table_exists:
        # Get table schema
        cursor.execute("PRAGMA table_info(video_jobs)")
        columns = cursor.fetchall()
        print("Columns in video_jobs table:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
