import json
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

from .environment import load_environment

load_environment()

from .ai import analyze_incident
from .auth import create_token, hash_password, require_role, verify_password, current_user
from .database import get_db, init_db, row_to_dict
from .emergency_contacts import contact_for_responder, notification_message


UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Sentinel AI API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str
    responder_type: Optional[str] = None
    location: Optional[str] = None
    availability_status: Optional[str] = "Available"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class StatusRequest(BaseModel):
    status: str


class SOSRequest(BaseModel):
    location: str
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    description: Optional[str] = "SOS emergency alert submitted by citizen."


def parse_incident(row):
    data = row_to_dict(row)
    if not data:
        return None
    data["ai_reason"] = json.loads(data["ai_reason"] or "[]")
    data["safety_recommendations"] = json.loads(data["safety_recommendations"] or "[]")
    data["emergency_contact"] = json.loads(data.get("emergency_contact") or "{}")
    if not data["emergency_contact"]:
        data["emergency_contact"] = contact_for_responder(data.get("recommended_responder", ""))
    data["public_id"] = f"SI-{1000 + data['id']}"
    data["assigned_to"] = data.get("recommended_responder") or "Pending Assignment"
    data["priority"] = data.get("severity", "Medium")
    data["is_emergency"] = bool(data.get("is_emergency"))
    data["estimated_response"] = _estimated_response(data.get("status", ""))
    data["image_url"] = f"/uploads/{Path(data['image_path']).name}" if data.get("image_path") else None
    data["audio_url"] = f"/uploads/{Path(data['audio_path']).name}" if data.get("audio_path") else None
    return data


def _estimated_response(status: str) -> str:
    if status in {"Waiting for Responder", "Reported", "Assigned"}:
        return "Pending Acceptance"
    if status == "Accepted":
        return "Responder accepted"
    if status == "In Progress":
        return "Responder in progress"
    if status == "Resolved":
        return "Completed"
    return "Pending Acceptance"


def save_upload(file: Optional[UploadFile], prefix: str) -> Optional[str]:
    if not file or not file.filename:
        return None
    safe_name = "".join(ch for ch in file.filename if ch.isalnum() or ch in ".-_").strip(".")
    target = UPLOAD_DIR / f"{prefix}-{safe_name}"
    with target.open("wb") as output:
        output.write(file.file.read())
    return str(target)


def responder_departments_for(user: dict) -> list[str]:
    return department_aliases(user.get("responder_type"))


def canonical_department(department: str | None) -> str:
    value = (department or "").strip().lower()
    aliases = {
        "ambulance": "Medical",
        "electricity department": "Electrical Department",
        "fire department": "Fire",
        "garbage": "Sanitation Department",
        "garbage department": "Sanitation Department",
        "medical department": "Medical",
        "police department": "Police",
        "sanitation": "Sanitation Department",
        "trash": "Sanitation Department",
        "waste": "Sanitation Department",
    }
    return aliases.get(value, (department or "").strip())


def department_aliases(department: str | None) -> list[str]:
    canonical = canonical_department(department)
    if not canonical:
        return []
    aliases = {
        "Sanitation Department": ["Sanitation Department", "Garbage", "Garbage Department", "Sanitation"],
        "Electrical Department": ["Electrical Department", "Electricity Department"],
        "Fire": ["Fire", "Fire Department"],
        "Medical": ["Medical", "Ambulance", "Medical Department"],
        "Police": ["Police", "Police Department"],
    }
    return aliases.get(canonical, [canonical])


def assign_matching_responders(db, incident_id: int, recommended_responder: str, is_emergency: bool):
    departments = department_aliases(recommended_responder)
    if not departments:
        responders = db.execute(
            """
            SELECT id, responder_type FROM users
            WHERE role = 'Responder'
              AND COALESCE(availability_status, 'Available') = 'Available'
            """
        ).fetchall()
    else:
        placeholders = ",".join("?" for _ in departments) or "?"
        responders = db.execute(
            f"""
            SELECT id, responder_type FROM users
            WHERE role = 'Responder'
              AND responder_type IN ({placeholders})
              AND COALESCE(availability_status, 'Available') = 'Available'
            """,
            departments or [canonical_department(recommended_responder)],
        ).fetchall()
    for responder in responders:
        db.execute(
            """
            INSERT INTO responder_assignments (incident_id, responder_id, recommended_responder, status)
            VALUES (?, ?, ?, 'Waiting for Responder')
            """,
            (incident_id, responder["id"], responder["responder_type"] or recommended_responder),
        )


