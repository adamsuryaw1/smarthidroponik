from flask import Flask, request, jsonify, render_template
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

DB_NAME = os.path.join(
    BASE_DIR,
    "database",
    "database.db"
)

manual_control = {
    "pompa_a": 0,
    "pompa_b": 0,
    "ph_up": 0,
    "ph_down": 0,
    "sirkulasi": 0
}

auto_control = {
    "mode": "MANUAL",
    "age_days": 7,
    "morning_time": "07:00",
    "evening_time": "17:00",
    # Smart Dosing config
    "target_ppm": 300,
    "ph_min": 5.8,
    "ph_max": 6.2,
    "ppm_tolerance": 30,
    "ph_tolerance": 0.2,
    "dosing_duration_ms": 250,
    "cooldown_sec": 10,
    "mixing_delay_sec": 7,
    "water_level_min": 10.0
}

planting_date = None

def get_db():
    return sqlite3.connect(DB_NAME)

# =========================
# INIT DATABASE
# =========================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sensor_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        temperature REAL,
        humidity REAL,
        water_level REAL,
        ph_value REAL,
        tds_ppm REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS watering_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        session TEXT,
        ph_value REAL,
        tds_ppm REAL,
        temperature REAL,
        humidity REAL,
        water_level REAL,
        mode TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auto_control (
        id INTEGER PRIMARY KEY,
        mode TEXT NOT NULL,
        age_days INTEGER NOT NULL,
        morning_time TEXT NOT NULL,
        evening_time TEXT NOT NULL,
        target_ppm INTEGER NOT NULL DEFAULT 300,
        ph_min REAL NOT NULL DEFAULT 5.8,
        ph_max REAL NOT NULL DEFAULT 6.2,
        ppm_tolerance INTEGER NOT NULL DEFAULT 30,
        ph_tolerance REAL NOT NULL DEFAULT 0.2,
        dosing_duration_ms INTEGER NOT NULL DEFAULT 250,
        cooldown_sec INTEGER NOT NULL DEFAULT 10,
        mixing_delay_sec INTEGER NOT NULL DEFAULT 7,
        water_level_min REAL NOT NULL DEFAULT 10.0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dosing_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        action TEXT NOT NULL,
        trigger_value REAL,
        target_value REAL,
        duration_ms INTEGER,
        note TEXT
    )
    """)

    cursor.execute("SELECT COUNT(*) FROM auto_control")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            """INSERT INTO auto_control
            (id, mode, age_days, morning_time, evening_time,
             target_ppm, ph_min, ph_max, ppm_tolerance, ph_tolerance,
             dosing_duration_ms, cooldown_sec, mixing_delay_sec, water_level_min)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (auto_control['mode'], auto_control['age_days'],
             auto_control['morning_time'], auto_control['evening_time'],
             auto_control['target_ppm'], auto_control['ph_min'], auto_control['ph_max'],
             auto_control['ppm_tolerance'], auto_control['ph_tolerance'],
             auto_control['dosing_duration_ms'], auto_control['cooldown_sec'],
             auto_control['mixing_delay_sec'], auto_control['water_level_min'])
        )

    conn.commit()
    conn.close()

