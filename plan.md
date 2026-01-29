Below is a **reworked “v1 improved plan”** optimized for:

* **frictionless install** (localhost-first, “one command” feel)
* **high correctness** (local file authority, line ranges)
* **good retrieval quality** (hybrid dense + lexical, optional rerank)
* **no auth / VPN by default** (but with a clean “advanced remote” path that still *feels* like localhost via tunneling)

I’m going to write it like a README/architecture doc you can basically drop into the repo.

---

# Probe v1 (Localhost‑First, OSS‑Friendly)

## 0) Core principle

**Default experience: everything runs on the same machine, bound to `127.0.0.1`.**
That means: no VPN, no auth, no secrets, minimal weirdness with editor env handling.

> Important note: “separate computers on localhost” isn’t literally possible. `localhost` is per-machine.
> The clean way to keep the *developer experience* as “localhost” across machines is to use an SSH tunnel/port-forward so your laptop still talks to `127.0.0.1`, but traffic is forwarded to the other machine.

---

# 1) What you’re building

A **single project-scoped MCP server** that exposes:

1. `search(query, top_k=12, mode="auto") -> results`
2. `open_file(path, start_line, end_line) -> exact lines from disk`
3. `index_status() -> indexing health + stats`

…and a **local indexer** that keeps the project’s index fresh. For v1, the simplest UX is:

✅ **`probe serve --watch` runs both the MCP server and the watcher/indexer**
(no separate daemon/service required)

---

# 2) Default deployment: localhost only (no auth)

### Services (docker compose)

* **Qdrant** (vector DB)
* **TEI embed service** (Hugging Face Text Embeddings Inference)
* Optional: **Reranker service** (custom FastAPI service for Qwen-Reranker / zerank-2)

> The reranker service is a small custom FastAPI wrapper — TEI doesn't support these instruction-aware rerankers out of the box.

### Hard rule for the default profile

Bind everything to localhost only:

* `127.0.0.1:6333` for Qdrant
* `127.0.0.1:8080` for TEI embeddings
* `127.0.0.1:8083` for Reranker service (optional)

No API keys needed because nothing is reachable off-machine.

### TEI hardware requirements

* GPU requires **CUDA 12.2+** compatible drivers
* Minimum compute capability **7.5** (Turing architecture or newer)
  * ❌ V100 (7.0) — not supported in default GPU mode
  * ✅ RTX 20xx, 30xx, 40xx, A100, H100
* CPU inference requires **TEI v1.8.2+** (v1.8.0–v1.8.1 have MKL bugs with Qwen3)

### TEI Docker image tags (architecture-specific)

TEI images are built per GPU architecture. Use `TEI_IMAGE_TAG` env var in docker-compose:

| GPU | Image Tag |
|-----|-----------|
| A100 (Ampere 80) | `ghcr.io/huggingface/text-embeddings-inference:1.8` |
| A10/A40 (Ampere 86) | `ghcr.io/huggingface/text-embeddings-inference:86-1.8` |
| RTX 4000 series (Ada) | `ghcr.io/huggingface/text-embeddings-inference:89-1.8` |
| T4/RTX 2000 (Turing) | `ghcr.io/huggingface/text-embeddings-inference:turing-1.8` |
| CPU | `ghcr.io/huggingface/text-embeddings-inference:cpu-1.8` |

Default to Ampere 80 (`1.8`) and document how to override for other architectures.

### Platform notes

**Windows:** Requires WSL2 + Docker Desktop. GPU passthrough works via WSL2 CUDA (NVIDIA driver 470.76+). Same docker-compose as Linux.

**macOS (Apple Silicon):** No native CUDA. Options:
* **Rosetta 2** — run `cpu-1.8` via x86_64 emulation (slower but works)
* **SSH tunnel** — use the two-computer setup (Section 3) for better performance
* **Docker Model Runner (v2)** — Docker Desktop ≥4.40 (macOS) or ≥4.41 (Windows) includes a host-based inference engine with Metal acceleration. Containers call `http://model-runner.docker.internal` for embeddings (requires `extra_hosts: ["model-runner.docker.internal:host-gateway"]` in compose for Docker Engine users). Supports `ai/qwen3-embedding` and `ai/qwen3-reranker`. OpenAI-compatible API. This is the cleanest path for native Apple Silicon performance while keeping Qdrant in Docker.

