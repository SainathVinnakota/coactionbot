import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional

import psycopg2
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

security = HTTPBearer(auto_error=False)
ALLOWED_ROLES = {"agent", "underwriter", "external"}


@dataclass
class AuthUser:
    user_id: int
    name: str
    email: str
    role: str


def _db_connect():
    sslmode = os.getenv("DB_SSL_MODE", "require")
    sslrootcert = os.getenv("DB_SSL_ROOT_CERT", "")
    connect_kwargs = {
        "host": settings.db_host,
        "database": settings.db_name,
        "user": settings.db_user,
        "password": settings.db_password,
        "port": settings.db_port,
        "sslmode": sslmode,
    }

    # Only pass sslrootcert when the configured file is actually available.
    if sslrootcert and os.path.exists(sslrootcert):
        connect_kwargs["sslrootcert"] = sslrootcert
    elif sslmode == "verify-full":
        logger.warning("db_ssl_root_cert_missing_fallback", sslrootcert=sslrootcert)
        connect_kwargs["sslmode"] = "require"

    return psycopg2.connect(**connect_kwargs)


def init_auth_table() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS app_users (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('agent', 'underwriter', 'external')),
        password_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    trigger_sql = """
    CREATE OR REPLACE FUNCTION touch_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    trig_bind_sql = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = 'app_users_touch_updated_at'
        ) THEN
            CREATE TRIGGER app_users_touch_updated_at
            BEFORE UPDATE ON app_users
            FOR EACH ROW
            EXECUTE FUNCTION touch_updated_at_column();
        END IF;
    END $$;
    """
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(trigger_sql)
            cur.execute(trig_bind_sql)
        conn.commit()
    logger.info("auth_table_ready")


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    iterations = 120000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64url(salt)}${_b64url(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iters, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iters)
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _jwt_secret() -> str:
    secret = settings.jwt_secret_key
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is required")
    return secret


def create_access_token(user: AuthUser) -> str:
    now = int(time.time())
    exp = now + (settings.jwt_access_token_exp_minutes * 60)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user.user_id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "iat": now,
        "exp": exp,
    }
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    sig = hmac.new(_jwt_secret().encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(sig)}"


def decode_access_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    head, body, sig = parts
    signing_input = f"{head}.{body}"
    expected = hmac.new(_jwt_secret().encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64url_decode(sig)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")
    payload = json.loads(_b64url_decode(body).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    return payload


def create_user(name: str, email: str, password: str, role: str) -> None:
    clean_role = (role or "").strip().lower()
    if clean_role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    clean_name = (name or "").strip()
    clean_email = _normalize_email(email)
    if not clean_name or not clean_email:
        raise HTTPException(status_code=400, detail="Name and email are required")
    if "@" not in clean_email:
        raise HTTPException(status_code=400, detail="Invalid email")
    pwd_hash = hash_password(password)
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_users (name, email, role, password_hash)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                (clean_name, clean_email, clean_role, pwd_hash),
            )
            created = cur.rowcount == 1
        conn.commit()
    if not created:
        raise HTTPException(status_code=409, detail="Email already exists")


def get_user_by_email(email: str) -> Optional[AuthUser]:
    clean_email = _normalize_email(email)
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, email, role FROM app_users WHERE email = %s",
                (clean_email,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return AuthUser(user_id=row[0], name=row[1], email=row[2], role=row[3])


def authenticate_user(email: str, password: str) -> Optional[AuthUser]:
    clean_email = _normalize_email(email)
    if "@" not in clean_email:
        return None
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, email, role, password_hash FROM app_users WHERE email = %s",
                (clean_email,),
            )
            row = cur.fetchone()
    if not row:
        return None
    if not verify_password(password, row[4]):
        return None
    return AuthUser(user_id=row[0], name=row[1], email=row[2], role=row[3])


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> AuthUser:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    payload = decode_access_token(creds.credentials)
    role = payload.get("role", "")
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid role in token")
    return AuthUser(
        user_id=int(payload["sub"]),
        name=payload.get("name", ""),
        email=payload.get("email", ""),
        role=role,
    )