# =========================
# DATABASE HELPERS
# =========================
def load_auto_control():
    global auto_control
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT mode, age_days, morning_time, evening_time,
               target_ppm, ph_min, ph_max, ppm_tolerance, ph_tolerance,
               dosing_duration_ms, cooldown_sec, mixing_delay_sec, water_level_min
        FROM auto_control WHERE id = 1
    """)
    row = cursor.fetchone()
    conn.close()

    if row is not None:
        auto_control['mode']               = row[0]
        auto_control['age_days']           = row[1]
        auto_control['morning_time']       = row[2]
        auto_control['evening_time']       = row[3]
        auto_control['target_ppm']         = row[4]
        auto_control['ph_min']             = row[5]
        auto_control['ph_max']             = row[6]
        auto_control['ppm_tolerance']      = row[7]
        auto_control['ph_tolerance']       = row[8]
        auto_control['dosing_duration_ms'] = row[9]
        auto_control['cooldown_sec']       = row[10]
        auto_control['mixing_delay_sec']   = row[11]
        auto_control['water_level_min']    = row[12]


def save_auto_control():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """INSERT OR REPLACE INTO auto_control
        (id, mode, age_days, morning_time, evening_time,
         target_ppm, ph_min, ph_max, ppm_tolerance, ph_tolerance,
         dosing_duration_ms, cooldown_sec, mixing_delay_sec, water_level_min,
         updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (auto_control['mode'], auto_control['age_days'],
         auto_control['morning_time'], auto_control['evening_time'],
         auto_control['target_ppm'], auto_control['ph_min'], auto_control['ph_max'],
         auto_control['ppm_tolerance'], auto_control['ph_tolerance'],
         auto_control['dosing_duration_ms'], auto_control['cooldown_sec'],
         auto_control['mixing_delay_sec'], auto_control['water_level_min'])
    )

    conn.commit()
    conn.close()

# =========================
# DASHBOARD
# =========================
@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/reports')
def reports():
    return render_template('reports.html')

# =========================
# API TERIMA DATA SENSOR
# =========================
@app.route('/api/sensor', methods=['POST'])
def receive_sensor():

    data = request.json

    temperature  = data.get("temperature")
    humidity     = data.get("humidity")
    ph_value     = data.get("ph_value")
    tds_ppm      = data.get("tds_ppm")
    water_level  = data.get("water_level")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO sensor_data
        (temperature, humidity, water_level, ph_value, tds_ppm)
        VALUES (?, ?, ?, ?, ?)
    """, (temperature, humidity, water_level, ph_value, tds_ppm))

    conn.commit()
    conn.close()

    return jsonify({"status": "success"}), 200

# =========================
# API DATA TERBARU
# =========================
@app.route('/api/sensor/latest')
def latest_sensor():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT temperature, humidity, water_level, ph_value, tds_ppm, timestamp
    FROM sensor_data
    ORDER BY id DESC
    LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return jsonify({}), 200

    return jsonify({
        "temperature": row[0],
        "humidity":    row[1],
        "water_level": row[2],
        "ph_value":    row[3],
        "tds_ppm":     row[4],
        "timestamp":   row[5]
    })


def get_targets_from_db(age_days):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT target_ppm_min, target_ppm_max, ph_min, ph_max
        FROM growth_phases
        WHERE ? >= umur_min AND ? <= umur_max
        LIMIT 1
    """, (age_days, age_days))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        ppm_min, ppm_max, ph_min, ph_max = row
        target_ppm = (ppm_min + ppm_max) // 2
        ppm_tolerance = (ppm_max - ppm_min) // 2
        if ppm_tolerance < 30: 
            ppm_tolerance = 30
        return {
            "target_ppm": target_ppm,
            "ppm_tolerance": ppm_tolerance,
            "ph_min": ph_min,
            "ph_max": ph_max
        }
    return None

def get_auto_targets(age_days):
    # Fallback to DB if possible
    try:
        db_targets = get_targets_from_db(age_days)
        if db_targets:
            return {
                "target_ppm": db_targets["target_ppm"],
                "ph_low": db_targets["ph_min"],
                "ph_high": db_targets["ph_max"]
            }
    except Exception:
        pass

    if age_days <= 3:
        return {"target_ppm": 100, "ph_low": 5.5, "ph_high": 6.0}
    elif age_days <= 7:
        return {"target_ppm": 400, "ph_low": 5.5, "ph_high": 6.5}
    elif age_days <= 14:
        return {"target_ppm": 650, "ph_low": 5.8, "ph_high": 6.5}
    elif age_days <= 20:
        return {"target_ppm": 900, "ph_low": 6.0, "ph_high": 6.8}
    elif age_days <= 25:
        return {"target_ppm": 1050, "ph_low": 6.0, "ph_high": 6.8}
    else:
        return {"target_ppm": 700, "ph_low": 6.0, "ph_high": 7.0}

