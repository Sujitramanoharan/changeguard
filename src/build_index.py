"""Build a FAISS index over past changes so we can find similar ones."""
import pandas as pd
import numpy as np
import faiss
import joblib
from sentence_transformers import SentenceTransformer

from config import DATA_PATH, FAISS_INDEX_PATH, FAISS_META_PATH, EMBED_MODEL_NAME


def change_to_text(row):
    """Turn a change record into a sentence the embedder can understand."""
    return (
        f"{row['change_type']} on {row['system']}, {row['change_size']} size, "
        f"requested by {row['requester_team']} during {row['requested_window']}. "
        f"Rollback exists: {row['rollback_plan_exists']}. "
        f"Schedule conflict: {row['schedule_conflict']}. "
        f"{row['description']}"
    )


def build():
    df = pd.read_csv(DATA_PATH)
    df["rollback_plan_tested"] = df["rollback_plan_tested"].fillna("None")

    print("Loading embedding model (first run downloads ~80MB)...")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    texts = df.apply(change_to_text, axis=1).tolist()
    print(f"Embedding {len(texts)} past changes...")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    embeddings = embeddings.astype("float32")

    # Normalize so inner-product = cosine similarity
    faiss.normalize_L2(embeddings)

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    # Save the index and the metadata (so we can look up what each vector was)
    faiss.write_index(index, str(FAISS_INDEX_PATH))
    meta = df[[
        "change_id", "system", "change_type", "change_size",
        "requested_window", "outcome", "risk_level", "description"
    ]].to_dict("records")
    joblib.dump(meta, FAISS_META_PATH)

    print("FAISS index built and saved:", FAISS_INDEX_PATH)
    print("Indexed", index.ntotal, "changes.")


if __name__ == "__main__":
    build()