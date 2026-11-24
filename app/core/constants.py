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

WELCOME_COPY = """
### Help Build Better Tools for Translators!

**What if AI could help you identify translation errors, reduce repetitive quality checks, and make your translation workflow more efficient—without replacing your professional judgment?**

Translation Commons is seeking volunteer translators of all experience levels to participate in an exciting research project exploring how open-weight artificial intelligence (AI) models can support translators and improve Linguistic Quality Assurance (LQA).

This research is being conducted by Luis Rodriguez, a Translation Commons research volunteer pursuing a Master's in Responsible AI, under the supervision of Soeren, with project coordination support from Carrie Stumpf, Localization Project Manager at Translation Commons.

Our goal is to explore accessible, cost-effective AI tools that can help nonprofit organizations and volunteer translators identify translation errors, improve quality, and streamline their workflows—without relying on expensive enterprise software.

### Why are we building a custom benchmark?

There are two types of models that could potentially support LQA workflows:

- **Quality Estimation (QE) Models -** estimates a human evaluation of “how good” the translation is based on a rubric (e.g. [SmartCAT Translation Score](https://www.smartcat.com/news/introducing-translation-quality-score/) gives score 1-100%)
- **AI-driven LQA -** these models aim to predict whether there is a translation error, and suggest the error type based on a taxonomy like [MQM](https://www.themqm.org/mqm-pillars/typology/) (eg. [ContentQuo Evaluate HT](https://www.contentquo.com/products/evaluate-ht))

As enterprise CAT tools like SmartCat and ContentQuo are cost-prohibitive, our goal is to evaluate the viability of using free models via Hugging Face that allow for non-commercial use.

However, we don’t know how good these free models are at catching errors if we don’t have examples to test against!

That’s where you come in: we need experienced linguists to help build a dataset of validated translation errors. **The data you curate will not be used to train an AI model.** It will be used to evaluate whether existing free and open-source models are good enough to support our linguist’s LQA workflow.

### How you can help!

As part of this project, we have developed a system that takes completed “gold standard” translations from the projects published in [TC Resource Library](https://translationcommons.org/zero-to-digital-resources/), and then automatically *suggests an error* that matches a particular type (e.g. omission) and severity (e.g. major vs minor).

Your role will be to validate and refine the errors to ensure they match the expected type and severity. We expect the system will suggest valid errors at least 80% of the time, and hope that having a starting point may be helpful to spark alternative ideas.

### How to Use the Interface

- The blue panel is the source and the reference. Both are read-only.
- Use × in that panel to flag that the source or reference already contains an error
- Each card shows the suggested error. Underlines and strikethroughs are a visual aid only.
- Use the pen to edit; angle brackets mark the error region and are not part of the sentence.
- Suggest an additional error is optional and is stored separately from generated candidates. The suggested target must differ from the reference.
- Back / Next keep saved work. You may skip incomplete cards and return later.
- Edits autosave. Use Save on a card to leave edit mode. Work is saved to the server. Use Save if a network error appears.
- A segment is resolved when every generated candidate is validated or rejected.

### Contact Info

If you run into any issues or have additional questions, feedback or just something you’d like to share, please reach out directly to [Carrie Stumpf](mailto:carrie@translationcommons.org) [carrie@translationcommons.org](mailto:carrie@translationcommons.org) and CC Luis Rodriguez [luisrodriguez@translationcommons.org](mailto:luisrodriguez@translationcommons.org)
""".strip()

HOWTO_GUIDE = """
### Error Types

The MQM error typology is a hierarchical system of error categories and subcategories used in the Multidimensional Quality Metrics (MQM) framework to classify translation and localization defects. It gives reviewers a shared vocabulary to identify what went wrong in human, machine, or AI-generated translations before scoring severity and overall quality.

The full typology includes 7 high-level error types including Terminology, Accuracy, Linguistic Fluency, Style, Locale conventions, Audience appropriateness (Verity in version 1).

We have decided to focus this project on Accuracy, specifically covering 3 error subtypes:

**Mistranslation** The target content does not accurately represent the source content, such as a flipped, distorted or unrelated meaning. For example:

1. The door is open → The door is closed
2. The chef sliced the bread → The chef weighed the bread
3. The bird crossed the river → The bird followed the river

**Addition** The target includes content that is not in the source, such as an extra specifier or constraint. For example:

1. They sell vehicles → They sell electric vehicles
2. She bought tickets → She bought weekend tickets
3. The store opens at nine → The store usually opens at nine

**Omission** Content that is in the source is missing from the target, such as a modifier or dependent phrase. For example:

1. The red bicycle was found → The bicycle was found
2. The keys on the table disappeared → The keys disappeared
3. The dog with the blue collar barked → The dog barked

### Error Severity

While MQM specifies 4 levels (Critical, Major, Minor, Neutral), this project will only have 2 broad severity levels: Major vs Minor

**Minor** is a limited local meaning error. The mechanism is clearly present, but the content stays broadly understandable, reliable, and usable, with only limited impact on its meaning. For examples

**Major** is a substantial meaning error. The mechanism causes a significant loss, change, reversal, restriction, or addition of important meaning. That seriously affects the reliability, interpretation, or usability of the content. Unrelated content stays.

| Error Subtype | Source Text | Minor | Major |
| --- | --- | --- | --- |
| **Mistranslation** | Click **Save** to keep your changes. | Click **Store** to keep your changes. | Click **Delete** to keep your changes. |
| **Omission** | The meeting starts at 9:00 AM sharp in Room 4B. | The meeting starts at 9:00 AM **~~sharp~~** in Room 4B. | The meeting starts at 9:00 AM **~~in Room 4B~~** |
| **Addition** | Wash with warm water. | Wash **gently** with warm water. | Wash with warm water **and bleach**. |

### General Rules

Validate only when all of the following are true:

1. The target sentence contains **exactly one intended error.**
2. That error matches the selected type (Mistranslation / Addition / Omission) and severity (Minor / Major).
3. There are no unrelated grammatical, fluency, or plausibility problems.
4. Assume there is no organizational terminology database.

You may edit the sentence and the labels before validating. Alternatively, you can reject the error and suggest another from scratch.

**If the reference translation has an existing error** Use × in that panel to flag that the source or reference already contains an error. Validation is then skipped.

### Independence

Do not discuss items with other annotators in your same target language until you have finished your own annotations. Overlap items exist so we can measure agreement later.
""".strip()

HOWTO_GUIDE_DEMO_SAVE = (
    "Work is saved in this session only. Use **Save** to confirm a local save. "
    "Nothing is sent to a server."
)

APP_TITLE = "Translation Commons Benchmark Builder"
COOKIE_ACCESS = "tcb_access_token"
COOKIE_REFRESH = "tcb_refresh_token"
