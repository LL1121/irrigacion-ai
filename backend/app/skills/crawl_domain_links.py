"""Escanea un sitio y lista subenlaces internos que responden HTTP 200."""

import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT = 8
MAX_LINKS_TO_CHECK = 60
USER_AGENT = "irrigacion-bot/1.0 (crawler institucional)"


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._in_a = False
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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
        (parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, "")
    )


def _is_internal(href: str, base_netloc: str) -> bool:
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return True
    return parsed.netloc.lower() == base_netloc.lower()


def _http_status(url: str, timeout: float = DEFAULT_TIMEOUT) -> int | None:
    req = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
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


def run(input_data):
    base_url = str(
        (input_data or {}).get("base_url")
        or (input_data or {}).get("url")
        or ""
    ).strip()
    if not base_url:
        return {"ok": False, "error": "Falta base_url"}
    if not re.match(r"^https?://", base_url, re.I):
        base_url = "https://" + base_url

    raw_keywords = (input_data or {}).get("keywords")
    keywords: list[str] = []
    if isinstance(raw_keywords, str) and raw_keywords.strip():
        keywords = [p.strip() for p in re.split(r"[,;|]", raw_keywords) if p.strip()]
    elif isinstance(raw_keywords, list):
        keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]

    parsed_base = urlparse(base_url)
    if not parsed_base.netloc:
        return {"ok": False, "error": f"URL inválida: {base_url}"}

    status = _http_status(base_url)
    if status != 200:
        return {
            "ok": False,
            "error": f"La URL base no respondió 200 (status={status})",
            "base_url": base_url,
        }

    req = Request(base_url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:  # noqa: S310
            html = resp.read().decode("utf-8", errors="replace")
            final_url = resp.geturl() or base_url
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"No pude leer el HTML: {exc}", "base_url": base_url}

    parser = _HrefParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    base_netloc = urlparse(final_url).netloc
    seen: set[str] = set()
    candidates: list[dict[str, str]] = []
    for href, text in parser.links:
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        if href.lower().startswith("mailto:"):
            continue
        absolute = urljoin(final_url, href)
        if not _is_internal(absolute, base_netloc):
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
    for item in candidates[:MAX_LINKS_TO_CHECK]:
        code = _http_status(item["url"])
        if code == 200:
            valid.append({**item, "status": 200})
        else:
            broken.append({**item, "status": code})

    return {
        "ok": True,
        "base_url": final_url,
        "keywords": keywords,
        "checked": min(len(candidates), MAX_LINKS_TO_CHECK),
        "valid_count": len(valid),
        "broken_count": len(broken),
        "valid_urls": [v["url"] for v in valid],
        "valid": valid,
        "broken_sample": broken[:15],
    }
