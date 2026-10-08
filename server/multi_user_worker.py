import asyncio
import hashlib
import httpx
import os
import re
import traceback
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
from telethon import TelegramClient, events, utils
from telethon.sessions import StringSession

from crypto_utils import decrypt_text
from coupon_sources import fetch_store_coupons, coupon_key

VERSION = "2.2.0"
CONFIG_REFRESH_SECONDS = 10
ACCOUNT_SYNC_SECONDS = 20
GROUP_REQUEST_SECONDS = 5
HEARTBEAT_SECONDS = 20
COUPON_SCAN_MINUTES = int(os.environ.get("COUPON_SCAN_MINUTES", "30"))
COUPON_HTTP_TIMEOUT = float(os.environ.get("COUPON_HTTP_TIMEOUT", "20"))

db = create_client(
    os.environ["SUPABASE_URL"].strip(),
    os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip(),
)

running_tasks = {}

async def send_ntfy(settings, keyword, group_name, sender_name, message, message_link=""):
    if not settings or settings.get("provider") != "ntfy":
        return

    topic = str(settings.get("ntfy_topic") or "").strip()
    if not topic:
        return

    priority = int(settings.get("ntfy_priority") or 5)
    priority = min(5, max(1, priority))

    body = (
        f"Palavra: {keyword}\n"
        f"Grupo: {group_name}\n"
        f"Usuario: {sender_name}\n\n"
        f"{message}"
    )
    if message_link:
        body += f"\n\nAbrir mensagem: {message_link}"

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
        response = await http.post(
            f"https://ntfy.sh/{topic}",
            content=body.encode("utf-8"),
            headers={
                "Title": "Promo Monitor - Alerta",
                "Priority": str(priority),
                "Tags": "rotating_light",
                "Content-Type": "text/plain; charset=utf-8",
            },
        )
        response.raise_for_status()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def event_group_candidates(event):
    result = set()
    if event.chat_id is not None:
        result.add(int(event.chat_id))

    chat = getattr(event, "chat", None)
    if chat is not None and getattr(chat, "id", None) is not None:
        result.add(int(chat.id))
        try:
            result.add(int(utils.get_peer_id(chat)))
        except Exception:
            pass

    extra = set()
    for gid in result:
        text = str(gid)
        if text.startswith("-100") and len(text) > 4:
            try:
                extra.add(int(text[4:]))
            except ValueError:
                pass
        elif gid > 0:
            try:
                extra.add(int(f"-100{gid}"))
            except ValueError:
                pass
    return result | extra

def detect_coupon(text):
    low = text.casefold()
    if not any(w in low for w in ("cupom","código","codigo","voucher","off","desconto")):
        return False, None, None

    code = None
    blocked = {
        "CUPOM","CODIGO","CÓDIGO","VOUCHER","DESCONTO",
        "PROMOCAO","PROMOÇÃO","GRUPO","TELEGRAM"
    }
    for item in re.findall(r"\b[A-Z0-9][A-Z0-9_-]{3,24}\b", text.upper()):
        if item in blocked:
            continue
        if any(c.isalpha() for c in item) and any(c.isdigit() for c in item):
            code = item
            break

    discount = None
    m = re.search(
        r"(\d{1,3}\s*%\s*(?:OFF|de desconto)?|R\$\s*\d+(?:[.,]\d{1,2})?\s*(?:OFF|de desconto)?)",
        text,
        re.I,
    )
    if m:
        discount = m.group(1).strip()

    return True, code, discount

async def set_worker_status(user_id, state, groups=0, keywords=0, error=None):
    await asyncio.to_thread(
        lambda: db.table("tg_worker_status").upsert({
            "user_id": user_id,
            "state": state,
            "last_heartbeat": now_iso(),
            "groups_active": groups,
            "keywords_active": keywords,
            "last_error": error,
            "version": VERSION,
            "updated_at": now_iso(),
        }).execute()
    )

async def set_telegram_status(user_id, status, error=None):
    await asyncio.to_thread(
        lambda: db.table("tg_telegram_status").upsert({
            "user_id": user_id,
            "status": status,
            "last_error": error,
        }).execute()
    )

async def save_telegram_coupon(user_id, group_name, message, code, discount, url):
    title = " ".join((message.strip().splitlines() or ["Cupom Telegram"])[0].split())
    title = title[:350] or "Cupom encontrado no Telegram"
    raw = f"telegram|{group_name.casefold()}|{title.casefold()}|{code or ''}|{url or ''}"
    key = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    await asyncio.to_thread(
        lambda: db.table("tg_coupons").upsert({
            "user_id": user_id,
            "coupon_key": key,
            "source": "telegram",
            "store_name": group_name,
            "title": title,
            "code": code,
            "discount_text": discount,
            "details": message[:3000],
            "source_url": url,
            "source_group": group_name,
            "active": True,
            "last_seen_at": now_iso(),
        }, on_conflict="user_id,coupon_key").execute()
    )