# =========================
# API MANUAL CONTROL
# =========================
@app.route('/api/manual', methods=['GET', 'POST'])
def manual_control_api():
    global manual_control

    if request.method == 'POST':
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({
                "status": "error",
                "message": "Invalid JSON payload"
            }), 400

        for key in manual_control:
            if key in data:
                try:
                    manual_control[key] = int(data[key])
                except (ValueError, TypeError):
                    manual_control[key] = 0

        return jsonify({
            "status": "success",
            "data": manual_control
        })

    return jsonify(manual_control)

# =========================
# API OTOMATISASI KONTROL (legacy, masih dipakai ESP)
# =========================
@app.route('/api/control', methods=['GET', 'POST'])
def control_api():
    global auto_control

    if request.method == 'POST':
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

        if 'mode' in data and data['mode'] in ['AUTO', 'MANUAL']:
            auto_control['mode'] = data['mode']

        if 'age_days' in data:
            try:
                age = int(data['age_days'])
                auto_control['age_days'] = max(0, min(age, 60))
            except (ValueError, TypeError):
                pass

        if 'morning_time' in data:
            auto_control['morning_time'] = str(data['morning_time'])
        if 'evening_time' in data:
            auto_control['evening_time'] = str(data['evening_time'])

        save_auto_control()

    targets = get_auto_targets(auto_control['age_days'])

    return jsonify({
        "mode":         auto_control['mode'],
        "age_days":     auto_control['age_days'],
        "morning_time": auto_control['morning_time'],
        "evening_time": auto_control['evening_time'],
        "target_ppm":   auto_control['target_ppm'],
        "ph_low":       auto_control['ph_min'],
        "ph_high":      auto_control['ph_max'],
        "ppm_tolerance":      auto_control['ppm_tolerance'],
        "ph_tolerance":       auto_control['ph_tolerance'],
        "dosing_duration_ms": auto_control['dosing_duration_ms'],
        "cooldown_sec":       auto_control['cooldown_sec'],
        "mixing_delay_sec":   auto_control['mixing_delay_sec'],
        "water_level_min":    auto_control['water_level_min'],
        "manual": manual_control
    })

# =========================
# API AUTO CONFIG (NEW – sesuai PRD /api/auto)
# =========================
@app.route('/api/auto', methods=['GET', 'POST'])
def auto_api():
    global auto_control

    if request.method == 'POST':
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

        str_fields = ['mode', 'morning_time', 'evening_time']
        int_fields = ['age_days', 'target_ppm', 'ppm_tolerance',
                      'dosing_duration_ms', 'cooldown_sec', 'mixing_delay_sec']
        float_fields = ['ph_min', 'ph_max', 'ph_tolerance', 'water_level_min']

        old_age = auto_control.get('age_days', 7)

        for f in str_fields:
            if f in data:
                auto_control[f] = str(data[f])

        if 'mode' in data and data['mode'] not in ['AUTO', 'MANUAL']:
            auto_control['mode'] = 'MANUAL'

        for f in int_fields:
            if f in data:
                try:
                    auto_control[f] = int(data[f])
                except (ValueError, TypeError):
                    pass

        for f in float_fields:
            if f in data:
                try:
                    auto_control[f] = float(data[f])
                except (ValueError, TypeError):
                    pass
        
        # Override with DB targets if age_days changed
        new_age = auto_control.get('age_days', 7)
        if new_age != old_age:
            try:
                db_targets = get_targets_from_db(new_age)
                if db_targets:
                    auto_control['target_ppm'] = db_targets['target_ppm']
                    auto_control['ppm_tolerance'] = db_targets['ppm_tolerance']
                    auto_control['ph_min'] = db_targets['ph_min']
                    auto_control['ph_max'] = db_targets['ph_max']
            except Exception as e:
                print("Error fetching DB targets:", e)

        # Clamp values
        auto_control['dosing_duration_ms'] = max(100, min(auto_control['dosing_duration_ms'], 2000))
        auto_control['cooldown_sec']       = max(5,   min(auto_control['cooldown_sec'],  120))
        auto_control['mixing_delay_sec']   = max(3,   min(auto_control['mixing_delay_sec'], 60))
        auto_control['ppm_tolerance']      = max(10,  min(auto_control['ppm_tolerance'],  200))

        save_auto_control()

    return jsonify({
        "mode":               auto_control['mode'],
        "modeAuto":           auto_control['mode'] == 'AUTO',
        "age_days":           auto_control['age_days'],
        "morning_time":       auto_control['morning_time'],
        "evening_time":       auto_control['evening_time'],
        "targetPPM":          auto_control['target_ppm'],
        "phMin":              auto_control['ph_min'],
        "phMax":              auto_control['ph_max'],
        "ppmTolerance":       auto_control['ppm_tolerance'],
        "phTolerance":        auto_control['ph_tolerance'],
        "dosingDurationMs":   auto_control['dosing_duration_ms'],
        "cooldownSec":        auto_control['cooldown_sec'],
        "mixingDelaySec":     auto_control['mixing_delay_sec'],
        "waterLevelMin":      auto_control['water_level_min'],
        "manual":             manual_control
    })

