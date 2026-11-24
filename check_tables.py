import sqlite3
conn = sqlite3.connect(r"C:\Users\HARIS\Desktop\SecureFed-IDS\web\var\securefed.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables:", tables)
for table in tables:
    table_name = table[0]
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    print(f"\n{table_name} columns:", columns)
    cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
    rows = cursor.fetchall()
    print(f"{table_name} rows (first 5):", rows)
conn.close()