def create_incident_record(
    user: dict,
    description: str,
    location: str,
    latitude: str | None = None,
    longitude: str | None = None,
    people_affected: str = "",
    image_path: str | None = None,
    audio_path: str | None = None,
    is_emergency: bool = False,
):
    analysis = analyze_incident(description, location, people_affected, image_path, audio_path, is_emergency=is_emergency)
    recommended_responder = canonical_department(analysis["recommended_responder"])
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO incidents (
                citizen_id, description, location, latitude, longitude, people_affected, image_path, audio_path,
                incident_category, incident_type, severity, confidence, priority_reason, ai_reason,
                ai_summary, impact_analysis, safety_recommendations, recommended_responder,
                responder_reason, emergency_contact, public_advisory, is_emergency, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                description,
                location,
                latitude,
                longitude,
                people_affected,
                image_path,
                audio_path,
                analysis.get("incident_category", "Emergency" if is_emergency else "General"),
                analysis["incident_type"],
                analysis["severity"],
                int(analysis["confidence"]),
                analysis.get("priority_reason", ""),
                json.dumps(analysis["ai_reason"]),
                analysis["ai_summary"],
                analysis["impact_analysis"],
                json.dumps(analysis["safety_recommendations"]),
                recommended_responder,
                analysis["responder_reason"],
                json.dumps(analysis["emergency_contact"]),
                analysis["public_advisory"],
                1 if is_emergency else 0,
                "Waiting for Responder",
            ),
        )
        incident_id = cursor.lastrowid
        assign_matching_responders(db, incident_id, recommended_responder, is_emergency)
        return parse_incident(db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone())


def responder_can_access_incident(db, user: dict, incident_id: int) -> bool:
    departments = responder_departments_for(user)
    incident = row_to_dict(db.execute("SELECT recommended_responder FROM incidents WHERE id = ?", (incident_id,)).fetchone())
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    assignment = db.execute(
        "SELECT id FROM responder_assignments WHERE incident_id = ? AND responder_id = ?",
        (incident_id, user["id"]),
    ).fetchone()
    return bool(assignment or (departments and incident["recommended_responder"] in departments))


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "Sentinel AI"}


