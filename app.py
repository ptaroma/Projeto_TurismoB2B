import hashlib
import importlib
import json
import logging
import os
import re
import secrets
import smtplib
import unicodedata
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

try:
    airportsdata = importlib.import_module("airportsdata")
except Exception:  # pragma: no cover - fallback quando pacote nao estiver disponivel
    airportsdata = None

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

DEFAULT_SQLITE_URL = f"sqlite:///{BASE_DIR / 'turismob2b.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))

AUTH_WINDOW_SECONDS = int(os.getenv("AUTH_WINDOW_SECONDS", "60"))
AUTH_MAX_ATTEMPTS = int(os.getenv("AUTH_MAX_ATTEMPTS", "10"))
INVITE_EXPIRY_HOURS = int(os.getenv("INVITE_EXPIRY_HOURS", "72"))
ALLOW_PUBLIC_SIGNUP = os.getenv("ALLOW_PUBLIC_SIGNUP", "false").strip().lower() == "true"

ADMIN_BOOTSTRAP_EMAIL = os.getenv("ADMIN_BOOTSTRAP_EMAIL", "").strip().lower()
ADMIN_BOOTSTRAP_PASSWORD = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "").strip()
ADMIN_BOOTSTRAP_NAME = os.getenv("ADMIN_BOOTSTRAP_NAME", "Administrador").strip()
LEAD_EMAIL_TO = os.getenv("LEAD_EMAIL_TO", "comercialtitan.cover@gmail.com").strip()
LEAD_WHATSAPP_NUMBER = os.getenv("LEAD_WHATSAPP_NUMBER", "+55 11 99469-1868").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER).strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"

logger = logging.getLogger("turismob2b.smtp")


