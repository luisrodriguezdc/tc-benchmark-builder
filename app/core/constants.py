ERROR_TYPES = ("Mistranslation", "Addition", "Omission")
SEVERITIES = ("Minor", "Major")
ANNOTATION_STATUSES = ("draft", "validated", "rejected")

REJECTION_REASONS = (
    ("no_meaningful_error", "No meaningful error"),
    ("multiple_errors", "Multiple errors"),
    ("grammar_fluency_plausibility", "Grammar / fluency / plausibility problem"),
    ("incorrect_unclear_perturbation", "Incorrect or unclear perturbation"),
    ("other", "Other"),
)

REJECTION_REASON_LABELS = dict(REJECTION_REASONS)

HOWTO_GUIDE = """
### Annotation rules

You are checking **synthetic translation errors**. Each card is one generated candidate
that should contain **exactly one** intended error.

**Validate** only when all of the following are true:

1. The target sentence contains exactly one intended error.
2. That error matches the selected type (Mistranslation / Addition / Omission) and severity (Minor / Major).
3. There are no unrelated grammatical, fluency, or plausibility problems.

You may edit the sentence and the labels before validating.

**Reject** a candidate when:

- There is no meaningful error.
- There are multiple errors.
- Grammar, fluency, or plausibility is broken in a way that is not the intended error.
- The perturbation is incorrect or unclear.
- Other (add a comment).

### Interface

- The yellow panel is the **source** and **reference** (read-only; you can copy them).
- Each card is a generated error. Red underlines are a visual aid only — you can still validate without a highlight.
- **(+) Suggest an additional error** is optional and is stored separately from generated candidates.
- **Back** / **Next** never discard saved work. You may skip incomplete cards and return later.
- Work is saved to the server. Use **Save** if a network error appears.
- A segment is **resolved** when every generated candidate is validated or rejected.

### Independence

Do not discuss items with other annotators until you have finished your own annotations.
Overlap items exist so we can measure agreement later.
""".strip()

APP_TITLE = "Translation Commons Benchmark Builder"
COOKIE_ACCESS = "tcb_access_token"
COOKIE_REFRESH = "tcb_refresh_token"
