"""FAISS-based retrieval of similar historical changes."""

import truststore

truststore.inject_into_ssl()

import faiss
import joblib
from sentence_transformers import SentenceTransformer

from config import (
    FAISS_INDEX_PATH,
    FAISS_META_PATH,
    EMBED_MODEL_PATH,
)


# -------------------------------------------------------------------
# Load retrieval artifacts once when the module is imported.
# -------------------------------------------------------------------

_model = SentenceTransformer(
    str(EMBED_MODEL_PATH)
)

_index = faiss.read_index(
    str(FAISS_INDEX_PATH)
)

_meta = joblib.load(
    FAISS_META_PATH
)


# -------------------------------------------------------------------
# Similar-change retrieval
# -------------------------------------------------------------------

def find_similar_changes(
    query_text,
    k=5,
    min_similarity=0.70,
):
    """Return sufficiently similar past changes with their outcomes."""

    emb = _model.encode(
        [query_text],
        convert_to_numpy=True,
    ).astype("float32")

    faiss.normalize_L2(emb)

    scores, idxs = _index.search(
        emb,
        k,
    )

    results = []

    for score, i in zip(
        scores[0],
        idxs[0],
    ):
        if score < min_similarity:
            continue

        rec = dict(_meta[i])

        rec["similarity"] = round(
            float(score),
            3,
        )

        results.append(rec)

    return results


# -------------------------------------------------------------------
# Standalone retrieval test
# -------------------------------------------------------------------

if __name__ == "__main__":

    test = (
        "Database-Schema-Change on Payments-Service, "
        "Large size, requested by Backend during Peak-Hours. "
        "Schedule conflict: Yes."
    )

    print(
        "Query:",
        test,
        "\n",
    )

    for r in find_similar_changes(test):

        print(
            f"  [{r['similarity']}] "
            f"{r['change_id']} | "
            f"{r['change_type']} on "
            f"{r['system']} -> "
            f"{r['outcome']} "
            f"(risk: {r['risk_level']})"
        )