def get_cors_origins() -> list[str]:
    raw = os.getenv("APP_CORS_ORIGINS", "*").strip()
    if raw == "*":
        return ["*"]
    return [x.strip() for x in raw.split(",") if x.strip()]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_engine():
    if DATABASE_URL.startswith("sqlite"):
        return create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    return create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_MAX_OVERFLOW,
        pool_recycle=DB_POOL_RECYCLE,
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    salt = Column(String(64), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="consultant")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(String(40), nullable=False)

    quotes = relationship("Quote", back_populates="user")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    expires_at = Column(String(40), nullable=False)
    created_at = Column(String(40), nullable=False)
    revoked_at = Column(String(40), nullable=True)


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    quote_name = Column(String(120), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    version = Column(Integer, nullable=False, default=1)
    total_to_client = Column(Float, nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(String(40), nullable=False)
    updated_at = Column(String(40), nullable=False)

    user = relationship("User", back_populates="quotes")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_type = Column(String(80), nullable=False)
    resource_type = Column(String(80), nullable=False, default="")
    resource_id = Column(String(80), nullable=False, default="")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(String(40), nullable=False)


class SignupInvite(Base):
    __tablename__ = "signup_invites"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    role = Column(String(20), nullable=False, default="consultant")
    full_name = Column(String(80), nullable=False, default="")
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(String(40), nullable=False)
    created_at = Column(String(40), nullable=False)
    used_at = Column(String(40), nullable=True)


class PublicQuoteLead(Base):
    __tablename__ = "public_quote_leads"

    id = Column(Integer, primary_key=True, index=True)
    travel_type = Column(String(30), nullable=False)
    full_name = Column(String(120), nullable=False)
    contact = Column(String(255), nullable=False)
    origin = Column(String(100), nullable=False)
    destination = Column(String(100), nullable=False)
    departure_date = Column(String(20), nullable=False)
    return_date = Column(String(20), nullable=False)
    adults = Column(Integer, nullable=False, default=1)
    children = Column(Integer, nullable=False, default=0)
    cabin = Column(String(30), nullable=False)
    created_at = Column(String(40), nullable=False)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    invite_token: str = Field(min_length=20, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=30, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class QuotePayload(BaseModel):
    client_company: str = Field(default="")
    client_contact: str = Field(default="")
    client_email: str = Field(default="")
    consultant_name: str = Field(default="")
    origin: str = Field(default="")
    destination: str = Field(default="")
    departure_date: str = Field(default="")
    return_date: str = Field(default="")
    adults: int = Field(default=1, ge=1, le=9)
    cabin: str = Field(default="economy")
    airfare_total: float = Field(default=0)
    hotel_total: float = Field(default=0)
    car_total: float = Field(default=0)
    extras_total: float = Field(default=0)
    service_fee: float = Field(default=0)
    margin_pct: float = Field(default=15)
    base_cost: float = Field(default=0)
    margin_value: float = Field(default=0)
    total_to_client: float = Field(default=0)
    validity_hours: int = Field(default=24, ge=1, le=168)
    notes: str = Field(default="")


class SaveQuoteRequest(BaseModel):
    quote_name: str = Field(min_length=2, max_length=120)
    payload: QuotePayload


class UpdateQuoteStatusRequest(BaseModel):
    status: str = Field(min_length=3, max_length=20)


class AdminCreateInviteRequest(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=80)
    role: str = Field(default="consultant", min_length=4, max_length=20)
    expires_in_hours: int = Field(default=INVITE_EXPIRY_HOURS, ge=1, le=336)


class PublicLeadQuoteRequest(BaseModel):
    travel_type: str = Field(min_length=3, max_length=30)
    full_name: str = Field(min_length=3, max_length=120)
    contact: str = Field(min_length=5, max_length=255)
    email: EmailStr
    origin: str = Field(min_length=3, max_length=100)
    destination: str = Field(min_length=3, max_length=100)
    departure_date: str = Field(min_length=8, max_length=20)
    return_date: str = Field(min_length=8, max_length=20)
    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=9)
    cabin: str = Field(min_length=3, max_length=30)


auth_attempts: dict[str, deque[datetime]] = defaultdict(deque)

PRIMARY_AIRPORTS = {
    "GRU",
    "CGH",
    "VCP",
    "GIG",
    "SDU",
    "BSB",
    "CNF",
    "POA",
    "FLN",
    "CWB",
    "SSA",
    "REC",
    "FOR",
    "BEL",
    "MAO",
}

AIRPORTS_BR_SEED: list[dict[str, Any]] = [
    {
        "iata": "GRU",
        "city": "Sao Paulo",
        "state": "SP",
        "name": "Aeroporto Internacional de Guarulhos",
        "is_primary": True,
        "keywords": ["guarulhos", "cumbica", "sao paulo"],
    },
    {
        "iata": "CGH",
        "city": "Sao Paulo",
        "state": "SP",
        "name": "Aeroporto de Congonhas",
        "is_primary": False,
        "keywords": ["congonhas", "sao paulo"],
    },
    {
        "iata": "VCP",
        "city": "Campinas",
        "state": "SP",
        "name": "Aeroporto de Viracopos",
        "is_primary": True,
        "keywords": ["viracopos", "campinas", "sao paulo"],
    },
    {
        "iata": "SDU",
        "city": "Rio de Janeiro",
        "state": "RJ",
        "name": "Aeroporto Santos Dumont",
        "is_primary": False,
        "keywords": ["santos dumont", "rio"],
    },
    {
        "iata": "GIG",
        "city": "Rio de Janeiro",
        "state": "RJ",
        "name": "Aeroporto Internacional Galeao",
        "is_primary": True,
        "keywords": ["galeao", "rio", "tom jobim"],
    },
    {
        "iata": "BSB",
        "city": "Brasilia",
        "state": "DF",
        "name": "Aeroporto Internacional de Brasilia",
        "is_primary": True,
        "keywords": ["brasilia", "jks"],
    },
    {
        "iata": "CNF",
        "city": "Belo Horizonte",
        "state": "MG",
        "name": "Aeroporto Internacional de Confins",
        "is_primary": True,
        "keywords": ["confins", "belo horizonte", "tancredo neves"],
    },
    {
        "iata": "PLU",
        "city": "Belo Horizonte",
        "state": "MG",
        "name": "Aeroporto da Pampulha",
        "is_primary": False,
        "keywords": ["pampulha", "belo horizonte"],
    },
    {
        "iata": "POA",
        "city": "Porto Alegre",
        "state": "RS",
        "name": "Aeroporto Salgado Filho",
        "is_primary": True,
        "keywords": ["porto alegre", "salgado filho"],
    },
    {
        "iata": "FLN",
        "city": "Florianopolis",
        "state": "SC",
        "name": "Aeroporto Hercilio Luz",
        "is_primary": True,
        "keywords": ["florianopolis", "hercilio luz"],
    },
    {
        "iata": "CWB",
        "city": "Curitiba",
        "state": "PR",
        "name": "Aeroporto Afonso Pena",
        "is_primary": True,
        "keywords": ["curitiba", "afonso pena", "sao jose dos pinhais"],
    },
    {
        "iata": "SSA",
        "city": "Salvador",
        "state": "BA",
        "name": "Aeroporto Internacional de Salvador",
        "is_primary": True,
        "keywords": ["salvador", "deputado luis eduardo magalhaes"],
    },
    {
        "iata": "REC",
        "city": "Recife",
        "state": "PE",
        "name": "Aeroporto Internacional do Recife",
        "is_primary": True,
        "keywords": ["recife", "guararapes"],
    },
    {
        "iata": "FOR",
        "city": "Fortaleza",
        "state": "CE",
        "name": "Aeroporto Internacional de Fortaleza",
        "is_primary": True,
        "keywords": ["fortaleza", "pinto martins"],
    },
    {
        "iata": "NAT",
        "city": "Natal",
        "state": "RN",
        "name": "Aeroporto Internacional de Natal",
        "is_primary": True,
        "keywords": ["natal", "sao goncalo do amarante"],
    },
    {
        "iata": "JPA",
        "city": "Joao Pessoa",
        "state": "PB",
        "name": "Aeroporto Presidente Castro Pinto",
        "is_primary": True,
        "keywords": ["joao pessoa", "castro pinto"],
    },
    {
        "iata": "MCZ",
        "city": "Maceio",
        "state": "AL",
        "name": "Aeroporto Internacional de Maceio",
        "is_primary": True,
        "keywords": ["maceio", "zumbi dos palmares"],
    },
    {
        "iata": "AJU",
        "city": "Aracaju",
        "state": "SE",
        "name": "Aeroporto de Aracaju",
        "is_primary": True,
        "keywords": ["aracaju", "santa maria"],
    },
    {
        "iata": "BEL",
        "city": "Belem",
        "state": "PA",
        "name": "Aeroporto Internacional de Belem",
        "is_primary": True,
        "keywords": ["belem", "val de cans"],
    },
    {
        "iata": "MAO",
        "city": "Manaus",
        "state": "AM",
        "name": "Aeroporto Internacional Eduardo Gomes",
        "is_primary": True,
        "keywords": ["manaus", "eduardo gomes"],
    },
    {
        "iata": "CGB",
        "city": "Cuiaba",
        "state": "MT",
        "name": "Aeroporto Marechal Rondon",
        "is_primary": True,
        "keywords": ["cuiaba", "marechal rondon", "varzea grande"],
    },
    {
        "iata": "GYN",
        "city": "Goiania",
        "state": "GO",
        "name": "Aeroporto Santa Genoveva",
        "is_primary": True,
        "keywords": ["goiania", "santa genoveva"],
    },
    {
        "iata": "VIX",
        "city": "Vitoria",
        "state": "ES",
        "name": "Aeroporto Eurico de Aguiar Salles",
        "is_primary": True,
        "keywords": ["vitoria", "eurico salles"],
    },
    {
        "iata": "IGU",
        "city": "Foz do Iguacu",
        "state": "PR",
        "name": "Aeroporto Internacional de Foz do Iguacu",
        "is_primary": True,
        "keywords": ["foz", "iguacu", "cataratas"],
    },
    {
        "iata": "SLZ",
        "city": "Sao Luis",
        "state": "MA",
        "name": "Aeroporto Internacional Marechal Cunha Machado",
        "is_primary": True,
        "keywords": ["sao luis", "cunha machado"],
    },
    {
        "iata": "THE",
        "city": "Teresina",
        "state": "PI",
        "name": "Aeroporto Senador Petronio Portella",
        "is_primary": True,
        "keywords": ["teresina", "petronio portella"],
    },
]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def normalize_text(value: str) -> str:
    if not value:
        return ""
    text_value = unicodedata.normalize("NFKD", value)
    text_value = "".join(ch for ch in text_value if not unicodedata.combining(ch))
    return " ".join(text_value.lower().strip().split())


def build_airports_catalog() -> list[dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}

    for airport in AIRPORTS_BR_SEED:
        iata = str(airport.get("iata", "")).upper().strip()
        if len(iata) != 3:
            continue
        catalog[iata] = {
            "iata": iata,
            "city": str(airport.get("city", "")).strip() or iata,
            "state": str(airport.get("state", "")).strip(),
            "name": str(airport.get("name", f"Aeroporto {iata}")).strip(),
            "is_primary": bool(airport.get("is_primary", False) or iata in PRIMARY_AIRPORTS),
            "keywords": [str(k).strip() for k in airport.get("keywords", []) if str(k).strip()],
        }

    if airportsdata is not None:
        try:
            all_airports = airportsdata.load("IATA")
            for code, row in all_airports.items():
                country = str(row.get("country", "")).upper().strip()
                if country != "BR":
                    continue

                iata = str(row.get("iata") or code or "").upper().strip()
                if len(iata) != 3 or iata == "\\N":
                    continue

                city = str(row.get("city") or "").strip() or iata
                state = str(row.get("subd") or "").strip()
                name = str(row.get("name") or f"Aeroporto {iata}").strip()

                keywords = [city, name]
                if state:
                    keywords.append(state)

                entry = {
                    "iata": iata,
                    "city": city,
                    "state": state,
                    "name": name,
                    "is_primary": iata in PRIMARY_AIRPORTS,
                    "keywords": [normalize_text(k) for k in keywords if k],
                }

                if iata in catalog:
                    existing = catalog[iata]
                    existing["is_primary"] = bool(existing.get("is_primary") or entry["is_primary"])
                    if not existing.get("state") and entry.get("state"):
                        existing["state"] = entry["state"]
                    if len(existing.get("name", "")) < len(entry.get("name", "")):
                        existing["name"] = entry["name"]
                    if len(existing.get("city", "")) < len(entry.get("city", "")):
                        existing["city"] = entry["city"]
                    merged = {normalize_text(k) for k in existing.get("keywords", []) + entry.get("keywords", []) if k}
                    existing["keywords"] = sorted(merged)
                else:
                    catalog[iata] = entry
        except Exception:
            pass

    return sorted(catalog.values(), key=lambda a: (normalize_text(a["city"]), a["iata"]))


AIRPORTS_BR = build_airports_catalog()


def airport_score(airport: dict[str, Any], query: str) -> int:
    query_norm = normalize_text(query)
    if not query_norm:
        return 0

    iata = str(airport["iata"])
    city = str(airport["city"])
    name = str(airport["name"])
    state = str(airport["state"])
    keywords = " ".join(str(k) for k in airport.get("keywords", []))

    iata_norm = normalize_text(iata)
    city_norm = normalize_text(city)
    name_norm = normalize_text(name)
    state_norm = normalize_text(state)
    all_norm = " ".join([iata_norm, city_norm, name_norm, state_norm, normalize_text(keywords)])

    score = 0
    if query_norm == iata_norm:
        score += 300
    if query_norm in city_norm:
        score += 180
    if city_norm.startswith(query_norm):
        score += 60
    if query_norm in name_norm:
        score += 120
    if query_norm in state_norm:
        score += 20
    if query_norm in all_norm:
        score += 30

    for token in query_norm.split(" "):
        if token and token in all_norm:
            score += 14

    if airport.get("is_primary"):
        score += 10

    return score


def security_headers(response: Response) -> None:
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"


def check_auth_rate_limit(request: Request, action: str) -> None:
    now = utcnow()
    ip = request.client.host if request.client else "unknown"
    key = f"{action}:{ip}"
    bucket = auth_attempts[key]
    window_start = now - timedelta(seconds=AUTH_WINDOW_SECONDS)

    while bucket and bucket[0] < window_start:
        bucket.popleft()

    if len(bucket) >= AUTH_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Tente novamente em instantes.")

    bucket.append(now)


def ensure_password_policy(password: str) -> None:
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if len(password) < 10 or not has_upper or not has_lower or not has_digit:
        raise HTTPException(
            status_code=400,
            detail="Senha fraca. Use ao menos 10 caracteres com maiuscula, minuscula e numero.",
        )


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000)
    return digest.hex()


def create_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return salt, hash_password(password, salt)


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return hash_password(password, salt) == expected_hash


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_invite_token() -> str:
    return f"tb2b_inv_{secrets.token_urlsafe(24)}"


def create_access_token(user: User) -> str:
    exp = utcnow() + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "type": "access",
        "exp": exp,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(db: Session, user: User) -> str:
    raw = secrets.token_urlsafe(64)
    token_obj = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=(utcnow() + timedelta(days=REFRESH_TOKEN_DAYS)).isoformat(),
        created_at=utcnow().isoformat(),
        revoked_at=None,
    )
    db.add(token_obj)
    db.commit()
    return raw


def parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header ausente")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Formato de token invalido")

    return parts[1].strip()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    token = parse_bearer_token(authorization)
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Token invalido ou expirado") from exc

    if decoded.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token invalido")

    user_id = int(decoded.get("sub", "0"))
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario inativo ou inexistente")

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
    }


def require_roles(*roles: str):
    def checker(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Permissao insuficiente")
        return user

    return checker


def audit_event(
    db: Session,
    *,
    user_id: int | None,
    event_type: str,
    resource_type: str = "",
    resource_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=True),
        created_at=utcnow().isoformat(),
    )
    db.add(entry)


def parse_iso_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D+", "", value)
    if not digits:
        return ""
    if value.strip().startswith("+"):
        return f"+{digits}"
    if digits.startswith("55"):
        return f"+{digits}"
    return f"+55{digits}"


def build_whatsapp_url(message: str) -> str:
    safe_number = re.sub(r"\D+", "", LEAD_WHATSAPP_NUMBER)
    return f"https://wa.me/{safe_number}?text={requests_quote(message)}"


def requests_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def send_public_lead_email(subject: str, body: str) -> bool:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and SMTP_FROM_EMAIL and LEAD_EMAIL_TO):
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = LEAD_EMAIL_TO
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        smtp.ehlo()
        if SMTP_USE_TLS:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)

    return True


