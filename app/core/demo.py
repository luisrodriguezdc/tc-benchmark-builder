"""In-memory backend so the UI can run without Supabase (DEMO_MODE=1)."""

from __future__ import annotations

import copy
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.auth import Profile
from app.core.importer import parse_csv

DEMO_USER_ID = "11111111-1111-1111-1111-111111111111"
DEMO_ALEX_ID = "22222222-2222-2222-2222-222222222222"
ROOT = Path(__file__).resolve().parents[2]
PILOT_CSV = ROOT / "data" / "tc_spanish_v3_codex_pilot.csv"
DEMO_SEGMENT_LIMIT = 12


def demo_enabled() -> bool:
    flag = os.environ.get("DEMO_MODE", "").strip().lower()
    if not flag:
        try:
            import streamlit as st

            if "DEMO_MODE" in st.secrets:
                flag = str(st.secrets["DEMO_MODE"]).strip().lower()
        except Exception:
            flag = ""
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    try:
        from app.core.config import get_settings

        return not get_settings().configured
    except Exception:
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


class _Result:
    def __init__(self, data: Any):
        self.data = data


class _Query:
    def __init__(self, store: "DemoStore", table: str):
        self.store = store
        self.table = table
        self._select = "*"
        self._filters: list[tuple[str, Any]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._insert: Any = None
        self._update: dict | None = None

    def select(self, columns: str):
        self._select = columns
        return self

    def eq(self, key: str, value: Any):
        self._filters.append((key, value))
        return self

    def in_(self, key: str, values: list):
        self._in_filters.append((key, list(values)))
        return self

    def order(self, column: str, desc: bool = False):
        self._order = (column, desc)
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def insert(self, row: dict | list):
        self._insert = row
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def upsert(self, row: dict, on_conflict: str | None = None):
        key = (on_conflict or "id").split(",")[0].strip()
        existing = [r for r in self.store.tables[self.table] if r.get(key) == row.get(key)]
        if existing:
            existing[0].update(row)
            return _Result([copy.deepcopy(existing[0])])
        return self.insert(row).execute()

    def execute(self) -> _Result:
        if self._insert is not None:
            rows = self._insert if isinstance(self._insert, list) else [self._insert]
            out = []
            for row in rows:
                item = dict(row)
                item.setdefault("id", _uid())
                item.setdefault("created_at", _now())
                self.store.tables[self.table].append(item)
                out.append(copy.deepcopy(item))
            return _Result(out)
        rows = list(self.store.tables.get(self.table, []))
        if self.table in ("profiles_public", "iaa_pair_stats", "iaa_agreements"):
            rows = self.store.virtual(self.table)
        for key, value in self._filters:
            rows = [r for r in rows if r.get(key) == value]
        for key, values in self._in_filters:
            allowed = set(values)
            rows = [r for r in rows if r.get(key) in allowed]
        if self._update is not None:
            for row in rows:
                row.update(self._update)
                row["updated_at"] = _now()
            return _Result([copy.deepcopy(r) for r in rows])
        if self._order:
            col, desc = self._order
            rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result([self.store.project(self.table, r, self._select) for r in rows])


class _Rpc:
    def __init__(self, store: "DemoStore", name: str, params: dict):
        self.store = store
        self.name = name
        self.params = params or {}

    def execute(self) -> _Result:
        fn = getattr(self.store, f"rpc_{self.name}", None)
        if fn is None:
            raise RuntimeError(f"Demo RPC not implemented: {self.name}")
        return _Result(fn(**self.params))


class DemoAuth:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def get_user(self):
        class _User:
            def __init__(self, uid: str):
                self.id = uid

        class _Resp:
            def __init__(self, uid: str):
                self.user = _User(uid)

        return _Resp(self.user_id)

    def set_session(self, *_args, **_kwargs) -> None:
        return None


class DemoClient:
    def __init__(self, store: "DemoStore", user_id: str = DEMO_USER_ID):
        self._store = store
        self._store.current_user_id = user_id
        self.auth = DemoAuth(user_id)

    def table(self, name: str) -> _Query:
        return _Query(self._store, name)

    def rpc(self, name: str, params: dict | None = None) -> _Rpc:
        return _Rpc(self._store, name, params or {})


class DemoStore:
    def __init__(self):
        self.current_user_id = DEMO_USER_ID
        self.tables: dict[str, list[dict]] = {
            "profiles": [],
            "language_pairs": [],
            "datasets": [],
            "segments": [],
            "error_candidates": [],
            "batches": [],
            "batch_items": [],
            "batch_item_candidates": [],
            "annotations": [],
            "annotation_history": [],
            "error_suggestions": [],
            "admin_audit_log": [],
        }

    def project(self, table: str, row: dict, select: str) -> dict:
        out = copy.deepcopy(row)
        select = (select or "*").strip()
        embeds: list[tuple[str, str]] = []
        cols: list[str] = []
        if select != "*":
            for part in _split_select(select):
                if "(" in part:
                    name, inner = part.split("(", 1)
                    embeds.append((name.strip(), inner.rstrip(")").strip()))
                else:
                    cols.append(part.strip())
            if cols and "*" not in cols:
                out = {k: out.get(k) for k in cols if k}
        for name, inner in embeds:
            out[name] = self._embed(table, row, name, inner)
        return out

    def _embed(self, table: str, row: dict, name: str, inner: str) -> dict | None:
        if name == "language_pairs":
            pair_id = row.get("language_pair_id")
            pair = next((p for p in self.tables["language_pairs"] if p["id"] == pair_id), None)
            if not pair:
                return None
            if inner == "*":
                return copy.deepcopy(pair)
            keys = [k.strip() for k in inner.split(",") if k.strip()]
            return {k: pair.get(k) for k in keys}
        return None

    def virtual(self, name: str) -> list[dict]:
        if name == "profiles_public":
            return [
                {"id": p["id"], "display_name": p["display_name"], "role": p["role"], "is_active": p["is_active"]}
                for p in self.tables["profiles"]
            ]
        if name == "iaa_pair_stats":
            return self._iaa_stats()
        if name == "iaa_agreements":
            return []
        return []

    def _iaa_stats(self) -> list[dict]:
        rows = []
        for pair in self.tables["language_pairs"]:
            segs = [
                s
                for s in self.tables["segments"]
                if any(d["id"] == s["dataset_id"] and d["language_pair_id"] == pair["id"] for d in self.tables["datasets"])
            ]
            n = len(segs)
            target = int(math.ceil(n * float(pair.get("iaa_target_pct") or 15) / 100.0)) if n else 0
            rows.append(
                {
                    "language_pair_id": pair["id"],
                    "source_lang": pair["source_lang"],
                    "target_lang": pair["target_lang"],
                    "iaa_target_pct": pair["iaa_target_pct"],
                    "unique_segments": n,
                    "unique_with_one": 0,
                    "unique_with_two": 0,
                    "coverage_pct": 0,
                    "iaa_target_count": target,
                }
            )
        return rows

    def rpc_claimable_count(self, p_language_pair_id: str) -> int:
        assigned = {i["segment_id"] for i in self.tables["batch_items"]}
        segs = self._published_segments(p_language_pair_id)
        mine = {
            i["segment_id"]
            for i in self.tables["batch_items"]
            if any(b["id"] == i["batch_id"] and b["owner_id"] == self.current_user_id for b in self.tables["batches"])
        }
        return sum(1 for s in segs if s["id"] not in assigned and s["id"] not in mine)

    def rpc_claim_batch(self, p_language_pair_id: str) -> str:
        if any(b["owner_id"] == self.current_user_id and b["status"] == "active" for b in self.tables["batches"]):
            raise RuntimeError("You already have an active batch")
        pair = next(p for p in self.tables["language_pairs"] if p["id"] == p_language_pair_id)
        assigned = {i["segment_id"] for i in self.tables["batch_items"]}
        segs = [s for s in self._published_segments(p_language_pair_id) if s["id"] not in assigned]
        segs.sort(key=lambda s: s.get("sample_order") or 0)
        take = segs[: int(pair.get("batch_size") or 10)]
        if not take:
            raise RuntimeError("No eligible segments available to claim for this language pair")
        number = 1 + max(
            (b["batch_number"] for b in self.tables["batches"] if b["language_pair_id"] == p_language_pair_id),
            default=0,
        )
        batch_id = _uid()
        self.tables["batches"].append(
            {
                "id": batch_id,
                "language_pair_id": p_language_pair_id,
                "owner_id": self.current_user_id,
                "batch_number": number,
                "status": "active",
                "last_position": 1,
                "claimed_at": _now(),
                "completed_at": None,
                "released_at": None,
                "created_at": _now(),
                "updated_at": _now(),
            }
        )
        for pos, seg in enumerate(take, start=1):
            item_id = _uid()
            self.tables["batch_items"].append(
                {
                    "id": item_id,
                    "batch_id": batch_id,
                    "segment_id": seg["id"],
                    "position": pos,
                    "source_error": False,
                }
            )
            for cand in self.tables["error_candidates"]:
                if cand["segment_id"] == seg["id"] and cand["status"] == "published":
                    self.tables["batch_item_candidates"].append(
                        {"batch_item_id": item_id, "candidate_id": cand["id"]}
                    )
        return batch_id

    def rpc_save_annotation(
        self,
        p_candidate_id: str,
        p_batch_id: str,
        p_status: str,
        p_edited_text: str,
        p_error_type: str,
        p_severity: str,
        p_rejection_reason: str | None,
        p_comment: str | None,
        p_expected_version: int,
    ) -> dict:
        uid = self.current_user_id
        existing = next(
            (
                a
                for a in self.tables["annotations"]
                if a["candidate_id"] == p_candidate_id and a["annotator_id"] == uid
            ),
            None,
        )
        if existing is None:
            if int(p_expected_version or 0) != 0:
                raise RuntimeError("version_conflict")
            row = {
                "id": _uid(),
                "candidate_id": p_candidate_id,
                "annotator_id": uid,
                "batch_id": p_batch_id,
                "status": p_status,
                "edited_text": p_edited_text,
                "error_type": p_error_type,
                "severity": p_severity,
                "rejection_reason": p_rejection_reason if p_status == "rejected" else None,
                "comment": p_comment,
                "version": 1,
                "created_at": _now(),
                "updated_at": _now(),
            }
            self.tables["annotations"].append(row)
        else:
            if existing["version"] != int(p_expected_version):
                raise RuntimeError("version_conflict")
            existing.update(
                {
                    "status": p_status,
                    "edited_text": p_edited_text,
                    "error_type": p_error_type,
                    "severity": p_severity,
                    "rejection_reason": p_rejection_reason if p_status == "rejected" else None,
                    "comment": p_comment,
                    "version": existing["version"] + 1,
                    "batch_id": p_batch_id,
                    "updated_at": _now(),
                }
            )
            row = existing
        self.tables["annotation_history"].append(
            {
                "id": _uid(),
                "annotation_id": row["id"],
                "rev": row["version"],
                "snapshot": copy.deepcopy(row),
                "changed_at": _now(),
            }
        )
        return copy.deepcopy(row)

    def rpc_set_batch_position(self, p_batch_id: str, p_position: int) -> None:
        for b in self.tables["batches"]:
            if b["id"] == p_batch_id:
                b["last_position"] = max(int(p_position), 1)
                return

    def rpc_flag_source_error(self, p_batch_id: str, p_segment_id: str, p_flagged: bool) -> None:
        for item in self.tables["batch_items"]:
            if item["batch_id"] == p_batch_id and item["segment_id"] == p_segment_id:
                item["source_error"] = bool(p_flagged)
                return
        raise RuntimeError("Segment is not in your batch")

    def rpc_submit_error_suggestion(
        self,
        p_segment_id: str,
        p_batch_id: str,
        p_suggested_text: str,
        p_error_type: str,
        p_severity: str,
        p_notes: str | None,
    ) -> str:
        sid = _uid()
        self.tables["error_suggestions"].append(
            {
                "id": sid,
                "segment_id": p_segment_id,
                "batch_id": p_batch_id,
                "author_id": self.current_user_id,
                "suggested_text": p_suggested_text,
                "error_type": p_error_type,
                "severity": p_severity,
                "notes": p_notes,
                "created_at": _now(),
            }
        )
        return sid

    def rpc_release_batch(self, p_batch_id: str) -> None:
        for b in self.tables["batches"]:
            if b["id"] == p_batch_id and b["status"] == "active":
                b["status"] = "released"
                b["released_at"] = _now()
                return
        raise RuntimeError("Active batch not found")

    def rpc_reassign_batch(self, p_batch_id: str, p_new_owner: str) -> None:
        if any(b["owner_id"] == p_new_owner and b["status"] == "active" for b in self.tables["batches"]):
            raise RuntimeError("Target translator already has an active batch")
        for b in self.tables["batches"]:
            if b["id"] == p_batch_id:
                b["owner_id"] = p_new_owner
                b["status"] = "active"
                b["released_at"] = None
                return
        raise RuntimeError("Batch not found")

    def rpc_write_audit(self, p_action: str, p_entity: str, p_entity_id: str | None, p_details: dict | None) -> None:
        self.tables["admin_audit_log"].append(
            {
                "id": _uid(),
                "actor_id": self.current_user_id,
                "action": p_action,
                "entity": p_entity,
                "entity_id": p_entity_id,
                "details": p_details or {},
                "created_at": _now(),
            }
        )

    def _published_segments(self, pair_id: str) -> list[dict]:
        ds_ids = {d["id"] for d in self.tables["datasets"] if d["language_pair_id"] == pair_id and d["status"] == "published"}
        segs = [s for s in self.tables["segments"] if s["dataset_id"] in ds_ids]
        published = {c["segment_id"] for c in self.tables["error_candidates"] if c["status"] == "published"}
        return [s for s in segs if s["id"] in published]

    def invite(self, email: str, display_name: str, role: str) -> dict:
        row = {
            "id": _uid(),
            "email": email,
            "display_name": display_name or email.split("@")[0],
            "role": role,
            "is_active": True,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.tables["profiles"].append(row)
        return row


def _split_select(select: str) -> list[str]:
    parts: list[str] = []
    buf = []
    depth = 0
    for ch in select:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def seed_store() -> DemoStore:
    store = DemoStore()
    pair_id = _uid()
    dataset_id = _uid()
    store.tables["profiles"].extend(
        [
            {
                "id": DEMO_USER_ID,
                "email": "demo@example.com",
                "display_name": "Demo Linguist",
                "role": "admin",
                "is_active": True,
                "created_at": _now(),
                "updated_at": _now(),
            },
            {
                "id": DEMO_ALEX_ID,
                "email": "alex@example.com",
                "display_name": "Alex",
                "role": "translator",
                "is_active": True,
                "created_at": _now(),
                "updated_at": _now(),
            },
        ]
    )
    store.tables["language_pairs"].append(
        {
            "id": pair_id,
            "source_lang": "en",
            "target_lang": "es-ES",
            "source_label": "English",
            "target_label": "Spanish",
            "iaa_target_pct": 15,
            "batch_size": 10,
            "is_active": True,
            "created_at": _now(),
            "updated_at": _now(),
        }
    )
    store.tables["datasets"].append(
        {
            "id": dataset_id,
            "language_pair_id": pair_id,
            "name": "Mentoring Guidelines v3 (demo)",
            "version": "1",
            "status": "published",
            "notes": "In-memory demo slice of the Spanish pilot",
            "created_at": _now(),
            "updated_at": _now(),
        }
    )
    rows = parse_csv(PILOT_CSV) if PILOT_CSV.exists() else []
    seen: dict[str, str] = {}
    for row in rows:
        if row.external_segment_id not in seen and len(seen) >= DEMO_SEGMENT_LIMIT:
            continue
        if row.external_segment_id not in seen:
            seg_id = _uid()
            seen[row.external_segment_id] = seg_id
            store.tables["segments"].append(
                {
                    "id": seg_id,
                    "dataset_id": dataset_id,
                    "external_id": row.external_segment_id,
                    "source_text": row.source_text,
                    "reference_text": row.reference_text,
                    "sample_order": row.sample_order,
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )
        store.tables["error_candidates"].append(
            {
                "id": _uid(),
                "segment_id": seen[row.external_segment_id],
                "external_id": row.candidate_id,
                "version": 1,
                "status": "published",
                "error_type": row.error_type,
                "severity": row.severity,
                "generated_text": row.generated_target,
                "target_span_start": row.target_span_start,
                "target_span_end": row.target_span_end,
                "ref_span_start": row.ref_span_start,
                "ref_span_end": row.ref_span_end,
                "target_insert_pos": row.target_insert_pos,
                "metadata": row.metadata,
                "created_at": _now(),
                "updated_at": _now(),
            }
        )
    return store


_STORE: DemoStore | None = None


def get_demo_store() -> DemoStore:
    global _STORE
    if _STORE is None:
        _STORE = seed_store()
    return _STORE


def get_demo_client(user_id: str = DEMO_USER_ID) -> DemoClient:
    return DemoClient(get_demo_store(), user_id=user_id)


def reset_demo_store() -> None:
    global _STORE
    _STORE = seed_store()


def demo_profile() -> Profile:
    return Profile(
        id=DEMO_USER_ID,
        email="demo@example.com",
        display_name="Demo Linguist",
        role="admin",
        is_active=True,
    )
