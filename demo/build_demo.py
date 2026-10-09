#!/usr/bin/env python3
"""Build the standalone Tiiny Host demo from the Spanish pilot CSV.

Writes demo/index.html and demo/tc-benchmark-builder-demo.zip (index.html at the zip root).
Does not modify the Streamlit application.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.spans import compute_span, realign_span  # noqa: E402

DEMO = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "tc_spanish_v3_codex_pilot.csv"
TEMPLATE = DEMO / "src" / "template.html"
APP_JS = DEMO / "src" / "app.js"
HTML_PATH = DEMO / "index.html"
ZIP_PATH = DEMO / "tc-benchmark-builder-demo.zip"

ERROR_TYPES = {"Mistranslation", "Addition", "Omission"}
SEVERITIES = {"Minor", "Major"}
# Live English → Spanish pair uses batch size 100 (supabase/migrations/0004_seed.sql).
BATCH_SIZE = 100


def _bmp(text: str, label: str) -> None:
    for ch in text:
        if ord(ch) > 0xFFFF:
            raise SystemExit(f"Non-BMP character in {label}: U+{ord(ch):X}")


def load_segments() -> list[dict]:
    grouped: dict[str, dict] = {}
    order: list[str] = []
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            et = (raw.get("error_type") or "").strip()
            sev = (raw.get("requested_severity") or "").strip()
            if et not in ERROR_TYPES:
                raise SystemExit(f"Unexpected error type: {et!r}")
            if sev not in SEVERITIES:
                raise SystemExit(f"Unexpected severity: {sev!r}")
            sid = (raw.get("segment_id") or "").strip()
            source = raw.get("source") or ""
            reference = raw.get("target") or ""
            generated = raw.get("perturbed_target") or ""
            _bmp(source, sid)
            _bmp(reference, sid)
            _bmp(generated, sid)
            if sid not in grouped:
                grouped[sid] = {
                    "id": sid,
                    "order": int(raw.get("sample_order") or 0),
                    "source": source,
                    "reference": reference,
                    "candidates": [],
                }
                order.append(sid)
            span = compute_span(reference, generated, et)
            grouped[sid]["candidates"].append(
                {
                    "id": (raw.get("candidate_id") or "").strip(),
                    "text": generated,
                    "type": et,
                    "severity": sev,
                    "ts": span.target_start,
                    "te": span.target_end,
                    "rs": span.ref_start,
                    "re": span.ref_end,
                    "ip": span.target_insert_pos,
                }
            )
    segments = [grouped[sid] for sid in order]
    segments.sort(key=lambda s: (s["order"], s["id"]))
    if len(segments) != 50:
        raise SystemExit(f"Expected 50 segments, found {len(segments)}")
    return segments


def payload(segments: list[dict]) -> dict:
    return {
        "pairLabel": "English → Spanish",
        "targetLabel": "Spanish",
        "dataset": "Mentoring Guidelines v3 (pilot)",
        "batchSize": BATCH_SIZE,
        "segments": segments,
    }


def embed_json(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Keep the JSON inside a script tag from being treated as HTML.
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def cross_check_spans(app_js: str) -> None:
    start = app_js.index("/*__SPAN_START__*/")
    end = app_js.index("/*__SPAN_END__*/")
    cases = [
        ("Sandra no fue al parque ayer.", 7, 9, "Ayer Sandra no fue al parque."),
        ("abcdef", 1, 3, "zzzzzz"),
        ("abcdef", 1, 3, "abcdef"),
        ("aaaXXXbbb", 3, 6, "aaaXXbbb"),
        ("hello world", 6, 11, "hello  world"),
        ("abcXYZdef", 3, 6, "abcXYdef"),
    ]
    script = app_js[start:end] + "\nconst cases = " + json.dumps(cases) + """;
for (const c of cases) {
  console.log(JSON.stringify(realignSpan(c[0], c[1], c[2], c[3])));
}
"""
    try:
        proc = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("node not found; skipped JS/Python span comparison")
        return
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) != len(cases):
        raise SystemExit(proc.stderr or "span check returned the wrong number of rows")
    for case, got in zip(cases, lines):
        expected = list(realign_span(*case))
        if got != expected:
            raise SystemExit(f"Span mismatch for {case!r}: js={got} python={expected}")
    print(f"span checks ok ({len(cases)} cases)")


def main() -> None:
    segments = load_segments()
    n_cand = sum(len(s["candidates"]) for s in segments)
    data = payload(segments)
    app_js = APP_JS.read_text(encoding="utf-8")
    if "</script>" in app_js.lower():
        raise SystemExit("app.js contains a script end tag")
    cross_check_spans(app_js)
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__PILOT_JSON__", embed_json(data))
    html = html.replace("__APP_JS__", app_js)
    if "__PILOT_JSON__" in html or "__APP_JS__" in html:
        raise SystemExit("template placeholders were not replaced")
    HTML_PATH.write_text(html, encoding="utf-8")
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(HTML_PATH, arcname="index.html")
    for kind in ("Mistranslation", "Addition", "Omission"):
        sample = next(
            (seg, cand)
            for seg in segments
            for cand in seg["candidates"]
            if cand["type"] == kind
        )
        seg, cand = sample
        if kind == "Omission":
            snippet = seg["reference"][cand["rs"]:cand["re"]]
        else:
            snippet = cand["text"][cand["ts"]:cand["te"]]
        print(f"highlight {kind}: {snippet!r}")
    print(f"segments={len(segments)} candidates={n_cand}")
    print(f"wrote {HTML_PATH} ({HTML_PATH.stat().st_size} bytes)")
    print(f"wrote {ZIP_PATH}")


if __name__ == "__main__":
    main()
