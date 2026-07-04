from flask import Flask, request, jsonify, render_template
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Fallback to local sqlite file when DATABASE_URL is not provided
DB_FILE = os.path.join(BASE_DIR, "database", "database.db")

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

database_url = os.getenv("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql://",
        1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = (
    database_url or f"sqlite:///{DB_FILE}"
)


db = SQLAlchemy(app)
with app.app_context():
    init_db()
    load_auto_control()

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


# =========================
# MODELS
# =========================
class SensorData(db.Model):
    __tablename__ = 'sensor_data'
    id = db.Column(db.Integer, primary_key=True)
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    water_level = db.Column(db.Float)
    ph_value = db.Column(db.Float)
    tds_ppm = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class WateringReport(db.Model):
    __tablename__ = 'watering_reports'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    session = db.Column(db.String)
    ph_value = db.Column(db.Float)
    tds_ppm = db.Column(db.Float)
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    water_level = db.Column(db.Float)
    mode = db.Column(db.String)


class AutoControl(db.Model):
    __tablename__ = 'auto_control'
    id = db.Column(db.Integer, primary_key=True)
    mode = db.Column(db.String, nullable=False)
    age_days = db.Column(db.Integer, nullable=False)
    morning_time = db.Column(db.String, nullable=False)
    evening_time = db.Column(db.String, nullable=False)
    target_ppm = db.Column(db.Integer, nullable=False, default=300)
    ph_min = db.Column(db.Float, nullable=False, default=5.8)
    ph_max = db.Column(db.Float, nullable=False, default=6.2)
    ppm_tolerance = db.Column(db.Integer, nullable=False, default=30)
    ph_tolerance = db.Column(db.Float, nullable=False, default=0.2)
    dosing_duration_ms = db.Column(db.Integer, nullable=False, default=250)
    cooldown_sec = db.Column(db.Integer, nullable=False, default=10)
    mixing_delay_sec = db.Column(db.Integer, nullable=False, default=7)
    water_level_min = db.Column(db.Float, nullable=False, default=10.0)
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())


class DosingLog(db.Model):
    __tablename__ = 'dosing_log'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    action = db.Column(db.String, nullable=False)
    trigger_value = db.Column(db.Float)
    target_value = db.Column(db.Float)
    duration_ms = db.Column(db.Integer)
    note = db.Column(db.String)


class GrowthPhase(db.Model):
    __tablename__ = 'growth_phases'
    id = db.Column(db.Integer, primary_key=True)
    umur_min = db.Column(db.Integer)
    umur_max = db.Column(db.Integer)
    target_ppm_min = db.Column(db.Integer)
    target_ppm_max = db.Column(db.Integer)
    ph_min = db.Column(db.Float)
    ph_max = db.Column(db.Float)


# =========================
# INIT DATABASE
# =========================
def init_db():
    db.create_all()

    ac = AutoControl.query.get(1)
    if ac is None:
        ac = AutoControl(
            id=1,
            mode=auto_control['mode'],
            age_days=auto_control['age_days'],
            morning_time=auto_control['morning_time'],
            evening_time=auto_control['evening_time'],
            target_ppm=auto_control['target_ppm'],
            ph_min=auto_control['ph_min'],
            ph_max=auto_control['ph_max'],
            ppm_tolerance=auto_control['ppm_tolerance'],
            ph_tolerance=auto_control['ph_tolerance'],
            dosing_duration_ms=auto_control['dosing_duration_ms'],
            cooldown_sec=auto_control['cooldown_sec'],
            mixing_delay_sec=auto_control['mixing_delay_sec'],
            water_level_min=auto_control['water_level_min']
        )
        db.session.add(ac)
        db.session.commit()

# =========================
# DATABASE HELPERS
# =========================
def load_auto_control():
    global auto_control
    ac = AutoControl.query.get(1)
    if ac:
        auto_control['mode'] = ac.mode
        auto_control['age_days'] = ac.age_days
        auto_control['morning_time'] = ac.morning_time
        auto_control['evening_time'] = ac.evening_time
        auto_control['target_ppm'] = ac.target_ppm
        auto_control['ph_min'] = ac.ph_min
        auto_control['ph_max'] = ac.ph_max
        auto_control['ppm_tolerance'] = ac.ppm_tolerance
        auto_control['ph_tolerance'] = ac.ph_tolerance
        auto_control['dosing_duration_ms'] = ac.dosing_duration_ms
        auto_control['cooldown_sec'] = ac.cooldown_sec
        auto_control['mixing_delay_sec'] = ac.mixing_delay_sec
        auto_control['water_level_min'] = ac.water_level_min