**macOS (Intel):** CPU inference works natively via `cpu-1.8`. No GPU acceleration.

---

# 3) Optional "two-computer" setup without building auth

If users want Desktop GPU box + Laptop editor, keep your stack auth-free by using **tunnels** instead of inventing auth.

## Option A (recommended): SSH port forwarding

Desktop runs Qdrant/TEI/Reranker bound to `127.0.0.1`.
Laptop forwards ports to its own localhost:

```bash
ssh -N \
  -L 6333:127.0.0.1:6333 \
  -L 8080:127.0.0.1:8080 \
  -L 8083:127.0.0.1:8083 \
  user@gpu-desktop
```

Now your MCP server still uses:

* `QDRANT_URL=http://127.0.0.1:6333`
* `TEI_EMBED_URL=http://127.0.0.1:8080`
* `RERANKER_URL=http://127.0.0.1:8083` (if using `balanced` or `pro` preset)

**No auth needed** because the desktop services aren’t exposed to the LAN or internet.

## Option B: LAN mode (simple, less safe)

Bind services to `0.0.0.0` and connect by LAN IP.
This is “works instantly,” but you should label it as **unsafe on shared networks**.

## Option C: Cloudflared

Fine as an “advanced option,” but **only recommend with Cloudflare Access / tokens**. If someone exposes Qdrant/TEI publicly without auth, it’s a footgun.

## Optional lightweight auth toggle (don't build auth; just turn it on)

If a user insists on exposing Qdrant beyond localhost, Qdrant supports API keys via env vars like `QDRANT__SERVICE__API_KEY`. ([Qdrant][2])
Make it opt-in and document it as "production-ish mode".

TEI also supports Bearer token auth if exposed:

```bash
# In docker-compose or CLI
--api-key your_secret_key
# or env var
API_KEY=your_secret_key
```

Clients then use `Authorization: Bearer your_secret_key` header.

---

# 4) Models + presets (address VRAM & latency up front)

### Why presets

People will bounce if the first run OOMs. So ship a “pick your hardware” switch.

## Preset: `lite` (default)

* Embeddings: **Qwen3-Embedding-0.6B** (fast + low VRAM)
* Reranker: off by default
* Intended: laptops / modest GPUs / CPU fallback

TEI supports Qwen3 embedding models and shows example docker usage. ([GitHub][1])

## Preset: `balanced`

* Embeddings: **Qwen3-Embedding-4B** (via TEI)
* Reranker: **Qwen3-Reranker-0.6B** (via custom FastAPI service — instruction-aware)

## Preset: `pro`

* Embeddings: **Qwen3-Embedding-8B** (via TEI)
* Reranker: **zerank-2** (via custom FastAPI service — state-of-the-art instruction-following) ([Hugging Face][9])
  Qwen's model card recommends instruction-style query formatting for better retrieval. ([Hugging Face][3])

### Reranker instruction-following

Both Qwen3-Reranker and zerank-2 support **instruction-aware reranking** — you can steer what "relevant" means:

| Reranker | Instruction support |
|----------|---------------------|
| **Qwen3-Reranker-0.6B** | Instruction-aware (user-defined instructions supported) |
| **zerank-2** | Native instruction-following + normalized scores + confidence statistic |

**Example instructions:**
* `"prefer implementation code, not tests"`
* `"prioritize TypeScript files"`
* `"focus on error handling and retry logic"`
* `"only show async/await patterns"`

If your queries often need this kind of steering, zerank-2 is explicitly built around it. For simpler "find relevant code" queries, Qwen3-Reranker-0.6B is sufficient.

### Practical note on VRAM

* Running an 8B embedder + multi‑B reranker simultaneously often implies **"big GPU" territory** (and batching/context settings matter).
* Don't promise exact VRAM numbers; instead document:

  * what preset targets
  * "if you OOM: use lite/balanced, reduce batch size, lower top‑N rerank candidates, or disable rerank"

