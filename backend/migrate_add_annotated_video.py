"""
Migration script to add annotated_video_path column to video_jobs table.
Run this once to update the database schema.
"""
import sqlite3

db_path = "siews.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(video_jobs)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "annotated_video_path" not in columns:
        print("Adding annotated_video_path column to video_jobs table...")
        cursor.execute("ALTER TABLE video_jobs ADD COLUMN annotated_video_path VARCHAR(255)")
        conn.commit()
        print("Column added successfully!")
    else:
        print("Column annotated_video_path already exists.")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