def save_auto_control():
    ac = AutoControl.query.get(1)
    if not ac:
        ac = AutoControl(id=1)
        db.session.add(ac)

    ac.mode = auto_control['mode']
    ac.age_days = auto_control['age_days']
    ac.morning_time = auto_control['morning_time']
    ac.evening_time = auto_control['evening_time']
    ac.target_ppm = auto_control['target_ppm']
    ac.ph_min = auto_control['ph_min']
    ac.ph_max = auto_control['ph_max']
    ac.ppm_tolerance = auto_control['ppm_tolerance']
    ac.ph_tolerance = auto_control['ph_tolerance']
    ac.dosing_duration_ms = auto_control['dosing_duration_ms']
    ac.cooldown_sec = auto_control['cooldown_sec']
    ac.mixing_delay_sec = auto_control['mixing_delay_sec']
    ac.water_level_min = auto_control['water_level_min']

    db.session.commit()

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

    sd = SensorData(
        temperature=temperature,
        humidity=humidity,
        water_level=water_level,
        ph_value=ph_value,
        tds_ppm=tds_ppm
    )
    db.session.add(sd)
    db.session.commit()

    return jsonify({"status": "success"}), 200

# =========================
# API DATA TERBARU
# =========================
@app.route('/api/sensor/latest')
def latest_sensor():
    row = SensorData.query.order_by(SensorData.id.desc()).first()
    if row is None:
        return jsonify({}), 200

    return jsonify({
        "temperature": row.temperature,
        "humidity": row.humidity,
        "water_level": row.water_level,
        "ph_value": row.ph_value,
        "tds_ppm": row.tds_ppm,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None
    })


def get_targets_from_db(age_days):
    gp = GrowthPhase.query.filter(age_days >= GrowthPhase.umur_min, age_days <= GrowthPhase.umur_max).first()
    if gp:
        ppm_min = gp.target_ppm_min or 0
        ppm_max = gp.target_ppm_max or 0
        ph_min = gp.ph_min
        ph_max = gp.ph_max
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

        dl = DosingLog(
            action=action,
            trigger_value=trigger_value,
            target_value=target_value,
            duration_ms=duration_ms,
            note=note
        )
        db.session.add(dl)
        db.session.commit()

        return jsonify({"status": "success"}), 201

    else:
        limit = int(request.args.get('limit', 20))
        rows = DosingLog.query.order_by(DosingLog.id.desc()).limit(limit).all()

        results = []
        for row in rows:
            results.append({
                "id": row.id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "action": row.action,
                "trigger_value": row.trigger_value,
                "target_value": row.target_value,
                "duration_ms": row.duration_ms,
                "note": row.note
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

        wr = WateringReport(
            session=session_val,
            ph_value=ph_value,
            tds_ppm=tds_ppm,
            temperature=temperature,
            humidity=humidity,
            water_level=water_level,
            mode=mode
        )
        db.session.add(wr)
        db.session.commit()

        return jsonify({"status": "success"}), 201

    else:
        date_filter    = request.args.get('date')
        session_filter = request.args.get('session')

        q = WateringReport.query
        if date_filter:
            try:
                q = q.filter(func.date(WateringReport.timestamp) == date_filter)
            except Exception:
                pass
        if session_filter and session_filter != 'Semua':
            q = q.filter(WateringReport.session == session_filter)

        rows = q.order_by(WateringReport.id.desc()).all()

        results = []
        for row in rows:
            results.append({
                "id": row.id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "session": row.session,
                "ph_value": row.ph_value,
                "tds_ppm": row.tds_ppm,
                "temperature": row.temperature,
                "humidity": row.humidity,
                "water_level": row.water_level,
                "mode": row.mode
            })

        return jsonify(results)

# =========================
# RUN SERVER
# =========================
if __name__ == '__main__':
    init_db()
    load_auto_control()
    app.run(host='0.0.0.0', port=5000, debug=True)