### Embedding dimensions and collections

Each embedding model produces different vector dimensions:

| Preset | Model | Dimensions |
|--------|-------|------------|
| `lite` | Qwen3-Embedding-0.6B | 1024 |
| `balanced` | Qwen3-Embedding-4B | 2560 |
| `pro` | Qwen3-Embedding-8B | 4096 |

Qdrant requires fixed vector size per collection. **Each preset uses its own collection** (e.g., `chunks_lite`, `chunks_balanced`, `chunks_pro`). Switching presets requires reindexing into the new collection.

### Reranker instruction formatting (internal detail)

The unified `instruction` parameter maps differently per reranker:

* **Qwen3-Reranker**: LM-style scoring via yes/no token logits. Uses this template:
  ```
  System: "Judge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be 'yes' or 'no'."
  User: "<Instruct>: {instruction}\n\n<Query>: {query}\n\n<Document>: {doc}"
  ```
* **zerank-2**: Cross-encoder style via `CrossEncoder.predict([(query, doc), ...])`. Instruction is prepended to query.

The reranker service handles this mapping internally — callers just pass `instruction`.

---

# 5) Data model (store minimal stuff in Qdrant)

**Goal:** keep Qdrant payload small and avoid storing full source code if possible.

### Collection setup (do this before indexing)

Create collection with proper indexes **before uploading data** — this lets HNSW build filter-aware links:

1. Create collection with correct vector dimension for the preset
2. Create **keyword payload indexes** for filtered fields:
   * `repo_id` (keyword)
   * `workspace_id` (keyword)
   * `file_path` (keyword)
   * `language` (keyword)
   * `chunk_kind` (keyword)

Without these indexes, every query scans all vectors before filtering — causing high CPU and slow queries under load.

### Qdrant vectors (2 retrieval signals)

* `dense`: embedding vector (from TEI)
* `sparse_bm25`: **BM25 sparse vector** generated by Qdrant server-side inference model `qdrant/bm25` ([Qdrant][4])

**Requirements:**
* Qdrant **≥1.15.2** (local BM25 inference added in this version)
* Sparse vector must be configured with **`Modifier.IDF`** for correct BM25 scoring:
  ```python
  sparse_vectors_config={
      "sparse_bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)
  }
  ```

Key detail: Qdrant notes that when doing inference at ingest time, **the input isn't stored unless you store it in payload**. ([Qdrant][4])
So you can compute BM25 without persisting the full text.

### BM25 configuration for code

Disable English stemming/stopwords — they break code identifier matching:

```python
client.upsert(
    collection_name=collection,
    points=[
        models.PointStruct(
            id=point_id,
            vector={
                "sparse_bm25": models.Document(
                    text=chunk_text,
                    model="qdrant/bm25",
                    options=models.Bm25Config(
                        language="none",  # Preserves exact tokens
                        avg_len=150       # Tune to your avg chunk size
                    )
                )
            },
            payload={...}
        )
    ]
)
```

**Why:** Default BM25 stems `getValue` → `getvalu` and removes `for`/`if` as stopwords. Code needs exact token matching.

**Consistency:** Use the same `Bm25Config` options at query time.

### Deterministic point IDs

Qdrant only accepts **UUID or u64** for point IDs — not arbitrary strings.

Use **UUIDv5** (deterministic, namespace-based) for idempotent upserts:

```python
import uuid
NAMESPACE = uuid.UUID('...your-fixed-namespace-uuid...')
point_id = uuid.uuid5(NAMESPACE, f"{workspace_id}:{file_path}:{start_line}:{end_line}")
```

Note: `chunk_hash` is intentionally **not** in the ID — it's used for staleness detection only. This way, when a chunk's content changes, the same position overwrites in place.

This ensures:
* Re-indexing the same chunk overwrites (no duplicates)
* "Delete stale chunks for file" is straightforward

### Qdrant payload (metadata)

