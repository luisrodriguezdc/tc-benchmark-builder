from app.core.spans import compute_span, realign_span, render_highlighted_html


def test_mistranslation_span():
    ref = "Sandra fue al parque ayer."
    pert = "Sandra no fue al parque ayer."
    span = compute_span(ref, pert, "Mistranslation")
    assert span.target_start is not None and span.target_end is not None
    assert "no" in pert[span.target_start : span.target_end] or pert[span.target_start : span.target_end]


def test_addition_span():
    ref = "Sandra fue al parque ayer."
    pert = "Sandra fue al parque publico ayer."
    span = compute_span(ref, pert, "Addition")
    assert span.target_start is not None
    snippet = pert[span.target_start : span.target_end]
    assert "publico" in snippet or snippet.strip()


def test_omission_uses_reference_span():
    ref = "Sandra fue al parque ayer."
    pert = "Sandra fue al parque."
    span = compute_span(ref, pert, "Omission")
    assert span.ref_start is not None and span.ref_end is not None
    assert "ayer" in ref[span.ref_start : span.ref_end]
    assert span.target_insert_pos is not None


def test_realign_exact_move():
    original = "Sandra no fue al parque ayer."
    start = original.index("no")
    end = start + 2
    edited = "Ayer Sandra no fue al parque."
    ns, ne, approx = realign_span(original, start, end, edited)
    assert edited[ns:ne] == "no"
    assert approx is False


def test_stale_offsets_not_silently_kept():
    ns, ne, approx = realign_span("abcdef", 1, 3, "zzzzzz")
    assert ns is None and ne is None
    assert approx is True


def test_highlight_escapes_html():
    html = render_highlighted_html("<b>keep</b> me", 0, 8)
    assert "&lt;b&gt;" in html
    assert "<b>" not in html.replace("<span", "")