# =========================
# API DOSING LOG
# =========================
@app.route('/api/dosing-log', methods=['GET', 'POST'])
def dosing_log_api():
    if request.method == 'POST':
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400

        action        = data.get("action", "")
        trigger_value = data.get("trigger_value")
        target_value  = data.get("target_value")
        duration_ms   = data.get("duration_ms")
        note          = data.get("note", "")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO dosing_log (action, trigger_value, target_value, duration_ms, note)
            VALUES (?, ?, ?, ?, ?)
        """, (action, trigger_value, target_value, duration_ms, note))
        conn.commit()
        conn.close()

        return jsonify({"status": "success"}), 201

    else:
        limit = int(request.args.get('limit', 20))
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, action, trigger_value, target_value, duration_ms, note
            FROM dosing_log ORDER BY id DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append({
                "id":            row[0],
                "timestamp":     row[1],
                "action":        row[2],
                "trigger_value": row[3],
                "target_value":  row[4],
                "duration_ms":   row[5],
                "note":          row[6]
            })

        return jsonify(results)

# =========================
# API WATERING REPORTS
# =========================
@app.route('/api/report', methods=['GET', 'POST'])
def watering_report_api():
    if request.method == 'POST':
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400

        session_val = data.get("session", "Manual")
        ph_value    = data.get("ph_value")
        tds_ppm     = data.get("tds_ppm")
        temperature = data.get("temperature")
        humidity    = data.get("humidity")
        water_level = data.get("water_level")
        mode        = data.get("mode", "MANUAL")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO watering_reports
            (session, ph_value, tds_ppm, temperature, humidity, water_level, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_val, ph_value, tds_ppm, temperature, humidity, water_level, mode))
        conn.commit()
        conn.close()

        return jsonify({"status": "success"}), 201

    else:
        date_filter    = request.args.get('date')
        session_filter = request.args.get('session')

        query = "SELECT id, timestamp, session, ph_value, tds_ppm, temperature, humidity, water_level, mode FROM watering_reports WHERE 1=1"
        params = []

        if date_filter:
            query += " AND date(timestamp) = ?"
            params.append(date_filter)
        if session_filter and session_filter != 'Semua':
            query += " AND session = ?"
            params.append(session_filter)

        query += " ORDER BY id DESC"

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append({
                "id":          row[0],
                "timestamp":   row[1],
                "session":     row[2],
                "ph_value":    row[3],
                "tds_ppm":     row[4],
                "temperature": row[5],
                "humidity":    row[6],
                "water_level": row[7],
                "mode":        row[8]
            })

        return jsonify(results)

# =========================
# RUN SERVER
# =========================
if __name__ == '__main__':
    init_db()
    load_auto_control()
    app.run(host='0.0.0.0', port=5000, debug=True)
