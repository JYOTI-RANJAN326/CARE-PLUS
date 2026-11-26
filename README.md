# CARE-PLUS

Healthcare and Medical Management System: role-based web app for patients, doctors and admins.

## Features
- Auth with hashed passwords and session cookies; roles: **patient**, **doctor**, **admin**
- Patients: browse doctors, book/cancel appointments, view prescriptions
- Doctors: confirm/cancel appointments, issue prescriptions (auto-completes the visit)
- Admin: dashboard stats, manage all appointments
- Double-booking prevented by a DB `UNIQUE(doctor, date, slot)` constraint
- Parameterised SQL (no SQL injection), output escaping (no XSS)

## Tech stack
Python, Flask, SQLite, vanilla JS (single-page UI)

## Run
```bash
pip install -r requirements.txt
python app.py        # http://127.0.0.1:5000
```
Demo logins: `admin@careplus.com / admin123`, `anita@careplus.com / doctor123`.
Set `SECRET_KEY` in production.

## REST API
| Method | Endpoint | Role |
|---|---|---|
| POST | `/api/register`, `/api/login`, `/api/logout` | public |
| GET | `/api/me`, `/api/doctors` | any |
| GET/POST | `/api/appointments` | any / patient |
| PATCH | `/api/appointments/<id>` | patient (cancel), doctor/admin |
| GET/POST | `/api/prescriptions` | patient,doctor / doctor |
| GET | `/api/stats` | admin |

## Schema
`users(id, name, email, password, role, specialization)` ·
`appointments(id, patient_id, doctor_id, date, slot, reason, status)` ·
`prescriptions(id, appointment_id, diagnosis, medicines, notes, created_at)`

## Future scope
Email reminders, JWT/OAuth, file uploads for reports, Docker + CI, pytest suite.