* `repo_id` (string)
* `workspace_id` (string UUID; see below)
* `file_path` (repo-relative)
* `file_hash` (sha256 of file)
* `chunk_hash` (sha256 of chunk text, truncated to 16 chars — for staleness detection)
* `start_line`, `end_line`
* `language`
* `chunk_kind` (code/doc/config)
* optional: `symbol` (function/class name)
* `indexed_at` timestamp

### Snippets: generate locally + staleness detection

`search()` should return a short snippet, but generate it by reading local file lines (same mechanism as `open_file`).
This keeps DB clean and results consistent with the user's working tree.

**Staleness check:** When generating the snippet, hash the lines and compare to stored `chunk_hash`. If mismatch:
* Return `stale: true` in the result (lets agent know index is behind)
* Optionally queue that file for reindexing in the background

---

# 6) Workspace identity (fix the clone/path edge cases)

**Don’t hash machine-id + path.** That causes weirdness with multiple clones, moves, tests.

Instead:

* On `probe init`, generate a **workspace UUID** and store it in `.probe/config.json`.
* That UUID becomes `workspace_id` forever for that working copy.

This makes:

* multiple clones on one machine safe
* repo moves safe
* no collisions from "same machine-id, same path hash"

> **Gitignore:** Add `.probe/` to your project's `.gitignore` by default. If a team wants shared workspace identity across clones (e.g., shared Qdrant cache), they can commit it explicitly.

---

# 7) Indexing & freshness (simple but SOLID)

## Storage: local manifest SQLite

Keep a local manifest database for correctness and resumability:

**Files table** (per file):

* `file_path` (primary key)
* `mtime`, `size` (fast skip)
* `file_hash` (correctness)
* `last_indexed_at`
* `last_error`

**Chunks table** (per chunk):

* `file_path`, `start_line`, `end_line`
* `chunk_hash`
* `point_id` (Qdrant point ID)
* `chunk_idx` (0-based index within file — enables neighbor expansion via `chunk_idx ± 1`)

**Workspace metadata**:

* `workspace_id`
* `last_seen_at` (updated on MCP server start — for prune command)
* `current_preset` (tracks which collection is in use)
* `embedding_model_id` (e.g., `Qwen/Qwen3-Embedding-0.6B`)
* `embedding_dimensions` (auto-detected at startup; see below)

### Index identity = embedding config

On startup, call TEI's embed endpoint once with a test string and record the actual returned vector dimension. Store this in the manifest alongside the model ID. If a mismatch is detected later (e.g., user switched presets but didn't reindex), `index_status()` should warn: `"index_config_mismatch": true` — and `search()` should return an error rather than garbage results.

## Incremental algorithm

1. Enumerate files (respect `.gitignore`, plus your default ignore list)
2. If `(mtime,size)` unchanged: skip
3. Else hash; if changed:

   * **delete all existing points for that `(workspace_id, file_path)`** — this is simpler and safer than trying to diff chunk ranges, since line numbers shift on edits
   * rechunk the file
   * upsert new chunks with fresh vectors
4. If file deleted: delete all points for that `(workspace_id, file_path)`

## Watcher (inside `serve --watch`)

* trailing debounce: **3s**
* max wait: **30s**
* “file stable” check: wait ~250–500ms for size/mtime to stop changing

## Big repo protection

If >N events quickly (e.g. checkout/rebase):

* stop per-file updates
* schedule a single incremental scan soon

## Periodic rescan fallback

File watchers miss events (editor temp files, network FS, mass renames). Add a lightweight background scan as insurance:

* Every **15 minutes**, enumerate files and check `(mtime, size)`
* Only hash/reindex files where these changed
* Doesn't replace watcher — just catches what it misses

## Branch-switch coverage without hook conflicts

**Don't install git hooks by default.** They conflict with Husky/pre-commit setups.

Instead:

* watcher detects `.git/HEAD` change and schedules a scan
* offer optional hooks as a *manual* snippet for users who want it

## Error behavior (graceful degradation)

