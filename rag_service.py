from sentence_transformers import SentenceTransformer
import faiss
from pypdf import PdfReader
import numpy as np
import os
import pickle

PDF_PATH = "knowledgebase/report.pdf"

VECTOR_DIR = "vectorstore"
FAISS_INDEX_PATH = os.path.join(VECTOR_DIR, "report_faiss.index")
CHUNKS_PATH = os.path.join(VECTOR_DIR, "report_chunks.pkl")


_cached_chunks = None
_cached_index = None


# load model once
model = SentenceTransformer("all-MiniLM-L6-v2")


def load_pdf(file_path):
    reader = PdfReader(file_path)
    text = ""

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

    return text


def split_text(text, chunk_size=500, overlap=100):
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


def create_faiss_index(chunks):
    embeddings = model.encode(chunks, convert_to_numpy=True, normalize_embeddings=True)
    embeddings = embeddings.astype("float32")

    dimension = embeddings.shape[1]
    # Inner product works well with normalized embeddings
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    return index


def save_vectorstore(index, chunks):
    os.makedirs(VECTOR_DIR, exist_ok=True)

    faiss.write_index(index, FAISS_INDEX_PATH)

    with open(CHUNKS_PATH, "wb") as f:
        pickle.dump(chunks, f)


def load_vectorstore():
    if not os.path.exists(FAISS_INDEX_PATH):
        return None, None
    if not os.path.exists(CHUNKS_PATH):
        return None, None

    index = faiss.read_index(FAISS_INDEX_PATH)
    with open(CHUNKS_PATH, "rb") as f:
        chunks = pickle.load(f)

    return index, chunks


def build_vectorstore():
    text = load_pdf(PDF_PATH)
    chunks = split_text(text)

    if not chunks:
        raise ValueError("No text chunks found in PDF.")

    index = create_faiss_index(chunks)
    save_vectorstore(index, chunks)

    return index, chunks


def get_or_create_vectorstore():
    global _cached_chunks, _cached_index
    # First use memory cache
    if _cached_chunks is not None and _cached_index is not None:
        return _cached_index, _cached_chunks

    # Then use saved FAISS index
    index, chunks = load_vectorstore()

    if index is None or chunks is None:
        index, chunks = build_vectorstore()

    _cached_index = index
    _cached_chunks = chunks

    return _cached_index, _cached_chunks


def search(query, chunks, index, k=3, min_score=0.35):
    query_embedding = model.encode(
        [query], convert_to_numpy=True, normalize_embeddings=True
    )
    query_embedding = query_embedding.astype("float32")

    scores, indices = index.search(query_embedding, k)

    ##distances, indices = index.search(np.array(query_embedding), k)

    results = []
    for score, i in zip(scores[0], indices[0]):
        if i != -1 and i < len(chunks):
            if score >= min_score:
                results.append(
                    {"chunk": chunks[i], "similarity_score": round(float(score), 3)}
                )

    return results


def get_rag_context(question, k=3):
    index, chunks = get_or_create_vectorstore()

    results = search(question, chunks, index, k=k)

    if not results:
        return {
            "context": "",
            "top_similarity": 0,
            "average_similarity": 0,
            "chunks": [],
        }

    context_parts = []
    scores = []

    for item in results:
        context_parts.append(
            f"[Cosine Similarity: {item['similarity_score']}]\n{item['chunk']}"
        )
        scores.append(item["similarity_score"])

    return {
        "context": "\n\n".join(context_parts),
        "top_similarity": max(scores),
        "average_similarity": round(sum(scores) / len(scores), 3),
        "chunks": results,
    }


def rebuild_vectorstore():
    global _cached_chunks, _cached_index

    _cached_chunks = None
    _cached_index = None

    index, chunks = build_vectorstore()

    _cached_index = index
    _cached_chunks = chunks

    return True


def get_vectorstore_stats():
    index, chunks = get_or_create_vectorstore()

    return {
        "total_vectors": index.ntotal,
        "total_chunks": len(chunks),
        "embedding_dimension": index.d,
        "faiss_index_path": FAISS_INDEX_PATH,
        "chunks_path": CHUNKS_PATH,
    }


if __name__ == "__main__":
    stats = get_vectorstore_stats()

    print("FAISS Vectorstore Stats")
    print("-----------------------")
    print(f"Total vectors: {stats['total_vectors']}")
    print(f"Total chunks: {stats['total_chunks']}")
    print(f"Embedding dimension: {stats['embedding_dimension']}")
    print(f"FAISS index path: {stats['faiss_index_path']}")
    print(f"Chunks path: {stats['chunks_path']}")
