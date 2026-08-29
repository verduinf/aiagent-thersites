import sqlite3
import os

db_path = r"S:\Agile Comic Tracker\Data\comics.db"
print("Checking DB:", db_path, "Exists:", os.path.exists(db_path))

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM comics")
    total = cursor.fetchone()[0]
    print(f"Total comics in DB: {total:,}")
    
    cursor.execute("SELECT filename, file_path FROM comics WHERE series_title LIKE '%Spider-Man%' AND issue_number IN (15, 25, 42, 101) LIMIT 10")
    rows = cursor.fetchall()
    print("Spider-Man matches found:", len(rows))
    for r in rows:
        print(" -", r[0])
        print("   Location:", r[1])
