import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# =========================
# TABEL DATA SENSOR
# =========================
cursor.execute("""
CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    temperature REAL,
    humidity REAL,
    ph_value REAL,
    tds_ppm REAL,
    water_level REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()

print("Database dan tabel berhasil dibuat.")