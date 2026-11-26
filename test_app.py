import os, tempfile
os.environ["CAREPLUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import app as A

def test_flow():
    A.init_db(); c = A.app.test_client(); c2 = A.app.test_client(); ca = A.app.test_client()
    assert c.post("/api/register", json={"name": "Pat", "email": "p@x.com", "password": "secret1"}).status_code == 201
    assert c.post("/api/login", json={"email": "p@x.com", "password": "secret1"}).status_code == 200
    doc = c.get("/api/doctors").get_json()[0]["id"]
    b = {"doctor_id": doc, "date": "2030-01-01", "slot": "10:00", "reason": "fever"}
    assert c.post("/api/appointments", json=b).status_code == 201
    assert c.post("/api/appointments", json=b).status_code == 409          # double booking
    assert c2.post("/api/login", json={"email": "anita@careplus.com", "password": "doctor123"}).status_code == 200
    aid = c2.get("/api/appointments").get_json()[0]["id"]
    assert c2.patch(f"/api/appointments/{aid}", json={"status": "confirmed"}).status_code == 200
    assert c2.post("/api/prescriptions", json={"appointment_id": aid, "diagnosis": "Flu", "medicines": "Paracetamol"}).status_code == 201
    assert c.get("/api/prescriptions").get_json()[0]["diagnosis"] == "Flu"
    assert c.get("/api/stats").status_code == 403                           # RBAC
    ca.post("/api/login", json={"email": "admin@careplus.com", "password": "admin123"})
    assert ca.get("/api/stats").get_json()["appointments"] == 1
