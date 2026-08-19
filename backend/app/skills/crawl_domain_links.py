"""Escanea un sitio y lista subenlaces internos que responden HTTP 200."""

import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT = 10
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._in_a = False
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() != "a":
            return
        href = ""
        for key, value in attrs:
            if key.lower() == "href" and value:
                href = value.strip()
                break
        if href:
            self._in_a = True
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._in_a:
            return
        self.links.append((self._href, " ".join(self._text).strip()))
        self._in_a = False
        self._href = ""
        self._text = []


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            parsed.query,
            "",
        )
    )


def _root_domain(netloc: str) -> str:
    """Extrae el dominio raíz descartando subdominio (www, etc.)."""
    parts = netloc.lower().split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return netloc.lower()


def _is_internal(absolute_url: str, base_root: str) -> bool:
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return _root_domain(parsed.netloc) == base_root


def _http_get(
    url: str, timeout: float = DEFAULT_TIMEOUT
) -> tuple[int | None, str, str]:
    """Retorna (status_code, html). html vacío si no es texto."""
    req = Request(url, headers=_HEADERS, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            status = int(getattr(resp, "status", 200) or 200)
            ct = (resp.headers.get("content-type") or "").lower()
            if "html" in ct:
                html = resp.read().decode("utf-8", errors="replace")
                final = resp.geturl() or url
            else:
                html = ""
                final = resp.geturl() or url
            return status, html, final
    except HTTPError as exc:
        return int(exc.code), "", url
    except (URLError, TimeoutError, ValueError, OSError):
        return None, "", url


def _http_status(url: str, timeout: float = DEFAULT_TIMEOUT) -> int | None:
    req = Request(url, headers=_HEADERS, method="HEAD")
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return int(getattr(resp, "status", 200) or 200)
    except HTTPError as exc:
        return int(exc.code)
    except (URLError, TimeoutError, ValueError, OSError):
        return None


def _matches_keywords(url: str, text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = f"{url} {text}".lower()
    return any(k.lower() in haystack for k in keywords if k)


def run(input_data: dict) -> dict:
    """Escanea subenlaces internos de un sitio y verifica cuáles responden 200.

    Args:
        input_data: Dict con claves:
            base_url (str): URL a escanear.
            max_links (int, opcional): Máx enlaces a verificar (default 20).
            keywords (list|str, opcional): Filtro por palabras clave.
                Si es None o vacío, devuelve todos los enlaces válidos.

    Returns:
        Dict con ok, base_url, valid (lista url+text+status), broken_sample.
    """
    data = input_data or {}
    base_url = str(data.get("base_url") or data.get("url") or "").strip()
    if not base_url:
        return {"ok": False, "error": "Falta base_url"}
    if not re.match(r"^https?://", base_url, re.I):
        base_url = "https://" + base_url

    try:
        max_links = int(data.get("max_links") or 20)
    except (TypeError, ValueError):
        max_links = 20

    raw_keywords = data.get("keywords") or data.get("filter_keywords")
    keywords: list[str] = []
    if isinstance(raw_keywords, str) and raw_keywords.strip():
        keywords = [
            p.strip()
            for p in re.split(r"[,;|]", raw_keywords)
            if p.strip()
        ]
    elif isinstance(raw_keywords, list):
        keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]

    parsed_base = urlparse(base_url)
    if not parsed_base.netloc:
        return {"ok": False, "error": f"URL inválida: {base_url}"}

    status, html, final_url = _http_get(base_url)
    if status != 200:
        return {
            "ok": False,
            "error": f"La URL base no respondió 200 (status={status})",
            "base_url": base_url,
        }
    if not html:
        return {
            "ok": False,
            "error": "La URL base no devolvió HTML",
            "base_url": final_url,
        }

    parser = _HrefParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        pass

    base_root = _root_domain(urlparse(final_url).netloc)
    seen: set[str] = set()
    candidates: list[dict] = []

    for href, text in parser.links:
        if not href:
            continue
        if href.startswith("#"):
            continue
        lower = href.lower()
        if lower.startswith(("javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(final_url, href)
        # Descartar fragment-only tras join
        absolute = absolute.split("#")[0]
        if not absolute:
            continue
        if not _is_internal(absolute, base_root):
            continue
        if not _matches_keywords(absolute, text, keywords):
            continue
        norm = _normalize_url(absolute)
        if norm in seen:
            continue
        seen.add(norm)
        candidates.append({"url": norm, "text": text[:180]})

    valid: list[dict] = []
    broken: list[dict] = []
    cap = max(1, max_links) * 3  # revisar hasta 3x para tener margen

    for item in candidates[:cap]:
        if len(valid) >= max_links:
            break
        code = _http_status(item["url"])
        if code == 200:
            valid.append({**item, "status": 200})
        else:
            broken.append({**item, "status": code})

    return {
        "ok": True,
        "base_url": final_url,
        "keywords": keywords,
        "max_links": max_links,
        "candidates_found": len(candidates),
        "valid_count": len(valid),
        "broken_count": len(broken),
        "valid_urls": [v["url"] for v in valid],
        "valid": valid,
        "broken_sample": broken[:10],
    }
