"""CSV parsing and upsert/versioning for segments and generated error candidates."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.core.constants import ERROR_TYPES, SEVERITIES
from app.core.spans import compute_span
from app.core.store import Store

METADATA_KEYS = (
    "mechanism",
    "perturbed_source",
    "selected_source_span",
    "source_operation",
    "xliff_unit_id",
    "xliff_unit_index",
    "xliff_file",
    "original_error_type",
    "origin_file",
    "origin_record_number",
    "system",
)

PILOT_COLUMNS = {
    "segment_id": "external_segment_id",
    "candidate_id": "candidate_id",
    "source": "source_text",
    "target": "reference_text",
    "perturbed_target": "generated_target",
    "requested_severity": "severity",
    "source_language_code": "source_lang",
    "target_language_code": "target_lang",
}


@dataclass
class CandidateRow:
    external_segment_id: str
    source_text: str
    reference_text: str
    candidate_id: str
    generated_target: str
    error_type: str
    severity: str
    sample_order: int = 0
    source_lang: str = "en"
    target_lang: str = "es-ES"
    dataset_name: str = "Mentoring Guidelines v3 (pilot)"
    dataset_version: str = "1"
    target_span_start: int | None = None
    target_span_end: int | None = None
    ref_span_start: int | None = None
    ref_span_end: int | None = None
    target_insert_pos: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportReport:
    datasets_upserted: int = 0
    segments_upserted: int = 0
    candidates_inserted: int = 0
    candidates_updated: int = 0
    candidates_versioned: int = 0
    candidates_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    preview: list[dict] = field(default_factory=list)


def _norm_header(name: str) -> str:
    return (name or "").strip().lstrip("\ufeff")


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _normalize_error_type(value: str) -> str:
    raw = (value or "").strip()
    mapping = {
        "undertranslation": "Omission",
        "omission": "Omission",
        "addition": "Addition",
        "overtranslation": "Addition",
        "mistranslation": "Mistranslation",
    }
    mapped = mapping.get(raw.lower(), raw)
    if mapped not in ERROR_TYPES:
        raise ValueError(f"Unknown error type: {value!r}")
    return mapped


def _normalize_severity(value: str) -> str:
    raw = (value or "").strip().title()
    if raw not in SEVERITIES:
        raise ValueError(f"Unknown severity: {value!r}")
    return raw


def _map_row(raw: dict[str, str]) -> dict[str, str]:
    mapped = {_norm_header(k): (v if v is not None else "") for k, v in raw.items()}
    for src, dest in PILOT_COLUMNS.items():
        if src in mapped and dest not in mapped:
            mapped[dest] = mapped[src]
    return mapped


def parse_csv(source: str | Path | Iterable[str]) -> list[CandidateRow]:
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
    elif isinstance(source, str) and ("\n" in source or source.endswith(".csv") is False and "," in source[:2000]):
        reader = csv.DictReader(io.StringIO(source))
    elif isinstance(source, str):
        text = Path(source).read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
    else:
        reader = csv.DictReader(source)

    rows: list[CandidateRow] = []
    for i, raw in enumerate(reader, start=2):
        m = _map_row(raw)
        if not m.get("external_segment_id") and not m.get("candidate_id"):
            continue
        metadata: dict[str, Any] = {}
        if m.get("metadata_json"):
            try:
                metadata = json.loads(m["metadata_json"])
            except json.JSONDecodeError as exc:
                raise ValueError(f"Row {i}: invalid metadata_json ({exc})") from exc
        for key in METADATA_KEYS:
            if m.get(key):
                metadata[key] = m[key]

        et = _normalize_error_type(m.get("error_type") or "")
        sev = _normalize_severity(m.get("severity") or "Major")
        reference = m.get("reference_text") or ""
        generated = m.get("generated_target") or ""
        span = compute_span(reference, generated, et)

        rows.append(
            CandidateRow(
                external_segment_id=str(m.get("external_segment_id") or "").strip(),
                source_text=m.get("source_text") or "",
                reference_text=reference,
                candidate_id=str(m.get("candidate_id") or "").strip(),
                generated_target=generated,
                error_type=et,
                severity=sev,
                sample_order=int(m.get("sample_order") or i),
                source_lang=(m.get("source_lang") or "en").strip(),
                target_lang=(m.get("target_lang") or "es-ES").strip(),
                dataset_name=(m.get("dataset_name") or "Mentoring Guidelines v3 (pilot)").strip(),
                dataset_version=str(m.get("dataset_version") or "1").strip(),
                target_span_start=_int_or_none(m.get("target_span_start")) or span.target_start,
                target_span_end=_int_or_none(m.get("target_span_end")) or span.target_end,
                ref_span_start=_int_or_none(m.get("ref_span_start")) or span.ref_start,
                ref_span_end=_int_or_none(m.get("ref_span_end")) or span.ref_end,
                target_insert_pos=_int_or_none(m.get("target_insert_pos")) or span.target_insert_pos,
                metadata=metadata,
            )
        )
    return rows


def persist_import(
    store: Store,
    rows: list[CandidateRow],
    *,
    publish: bool = False,
    create_missing_pairs: bool = True,
) -> ImportReport:
    report = ImportReport()
    if not rows:
        report.errors.append("No rows to import.")
        return report

    status = "published" if publish else "draft"
    datasets: dict[tuple, dict] = {}
    segments: dict[tuple, dict] = {}

    for row in rows:
        pair = store.find_language_pair(row.source_lang, row.target_lang)
        if pair is None:
            if not create_missing_pairs:
                report.errors.append(
                    f"Unknown language pair {row.source_lang}→{row.target_lang} for candidate {row.candidate_id}"
                )
                continue
            pair = store.insert_language_pair(
                {
                    "source_lang": row.source_lang,
                    "target_lang": row.target_lang,
                    "source_label": "",
                    "target_label": "",
                    "iaa_target_pct": 15,
                    "batch_size": 100,
                    "is_active": True,
                }
            )
        ds_key = (pair["id"], row.dataset_name, row.dataset_version)
        if ds_key not in datasets:
            dataset = store.upsert_dataset(
                {
                    "language_pair_id": pair["id"],
                    "name": row.dataset_name,
                    "version": row.dataset_version,
                    "status": status,
                }
            )
            datasets[ds_key] = dataset
            report.datasets_upserted += 1
        dataset = datasets[ds_key]

        seg_key = (dataset["id"], row.external_segment_id)
        if seg_key not in segments:
            segment = store.upsert_segment(
                {
                    "dataset_id": dataset["id"],
                    "external_id": row.external_segment_id,
                    "source_text": row.source_text,
                    "reference_text": row.reference_text,
                    "sample_order": row.sample_order,
                }
            )
            segments[seg_key] = segment
            report.segments_upserted += 1
        segment = segments[seg_key]

        payload = {
            "segment_id": segment["id"],
            "external_id": row.candidate_id,
            "status": status,
            "error_type": row.error_type,
            "severity": row.severity,
            "generated_text": row.generated_target,
            "target_span_start": row.target_span_start,
            "target_span_end": row.target_span_end,
            "ref_span_start": row.ref_span_start,
            "ref_span_end": row.ref_span_end,
            "target_insert_pos": row.target_insert_pos,
            "metadata": row.metadata,
        }

        existing = store.find_candidate(segment["id"], row.candidate_id)
        if existing is None:
            payload["version"] = 1
            store.insert_candidate(payload)
            report.candidates_inserted += 1
            continue

        identical = (
            existing.get("generated_text") == row.generated_target
            and existing.get("error_type") == row.error_type
            and existing.get("severity") == row.severity
        )
        if identical and existing.get("status") == status:
            report.candidates_skipped += 1
            continue

        assigned = existing.get("status") == "published" and store.candidate_is_assigned(existing["id"])
        if assigned:
            payload["version"] = store.max_candidate_version(segment["id"], row.candidate_id) + 1
            store.insert_candidate(payload)
            report.candidates_versioned += 1
        else:
            store.update_candidate(existing["id"], payload)
            report.candidates_updated += 1

    report.preview = [
        {
            "segment_id": r.external_segment_id,
            "candidate_id": r.candidate_id,
            "error_type": r.error_type,
            "severity": r.severity,
            "generated_target": r.generated_target[:120],
        }
        for r in rows[:25]
    ]
    return report


def parse_and_persist(
    store: Store,
    source: str | Path,
    *,
    publish: bool = False,
) -> ImportReport:
    rows = parse_csv(source)
    return persist_import(store, rows, publish=publish)
