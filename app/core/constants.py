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

HOWTO_DEMO_INTRO = """
### This demo

You are looking at a clickable preview of the Translation Commons Benchmark Builder.
There is no login. Validate, reject, edit, and suggest as you would in the live tool.
Everything you change is stored in this session only. **Reset Demo** erases that local
copy. The live database is unchanged.
""".strip()

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

- The blue panel is the **source** and the **reference**. Both are read-only. Use **×** in that panel to flag that the source or reference already contains an error. Validation is then skipped; **Undo** clears the flag.
- Each card shows the suggested error. Underlines and strikethroughs are a visual aid only. Use the pen to edit; angle brackets mark the error region and are not part of the sentence.
- **Suggest an additional error** is optional and is stored separately from generated candidates. The suggested target must differ from the reference.
- **Back** / **Next** keep saved work. You may skip incomplete cards and return later.
- Edits autosave. Use **Save** on a card to leave edit mode.
- A segment is **resolved** when every generated candidate is validated or rejected.

### Independence

Do not discuss items with other annotators until you have finished your own annotations.
Overlap items exist so we can measure agreement later.
""".strip()

HOWTO_GUIDE_DEMO_SAVE = (
    "Work is saved in this session only. Use **Save** to confirm a local save. "
    "Nothing is sent to a server."
)

APP_TITLE = "Translation Commons Benchmark Builder"
COOKIE_ACCESS = "tcb_access_token"
COOKIE_REFRESH = "tcb_refresh_token"
