# Trained models

These files are produced by `src/train_ticket_model.py` and `src/train_code_model.py`
and loaded by the app at startup. The `.pkl` and `.index` files are binary, so an
editor cannot show them as text; that is expected.

| File | What it is | Readable? |
|---|---|---|
| `ticket_model.pkl` | Change-ticket LightGBM model with its category encoder, change-type risk rates and base rate (joblib) | Binary |
| `ticket_similar.index` | FAISS index of the 26,076 real Rabobank changes, for "similar past changes" | Binary |
| `ticket_stats.json` | Historical incident and schedule rates used by the evidence tools | Text |
| `code_model.pkl` | Code-change LightGBM model with its encoder and metadata (joblib) | Binary |
| `code_similar.index` | FAISS index of the 106,674 ApacheJIT commits | Binary |
| `metrics.json` | Evaluation results of both models (AUC, baselines, feature importance) | Text |

To check the binary files load:

```
python -c "import joblib, faiss; print(list(joblib.load('models/ticket_model.pkl'))); print(faiss.read_index('models/ticket_similar.index').ntotal)"
```
