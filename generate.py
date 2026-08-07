"""Take reranked chunks + question -> cited answer via HF Inference API.
Temporary generation backend for local testing; the real deployment runs an
open model directly on the HF Space (ZeroGPU) instead of calling this API."""
import os

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

from logsetup import get_logger

load_dotenv()
log = get_logger(__name__)

MODEL = "Qwen/Qwen2.5-7B-Instruct"

SYSTEM_PROMPT = (
    "You are a clinical evidence assistant for a surgery department. "
    "Answer ONLY using the numbered excerpts below, citing them inline as [PMID]. "
    "If the excerpts don't answer the question, say so explicitly instead of guessing "
    "or using outside knowledge. This is a literature-search aid for clinicians, "
    "not a substitute for clinical judgment."
)


def _client():
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN not set in .env")
    return InferenceClient(token=token)


def _format_context(chunks):
    return "\n\n".join(
        f"[{c['pmid']}] ({', '.join(c.get('pub_types') or []) or 'unspecified type'}) "
        f"{c['title']}\n{c['text']}"
        for c in chunks
    )


def generate_answer(question, chunks, model=MODEL, max_tokens=600):
    if not chunks:
        return "No relevant literature found in the corpus for this question."
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {question}\n\nExcerpts:\n{_format_context(chunks)}"},
    ]
    response = _client().chat.completions.create(model=model, messages=messages, max_tokens=max_tokens)
    answer = response.choices[0].message.content
    log.info(f"generated answer for question={question!r} using {len(chunks)} chunks, model={model}")
    return answer


def demo():
    from retrieval import retrieve

    question = "what are the risk factors for postoperative bleeding after liver transplant"
    chunks = retrieve(question, top_k=5, candidate_pool=50)
    assert chunks, "no retrieval results - is Qdrant populated?"
    answer = generate_answer(question, chunks)
    assert answer and len(answer) > 20
    print("ANSWER:\n", answer)
    print("\nSOURCES:", [c["pmid"] for c in chunks])


if __name__ == "__main__":
    demo()
