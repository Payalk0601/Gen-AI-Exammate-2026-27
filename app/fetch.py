"""Download source documents into data/raw/ with requests (timeouts, retries, error handling).

  python -m app.fetch
Writes data/raw/manifest.json describing what was fetched or why it failed.
"""
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TIMEOUT = (5, 30)                  # (connect, read) seconds
MAX_BYTES = 60 * 1024 * 1024       # refuse anything above 60 MB
RETRIES = 2
HEADERS = {"User-Agent": "KachraCheck-student-project/0.1 (educational)"}

SOURCES = [
    ("swmp_home.html", "https://swmp.cpcb.gov.in/"),
    ("solid-waste-management-rules-2026.pdf",
     "https://swmp.cpcb.gov.in/img/cpcb_doc/solid-waste-management-rules-2026.pdf"),
    ("swm-rules-2016-toolkit-npc.pdf",
     "https://npcindia.gov.in/NPC/Files/delhiOFC/EM/Toolkit-kit-on-Solid-waste-management.pdf"),
    ("swm-rules-2016-cag-summary.pdf",
     "https://www.cag.org.in/sites/default/files/database/report_swm_rules_2016_salient_features_20170707_0.pdf"),
]


def fetch_one(name, url, out_dir=RAW_DIR, session=None, timeout=TIMEOUT, retries=RETRIES) -> dict:
    """Download one URL. Never raises: returns a result dict with status 'ok' or 'failed'."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()
    result = {"name": name, "url": url, "status": "failed", "error": None}
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=timeout, stream=True)
            resp.raise_for_status()
            declared = int(resp.headers.get("Content-Length") or 0)
            if declared > MAX_BYTES:
                raise ValueError(f"file too large ({declared} bytes)")
            data, size = hashlib.sha256(), 0
            tmp = out_dir / (name + ".part")
            with tmp.open("wb") as f:
                for chunk in resp.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("download exceeded size limit")
                    data.update(chunk)
                    f.write(chunk)
            if size == 0:
                raise ValueError("empty response")
            tmp.replace(out_dir / name)
            result.update(status="ok", bytes=size, sha256=data.hexdigest(),
                          content_type=resp.headers.get("Content-Type"),
                          fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          error=None)
            return result
        except requests.exceptions.Timeout:
            result["error"] = "timeout"
        except requests.exceptions.HTTPError as err:
            result["error"] = f"HTTP {err.response.status_code}"
            if err.response.status_code < 500:      # 4xx will not fix itself
                break
        except requests.exceptions.RequestException as err:
            result["error"] = f"{type(err).__name__}: {err}"
        except (OSError, ValueError) as err:
            result["error"] = f"{type(err).__name__}: {err}"
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    return result


def main(argv=None) -> int:
    results = []
    with requests.Session() as session:
        for name, url in SOURCES:
            res = fetch_one(name, url, session=session)
            tag = "OK  " if res["status"] == "ok" else "FAIL"
            detail = f"{res.get('bytes', 0):,} bytes" if res["status"] == "ok" else res["error"]
            print(f"[{tag}] {name}: {detail}")
            results.append(res)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "manifest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    ok = sum(r["status"] == "ok" for r in results)
    print(f"{ok}/{len(results)} downloaded; manifest at data/raw/manifest.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