| Scenario | Behavior |
|----------|----------|
| **Qdrant unreachable on startup** | Retry 3x with backoff. If still down: start MCP server anyway, `search()` returns clear error. Log warning. |
| **TEI errors mid-indexing** | Log error, mark file as `last_error` in manifest, skip it, continue. Don't crash. |
| **Watcher crashes** | Log error, attempt restart (max 3 retries). After that, warn via `index_status()` (`watcher_running: false`). MCP server stays up with stale index. |
| **Qdrant dies mid-session** | `search()` returns error. `index_status()` shows `backend_reachable: false`. Watcher pauses, retries periodically. |

**Principle:** Degrade gracefully, never crash the whole thing, surface all errors via `index_status()`.

Note: If backend is down, the agent (Claude Code / Cursor / Codex) will fall back to its built-in file reading and grep — it's not helpless without RAG.

---

# 8) Chunking (code-aware, plus context fixes)

## For code

* AST-aware chunking (tree-sitter) into functions/classes/modules
* min ~20-30 lines, max ~250 lines
* **Exception:** semantic units (functions, classes) are kept whole regardless of size — a 10-line function is its own chunk
* only overlap when splitting huge blocks (20–40 lines)

### Tree-sitter bundling

* Use `tree-sitter-language-pack` — pre-built wheels for 165+ languages, no grammar compilation needed ([PyPI][10])
* For unsupported languages: fall back to line-based chunking (150 lines, 30-line overlap)
* Embeddings (Qwen) work on any text regardless — tree-sitter only affects chunking quality

### Token limits

All Qwen3 embedders have 32k+ context. The 250-line max chunk (~1000 tokens typical) is well within limits — no truncation concerns.

### Fix "adjacent function context" cheaply

Add 2 lightweight enhancements:

1. **Header chunk per file**: imports + top-level constants/types
2. **Neighbor expansion**: after final ranking, expand **top 5 results** by including their immediately adjacent chunks (prev/next) as related results

This catches "helper function is right above" situations without adding noise to all 50 candidates.

## Docs/config

* markdown by headings
* yaml/toml/json by top-level blocks
* cap by line ranges

---

# 9) Retrieval pipeline (fast default, quality option)

### Step 0: cache

Add an in-memory LRU cache:

* key: `(workspace_id, index_generation, query, top_k, mode, instruction)`
* value: final results

Increment `index_generation` **per scan completion** (not per file):
* After watcher debounce completes and all pending files are indexed → increment
* After `probe scan` completes → increment
* Single file upserts don't increment until the batch is done

This gives good cache hit rates while still invalidating when meaningful changes land.

### Concurrency limits / backpressure

Since `serve --watch` runs indexing and search in the same process:

* Limit parallel embedding requests (e.g., semaphore with max 4 concurrent)
* Limit rerank queue length
* Prioritize `search()` over background indexing to keep queries responsive

This prevents indexing from starving search latency.

## Step 1: Dense retrieval

* Embed query using a stable instruction template (Qwen recommends instruction-style queries for better retrieval; they note ~1–5% drop without query instruct in many retrieval scenarios). ([Hugging Face][3])
* Qdrant dense search top `K_dense` (e.g. 30–50) filtered by `repo_id + workspace_id`

## Step 2: Lexical retrieval (clear + specified)

Use BM25 sparse vectors in Qdrant:

* Query sparse top `K_sparse` (e.g. 30–50) using BM25
  Qdrant documents BM25 + sparse vectors for full-text search and provides a server-side BM25 inference model. ([Qdrant][5])

> **Known limitation:** Qdrant's default BM25 tokenizer splits on word boundaries — `getUserName` is one token, not three. Dense retrieval compensates for this; code-aware tokenization is a v2 consideration.

## Step 3: Fuse (Qdrant-side RRF)

Use Qdrant's built-in fusion via Query API (single round-trip, since v1.10.0):

```python
response = client.query_points(
    collection_name=collection,
    prefetch=[
        models.Prefetch(query=dense_vec, using="dense", limit=50),
        models.Prefetch(query=sparse_query, using="sparse_bm25", limit=50)
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    with_payload=True,
    limit=30  # fused candidates for rerank or final output
)
```

Both searches run concurrently server-side; Qdrant handles the RRF merge.