async def resolve_group_requests(user_id, client):
    response = await asyncio.to_thread(
        lambda: db.table("tg_group_requests")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .order("id")
        .limit(20)
        .execute()
    )

    for row in response.data or []:
        request_id = row["id"]
        identifier = str(row.get("identifier", "")).strip()
        try:
            await asyncio.to_thread(
                lambda: db.table("tg_group_requests")
                .update({"status":"processing","error_message":None})
                .eq("id", request_id)
                .execute()
            )

            target = int(identifier) if identifier.lstrip("-").isdigit() else identifier
            entity = await client.get_entity(target)
            canonical_id = int(utils.get_peer_id(entity))
            name = getattr(entity, "title", None) or identifier
            username = (getattr(entity, "username", "") or "").lstrip("@")

            await asyncio.to_thread(
                lambda: db.table("tg_groups").upsert({
                    "user_id": user_id,
                    "telegram_group_id": canonical_id,
                    "name": name,
                    "username": username,
                    "active": True,
                }, on_conflict="user_id,telegram_group_id").execute()
            )

            await asyncio.to_thread(
                lambda: db.table("tg_group_requests")
                .update({"status":"resolved","processed_at":now_iso(),"error_message":None})
                .eq("id", request_id)
                .execute()
            )
        except Exception as exc:
            await asyncio.to_thread(
                lambda exc=exc: db.table("tg_group_requests")
                .update({"status":"error","processed_at":now_iso(),"error_message":str(exc)[:1000]})
                .eq("id", request_id)
                .execute()
            )

async def user_monitor_loop(account):
    user_id = account["user_id"]
    api_id = int(account["api_id"])
    api_hash = decrypt_text(account["api_hash_enc"])
    session_string = decrypt_text(account["session_enc"])

    if not api_hash or not session_string:
        await set_telegram_status(user_id, "error", "Credenciais/sessão incompletas.")
        return

    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    config = {"groups": set(), "keywords": [], "alerts": {"provider":"none"}}
    last_error = None

    async def refresh_config():
        groups_resp, keywords_resp, alerts_resp = await asyncio.gather(
            asyncio.to_thread(
                lambda: db.table("tg_groups")
                .select("telegram_group_id")
                .eq("user_id", user_id)
                .eq("active", True)
                .execute()
            ),
            asyncio.to_thread(
                lambda: db.table("tg_keywords")
                .select("word")
                .eq("user_id", user_id)
                .eq("active", True)
                .execute()
            ),
            asyncio.to_thread(
                lambda: db.table("tg_alert_settings")
                .select("provider,ntfy_topic,ntfy_priority")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            ),
        )

        config["groups"] = {
            int(row["telegram_group_id"])
            for row in (groups_resp.data or [])
            if row.get("telegram_group_id") is not None
        }
        words = [
            str(row.get("word","")).strip()
            for row in (keywords_resp.data or [])
            if str(row.get("word","")).strip()
        ]
        config["keywords"] = sorted(words, key=lambda x: (-len(x), x.casefold()))
        config["alerts"] = alerts_resp.data or {"provider":"none"}

    async def config_loop():
        nonlocal last_error
        while True:
            try:
                await refresh_config()
            except Exception as exc:
                last_error = f"config: {exc}"
            await asyncio.sleep(CONFIG_REFRESH_SECONDS)

    async def request_loop():
        nonlocal last_error
        while True:
            try:
                await resolve_group_requests(user_id, client)
            except Exception as exc:
                last_error = f"group_requests: {exc}"
            await asyncio.sleep(GROUP_REQUEST_SECONDS)

    async def heartbeat_loop():
        while True:
            await set_worker_status(
                user_id,
                "online",
                groups=len(config["groups"]),
                keywords=len(config["keywords"]),
                error=last_error,
            )
            await asyncio.sleep(HEARTBEAT_SECONDS)

    @client.on(events.NewMessage())
    async def on_message(event):
        nonlocal last_error
        try:
            if not config["groups"] or not config["keywords"]:
                return
            if not (event_group_candidates(event) & config["groups"]):
                return

            text = event.raw_text or ""
            if not text.strip():
                return

            folded = text.casefold()
            found = next((w for w in config["keywords"] if w.casefold() in folded), None)
            if not found:
                return

            chat = await event.get_chat()
            sender = await event.get_sender()
            group_name = getattr(chat, "title", None) or str(event.chat_id)
            username = (getattr(chat, "username", "") or "").lstrip("@")

            first = (getattr(sender, "first_name", "") or "") if sender else ""
            last = (getattr(sender, "last_name", "") or "") if sender else ""
            sender_name = f"{first} {last}".strip() or "Desconhecido"

            message_link = ""
            if username:
                message_link = f"https://t.me/{username}/{event.id}"
            else:
                try:
                    peer = str(utils.get_peer_id(chat))
                    if peer.startswith("-100"):
                        message_link = f"https://t.me/c/{peer[4:]}/{event.id}"
                except Exception:
                    pass

            is_coupon, code, discount = detect_coupon(text)

            await asyncio.to_thread(
                lambda: db.table("tg_occurrences").upsert({
                    "user_id": user_id,
                    "occurred_at": now_iso(),
                    "telegram_date": (
                        event.message.date.astimezone(timezone.utc).isoformat()
                        if event.message.date else None
                    ),
                    "telegram_group_id": int(event.chat_id) if event.chat_id is not None else None,
                    "group_name": group_name,
                    "username": username,
                    "sender": sender_name,
                    "keyword": found,
                    "message": text,
                    "message_id": int(event.id),
                    "message_link": message_link,
                    "is_coupon": is_coupon,
                }, on_conflict="user_id,telegram_group_id,message_id,keyword").execute()
            )

            if is_coupon:
                await save_telegram_coupon(
                    user_id, group_name, text, code, discount, message_link
                )

            try:
                await send_ntfy(
                    config.get("alerts"),
                    found,
                    group_name,
                    sender_name,
                    text,
                    message_link,
                )
            except Exception as exc:
                last_error = f"ntfy: {exc}"
                print(f"[NTFY] {user_id}: {exc}", flush=True)
        except Exception as exc:
            last_error = f"message: {exc}"
            traceback.print_exc()

    tasks = []
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await set_telegram_status(user_id, "error", "Sessão Telegram perdeu autorização.")
            await set_worker_status(user_id, "offline", error="Sessão não autorizada.")
            return

        await set_telegram_status(user_id, "connected", None)
        await refresh_config()
        tasks = [
            asyncio.create_task(config_loop()),
            asyncio.create_task(request_loop()),
            asyncio.create_task(heartbeat_loop()),
        ]
        await client.run_until_disconnected()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await set_worker_status(user_id, "offline", error=str(exc)[:1000])
        traceback.print_exc()
    finally:
        for task in tasks:
            task.cancel()
        try:
            await client.disconnect()
        except Exception:
            pass

