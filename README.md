# Translation Commons Benchmark Builder

Clickable demo of the volunteer workspace for checking **synthetic translation errors** (English → Spanish Mentoring Guidelines sample).

Live app: [https://tc-benchmark-builder.streamlit.app](https://tc-benchmark-builder.streamlit.app)

There is no login. You are **Demo Linguist**. Work stays in this browser session. **Reset Demo** in the sidebar clears it. The app may also reset when Streamlit Community Cloud sleeps or restarts.

## Try it

1. Open the live app (or run locally — below).
2. On **All Batches**, claim the English → Spanish sample (**Claim This Batch**). Other language rows are placeholders.
3. For each segment, review the source and reference, then each error card:
   - **Validate** if the sentence has exactly one intended error that matches the type and severity, with no extra fluency problems.
   - **Edit** to change the sentence. Angle brackets `<>` mark the error region; they are not part of the sentence.
   - **×** on a card to reject it (wrong perturbation, multiple errors, and so on).
   - **×** on the source/reference panel if those sentences already contain an error. Validate becomes **Invalid source**. **Undo** clears the flag.
   - **Suggest an additional error** to add another card, already in edit mode, with the reference pre-filled. Save only works if the suggested target differs from the reference.
4. **Back** / **Next** move between segments. Edits autosave in the session.

## Run locally

Python 3.11 or 3.12:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DEMO_MODE=1 streamlit run streamlit_app.py
```

Open [http://localhost:8501](http://localhost:8501). Same demo as Cloud.

## Sample data

Twelve real English → Spanish segments from the Mentoring Guidelines v3 pilot CSV in [`data/`](data/). Underlines and strikethroughs on cards are a visual aid only.

## License

Prototype for Translation Commons volunteer workflow testing.
