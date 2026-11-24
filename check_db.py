import sqlite3
conn = sqlite3.connect(r"C:\Users\HARIS\Desktop\SecureFed-IDS\web\var\securefed.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM datasets")
print("Datasets:", cursor.fetchall())
cursor.execute("SELECT * FROM experiments")
print("Experiments:", cursor.fetchall())
conn.close()