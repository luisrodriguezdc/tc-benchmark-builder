#!/usr/bin/env python3
"""Rewrite data/import_template.csv (already shipped; this is a convenience regenerator)."""

from pathlib import Path

TEMPLATE = """external_segment_id,dataset_name,dataset_version,source_lang,target_lang,source_text,reference_text,candidate_id,generated_target,error_type,severity,sample_order,target_span_start,target_span_end,ref_span_start,ref_span_end,target_insert_pos,metadata_json
seg-001,Mentoring Guidelines,v1,en,es-ES,Sandra went to the park yesterday.,Sandra fue al parque ayer.,cand-001,Sandra no fue al parque ayer.,Mistranslation,Major,1,,,,,,"{}"
seg-001,Mentoring Guidelines,v1,en,es-ES,Sandra went to the park yesterday.,Sandra fue al parque ayer.,cand-002,Sandra fue al parque publico ayer.,Addition,Minor,1,,,,,,"{}"
seg-001,Mentoring Guidelines,v1,en,es-ES,Sandra went to the park yesterday.,Sandra fue al parque ayer.,cand-003,Sandra fue al parque.,Omission,Major,1,,,,,,"{}"
"""


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "import_template.csv"
    path.write_text(TEMPLATE, encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