def migrate_legacy_schema_for_sqlite() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        user_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(users)"))
        }
        if "role" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'consultant'"))
        if "is_active" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))

        quote_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(quotes)"))
        }
        if "status" not in quote_cols:
            conn.execute(text("ALTER TABLE quotes ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'draft'"))
        if "version" not in quote_cols:
            conn.execute(text("ALTER TABLE quotes ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))


def bootstrap_admin(db: Session) -> None:
    if not ADMIN_BOOTSTRAP_EMAIL or not ADMIN_BOOTSTRAP_PASSWORD:
        return

    exists = db.query(User).filter(User.email == ADMIN_BOOTSTRAP_EMAIL).first()
    if exists:
        return

    ensure_password_policy(ADMIN_BOOTSTRAP_PASSWORD)
    salt, pwd_hash = create_password(ADMIN_BOOTSTRAP_PASSWORD)
    admin_user = User(
        name=ADMIN_BOOTSTRAP_NAME,
        email=ADMIN_BOOTSTRAP_EMAIL,
        salt=salt,
        password_hash=pwd_hash,
        role="admin",
        is_active=True,
        created_at=utcnow().isoformat(),
    )
    db.add(admin_user)
    db.commit()


app = FastAPI(title="TurismoB2B Workspace API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    security_headers(response)
    return response


@app.on_event("startup")
def startup() -> None:
    if ENVIRONMENT == "production" and JWT_SECRET == "dev-only-change-me":
        raise RuntimeError("JWT_SECRET padrao invalido em producao")

    Base.metadata.create_all(bind=engine)
    migrate_legacy_schema_for_sqlite()
    db = SessionLocal()
    try:
        bootstrap_admin(db)
    finally:
        db.close()


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/workspace")
def workspace() -> FileResponse:
    return FileResponse(STATIC_DIR / "workspace.html")


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/airports/search")
def search_airports(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=30),
    offset: int = Query(default=0),
    _: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, min(offset, 5000))
    query = q.strip()

    if not query:
        rows = AIRPORTS_BR[safe_offset : safe_offset + safe_limit]
        return [
            {
                "iata": a["iata"],
                "city": a["city"],
                "state": a["state"],
                "name": a["name"],
                "is_primary": a["is_primary"],
                "label": f"{a['city']} ({a['iata']}) - {a['name']}",
                "score": 0,
            }
            for a in rows
        ]

    scored: list[tuple[int, dict[str, Any]]] = []

    for airport in AIRPORTS_BR:
        score = airport_score(airport, query)
        if score > 0:
            scored.append((score, airport))

    scored.sort(key=lambda item: (-item[0], item[1]["city"], item[1]["iata"]))

    return [
        {
            "iata": a["iata"],
            "city": a["city"],
            "state": a["state"],
            "name": a["name"],
            "is_primary": a["is_primary"],
            "label": f"{a['city']} ({a['iata']}) - {a['name']}",
            "score": score,
        }
        for score, a in scored[safe_offset : safe_offset + safe_limit]
    ]


@app.get("/api/public/airports")
def public_airports(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=50),
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 100))
    query = q.strip()

    if not query:
        rows = AIRPORTS_BR[:safe_limit]
        return [
            {
                "iata": a["iata"],
                "city": a["city"],
                "state": a["state"],
                "name": a["name"],
                "label": f"{a['city']} ({a['iata']})",
            }
            for a in rows
        ]

    scored: list[tuple[int, dict[str, Any]]] = []
    for airport in AIRPORTS_BR:
        score = airport_score(airport, query)
        if score > 0:
            scored.append((score, airport))

    scored.sort(key=lambda item: (-item[0], item[1]["city"], item[1]["iata"]))
    return [
        {
            "iata": a["iata"],
            "city": a["city"],
            "state": a["state"],
            "name": a["name"],
            "label": f"{a['city']} ({a['iata']})",
        }
        for _, a in scored[:safe_limit]
    ]


