import os
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any

from database import db, create_document, get_documents
from schemas import (
    Patient,
    TriageEvent,
    Staff,
    Shift,
    Room,
    Admission,
    InventoryItem,
    Procedure,
    LabOrder,
    LabResult,
    Prescription,
    AuditLog,
    InsuranceClaim,
    GovernmentReport,
    PayrollRecord,
)

app = FastAPI(title="RS Rujukan Regional - Hospital 4.0 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "RS Rujukan Regional API running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:20]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# ---------- Minimal functional endpoints for the MVP ----------

# 1) Create patient profile
@app.post("/patients")
def create_patient(payload: Patient):
    pid = create_document("patient", payload)
    create_document("auditlog", AuditLog(action="create", entity="patient", entity_id=pid, meta={"source": "api"}))
    return {"id": pid}

# 2) Triage event with automatic consent handling
@app.post("/triage")
def triage(payload: TriageEvent):
    data = payload.model_dump()
    critical = False
    if payload.gcs is not None and payload.gcs <= 8:
        critical = True
    spo2 = payload.vital_signs.get("spo2") if payload.vital_signs else None
    if spo2 is not None and spo2 < 90:
        critical = True
    if critical and not payload.consent_emergency_protocol:
        data["consent_emergency_protocol"] = True
        data.setdefault("critical_flags", []).append("auto_consent_emergency_protocol")
    tid = create_document("triageevent", data)
    create_document("auditlog", AuditLog(action="create", entity="triageevent", entity_id=tid))
    return {"id": tid, "critical": critical, "consent": data.get("consent_emergency_protocol", False)}

# 3) Admission and room tracking
@app.post("/admissions")
def create_admission(payload: Admission):
    # Basic bed availability check
    room = db["room"].find_one({"code": payload.room_code})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.get("occupied_beds", 0) >= room.get("bed_count", 0):
        raise HTTPException(status_code=409, detail="No available bed")
    aid = create_document("admission", payload)
    db["room"].update_one({"code": payload.room_code}, {"$inc": {"occupied_beds": 1}})
    create_document("auditlog", AuditLog(action="create", entity="admission", entity_id=aid))
    return {"id": aid}

@app.post("/admissions/{admission_id}/discharge")
def discharge(admission_id: str):
    adm = db["admission"].find_one({"_id": {"$eq": db["admission"].codec_options.document_class()._id} }) if False else None
    # simple discharge: decrement bed
    admission = db["admission"].find_one({"_id": {"$oid": admission_id}})
    if not admission:
        # fallback simple find by string id, for viewer context ignore ObjectId parsing
        admission = db["admission"].find_one({"id": admission_id})
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    db["room"].update_one({"code": admission.get("room_code")}, {"$inc": {"occupied_beds": -1}})
    db["admission"].update_one({"_id": admission.get("_id")}, {"$set": {"end": datetime.now(timezone.utc)}})
    create_document("auditlog", AuditLog(action="update", entity="admission", entity_id=admission_id, meta={"op": "discharge"}))
    return {"status": "ok"}

# 4) Procedures with sterile workflow
@app.post("/procedures")
def create_procedure(payload: Procedure):
    data = payload.model_dump()
    if payload.requires_sterile and not payload.sterile_batch:
        data["sterile_batch"] = f"AUTO-{int(datetime.now().timestamp())}"
        data["cssd_return_due"] = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
    pid = create_document("procedure", data)
    create_document("auditlog", AuditLog(action="create", entity="procedure", entity_id=pid))
    return {"id": pid}

# 5) Pharmacy: validate prescription and stock status
class PrescriptionValidateRequest(BaseModel):
    prescription: Prescription

@app.post("/pharmacy/validate")
def validate_prescription(req: PrescriptionValidateRequest):
    p = req.prescription
    # Simple allergy and interaction checker stub
    allergen_set = {a.substance.lower() for a in db["patient"].find_one({"_id": {"$exists": False}}) or []} if False else set()
    items = p.items
    out_of_stock = []
    for it in items:
        sku = it.get("drug") or it.get("sku")
        inv = db["inventoryitem"].find_one({"sku": sku})
        if not inv or inv.get("stock", 0) <= 0:
            out_of_stock.append(sku)
    status = "validated" if not out_of_stock else "out_of_stock_external"
    return {"status": status, "out_of_stock": out_of_stock}

# 6) External lab result intake (simulated)
@app.post("/labs/external/callback")
def external_lab_result(payload: LabResult):
    rid = create_document("labresult", payload)
    create_document("auditlog", AuditLog(action="create", entity="labresult", entity_id=rid, meta={"source": "external"}))
    return {"id": rid}

# 7) Simple dashboards
@app.get("/dashboard/bor")
def dashboard_bor():
    total_beds = 0
    occupied = 0
    for r in db["room"].find({}):
        total_beds += r.get("bed_count", 0)
        occupied += r.get("occupied_beds", 0)
    return {"total_beds": total_beds, "occupied": occupied, "bor": (occupied / total_beds * 100) if total_beds else 0}

@app.get("/schema")
def get_schema():
    # Minimal exposure so tools/viewers can read collection names
    return {
        "collections": [
            "patient", "triageevent", "staff", "shift", "room", "admission",
            "inventoryitem", "procedure", "laborder", "labresult", "prescription",
            "auditlog", "insuranceclaim", "governmentreport", "payrollrecord"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
