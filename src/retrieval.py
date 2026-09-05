"""Find similar past changes using the FAISS index."""
import faiss
import joblib
from sentence_transformers import SentenceTransformer

from config import FAISS_INDEX_PATH, FAISS_META_PATH, EMBED_MODEL_NAME

# Load once when imported
_model = SentenceTransformer(EMBED_MODEL_NAME)
_index = faiss.read_index(str(FAISS_INDEX_PATH))
_meta = joblib.load(FAISS_META_PATH)


def find_similar_changes(query_text, k=5):
    """Return the k most similar past changes with their outcomes."""
    emb = _model.encode([query_text], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(emb)
    scores, idxs = _index.search(emb, k)

    results = []
    for score, i in zip(scores[0], idxs[0]):
        rec = dict(_meta[i])
        rec["similarity"] = round(float(score), 3)
        results.append(rec)
    return results


if __name__ == "__main__":
    # quick test
    test = ("Database-Schema-Change on Payments-Service, Large size, "
            "requested by Backend during Peak-Hours. Schedule conflict: Yes.")
    print("Query:", test, "\n")
    for r in find_similar_changes(test):
        print(f"  [{r['similarity']}] {r['change_id']} | {r['change_type']} on "
              f"{r['system']} -> {r['outcome']} (risk: {r['risk_level']})")