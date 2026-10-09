"""Compute and realign error-span offsets with difflib (no rich-text editor)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class Span:
    target_start: int | None = None
    target_end: int | None = None
    ref_start: int | None = None
    ref_end: int | None = None
    target_insert_pos: int | None = None


def compute_span(reference: str, perturbed: str, error_type: str) -> Span:
    """Derive original/perturbed span offsets from reference vs generated target."""
    sm = SequenceMatcher(a=reference, b=perturbed, autojunk=False)
    opcodes = [op for op in sm.get_opcodes() if op[0] != "equal"]
    if not opcodes:
        return Span()

    def _longest(ops: list) -> tuple:
        return max(ops, key=lambda o: max(o[2] - o[1], o[4] - o[3], 1))

    et = (error_type or "").strip()
    if et == "Omission":
        deletes = [op for op in opcodes if op[0] in ("delete", "replace")]
        tag, i1, i2, j1, j2 = _longest(deletes) if deletes else opcodes[0]
        return Span(ref_start=i1, ref_end=i2, target_insert_pos=j1)
    if et == "Addition":
        inserts = [op for op in opcodes if op[0] in ("insert", "replace")]
        tag, i1, i2, j1, j2 = _longest(inserts) if inserts else opcodes[0]
        return Span(target_start=j1, target_end=j2)
    # Mistranslation (and anything else): highlight the substituted target span.
    replaces = [op for op in opcodes if op[0] == "replace"]
    inserts = [op for op in opcodes if op[0] == "insert"]
    pool = replaces or inserts or opcodes
    tag, i1, i2, j1, j2 = _longest(pool)
    return Span(
        target_start=j1 if j2 > j1 else None,
        target_end=j2 if j2 > j1 else None,
        ref_start=i1 if i2 > i1 else None,
        ref_end=i2 if i2 > i1 else None,
    )


def realign_span(
    original_text: str,
    start: int | None,
    end: int | None,
    new_text: str,
) -> tuple[int | None, int | None, bool]:
    """
    Return (start, end, approximate).

    If offsets are stale after an edit, try to relocate the original snippet.
    Never return offsets that would present a stale highlight as correct:
    failed realignment yields (None, None, True).
    """
    if start is None or end is None:
        return None, None, False
    if start < 0 or end < start or end > len(original_text):
        return None, None, True
    if original_text == new_text and end <= len(new_text):
        return start, end, False

    snippet = original_text[start:end]
    if snippet:
        count = new_text.count(snippet)
        if count == 1:
            idx = new_text.index(snippet)
            return idx, idx + len(snippet), False
        if count > 1:
            idx = new_text.index(snippet)
            return idx, idx + len(snippet), True

    sm = SequenceMatcher(a=original_text, b=new_text, autojunk=False)
    mapped_start: int | None = None
    mapped_end: int | None = None
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            overlap_start = max(i1, start)
            overlap_end = min(i2, end)
            if overlap_end > overlap_start:
                delta = overlap_start - i1
                chunk_start = j1 + delta
                chunk_end = j1 + delta + (overlap_end - overlap_start)
                if mapped_start is None:
                    mapped_start = chunk_start
                mapped_end = chunk_end
    if mapped_start is not None and mapped_end is not None and mapped_end > mapped_start:
        return mapped_start, mapped_end, True
    return None, None, True


def with_tags(text: str, start: int | None, end: int | None) -> str:
    """Wrap the error region in angle brackets for the editor."""
    if start is None or end is None or start < 0 or end > len(text) or start >= end:
        return text
    return text[:start] + "<" + text[start:end] + ">" + text[end:]


def parse_tags(raw: str) -> tuple[str, int | None, int | None]:
    """Parse a single <error> region. Brackets are not part of the sentence."""
    open_i = raw.find("<")
    close_i = raw.find(">", open_i + 1) if open_i != -1 else -1
    nested = raw.find("<", open_i + 1) if open_i != -1 else -1
    if open_i == -1 or close_i == -1 or nested != -1 or ">" in raw[close_i + 1 :]:
        return raw.replace("<", "").replace(">", ""), None, None
    before = raw[:open_i]
    mid = raw[open_i + 1 : close_i]
    after = raw[close_i + 1 :]
    text = before + mid + after
    start = len(before)
    end = start + len(mid)
    if end == start:
        return text, None, None
    return text, start, end


@dataclass(frozen=True)
class Region:
    text: str
    start: int | None = None
    end: int | None = None
    strike: bool = False
    approximate: bool = False


def region_of(
    *,
    error_type: str,
    generated_text: str,
    edited_text: str,
    reference_text: str,
    target_span_start: int | None,
    target_span_end: int | None,
    ref_span_start: int | None,
    ref_span_end: int | None,
    target_insert_pos: int | None,
    omitted_text: str | None = None,
    insert_at: int | None = None,
    span_start: int | None = None,
    span_end: int | None = None,
    has_custom_omission: bool = False,
) -> Region:
    """Visual region for a candidate: underline, or strikethrough for omissions."""
    if error_type == "Omission":
        base = edited_text
        if has_custom_omission:
            omitted = omitted_text or ""
            ip = insert_at
        else:
            if ref_span_start is not None and ref_span_end is not None:
                omitted = reference_text[ref_span_start:ref_span_end]
            else:
                omitted = ""
            ip = target_insert_pos
        if ip is None or ip < 0 or ip > len(base):
            ip = len(base)
        shown = base[:ip] + omitted + base[ip:]
        return Region(
            text=shown,
            start=ip if omitted else None,
            end=(ip + len(omitted)) if omitted else None,
            strike=True,
        )

    if (
        span_start is not None
        and span_end is not None
        and span_start >= 0
        and span_end > span_start
        and span_end <= len(edited_text)
    ):
        return Region(text=edited_text, start=span_start, end=span_end)

    start, end = target_span_start, target_span_end
    approximate = False
    if edited_text != generated_text:
        start, end, approximate = realign_span(
            generated_text, target_span_start, target_span_end, edited_text
        )
    return Region(text=edited_text, start=start, end=end, approximate=approximate)


def render_highlighted_html(
    text: str,
    start: int | None,
    end: int | None,
    *,
    approximate: bool = False,
    strike: bool = False,
) -> str:
    """Escape text and wrap the span in a teal underline or strikethrough."""
    escaped = html.escape(text)
    if start is None or end is None or start < 0 or end > len(text) or start >= end:
        return escaped
    before = html.escape(text[:start])
    mid = html.escape(text[start:end])
    after = html.escape(text[end:])
    if strike:
        style = (
            "text-decoration: line-through; text-decoration-color: #3697b3; "
            "text-decoration-thickness: 2px;"
        )
    else:
        style = (
            "text-decoration: underline; text-decoration-color: #3697b3; "
            "text-underline-offset: 3px; text-decoration-thickness: 2px;"
        )
    if approximate:
        style += " opacity: 0.85;"
    return f'{before}<span style="{style}">{mid}</span>{after}'
