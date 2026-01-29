"""Reranker service for Probe.

Supports:
- Qwen/Qwen3-Reranker-0.6B (instruction-aware, LM-style scoring)
- zeroentropy/zerank-2 (instruction-following cross-encoder)
"""

from __future__ import annotations

import os
from typing import Any

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configuration
MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen3-Reranker-0.6B")
HOST = os.getenv("HOST", "127.0.0.1")  # Default to localhost for security
PORT = int(os.getenv("PORT", "8083"))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

app = FastAPI(title="Probe Reranker", version="0.1.0")

# Model loading (lazy)
_model = None
_tokenizer = None


class RerankRequest(BaseModel):
    """Request for reranking documents."""

    query: str
    documents: list[str]
    instruction: str | None = None


class RerankResult(BaseModel):
    """Single rerank result."""

    index: int
    score: float


class RerankResponse(BaseModel):
    """Response with reranked documents."""

    results: list[RerankResult]


def get_model():
    """Lazy load the reranker model."""
    global _model, _tokenizer

    if _model is None:
        if "zerank" in MODEL_ID.lower():
            # zerank-2: Cross-encoder style
            from sentence_transformers import CrossEncoder

            _model = CrossEncoder(MODEL_ID, device=DEVICE)
            _tokenizer = None  # Not needed for CrossEncoder
        else:
            # Qwen3-Reranker: LM-style scoring
            from transformers import AutoModelForCausalLM, AutoTokenizer

            _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
            _model = AutoModelForCausalLM.from_pretrained(
                MODEL_ID,
                torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
                device_map="auto" if DEVICE == "cuda" else None,
                trust_remote_code=True,
            )

    return _model, _tokenizer


def rerank_with_qwen(
    query: str,
    documents: list[str],
    instruction: str | None,
    model: Any,
    tokenizer: Any,
) -> list[RerankResult]:
    """Rerank using Qwen3-Reranker (LM-style yes/no scoring)."""
    results = []

    # System prompt for Qwen reranker
    system = (
        "Judge whether the Document meets the requirements based on the Query "
        "and the Instruct provided. Note that the answer can only be 'yes' or 'no'."
    )

    for idx, doc in enumerate(documents):
        # Build prompt
        if instruction:
            user = f"<Instruct>: {instruction}\n\n<Query>: {query}\n\n<Document>: {doc}"
        else:
            user = f"<Query>: {query}\n\n<Document>: {doc}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        # Tokenize
        inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(model.device)

        # Get logits for yes/no tokens
        with torch.no_grad():
            outputs = model(inputs)
            logits = outputs.logits[:, -1, :]

        # Get yes/no token IDs
        yes_id = tokenizer.encode("yes", add_special_tokens=False)[0]
        no_id = tokenizer.encode("no", add_special_tokens=False)[0]

        # Compute probability of "yes"
        probs = torch.softmax(logits[:, [yes_id, no_id]], dim=-1)
        yes_prob = probs[0, 0].item()

        results.append(RerankResult(index=idx, score=yes_prob))

    # Sort by score descending
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def rerank_with_zerank(
    query: str,
    documents: list[str],
    instruction: str | None,
    model: Any,
) -> list[RerankResult]:
    """Rerank using zerank-2 (cross-encoder)."""
    # Prepend instruction to query if provided
    effective_query = f"{instruction}: {query}" if instruction else query

    # Build pairs
    pairs = [(effective_query, doc) for doc in documents]

    # Get scores
    scores = model.predict(pairs)

    # Build results
    results = [RerankResult(index=i, score=float(s)) for i, s in enumerate(scores)]

    # Sort by score descending
    results.sort(key=lambda r: r.score, reverse=True)
    return results


@app.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest) -> RerankResponse:
    """Rerank documents by relevance to query."""
    if not request.documents:
        return RerankResponse(results=[])

    try:
        model, tokenizer = get_model()

        if tokenizer is None:
            # zerank-2
            results = rerank_with_zerank(
                query=request.query,
                documents=request.documents,
                instruction=request.instruction,
                model=model,
            )
        else:
            # Qwen3-Reranker
            results = rerank_with_qwen(
                query=request.query,
                documents=request.documents,
                instruction=request.instruction,
                model=model,
                tokenizer=tokenizer,
            )

        return RerankResponse(results=results)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "model": MODEL_ID}


if __name__ == "__main__":
    # Load model on startup
    print(f"Loading model: {MODEL_ID}")
    get_model()
    print(f"Model loaded, starting server on {HOST}:{PORT}...")

    uvicorn.run(app, host=HOST, port=PORT)