async def account_supervisor():
    while True:
        response = await asyncio.to_thread(
            lambda: db.table("tg_telegram_private")
            .select("user_id,api_id,api_hash_enc,session_enc,updated_at")
            .not_.is_("session_enc", "null")
            .execute()
        )
        accounts = {row["user_id"]: row for row in (response.data or [])}

        for user_id in list(running_tasks):
            if user_id not in accounts:
                running_tasks[user_id].cancel()
                del running_tasks[user_id]

        for user_id, account in accounts.items():
            task = running_tasks.get(user_id)
            if task is None or task.done():
                running_tasks[user_id] = asyncio.create_task(user_monitor_loop(account))

        await asyncio.sleep(ACCOUNT_SYNC_SECONDS)

async def coupon_scan_once():
    response = await asyncio.to_thread(
        lambda: db.table("tg_coupon_sites").select("*").eq("active", True).execute()
    )

    for site in response.data or []:
        sources = site.get("sources") or ["meliuz","cuponeria","picodi","promobit"]
        for source in sources:
            try:
                results = await fetch_store_coupons(
                    source=source,
                    store_name=site["store_name"],
                    store_slug=site["store_slug"],
                    timeout=COUPON_HTTP_TIMEOUT,
                )
                # Só mantém ativos os cupons que a fonte confirmou nesta varredura.
                await asyncio.to_thread(
                    lambda site=site, source=source: db.table("tg_coupons")
                    .update({"active": False})
                    .eq("user_id", site["user_id"])
                    .eq("source", source)
                    .eq("store_name", site["store_name"])
                    .execute()
                )

                for item in results:
                    if not item.code:
                        continue
                    payload = {
                        "user_id": site["user_id"],
                        "coupon_key": coupon_key(item.source,item.store_name,item.title,item.code),
                        "source": item.source,
                        "store_name": item.store_name,
                        "title": item.title,
                        "code": item.code,
                        "discount_text": item.discount_text,
                        "details": item.details,
                        "source_url": item.source_url,
                        "active": True,
                        "last_seen_at": now_iso(),
                    }
                    await asyncio.to_thread(
                        lambda payload=payload: db.table("tg_coupons")
                        .upsert(payload, on_conflict="user_id,coupon_key")
                        .execute()
                    )
            except Exception as exc:
                print(f"[CUPOM] {site['store_name']} / {source}: {exc}", flush=True)

async def coupon_loop():
    while True:
        try:
            await coupon_scan_once()
            await asyncio.to_thread(lambda: db.rpc("tg_cleanup_old_data").execute())
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(max(5, COUPON_SCAN_MINUTES) * 60)

async def main():
    print("Promo Monitor V2 iniciado.", flush=True)
    await asyncio.gather(account_supervisor(), coupon_loop())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
