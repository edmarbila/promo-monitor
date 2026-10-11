import asyncio
import hashlib
import re
import unicodedata

import httpx


NTFY_BASE_URL = "https://ntfy.sh"


def _safe_topic(topic):
    value = str(topic or "").strip()
    if not value:
        return ""
    if not re.fullmatch(r"[-_A-Za-z0-9]{1,64}", value):
        raise ValueError("Tópico ntfy inválido.")
    return value


def _normalize_text(value):
    text = str(value or "").casefold()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _slug(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "loja"


def product_dedupe_key(keyword, message):
    normalized = _normalize_text(message)
    raw = f"product|{str(keyword or '').casefold().strip()}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def coupon_dedupe_key(store_name, code):
    store = re.sub(r"\s+", " ", str(store_name or "").casefold()).strip()
    raw = f"coupon|{store}|{str(code or '').upper().strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def release_notification(db, user_id, dedupe_key):
    await asyncio.to_thread(
        lambda: db.table("tg_notification_log")
        .delete()
        .eq("user_id", user_id)
        .eq("dedupe_key", dedupe_key)
        .execute()
    )


async def claim_notification(db, user_id, dedupe_key, kind, topic, ttl_hours):
    topic = _safe_topic(topic)
    response = await asyncio.to_thread(
        lambda: db.rpc(
            "tg_claim_notification",
            {
                "p_user_id": user_id,
                "p_dedupe_key": dedupe_key,
                "p_kind": kind,
                "p_topic": topic,
                "p_ttl_hours": int(ttl_hours),
            },
        ).execute()
    )
    data = response.data
    if isinstance(data, bool):
        return data
    if isinstance(data, list) and data:
        if isinstance(data[0], bool):
            return data[0]
        if isinstance(data[0], dict):
            value = next(iter(data[0].values()), False)
            return bool(value)
    return bool(data)


async def publish_ntfy(topic, title, message, priority=5, tags=None):
    topic = _safe_topic(topic)
    if not topic:
        return

    priority = min(5, max(1, int(priority or 5)))
    headers = {
        "Title": str(title or "Promo Monitor")[:200],
        "Priority": str(priority),
        "Content-Type": "text/plain; charset=utf-8",
    }
    if tags:
        headers["Tags"] = str(tags)

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
        response = await http.post(
            f"{NTFY_BASE_URL}/{topic}",
            content=str(message or "").encode("utf-8"),
            headers=headers,
        )
        response.raise_for_status()
