import hashlib
import re
import unicodedata
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

@dataclass
class CouponResult:
    source: str
    store_name: str
    title: str
    code: str | None
    discount_text: str | None
    details: str | None
    source_url: str

def slugify(value):
    normalized = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

def coupon_key(source, store, title, code):
    raw = "|".join([
        source.strip().lower(),
        store.strip().casefold(),
        title.strip().casefold(),
        (code or "").strip().upper(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _discount(text):
    for pattern in [
        r"\b\d{1,3}\s*%\s*(?:OFF|de desconto)?\b",
        r"\bR\$\s*\d+(?:[.,]\d{1,2})?\s*(?:OFF|de desconto)?\b",
        r"\bfrete\s+gr[aá]tis\b",
        r"\bcashback\b",
    ]:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(0).strip()
    return None

def _likely_code(text):
    blocked = {
        "CUPOM","DESCONTO","CASHBACK","OFERTA","OFF","BRASIL",
        "PRIMEIRA","COMPRA","SITE","APP","MELIUZ","CUPONERIA","REGRAS"
    }
    for item in re.findall(r"\b[A-Z0-9][A-Z0-9_-]{3,24}\b", text.upper()):
        if item in blocked:
            continue
        if any(c.isdigit() for c in item) and any(c.isalpha() for c in item):
            return item
    return None

def _extract(source, store_name, url, html):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    for heading in soup.find_all(["h2","h3","h4"]):
        title = " ".join(heading.get_text(" ", strip=True).split())
        low = title.casefold()
        if len(title) < 6:
            continue
        if not any(x in low for x in ["cupom","desconto","off","frete grátis","cashback"]):
            continue
        if low.startswith("como ") or "perguntas frequentes" in low:
            continue
        if low in seen:
            continue
        seen.add(low)

        blob = " ".join(heading.parent.get_text(" ", strip=True).split())[:1400]
        results.append(CouponResult(
            source=source,
            store_name=store_name,
            title=title[:400],
            code=_likely_code(blob),
            discount_text=_discount(blob),
            details=blob[:1000],
            source_url=url,
        ))
        if len(results) >= 50:
            break
    return results

async def fetch_store_coupons(source, store_name, store_slug, timeout=20):
    slug = slugify(store_slug or store_name)
    if source == "meliuz":
        url = f"https://www.meliuz.com.br/cupom/{slug}"
    elif source == "cuponeria":
        url = f"https://www.cuponeria.com.br/cupom-desconto/{slug}"
    else:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PromoMonitor/2.0)",
        "Accept-Language": "pt-BR,pt;q=0.9",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()

    return _extract(source, store_name, str(response.url), response.text)