## Step 4 (optional): Rerank

Two modes:

### `mode="fast"` (default)

* skip rerank
* return fused top 10–12

### `mode="quality"`

* rerank only top **N=15–25** candidates (not 50)
* call custom reranker service (`POST /rerank`) with Qwen-Reranker or zerank-2
* if `instruction` provided, pass it to the reranker for steering (e.g. "prefer implementation, not tests")
* enforce a timeout (e.g. 300ms) and fallback to RRF ordering if exceeded

**This directly addresses reranker latency.** You’re not forcing every query through a heavy second stage.

## Step 5: Dedup + merge adjacent

* dedup by `(path,start,end)`
* merge nearby ranges in same file within ~20 lines to reduce noise

---

# 10) MCP tool contract (minimal & agent-friendly)

## Tool: `search(query, top_k=12, mode="auto", instruction=null, filters=null)`

**Parameters:**
* `query`: the search query
* `top_k`: number of results to return (default 12)
* `mode`: `"fast"` (no rerank), `"quality"` (with rerank), or `"auto"` (quality if reranker available)
* `instruction` (optional): steering instruction for the reranker, e.g. `"prefer implementation, not tests"` — requires `balanced` or `pro` preset with reranker enabled
* `filters` (optional): pre-filter before vector search — leverages payload indexes for fast filtering
  * `languages`: `["python", "typescript"]` — filter by detected language
  * `chunk_kinds`: `["code", "doc"]` — filter by chunk type
  * `include_globs`: `["src/**"]` — only match these paths
  * `exclude_globs`: `["**/*.test.*", "**/__tests__/**"]` — exclude these paths

**Returns** list of results:

* `repo_id`
* `workspace_id`
* `path`
* `start_line`, `end_line`
* `snippet` (first 15-20 lines of chunk, generated locally from disk; use `open_file()` for full content)
* `score` (final)
* `stale` (bool) — `true` if `chunk_hash` doesn't match current file content (index is behind working tree)
* optional `signals`: `{ dense_rank, bm25_rank, rerank_score }` — `rerank_score` only present when `mode="quality"`
* `source`: `"path#Lstart-Lend"`

## Tool: `open_file(path, start_line, end_line)`

* validates path sandbox under project root
* **resolves symlinks** via `realpath()` and rejects if target escapes project root
* returns exact lines with line numbers
* returns `file_hash`, `mtime` so agent can notice drift

## Tool: `index_status()`

* `watcher_running`
* `last_scan_time`
* `files_indexed`, `chunks_indexed`
* `index_generation`
* `backend_reachable` + `last_error`
* `current_preset` (lite/balanced/pro)
* **Capability flags**:
  * `dense_available`: bool (TEI reachable)
  * `bm25_available`: bool (Qdrant supports server-side BM25)
  * `reranker_available`: bool (reranker service reachable)
* **Progress during indexing** (when active):
  * `indexing_in_progress`: bool
  * `progress`: `{ phase, files_scanned, files_total, chunks_embedded, chunks_total }`

This prevents the "it's dumb" confusion and lets agents/users see indexing progress and available features.

---

# 11) Orphan cleanup (stale workspace chunks)

Add one command:

## `probe prune`

* lists workspaces in Qdrant with last indexed time
* deletes ones not seen recently
* optional `--older-than 30d`

### Workspace registry in Qdrant (not just local SQLite)

**Problem:** If you rely only on local SQLite for workspace tracking, orphans leak when:
* Repo folder is deleted
* `.probe/` is wiped
* Machine is gone

**Solution:** Store one lightweight workspace record **in Qdrant** (separate `workspaces` collection):

```python
# On MCP server start, upsert workspace meta
{
    "id": workspace_id,  # UUID
    "repo_id": repo_id,
    "last_seen_at": now(),
    "preset": "balanced"
}
```

On MCP server start:
1. Upsert workspace record in Qdrant `workspaces` collection
2. Update `last_seen_at` in local SQLite (for local queries)

`prune` reads from **Qdrant** (not local SQLite) to find stale workspaces, then deletes all points matching those `workspace_id` values.

