import sqlite3
conn = sqlite3.connect(r"C:\Users\HARIS\Desktop\SecureFed-IDS\web\var\securefed.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM experiments WHERE id=?", ("9dea5f7968f3482089d18203ea372a47",))
print("Experiment:", cursor.fetchone())
cursor.execute("SELECT * FROM experiments WHERE id=?", ("19cdd5f68766413b8377ed8f26cae47d",))
print("Experiment 2:", cursor.fetchone())
conn.close()