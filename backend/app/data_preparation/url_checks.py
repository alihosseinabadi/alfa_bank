"""Bounded URL checks; no access inference from a successful HTTP response."""
from datetime import datetime, timezone
from urllib.parse import urlsplit
import time
import httpx

def check_url(url: str, client: httpx.Client, retries: int = 1) -> dict:
    result = {"url": url, "checked_at": datetime.now(timezone.utc).isoformat(),
              "state": "unchecked", "status_code": None, "attempts": 0, "final_url": None}
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        result["state"] = "unavailable"
        result["error"] = "invalid_or_relative_url"
        return result
    for attempt in range(retries + 1):
        result["attempts"] += 1
        try:
            response = client.head(url)
            if response.status_code in {403, 405, 501}:
                # Stream a small GET probe instead of downloading the material.
                with client.stream("GET", url, headers={"Range": "bytes=0-1023"}) as probe:
                    code, final = probe.status_code, str(probe.url)
            else:
                code, final = response.status_code, str(response.url)
            result.update(status_code=code, final_url=final)
            if 200 <= code < 400:
                result["state"] = "reachable"
            elif code in {404, 410}:
                result["state"] = "unavailable"
            elif code in {401, 403}:
                result["state"] = "reachable"
                result["requires_auth_or_blocked_probe"] = True
            else:
                result["state"] = "temporary_failure"
        except httpx.HTTPError as exc:
            result["state"] = "temporary_failure"
            result["error"] = type(exc).__name__
        if result["state"] != "temporary_failure":
            break
        if attempt < retries:
            time.sleep(0.2)
    return result

def check_urls(urls: list[str], timeout: float = 5, retries: int = 1, workers: int = 4) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor
    if not 0 <= retries <= 3 or not 1 <= workers <= 8 or not 0 < timeout <= 30:
        raise ValueError("URL check limits exceeded")
    with httpx.Client(timeout=timeout, follow_redirects=True, max_redirects=5,
                      headers={"User-Agent": "AlfaKursCatalogCheck/1.0"}) as client:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(lambda url: check_url(url, client, retries), sorted(set(urls))))
