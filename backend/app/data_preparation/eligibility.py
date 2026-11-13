"""Audience filtering shared by index construction and retrieval."""
from urllib.parse import urlsplit, quote
from .contracts import Material, Chunk

# Route mapping is explicit and versioned; only a slug supplied by the archive
# is appended. Never derive a URL from a title.
ROUTES = {"article": "articles", "course": "courses", "document": "documents",
          "webinar": "webinars", "podcast": "podcasts", "glossary": "glossary",
          "calculator": "calculators"}
ORIGIN = "https://kurs.alfabank.ru"

def material_url(raw: str, item_type: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme:
        return raw if parsed.scheme in {"http", "https"} and parsed.netloc else ""
    if raw.startswith("//") or ".." in raw.split("/") or "?" in raw or "#" in raw:
        return ""
    if raw.startswith("/"):
        return ORIGIN + raw
    return f"{ORIGIN}/{ROUTES[item_type]}/{quote(raw.strip('/'), safe='-_/')}/"

def can_retrieve(chunk: Chunk, material: Material, entitlement_keys: set[str] | None = None) -> bool:
    if chunk.material_key != material.material_key or not material.is_discoverable:
        return False
    if material.url_state == "unavailable":
        return False
    return chunk.access_scope == "public" or chunk.entitlement_key in (entitlement_keys or set())

def public_chunks(materials: list[Material], chunks: list[Chunk]) -> list[Chunk]:
    lookup = {m.material_key: m for m in materials}
    return [c for c in chunks if c.material_key in lookup and can_retrieve(c, lookup[c.material_key])]
