"""CARE-PLUS: Healthcare and Medical Management (Flask + SQLite)."""
import os, sqlite3
from functools import wraps
from flask import Flask, g, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

DB = os.environ.get("CAREPLUS_DB", "careplus.db")
app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN('admin','doctor','patient')),
  specialization TEXT);
CREATE TABLE IF NOT EXISTS appointments(
  id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL, doctor_id INTEGER NOT NULL,
  date TEXT NOT NULL, slot TEXT NOT NULL, reason TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','confirmed','completed','cancelled')),
  UNIQUE(doctor_id, date, slot),
  FOREIGN KEY(patient_id) REFERENCES users(id), FOREIGN KEY(doctor_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS prescriptions(
  id INTEGER PRIMARY KEY, appointment_id INTEGER UNIQUE NOT NULL,
  diagnosis TEXT NOT NULL, medicines TEXT NOT NULL, notes TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(appointment_id) REFERENCES appointments(id));
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()

def init_db():
    c = sqlite3.connect(DB); c.executescript(SCHEMA)
    if not c.execute("SELECT 1 FROM users").fetchone():
        seed = [("Admin", "admin@careplus.com", "admin123", "admin", None),
                ("Dr. Anita Sharma", "anita@careplus.com", "doctor123", "doctor", "Cardiology"),
                ("Dr. Rahul Verma", "rahul@careplus.com", "doctor123", "doctor", "General Medicine")]
        c.executemany("INSERT INTO users(name,email,password,role,specialization) VALUES(?,?,?,?,?)",
                      [(n, e, generate_password_hash(p), r, s) for n, e, p, r, s in seed])
    c.commit(); c.close()

def err(msg, code=400): return jsonify(error=msg), code

def login_required(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if "uid" not in session: return err("Login required", 401)
            if roles and session["role"] not in roles: return err("Forbidden", 403)
            return f(*a, **k)
        return w
    return deco

@app.get("/")
def index(): return send_from_directory("static", "index.html")

# ---------- auth ----------
@app.post("/api/register")
def register():
    d = request.get_json(silent=True) or {}
    name, email, pw = (d.get("name") or "").strip(), (d.get("email") or "").strip().lower(), d.get("password") or ""
    role = d.get("role", "patient")
    if not name or "@" not in email or len(pw) < 6: return err("Name, valid email and 6+ char password required")
    if role not in ("patient", "doctor"): return err("Invalid role")
    if role == "doctor" and not d.get("specialization"): return err("Specialization required for doctors")
    try:
        db().execute("INSERT INTO users(name,email,password,role,specialization) VALUES(?,?,?,?,?)",
                     (name, email, generate_password_hash(pw), role, d.get("specialization")))
        db().commit()
    except sqlite3.IntegrityError:
        return err("Email already registered", 409)
    return jsonify(ok=True), 201

@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    u = db().execute("SELECT * FROM users WHERE email=?", ((d.get("email") or "").lower(),)).fetchone()
    if not u or not check_password_hash(u["password"], d.get("password") or ""): return err("Invalid credentials", 401)
    session.update(uid=u["id"], role=u["role"], name=u["name"])
    return jsonify(id=u["id"], name=u["name"], role=u["role"])

@app.post("/api/logout")
def logout(): session.clear(); return jsonify(ok=True)

@app.get("/api/me")
def me():
    if "uid" not in session: return err("Not logged in", 401)
    return jsonify(id=session["uid"], name=session["name"], role=session["role"])

# ---------- doctors ----------
@app.get("/api/doctors")
@login_required()
def doctors():
    rows = db().execute("SELECT id,name,specialization FROM users WHERE role='doctor' ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])

# ---------- appointments ----------
APPT_SQL = """SELECT a.*, p.name patient, d.name doctor, d.specialization,
  (SELECT 1 FROM prescriptions r WHERE r.appointment_id=a.id) has_rx
  FROM appointments a JOIN users p ON p.id=a.patient_id JOIN users d ON d.id=a.doctor_id"""

@app.get("/api/appointments")
@login_required()
def list_appts():
    col = {"patient": "a.patient_id", "doctor": "a.doctor_id"}.get(session["role"])
    q, args = APPT_SQL, ()
    if col: q += f" WHERE {col}=?"; args = (session["uid"],)
    rows = db().execute(q + " ORDER BY a.date DESC, a.slot", args).fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/api/appointments")
@login_required("patient")
def book():
    d = request.get_json(silent=True) or {}
    if not all(d.get(k) for k in ("doctor_id", "date", "slot")): return err("doctor_id, date, slot required")
    doc = db().execute("SELECT 1 FROM users WHERE id=? AND role='doctor'", (d["doctor_id"],)).fetchone()
    if not doc: return err("Doctor not found", 404)
    try:
        db().execute("INSERT INTO appointments(patient_id,doctor_id,date,slot,reason) VALUES(?,?,?,?,?)",
                     (session["uid"], d["doctor_id"], d["date"], d["slot"], d.get("reason", "")))
        db().commit()
    except sqlite3.IntegrityError:
        return err("Slot already booked", 409)
    return jsonify(ok=True), 201

@app.patch("/api/appointments/<int:aid>")
@login_required()
def update_appt(aid):
    status = (request.get_json(silent=True) or {}).get("status")
    a = db().execute("SELECT * FROM appointments WHERE id=?", (aid,)).fetchone()
    if not a: return err("Not found", 404)
    role, uid = session["role"], session["uid"]
    allowed = {"patient": {"cancelled"} if a["patient_id"] == uid else set(),
               "doctor": {"confirmed", "completed", "cancelled"} if a["doctor_id"] == uid else set(),
               "admin": {"confirmed", "completed", "cancelled"}}[role]
    if status not in allowed: return err("Not allowed", 403)
    db().execute("UPDATE appointments SET status=? WHERE id=?", (status, aid)); db().commit()
    return jsonify(ok=True)

# ---------- prescriptions ----------
@app.post("/api/prescriptions")
@login_required("doctor")
def add_rx():
    d = request.get_json(silent=True) or {}
    a = db().execute("SELECT * FROM appointments WHERE id=?", (d.get("appointment_id"),)).fetchone()
    if not a or a["doctor_id"] != session["uid"]: return err("Appointment not found", 404)
    if not d.get("diagnosis") or not d.get("medicines"): return err("Diagnosis and medicines required")
    try:
        db().execute("INSERT INTO prescriptions(appointment_id,diagnosis,medicines,notes) VALUES(?,?,?,?)",
                     (a["id"], d["diagnosis"], d["medicines"], d.get("notes", "")))
        db().execute("UPDATE appointments SET status='completed' WHERE id=?", (a["id"],)); db().commit()
    except sqlite3.IntegrityError:
        return err("Prescription already exists", 409)
    return jsonify(ok=True), 201

@app.get("/api/prescriptions")
@login_required("patient", "doctor")
def list_rx():
    col = "a.patient_id" if session["role"] == "patient" else "a.doctor_id"
    rows = db().execute(f"""SELECT r.*, a.date, p.name patient, d.name doctor FROM prescriptions r
      JOIN appointments a ON a.id=r.appointment_id JOIN users p ON p.id=a.patient_id
      JOIN users d ON d.id=a.doctor_id WHERE {col}=? ORDER BY r.created_at DESC""", (session["uid"],)).fetchall()
    return jsonify([dict(r) for r in rows])

# ---------- admin ----------
@app.get("/api/stats")
@login_required("admin")
def stats():
    q = lambda s: db().execute(s).fetchone()[0]
    by = {r[0]: r[1] for r in db().execute("SELECT status, COUNT(*) FROM appointments GROUP BY status")}
    return jsonify(patients=q("SELECT COUNT(*) FROM users WHERE role='patient'"),
                   doctors=q("SELECT COUNT(*) FROM users WHERE role='doctor'"),
                   appointments=q("SELECT COUNT(*) FROM appointments"), by_status=by)

if __name__ == "__main__":
    init_db(); app.run(debug=True)
