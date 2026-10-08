from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag


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
    normalized_code = (code or "").strip().upper()
    identity = f"code:{normalized_code}" if normalized_code else f"title:{title.strip().casefold()}"
    raw = "|".join([
        source.strip().lower(),
        store.strip().casefold(),
        identity,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clean(value):
    return " ".join(str(value or "").split()).strip()


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


_CODE_BLOCKED = {
    "CUPOM", "CUPONS", "CODIGO", "CÓDIGO", "DESCONTO", "CASHBACK",
    "OFERTA", "OFERTAS", "OFF", "BRASIL", "PRIMEIRA", "COMPRA",
    "SITE", "APP", "MELIUZ", "CUPONERIA", "REGRAS", "EXCLUSIVO",
    "VER", "COPIAR", "LOJA", "PROMOCAO", "PROMOÇÃO",
    "TRUE", "FALSE", "NULL", "NONE", "ACTIVE", "INACTIVE", "EXPIRED",
}


def _valid_code(value):
    value = _clean(value).upper().strip(" .,:;()[]{}")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,39}", value):
        return None
    if value in _CODE_BLOCKED:
        return None
    return value


def _explicit_code(text):
    text = _clean(text)
    patterns = [
        r"\b([A-Z0-9][A-Z0-9_-]{2,39})\s+(?:VER|COPIAR)\s+CUPOM\b",
        r"\b(?:VER|COPIAR)\s+CUPOM\s+([A-Z0-9][A-Z0-9_-]{2,39})\b",
        r"\b(?:CÓDIGO|CODIGO)\s*[:\-]\s*([A-Z0-9][A-Z0-9_-]{2,39})\b",
    ]
    upper = text.upper()
    for pattern in patterns:
        m = re.search(pattern, upper, re.I)
        if m:
            code = _valid_code(m.group(1))
            if code:
                return code
    return None


def _code_from_attrs(heading):
    node = heading
    for _ in range(5):
        if node is None or not isinstance(node, Tag):
            break

        candidates = [node]
        try:
            candidates.extend(node.find_all(True, limit=80))
        except Exception:
            pass

        for tag in candidates:
            for key, raw_value in (tag.attrs or {}).items():
                low_key = str(key).lower()
                if any(x in low_key for x in ("id", "url", "href", "class", "style")):
                    continue
                if not any(x in low_key for x in ("code", "codigo", "cupom", "coupon", "clipboard")):
                    continue

                values = raw_value if isinstance(raw_value, (list, tuple)) else [raw_value]
                for value in values:
                    code = _valid_code(value)
                    if code:
                        return code

        html = str(node)
        for pattern in [
            r'(?i)(?:coupon[_-]?code|couponcode|codigo|código|cupom)["\'\s:=_-]+["\']([A-Z0-9][A-Z0-9_-]{2,39})["\']',
            r'(?i)data-(?:code|codigo|coupon-code|cupom)=["\']([A-Z0-9][A-Z0-9_-]{2,39})["\']',
        ]:
            m = re.search(pattern, html)
            if m:
                code = _valid_code(m.group(1))
                if code:
                    return code

        node = node.parent

    return None


def _section_text(heading, max_chars=2200):
    parts = []
    seen = set()

    for node in heading.next_elements:
        if isinstance(node, Tag) and node is not heading and node.name in {"h2", "h3", "h4"}:
            break
        if not isinstance(node, NavigableString):
            continue

        value = _clean(node)
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        parts.append(value)

        if sum(len(x) + 1 for x in parts) >= max_chars:
            break

    return _clean(" ".join(parts))[:max_chars]


def _description(section, title, code):
    text = _clean(section)
    if not text:
        return None

    if title:
        text = re.sub(re.escape(title), " ", text, count=1, flags=re.I)
    if code:
        text = re.sub(rf"\b{re.escape(code)}\b", " ", text, flags=re.I)

    text = re.sub(r"\b(?:ver|copiar)\s+cupom\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:ver|aproveitar)\s+oferta\b", " ", text, flags=re.I)
    text = re.sub(r"\b\d+\s+cupons?\s+pegos\b", " ", text, flags=re.I)
    text = re.sub(r"\bEXCLUSIVO\b", " ", text, flags=re.I)
    text = re.sub(r"\bREGRAS?\b", " ", text, flags=re.I)
    text = re.sub(
        r"\+?\s*até\s*\d+(?:[.,]\d+)?%\s*(?:de\s*)?cashback(?:\s*\.\s*era\s*\d+(?:[.,]\d+)?%)?",
        " ",
        text,
        flags=re.I,
    )
    text = _clean(text).strip(" -–—•|.:;")

    if len(text) < 10:
        return None
    return text[:1000]


def _embedded_codes(html):
    found = []
    seen = set()
    patterns = [
        r'(?i)["\'](?:coupon[_-]?code|couponcode|coupon_code|cupom|codigo|código)["\']\s*:\s*["\']([A-Z0-9][A-Z0-9_-]{2,39})["\']',
        r'(?i)data-(?:coupon-code|coupon_code|cupom|codigo|code)=["\']([A-Z0-9][A-Z0-9_-]{2,39})["\']',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, html):
            code = _valid_code(match.group(1))
            if code and code not in seen:
                seen.add(code)
                found.append(code)
    return found


def _source_urls(source, slug):
    if source == "meliuz":
        return [
            f"https://www.meliuz.com.br/desconto/cupom-{slug}",
            f"https://www.meliuz.com.br/desconto/cupom-desconto-{slug}",
            f"https://www.meliuz.com.br/desconto/{slug}",
        ]
    if source == "cuponeria":
        return [
            f"https://www.cuponeria.com.br/cupom-desconto/{slug}",
            f"https://www.cuponeria.com.br/cupom/{slug}",
        ]
    if source == "picodi":
        return [f"https://www.picodi.com/br/{slug}"]
    if source == "promobit":
        return [f"https://www.promobit.com.br/cupons/loja/{slug}/"]
    return []


def _extract(source, store_name, url, html):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_codes = set()
    expired_section = False

    for heading in soup.find_all(["h2", "h3", "h4"]):
        title = _clean(heading.get_text(" ", strip=True))
        low = title.casefold()

        if "expirad" in low:
            expired_section = True
            continue
        if expired_section:
            continue

        if len(title) < 4:
            continue

        section = _section_text(heading)
        code = _explicit_code(section) or _code_from_attrs(heading)

        # Fontes externas entram na central apenas quando existe um código real.
        if not code:
            continue
        if code in seen_codes:
            continue
        seen_codes.add(code)

        combined = _clean(f"{title} {section}")
        details = _description(section, title, code)
        discount = _discount(combined)
        display_title = title if details else f"Cupom {store_name}"

        results.append(CouponResult(
            source=source,
            store_name=store_name,
            title=display_title[:400],
            code=code,
            discount_text=discount,
            details=details,
            source_url=url,
        ))

        if len(results) >= 80:
            break

    # Algumas fontes mantêm o código em JSON/data-attributes e só o revelam
    # visualmente ao clicar em "Ver/Pegar cupom".
    for code in _embedded_codes(html):
        if code in seen_codes:
            continue
        seen_codes.add(code)
        results.append(CouponResult(
            source=source,
            store_name=store_name,
            title=f"Cupom {store_name}",
            code=code,
            discount_text=None,
            details=None,
            source_url=url,
        ))
        if len(results) >= 80:
            break

    return results


async def fetch_store_coupons(source, store_name, store_slug, timeout=20):
    slug = slugify(store_slug or store_name)
    urls = _source_urls(source, slug)
    if not urls:
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    last_success = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for url in urls:
            try:
                response = await client.get(url)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                last_success = response
                results = _extract(source, store_name, str(response.url), response.text)
                if results:
                    return results
            except httpx.HTTPStatusError:
                continue

    # Página existe, mas não expôs nenhum código digitável no HTML.
    # Não cadastramos oferta genérica como se fosse cupom.
    if last_success is not None:
        return []
    return []
