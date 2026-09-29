"""FAISS nearest-neighbour search over real historical changes.

Each historical change is encoded from the same attributes the risk
model uses (one-hot categories + log-scaled, standardised numbers) and
searched by Euclidean distance, so a 5-line commit is never "similar"
to a 5,000-line one. The neighbours' real outcomes are shown to
reviewers and feed the risk policy.
"""

import faiss
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler


def log1p_clipped(X):
    """log(1 + x) for non-negative counts (module-level so it pickles)."""

    return np.log1p(np.clip(X, 0, None))


def make_encoder(categorical: list, numeric: list) -> ColumnTransformer:
    """One-hot categories + log-scaled, standardised numbers."""

    transformers = []

    if categorical:
        transformers.append((
            "cat",
            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            categorical,
        ))

    if numeric:
        transformers.append((
            "num",
            make_pipeline(
                FunctionTransformer(log1p_clipped),
                StandardScaler(),
            ),
            numeric,
        ))

    return ColumnTransformer(transformers)


def _vectors(encoder, frame) -> np.ndarray:
    return np.ascontiguousarray(
        np.nan_to_num(np.asarray(encoder.transform(frame), dtype="float32"))
    )


def build_index(encoder, frame, index_path) -> None:
    """Encode the historical changes and write the FAISS index."""

    vectors = _vectors(encoder, frame)
    index = faiss.IndexFlatL2(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(index_path))


_indexes = {}


def search(index_path, encoder, meta: list, frame, k: int = 5,
           id_key: str = "change_id") -> list:
    """Return the k most similar distinct historical changes."""

    key = str(index_path)

    if key not in _indexes:
        _indexes[key] = faiss.read_index(key)

    # One change can appear once per affected system; over-fetch and
    # keep the first (most similar) row of each distinct change.
    dists, idxs = _indexes[key].search(_vectors(encoder, frame), k * 40)

    results, seen = [], set()

    for dist, i in zip(dists[0], idxs[0]):
        if i < 0 or meta[i][id_key] in seen:
            continue
        seen.add(meta[i][id_key])
        rec = dict(meta[i])
        # Squared L2 distance -> 0..1 similarity (1 = identical).
        rec["similarity"] = round(1.0 / (1.0 + float(np.sqrt(max(dist, 0.0)))), 3)
        results.append(rec)
        if len(results) == k:
            break

    return results