This keeps per-chunk updates cheap while ensuring orphans can always be cleaned up.

---

# 12) Setup flow (what users actually do)

## One-time: install probe + backend

```bash
# Install probe CLI (pick one)
curl -fsSL https://raw.githubusercontent.com/EfrainTorres/probe/main/install.sh | sh
uv tool install probe                           # if you use uv
pipx install probe                              # if you use pipx

# Bring up backend services
docker compose --profile lite up -d   # or: balanced, pro
```

## Per repo:

```bash
probe init
probe serve --watch
```

That's it for v1.

---

# 13) Client wiring (Cursor / Claude Code / Codex)

### Claude Code

* Project scope: `.mcp.json`
* Supports `${VAR}` and `${VAR:-default}` expansion in command/args/env/url/headers. ([Claude Code][6])

### Codex

* MCP config stored in `~/.codex/config.toml`, or project-scoped `.codex/config.toml` (trusted projects)
* Uses `[mcp_servers.<server-name>]` tables and supports STDIO servers. ([OpenAI Developers][7])

### Cursor

Cursor’s UI creates an `mcp.json` and expects the `mcpServers` JSON shape; an example workflow and config shape is shown in the Cursor setup steps in Omni’s MCP instructions. ([Omni Docs][8])
(Also: Cursor env-var interpolation support is historically inconsistent; defaulting to “no secrets needed” avoids this class of issue.)

---

# 14) V1 implementation checklist (what to build first)

## Repo structure

**Language:** Python 3.12+

* `probe/` — Main package
  * `__init__.py` — Version, exports
  * `__main__.py` — `python -m probe` entry
  * `config.py` — Load `.probe/config.json`, env vars
  * `types.py` — Shared Pydantic models (Chunk, SearchResult, etc.)
  * `server.py` — MCP stdio server + tool handlers (search, open_file, index_status)
  * `indexing.py` — Pipeline: scan → chunk → embed → store
  * `retrieval.py` — Pipeline: dense → sparse → fusion → rerank
  * `cli.py` — Commands (init, serve, scan, prune, doctor)
  * `chunking/` — Directory (multiple strategies)
    * `__init__.py` — Exports `chunk()` dispatcher
    * `tree_sitter.py` — AST-aware chunking
    * `text.py` — Markdown + line-based fallback
  * `storage/` — Directory (distinct backends)
    * `__init__.py` — Exports
    * `qdrant.py` — Vector storage client
    * `manifest.py` — SQLite file/chunk tracking
* `tests/` — pytest tests mirroring `probe/` structure
* `services/reranker/` — FastAPI reranker service (Dockerfile included)
* `deploy/docker-compose.yml` — Qdrant + TEI + optional reranker (profiles: `lite`, `balanced`, `pro`)
* `pyproject.toml` — Dependencies, CLI entry point
* `docs/` — Presets guide, troubleshooting

## Build in this order

1. **MCP server skeleton** (stdio) + `open_file` sandboxing
2. **Chunker** (tree-sitter + fallback)
3. **Manifest SQLite** + incremental scan
4. **Qdrant upsert + delete stale**
5. **Dense retrieval** (TEI embeddings)
6. **BM25 retrieval** (Qdrant `qdrant/bm25` sparse) ([Qdrant][4])
7. **Hybrid search** (Qdrant Query API with RRF fusion) + return results w/ local snippets
8. **Watcher inside serve** + debounce + big-change protection
9. **index_status**
10. **Caching**
11. **`probe doctor`** — health check: Qdrant reachable, TEI reachable, one test embed (verify dims match collection), BM25 inference works, reranker reachable (if configured). Low effort, huge support-time savings.
12. **Optional rerank mode via custom reranker service** (Qwen-Reranker / zerank-2)
13. **Prune command**

---

# 15) What this buys you (why it’s the “sweet spot”)

