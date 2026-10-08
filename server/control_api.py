import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from auth_utils import current_user_id
from crypto_utils import encrypt_text, decrypt_text

SUPABASE_URL = os.environ["SUPABASE_URL"].strip()
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

origins = [
    x.strip()
    for x in os.environ.get("ALLOWED_ORIGINS", "http://localhost:8080").split(",")
    if x.strip()
]

app = FastAPI(title="Promo Monitor Control API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

class RequestCodeBody(BaseModel):
    api_id: int
    api_hash: str = Field(min_length=8, max_length=256)
    phone: str = Field(min_length=6, max_length=40)

class ConfirmCodeBody(BaseModel):
    code: str = Field(min_length=2, max_length=20)

class Confirm2FABody(BaseModel):
    password: str = Field(min_length=1, max_length=256)

def hint(phone):
    digits = "".join(c for c in phone if c.isdigit())
    return "••••" if len(digits) <= 4 else f"••••{digits[-4:]}"

def set_status(user_id, status, phone_hint=None, error=None):
    payload = {
        "user_id": user_id,
        "status": status,
        "last_error": error,
    }
    if phone_hint is not None:
        payload["phone_hint"] = phone_hint
    db.table("tg_telegram_status").upsert(payload).execute()

def get_private(user_id):
    return (
        db.table("tg_telegram_private")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data
    )

@app.get("/health")
async def health():
    return {"ok": True, "version": "2.0.0"}

@app.get("/telegram/status")
async def telegram_status(user_id: str = Depends(current_user_id)):
    data = (
        db.table("tg_telegram_status")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data
    )
    return data or {"user_id": user_id, "status": "not_configured"}

@app.post("/telegram/request-code")
async def request_code(body: RequestCodeBody, user_id: str = Depends(current_user_id)):
    client = TelegramClient(StringSession(), body.api_id, body.api_hash.strip())
    try:
        await client.connect()
        sent = await client.send_code_request(body.phone.strip())

        db.table("tg_telegram_private").upsert({
            "user_id": user_id,
            "api_id": body.api_id,
            "api_hash_enc": encrypt_text(body.api_hash.strip()),
            "phone_enc": encrypt_text(body.phone.strip()),
            "pending_session_enc": encrypt_text(client.session.save()),
            "session_enc": None,
            "phone_code_hash_enc": encrypt_text(sent.phone_code_hash),
        }).execute()

        set_status(user_id, "code_sent", hint(body.phone), None)
        return {"ok": True, "status": "code_sent", "phone_hint": hint(body.phone)}
    except Exception as exc:
        set_status(user_id, "error", error=str(exc)[:1000])
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        await client.disconnect()

@app.post("/telegram/confirm-code")
async def confirm_code(body: ConfirmCodeBody, user_id: str = Depends(current_user_id)):
    row = get_private(user_id)
    if not row:
        raise HTTPException(status_code=400, detail="Configuração Telegram não encontrada.")

    api_hash = decrypt_text(row["api_hash_enc"])
    phone = decrypt_text(row["phone_enc"])
    pending = decrypt_text(row["pending_session_enc"])
    phone_code_hash = decrypt_text(row["phone_code_hash_enc"])
    if not all([api_hash, phone, pending, phone_code_hash]):
        raise HTTPException(status_code=400, detail="Fluxo expirado. Envie novo código.")

    client = TelegramClient(StringSession(pending), int(row["api_id"]), api_hash)
    try:
        await client.connect()
        try:
            await client.sign_in(
                phone=phone,
                code=body.code.strip(),
                phone_code_hash=phone_code_hash,
            )
        except SessionPasswordNeededError:
            db.table("tg_telegram_private").update({
                "pending_session_enc": encrypt_text(client.session.save())
            }).eq("user_id", user_id).execute()
            set_status(user_id, "2fa_required", hint(phone), None)
            return {"ok": True, "status": "2fa_required"}

        if not await client.is_user_authorized():
            raise RuntimeError("Telegram não autorizou a sessão.")

        db.table("tg_telegram_private").update({
            "session_enc": encrypt_text(client.session.save()),
            "pending_session_enc": None,
            "phone_code_hash_enc": None,
        }).eq("user_id", user_id).execute()

        set_status(user_id, "connected", hint(phone), None)
        return {"ok": True, "status": "connected"}
    except Exception as exc:
        set_status(user_id, "error", hint(phone), str(exc)[:1000])
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        await client.disconnect()

@app.post("/telegram/confirm-2fa")
async def confirm_2fa(body: Confirm2FABody, user_id: str = Depends(current_user_id)):
    row = get_private(user_id)
    if not row:
        raise HTTPException(status_code=400, detail="Configuração Telegram não encontrada.")

    api_hash = decrypt_text(row["api_hash_enc"])
    phone = decrypt_text(row["phone_enc"])
    pending = decrypt_text(row["pending_session_enc"])
    if not all([api_hash, phone, pending]):
        raise HTTPException(status_code=400, detail="Fluxo expirado.")

    client = TelegramClient(StringSession(pending), int(row["api_id"]), api_hash)
    try:
        await client.connect()
        await client.sign_in(password=body.password)
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram não autorizou a sessão.")

        db.table("tg_telegram_private").update({
            "session_enc": encrypt_text(client.session.save()),
            "pending_session_enc": None,
            "phone_code_hash_enc": None,
        }).eq("user_id", user_id).execute()

        set_status(user_id, "connected", hint(phone), None)
        return {"ok": True, "status": "connected"}
    except Exception as exc:
        set_status(user_id, "error", hint(phone), str(exc)[:1000])
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        await client.disconnect()

@app.post("/telegram/disconnect")
async def disconnect_telegram(user_id: str = Depends(current_user_id)):
    db.table("tg_telegram_private").delete().eq("user_id", user_id).execute()
    set_status(user_id, "disconnected", None, None)
    db.table("tg_worker_status").upsert({
        "user_id": user_id,
        "state": "offline"
    }).execute()
    return {"ok": True, "status": "disconnected"}
