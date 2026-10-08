import asyncio
import httpx
import os
from datetime import datetime, timezone

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
from coupon_sources import fetch_store_coupons, coupon_key

SUPABASE_URL = os.environ["SUPABASE_URL"].strip()
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

origins = [
    x.strip()
    for x in os.environ.get("ALLOWED_ORIGINS", "http://localhost:8080").split(",")
    if x.strip()
]

app = FastAPI(title="Promo Monitor Control API", version="2.2.0")
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

class ScanStoreBody(BaseModel):
    store_id: int

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
    return {"ok": True, "version": "2.2.0"}

@app.post("/coupons/scan")
async def scan_store_coupons(body: ScanStoreBody, user_id: str = Depends(current_user_id)):
    site = (
        db.table("tg_coupon_sites")
        .select("*")
        .eq("id", body.store_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data
    )
    if not site:
        raise HTTPException(status_code=404, detail="Loja não encontrada.")

    sources = site.get("sources") or ["meliuz", "cuponeria", "picodi", "promobit"]
    sources = list(dict.fromkeys(sources))
    now = datetime.now(timezone.utc).isoformat()

    async def scan_source(source):
        try:
            results = await fetch_store_coupons(
                source=source,
                store_name=site["store_name"],
                store_slug=site["store_slug"],
                timeout=float(os.environ.get("COUPON_HTTP_TIMEOUT", "20")),
            )

            db.table("tg_coupons").update({"active": False}) \
                .eq("user_id", user_id) \
                .eq("source", source) \
                .eq("store_name", site["store_name"]) \
                .execute()

            saved = 0
            for item in results:
                if not item.code:
                    continue
                payload = {
                    "user_id": user_id,
                    "coupon_key": coupon_key(item.source, item.store_name, item.title, item.code),
                    "source": item.source,
                    "store_name": item.store_name,
                    "title": item.title,
                    "code": item.code,
                    "discount_text": item.discount_text,
                    "details": item.details,
                    "source_url": item.source_url,
                    "active": True,
                    "last_seen_at": now,
                }
                db.table("tg_coupons").upsert(
                    payload, on_conflict="user_id,coupon_key"
                ).execute()
                saved += 1

            return {"source": source, "saved": saved, "error": None}
        except Exception as exc:
            return {"source": source, "saved": 0, "error": str(exc)[:500]}

    results = await asyncio.gather(*(scan_source(source) for source in sources))
    total = sum(item["saved"] for item in results)
    return {
        "ok": True,
        "store": site["store_name"],
        "total": total,
        "sources": results,
    }


@app.post("/alerts/ntfy/test")
async def test_ntfy_alert(user_id: str = Depends(current_user_id)):
    settings = (
        db.table("tg_alert_settings")
        .select("provider,ntfy_topic,ntfy_priority")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data
    )
    if not settings or settings.get("provider") != "ntfy":
        raise HTTPException(status_code=400, detail="Ative o ntfy antes de testar.")

    topic = str(settings.get("ntfy_topic") or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Tópico ntfy não configurado.")

    priority = min(5, max(1, int(settings.get("ntfy_priority") or 5)))

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
            response = await http.post(
                f"https://ntfy.sh/{topic}",
                content="Teste do Promo Monitor. Se esta mensagem chegou, os alertas ntfy estão configurados.".encode("utf-8"),
                headers={
                    "Title": "Promo Monitor - Teste",
                    "Priority": str(priority),
                    "Tags": "white_check_mark",
                    "Content-Type": "text/plain; charset=utf-8",
                },
            )
            response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao enviar para ntfy: {exc}")

    return {"ok": True, "topic": topic}


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
