import sqlite3
conn = sqlite3.connect("web/backend/var/securefed.db")
cursor = conn.cursor()
cursor.execute("SELECT id, name, dataset_type, validation_status, feature_count, label_column, research_compatible, rows FROM Dataset")
print("ID\tName\tType\tStatus\tFeatures\tLabel\tResearch\tRows")
for row in cursor.fetchall():
    print(row)
conn.close()