@app.post("/api/public/lead-quote")
def create_public_lead_quote(body: PublicLeadQuoteRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    travel_type = normalize_text(body.travel_type)
    allowed_types = {"turismo", "negocios", "pessoal"}
    if travel_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Tipo de viagem invalido")

    try:
        departure_dt = parse_iso_date(body.departure_date)
        return_dt = parse_iso_date(body.return_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Datas invalidas") from exc

    if return_dt < departure_dt:
        raise HTTPException(status_code=400, detail="Data de retorno nao pode ser menor que data de ida")

    safe_cabin = normalize_text(body.cabin)
    allowed_cabins = {"economica", "premium economy", "executiva", "primeira classe"}
    if safe_cabin not in allowed_cabins:
        raise HTTPException(status_code=400, detail="Classe invalida")

    lead = PublicQuoteLead(
        travel_type=travel_type,
        full_name=body.full_name.strip(),
        contact=body.contact.strip(),
        origin=body.origin.strip(),
        destination=body.destination.strip(),
        departure_date=body.departure_date,
        return_date=body.return_date,
        adults=body.adults,
        children=body.children,
        cabin=safe_cabin,
        created_at=utcnow().isoformat(),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    formatted_type = travel_type.title()
    message_lines = [
        "Nova solicitacao de cotacao recebida no site",
        f"Tipo de viagem: {formatted_type}",
        f"Nome: {body.full_name.strip()}",
        f"Contato: {body.contact.strip()}",
        f"Email: {body.email.strip()}",
        f"Origem: {body.origin.strip()}",
        f"Destino: {body.destination.strip()}",
        f"Ida: {body.departure_date}",
        f"Retorno: {body.return_date}",
        f"Adultos: {body.adults}",
        f"Criancas: {body.children}",
        f"Classe: {body.cabin.strip()}",
        f"Lead ID: {lead.id}",
    ]
    message_text = "\n".join(message_lines)

    email_sent = False
    try:
        email_sent = send_public_lead_email(
            subject=f"TurismoB2B | Nova solicitacao {formatted_type}",
            body=message_text,
        )
    except Exception:
        logger.exception("Falha no envio SMTP de lead publico")
        email_sent = False

    client_message = (
        "Sua solicitacao de Cotacao foi enviada com sucesso. Obrigado por confiar em nosso trabalho"
        if email_sent
        else "Sua solicitacao foi registrada, mas tivemos uma falha temporaria no envio de e-mail ao comercial."
    )

    return {
        "ok": True,
        "lead_id": lead.id,
        "email_target": LEAD_EMAIL_TO,
        "email_sent": email_sent,
        "client_message": client_message,
    }


@app.post("/api/auth/register")
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not ALLOW_PUBLIC_SIGNUP:
        raise HTTPException(status_code=403, detail="Cadastro publico desativado. Contate o administrador.")

    check_auth_rate_limit(request, "register")

    email = body.email.lower().strip()

    invite_hash = hash_token(body.invite_token.strip())
    invite = db.query(SignupInvite).filter(SignupInvite.token_hash == invite_hash).first()
    if not invite:
        raise HTTPException(status_code=403, detail="Cadastro restrito. Solicite convite ao administrador.")

    if invite.used_at:
        raise HTTPException(status_code=403, detail="Convite ja utilizado.")

    if datetime.fromisoformat(invite.expires_at) < utcnow():
        raise HTTPException(status_code=403, detail="Convite expirado. Solicite um novo convite.")

    if invite.email.lower().strip() != email:
        raise HTTPException(status_code=403, detail="Convite nao corresponde ao email informado.")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email ja cadastrado")

    ensure_password_policy(body.password)
    salt, pwd_hash = create_password(body.password)

    user = User(
        name=(invite.full_name.strip() or body.name.strip()),
        email=email,
        salt=salt,
        password_hash=pwd_hash,
        role=invite.role,
        is_active=True,
        created_at=utcnow().isoformat(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    invite.used_at = utcnow().isoformat()
    db.add(invite)

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(db, user)

    audit_event(
        db,
        user_id=user.id,
        event_type="auth.register",
        resource_type="user",
        resource_id=str(user.id),
        metadata={"invite_id": invite.id, "invited_by": invite.created_by_user_id},
    )
    db.commit()

    return {
        "token": access_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
        "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role},
    }


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    check_auth_rate_limit(request, "login")

    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario inativo")
    if not verify_password(body.password, user.salt, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciais invalidas")

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(db, user)

    audit_event(db, user_id=user.id, event_type="auth.login", resource_type="user", resource_id=str(user.id))
    db.commit()

    return {
        "token": access_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
        "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role},
    }


@app.post("/api/auth/refresh")
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    token_hash = hash_token(body.refresh_token)
    token_obj = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if not token_obj or token_obj.revoked_at:
        raise HTTPException(status_code=401, detail="Refresh token invalido")

    if datetime.fromisoformat(token_obj.expires_at) < utcnow():
        raise HTTPException(status_code=401, detail="Refresh token expirado")

    user = db.query(User).filter(User.id == token_obj.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario inativo ou inexistente")

    token_obj.revoked_at = utcnow().isoformat()
    db.add(token_obj)

    new_refresh = create_refresh_token(db, user)
    access = create_access_token(user)

    audit_event(db, user_id=user.id, event_type="auth.refresh", resource_type="user", resource_id=str(user.id))
    db.commit()

    return {
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
    }


@app.post("/api/auth/logout")
def logout(
    body: LogoutRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if body.refresh_token:
        token_hash = hash_token(body.refresh_token)
        token_obj = (
            db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash, RefreshToken.user_id == user["id"])
            .first()
        )
        if token_obj and not token_obj.revoked_at:
            token_obj.revoked_at = utcnow().isoformat()
            db.add(token_obj)

    audit_event(db, user_id=user["id"], event_type="auth.logout", resource_type="user", resource_id=str(user["id"]))
    db.commit()
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
    }


@app.post("/api/quotes")
def create_quote(
    body: SaveQuoteRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    now = utcnow().isoformat()
    quote = Quote(
        user_id=user["id"],
        quote_name=body.quote_name.strip(),
        status="draft",
        version=1,
        total_to_client=body.payload.total_to_client,
        payload_json=json.dumps(body.payload.model_dump(), ensure_ascii=True),
        created_at=now,
        updated_at=now,
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)

    audit_event(
        db,
        user_id=user["id"],
        event_type="quote.create",
        resource_type="quote",
        resource_id=str(quote.id),
        metadata={"quote_name": quote.quote_name},
    )
    db.commit()

    return {"id": quote.id, "ok": True}


@app.get("/api/quotes")
def list_quotes(
    user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = (
        db.query(Quote)
        .filter(Quote.user_id == user["id"])
        .order_by(Quote.created_at.desc())
        .limit(100)
        .all()
    )
    out = []
    for row in rows:
        out.append(
            {
                "id": row.id,
                "quote_name": row.quote_name,
                "status": row.status,
                "version": row.version,
                "total_to_client": row.total_to_client,
                "payload": json.loads(row.payload_json),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )
    return out


@app.patch("/api/quotes/{quote_id}/status")
def update_quote_status(
    quote_id: int,
    body: UpdateQuoteStatusRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    allowed_status = {"draft", "sent", "approved", "expired", "cancelled"}
    status = body.status.strip().lower()
    if status not in allowed_status:
        raise HTTPException(status_code=400, detail="Status invalido")

    quote = db.query(Quote).filter(Quote.id == quote_id, Quote.user_id == user["id"]).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Cotacao nao encontrada")

    quote.status = status
    quote.version += 1
    quote.updated_at = utcnow().isoformat()
    db.add(quote)

    audit_event(
        db,
        user_id=user["id"],
        event_type="quote.status.update",
        resource_type="quote",
        resource_id=str(quote.id),
        metadata={"new_status": status},
    )
    db.commit()
    return {"ok": True}


@app.delete("/api/quotes/{quote_id}")
def delete_quote(
    quote_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    quote = db.query(Quote).filter(Quote.id == quote_id, Quote.user_id == user["id"]).first()
    if quote:
        db.delete(quote)
        audit_event(
            db,
            user_id=user["id"],
            event_type="quote.delete",
            resource_type="quote",
            resource_id=str(quote_id),
        )
        db.commit()
    return {"ok": True}


@app.get("/api/admin/users")
def admin_users(
    _: dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at,
        }
        for u in rows
    ]


@app.get("/api/admin/audit")
def admin_audit(
    limit: int = 100,
    _: dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 500))
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(safe_limit).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "event_type": r.event_type,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "metadata": json.loads(r.metadata_json),
            "created_at": r.created_at,
        }
        for r in rows
    ]


@app.post("/api/admin/invites")
def admin_create_invite(
    body: AdminCreateInviteRequest,
    user: dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    allowed_roles = {"consultant", "admin"}
    role = body.role.strip().lower()
    if role not in allowed_roles:
        raise HTTPException(status_code=400, detail="Role invalida")

    if role == "admin" and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Permissao insuficiente")

    email = body.email.lower().strip()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Este email ja possui usuario")

    raw_token = create_invite_token()
    invite = SignupInvite(
        email=email,
        token_hash=hash_token(raw_token),
        role=role,
        full_name=body.name.strip(),
        created_by_user_id=user["id"],
        expires_at=(utcnow() + timedelta(hours=body.expires_in_hours)).isoformat(),
        created_at=utcnow().isoformat(),
        used_at=None,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    audit_event(
        db,
        user_id=user["id"],
        event_type="auth.invite.create",
        resource_type="invite",
        resource_id=str(invite.id),
        metadata={"invitee_email": email, "role": role, "expires_at": invite.expires_at},
    )
    db.commit()

    return {
        "id": invite.id,
        "email": invite.email,
        "role": invite.role,
        "expires_at": invite.expires_at,
        "used_at": invite.used_at,
        "invite_token": raw_token,
    }


@app.get("/api/admin/invites")
def admin_list_invites(
    include_used: bool = False,
    _: dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = db.query(SignupInvite)
    if not include_used:
        query = query.filter(SignupInvite.used_at.is_(None))

    rows = query.order_by(SignupInvite.created_at.desc()).limit(200).all()
    return [
        {
            "id": row.id,
            "email": row.email,
            "role": row.role,
            "full_name": row.full_name,
            "created_by_user_id": row.created_by_user_id,
            "expires_at": row.expires_at,
            "created_at": row.created_at,
            "used_at": row.used_at,
            "is_expired": datetime.fromisoformat(row.expires_at) < utcnow(),
        }
        for row in rows
    ]


@app.delete("/api/admin/invites/{invite_id}")
def admin_revoke_invite(
    invite_id: int,
    user: dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    invite = db.query(SignupInvite).filter(SignupInvite.id == invite_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Convite nao encontrado")

    if invite.used_at:
        raise HTTPException(status_code=400, detail="Convite ja utilizado")

    db.delete(invite)
    audit_event(
        db,
        user_id=user["id"],
        event_type="auth.invite.revoke",
        resource_type="invite",
        resource_id=str(invite_id),
        metadata={"invitee_email": invite.email},
    )
    db.commit()
    return {"ok": True}


@app.post("/api/flight-options/simulate")
def simulate_options(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    origem = str(payload.get("origin", "GRU")).strip().upper()
    destino = str(payload.get("destination", "BSB")).strip().upper()
    adultos = int(payload.get("adults", 1))
    cabine = str(payload.get("cabin", "economy"))

    if len(origem) != 3 or len(destino) != 3:
        raise HTTPException(status_code=400, detail="Origem e destino devem ter 3 letras IATA")

    base = 850 + adultos * 320
    if cabine == "premium_economy":
        base *= 1.38
    if cabine == "business":
        base *= 2.60
    base += ord(origem[0]) + ord(destino[0])

    cias = ["G3", "LA", "AD", "2Z", "JJ"]
    out: list[dict[str, Any]] = []
    for i in range(5):
        conexoes = i % 3
        fator = 0.86 + i * 0.09
        preco = round(base * fator + conexoes * 120, 2)
        out.append(
            {
                "id": f"sim_{i+1}",
                "cia": cias[i],
                "voo": f"{cias[i]}{1200 + i * 37}",
                "conexoes": conexoes,
                "duracao": f"{2 + conexoes}h {15 + i * 10}m",
                "preco": preco,
                "moeda": "BRL",
            }
        )

    out.sort(key=lambda x: x["preco"])
    audit_event(
        db,
        user_id=user["id"],
        event_type="flight.simulate",
        resource_type="search",
        metadata={"origin": origem, "destination": destino, "adults": adultos, "cabin": cabine},
    )
    db.commit()
    return out