@app.post("/auth/register")
def register(payload: RegisterRequest):
    if payload.role not in {"Citizen", "Responder"}:
        raise HTTPException(status_code=400, detail="Role must be Citizen or Responder")
    with get_db() as db:
        existing = db.execute("SELECT id FROM users WHERE email = ?", (payload.email.lower(),)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
        cursor = db.execute(
            """
            INSERT INTO users (name, email, password_hash, role, responder_type, location, availability_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name.strip(),
                payload.email.lower(),
                hash_password(payload.password),
                payload.role,
                canonical_department(payload.responder_type) if payload.role == "Responder" else None,
                payload.location,
                payload.availability_status if payload.role == "Responder" else None,
            ),
        )
        user = {
            "id": cursor.lastrowid,
            "name": payload.name.strip(),
            "email": payload.email.lower(),
            "role": payload.role,
            "responder_type": canonical_department(payload.responder_type) if payload.role == "Responder" else None,
            "location": payload.location,
            "availability_status": payload.availability_status if payload.role == "Responder" else None,
        }
    return {"token": create_token(user), "user": user}


@app.post("/auth/login")
def login(payload: LoginRequest):
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE email = ?", (payload.email.lower(),)).fetchone()
    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user = {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "responder_type": row["responder_type"],
        "location": row["location"],
        "availability_status": row["availability_status"],
    }
    return {"token": create_token(user), "user": user}


@app.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return user


@app.post("/ai/analyze")
def analyze_only(
    description: str = Form(...),
    location: str = Form(...),
    people_affected: str = Form(""),
    image: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    user: dict = Depends(require_role("Citizen", "Responder")),
):
    image_path = save_upload(image, f"preview-image-{user['id']}") if image else None
    audio_path = save_upload(audio, f"preview-audio-{user['id']}") if audio else None
    return analyze_incident(description, location, people_affected, image_path, audio_path)


@app.post("/incidents")
def create_incident(
    description: str = Form(...),
    location: str = Form(...),
    latitude: str = Form(""),
    longitude: str = Form(""),
    people_affected: str = Form(""),
    image: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    user: dict = Depends(require_role("Citizen")),
):
    image_path = save_upload(image, f"incident-image-{user['id']}") if image else None
    audio_path = save_upload(audio, f"incident-audio-{user['id']}") if audio else None
    return create_incident_record(user, description, location, latitude or None, longitude or None, people_affected, image_path, audio_path)


@app.post("/incidents/sos")
def create_sos(payload: SOSRequest, user: dict = Depends(require_role("Citizen"))):
    if not payload.location.strip():
        raise HTTPException(status_code=400, detail="Location is required for SOS alerts")
    description = payload.description or "SOS emergency alert submitted by citizen."
    return create_incident_record(
        user,
        description,
        payload.location.strip(),
        payload.latitude,
        payload.longitude,
        "Unknown",
        is_emergency=True,
    )


@app.get("/incidents")
def list_incidents(user: dict = Depends(current_user)):
    severity_order = "CASE severity WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END"
    with get_db() as db:
        if user["role"] == "Citizen":
            rows = db.execute(
                f"SELECT * FROM incidents ORDER BY {severity_order}, created_at DESC",
            ).fetchall()
        else:
            if user.get("responder_type"):
                departments = responder_departments_for(user)
                placeholders = ",".join("?" for _ in departments) or "?"
                rows = db.execute(
                    f"""
                    SELECT DISTINCT i.* FROM incidents i
                    LEFT JOIN responder_assignments ra ON ra.incident_id = i.id
                    WHERE i.recommended_responder IN ({placeholders})
                       OR ra.responder_id = ?
                    ORDER BY i.is_emergency DESC, {severity_order}, i.created_at DESC
                    """,
                    (*departments, user["id"]),
                ).fetchall()
            else:
                rows = db.execute(f"SELECT * FROM incidents ORDER BY is_emergency DESC, {severity_order}, created_at DESC").fetchall()
    return [parse_incident(row) for row in rows]


@app.get("/incidents/{incident_id}")
def incident_detail(incident_id: int, user: dict = Depends(current_user)):
    with get_db() as db:
        row = db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        assignment = row_to_dict(db.execute("SELECT * FROM responder_assignments WHERE incident_id = ? ORDER BY id DESC", (incident_id,)).fetchone())
    incident = parse_incident(row)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if user["role"] == "Responder":
        departments = responder_departments_for(user)
        assigned_to_user = assignment and assignment.get("responder_id") == user["id"]
        if departments and incident["recommended_responder"] not in departments and not assigned_to_user:
            raise HTTPException(status_code=403, detail="Not allowed")
    incident["assignment"] = assignment
    incident["notification"] = notification_message(incident)
    incident["timeline"] = [
        {"label": "Reported", "time": incident["created_at"]},
        {"label": f"AI triaged as {incident['severity']}", "time": incident["created_at"]},
        {"label": incident["status"], "time": incident["updated_at"]},
    ]
    return incident


@app.patch("/incidents/{incident_id}/status")
def update_status(incident_id: int, payload: StatusRequest, user: dict = Depends(require_role("Responder"))):
    allowed = {"Waiting for Responder", "Assigned", "Accepted", "In Progress", "Resolved", "Rejected"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status")
    with get_db() as db:
        if not responder_can_access_incident(db, user, incident_id):
            raise HTTPException(status_code=403, detail="Not allowed")
        db.execute(
            "UPDATE incidents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (payload.status, incident_id),
        )
        db.execute(
            "UPDATE responder_assignments SET status = ?, responder_id = COALESCE(responder_id, ?), updated_at = CURRENT_TIMESTAMP WHERE incident_id = ?",
            (payload.status, user["id"], incident_id),
        )
    return {"status": payload.status}


@app.post("/responders/assign/{incident_id}")
def assign_responder(incident_id: int, user: dict = Depends(require_role("Responder"))):
    with get_db() as db:
        incident = row_to_dict(db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone())
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if not responder_can_access_incident(db, user, incident_id):
            raise HTTPException(status_code=403, detail="Not allowed")
        db.execute("UPDATE incidents SET status = 'Assigned', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (incident_id,))
        db.execute(
            """
            INSERT INTO responder_assignments (incident_id, responder_id, recommended_responder, status)
            VALUES (?, ?, ?, 'Assigned')
            """,
            (incident_id, user["id"], incident["recommended_responder"] or "Disaster Response Team"),
        )
    return {"message": "Dispatch recommendation saved", "status": "Assigned"}


@app.get("/responders/assignments")
def responder_assignments(user: dict = Depends(require_role("Responder"))):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT i.*, ra.status AS assignment_status, ra.assigned_at
            FROM responder_assignments ra
            JOIN incidents i ON i.id = ra.incident_id
            WHERE ra.responder_id = ?
            ORDER BY ra.assigned_at DESC
            """,
            (user["id"],),
        ).fetchall()
    return [parse_incident(row) for row in rows]


@app.get("/responders/notifications")
def responder_notifications(user: dict = Depends(require_role("Responder"))):
    severity_order = "CASE severity WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END"
    with get_db() as db:
        if user.get("responder_type"):
            departments = responder_departments_for(user)
            placeholders = ",".join("?" for _ in departments) or "?"
            rows = db.execute(
                f"""
                SELECT DISTINCT i.* FROM incidents i
                LEFT JOIN responder_assignments ra ON ra.incident_id = i.id
                WHERE (i.recommended_responder IN ({placeholders}) OR ra.responder_id = ?)
                  AND i.status IN ('Waiting for Responder', 'Reported', 'Assigned', 'Accepted', 'In Progress')
                ORDER BY i.is_emergency DESC, {severity_order}, i.created_at DESC
                """,
                (*departments, user["id"]),
            ).fetchall()
        else:
            rows = db.execute(
                f"""
                SELECT * FROM incidents
                WHERE status IN ('Waiting for Responder', 'Reported', 'Assigned', 'Accepted', 'In Progress')
                ORDER BY {severity_order}, created_at DESC
                """
            ).fetchall()
    incidents = [parse_incident(row) for row in rows]
    return [
        {
            "id": incident["id"],
            "message": notification_message(incident),
            "incident_type": incident["incident_type"],
            "severity": incident["severity"],
            "is_emergency": incident["is_emergency"],
            "location": incident["location"],
            "created_at": incident["created_at"],
        }
        for incident in incidents
    ]
