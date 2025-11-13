"""
Database Schemas for RS Rujukan Regional (Hospital 4.0)

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercase of the class name, e.g., Patient -> "patient".

These schemas are designed for core modules: patients, triage, staff & shifts,
rooms/admissions, labs, prescriptions/pharmacy, audit, claims/reports, and payroll.
"""

from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal, Dict, Any
from datetime import datetime

# ---------- Shared/Embedded Types ----------

class PersonName(BaseModel):
    first: str
    last: Optional[str] = None
    middle: Optional[str] = None

class Contact(BaseModel):
    name: str
    relation: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None

class Allergy(BaseModel):
    substance: str
    reaction: Optional[str] = None
    severity: Optional[Literal["mild", "moderate", "severe", "anaphylaxis"]] = None

class ChronicCondition(BaseModel):
    name: str
    status: Optional[Literal["active", "remission", "resolved"]] = "active"

class InsuranceInfo(BaseModel):
    type: Literal[
        "umum",
        "bpjs",
        "pppk",
        "jampersal",
        "jamkesda",
        "sisrute",
        "telemedis",
    ]
    policy_number: Optional[str] = None
    provider: Optional[str] = None

# ---------- Core Collections ----------

class Patient(BaseModel):
    national_mrn: str = Field(..., description="ID rekam medis unik nasional")
    name: PersonName
    birth_date: Optional[datetime] = None
    gender: Optional[Literal["male", "female", "other"]] = None
    phone: Optional[str] = None
    address: Optional[str] = None

    categories: List[InsuranceInfo] = Field(default_factory=list, description="Kategori/jenis pasien")

    family_profile: Optional[Dict[str, Any]] = None
    guarantor: Optional[Contact] = None
    emergency_contacts: List[Contact] = Field(default_factory=list)

    allergies: List[Allergy] = Field(default_factory=list)
    chronic_conditions: List[ChronicCondition] = Field(default_factory=list)

    qr_wristband: Optional[str] = Field(None, description="QR code content for wristband")

    telemed_referral_type: Optional[Literal["UGD", "URJ"]] = None
    telemed_referral_time: Optional[datetime] = None

class TriageEvent(BaseModel):
    patient_id: str
    arrival_mode: Optional[str] = None
    gcs: Optional[int] = Field(None, ge=3, le=15)
    vital_signs: Dict[str, Optional[float]] = Field(default_factory=dict, description="td_systolic, td_diastolic, nadi, spo2, rr, temp")
    esi_level: Optional[int] = Field(None, ge=1, le=5)
    critical_flags: List[str] = Field(default_factory=list)
    consent_emergency_protocol: bool = False
    notes: Optional[str] = None

class Staff(BaseModel):
    staff_id: str
    name: PersonName
    role: Literal["dokter_umum", "spesialis", "sub_spesialis", "perawat_junior", "perawat_madya", "perawat_senior", "farmasi", "laboran", "admin"]
    sip: Optional[str] = None
    str_number: Optional[str] = None
    qualifications: List[str] = Field(default_factory=list)
    on_call: bool = False

class Shift(BaseModel):
    staff_id: str
    area: Literal["IGD", "ICU", "NICU", "Isolasi", "Bedah", "URJ", "URI", "HD", "Ruang Umum"]
    start: datetime
    end: datetime

class Room(BaseModel):
    code: str
    zone: Literal["Airborne", "Droplet", "Contact", "ICU", "NICU", "HD", "Bedah_Elektif", "Bedah_Emergensi", "Negatif", "Positif", "Umum"]
    bed_count: int = 1
    occupied_beds: int = 0
    tariff_class: Literal["VVIP", "VIP", "1", "2", "3"] = "3"

class Admission(BaseModel):
    patient_id: str
    room_code: str
    bed_number: Optional[int] = None
    start: datetime
    end: Optional[datetime] = None
    risk_movement: Optional[str] = None

class InventoryItem(BaseModel):
    sku: str
    name: str
    type: Literal["obat", "alat_medis", "material"]
    barcode: Optional[str] = None
    stock: int = 0
    sterile_batch: Optional[str] = None

class Procedure(BaseModel):
    patient_id: str
    doctor_id: str
    description: str
    requires_sterile: bool = False
    sterile_batch: Optional[str] = None
    cssd_return_due: Optional[datetime] = None
    materials: List[Dict[str, Any]] = Field(default_factory=list, description="material barcode/sku tracking")
    e_signature: Optional[str] = None
    iot_devices: List[str] = Field(default_factory=list, description="ventilator, infus pump IDs, etc.")

class LabOrder(BaseModel):
    patient_id: str
    tests: List[str]
    source: Literal["UGD", "URJ", "RI", "External"] = "UGD"
    tube_barcode: Optional[str] = None
    status: Literal["ordered", "in_progress", "completed"] = "ordered"
    external_ref: Optional[str] = None

class LabResult(BaseModel):
    order_id: str
    results: Dict[str, Any]
    status: Literal["completed", "partial"] = "completed"

class Prescription(BaseModel):
    patient_id: str
    items: List[Dict[str, Any]] = Field(default_factory=list, description="[{drug, dose, freq, duration, compound: bool}]")
    allergies_checked: bool = False
    interactions_checked: bool = False
    status: Literal["draft", "validated", "dispensed", "out_of_stock_external"] = "draft"

class AuditLog(BaseModel):
    actor_id: Optional[str] = None
    action: str
    entity: str
    entity_id: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

class InsuranceClaim(BaseModel):
    patient_id: str
    payer: Literal["BPJS", "Askes", "Swasta", "Jamkesda", "Jampersal"]
    amount: float
    status: Literal["submitted", "in_review", "approved", "rejected", "paid"] = "submitted"

class GovernmentReport(BaseModel):
    kind: Literal["VClaim", "SISRUTE", "SATUSEHAT"]
    payload: Dict[str, Any]
    status: Literal["queued", "sent", "error"] = "queued"

class PayrollRecord(BaseModel):
    staff_id: str
    month: str  # YYYY-MM
    kehadiran: int = 0
    tindakan_langsung: int = 0
    tindakan_asistensi: int = 0
    insentif_igd: int = 0
    insentif_icu: int = 0
    insentif_isolasi: int = 0
    bonus_bpjs: float = 0.0
    base_salary: float = 0.0
    total: float = 0.0

# Note: A GET /schema endpoint in the backend will expose these definitions for viewers/tools.