* **Install is easy**: docker compose + one binary, no network complexity
* **Correctness is high**: the only “truth” is local disk via `open_file`
* **Speed is good**: caches + fast mode + smaller rerank candidate sets
* **Hybrid retrieval is real**: dense + BM25 (not vague “keyword search”) ([Qdrant][5])
* **Advanced users can scale**: SSH tunnel makes remote GPU feel like localhost

---

If you want next: I can draft the **exact tool JSON schema** (the "shape" that nudges agents to cite and call `open_file`), plus a concrete **docker-compose with profiles** (`lite`, `balanced`, `pro`) and a "copy/paste" **`.mcp.json` + Codex config.toml examples**.

---

# 16) V2 ideas (not v1 scope)

Brief list of polish/UX improvements for later:

* **`probe up`** — wrapper that auto-detects GPU architecture via `nvidia-smi`, sets `TEI_IMAGE_TAG`, runs `docker compose up`
* **Code-aware BM25 tokenization** — custom tokenizer that splits `getUserName` → `get`, `User`, `Name` for better lexical recall
* **Preset auto-detection** — detect available VRAM on startup, suggest/default to appropriate preset
* **Single-binary distribution** — bundle TEI + Qdrant as optional embedded mode for "zero docker" installs
* **Apple Silicon native support** — `docker-compose.apple.yml` profile using Docker Model Runner for Metal-accelerated embeddings/reranking. Skips TEI container, points at `http://model-runner.docker.internal`. Requires Docker Desktop ≥4.40 (macOS). Models: `ai/qwen3-embedding`, `ai/qwen3-reranker`.

---

# 17) Distribution

## Install methods (priority order)

1. **Binary** (recommended) — No Python required
   ```bash
   curl -fsSL https://raw.githubusercontent.com/EfrainTorres/probe/main/install.sh | sh
   ```

2. **uv tool** / **pipx** — For Python users
   ```bash
   uv tool install probe   # or: pipx install probe
   ```

3. **Source** — For contributors
   ```bash
   git clone https://github.com/EfrainTorres/probe && cd probe && uv sync
   ```

## CI/CD (GitHub Actions)

On tagged release (`v*`):

1. **PyPI publish** — Trusted Publishing via OIDC (tokenless) ([PyPI Docs][11])
2. **Binary builds** — PyInstaller matrix:

   | Runner | Output |
   |--------|--------|
   | `ubuntu-latest` | `probe-linux-x64` |
   | `ubuntu-24.04-arm` | `probe-linux-arm64` |
   | `macos-latest` | `probe-darwin-arm64` |
   | `macos-15-intel` | `probe-darwin-x64` |
   | `windows-latest` | `probe-windows-x64.exe` |

3. **GitHub Release** — binaries + SHA256 checksums attached

## Install script

* Detects OS and architecture
* Downloads correct binary from GitHub Releases
* Verifies SHA256 checksum
* Places in `~/.local/bin` (Linux/macOS) or prompts for location (Windows)

[1]: https://github.com/huggingface/text-embeddings-inference "GitHub - huggingface/text-embeddings-inference: A blazing fast inference solution for text embeddings models"
[2]: https://qdrant.tech/documentation/guides/security/ "Security - Qdrant"
[3]: https://huggingface.co/Qwen/Qwen3-Embedding-8B "Qwen/Qwen3-Embedding-8B · Hugging Face"
[4]: https://qdrant.tech/documentation/concepts/inference/ "Inference - Qdrant"
[5]: https://qdrant.tech/documentation/guides/text-search/ "Text Search - Qdrant"
[6]: https://code.claude.com/docs/en/mcp "Connect Claude Code to tools via MCP - Claude Code Docs"
[7]: https://developers.openai.com/codex/mcp/ "Model Context Protocol"
[8]: https://docs.omni.co/ai/mcp/cursor "Using the MCP Server in Cursor - Omni Docs"
[9]: https://huggingface.co/zeroentropy/zerank-2 "zeroentropy/zerank-2 · Hugging Face"
[10]: https://pypi.org/project/tree-sitter-language-pack/ "tree-sitter-language-pack · PyPI"
[11]: https://docs.pypi.org/trusted-publishers/using-a-publisher/ "Publishing with a Trusted Publisher · PyPI Docs"
