# Probe

Project-scoped RAG for AI coding agents. Hybrid dense + BM25 retrieval, localhost-first.

## Install

```sh
# 1. Start services (pick your hardware)
docker compose --profile lite up -d      # Laptops / modest GPUs
docker compose --profile balanced up -d  # Mid-range GPUs (~8GB VRAM)
docker compose --profile pro up -d       # High-end GPUs (~16GB+ VRAM)

# 2. Initialize your project
cd /path/to/your/project
probe init

# 3. Start the server
probe serve --watch
```

That's it. Add to your editor's MCP config and go.

## Presets

| Preset | Embedding Model | Reranker | Use Case |
|--------|-----------------|----------|----------|
| `lite` | Qwen3-Embedding-0.6B | — | Laptops, CPU, quick iteration |
| `balanced` | Qwen3-Embedding-4B | Qwen3-Reranker-0.6B | Good quality, reasonable VRAM |
| `pro` | Qwen3-Embedding-8B | zerank-2 | Best quality, needs big GPU |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_URL` | http://127.0.0.1:6333 | Vector database |
| `TEI_EMBED_URL` | http://127.0.0.1:8080 | Embedding service |
| `RERANKER_URL` | http://127.0.0.1:8083 | Reranker (balanced/pro only) |
| `TEI_IMAGE_TAG` | 1.8 | TEI Docker image version |

### GPU Architecture

Override `TEI_IMAGE_TAG` for your GPU:

| GPU | Tag |
|-----|-----|
| A100 (Ampere 80) | `1.8` (default) |
| A10/A40 (Ampere 86) | `86-1.8` |
| RTX 4000 series (Ada) | `89-1.8` |
| T4/RTX 2000 (Turing) | `turing-1.8` |
| CPU | `cpu-1.8` |

```sh
TEI_IMAGE_TAG=turing-1.8 docker compose --profile lite up -d
```

## CLI

```sh
probe init              # Initialize workspace
probe serve --watch     # Run MCP server + file watcher
probe scan              # Force reindex
probe prune             # Clean orphan workspaces
probe doctor            # Health check
```

## Editor Setup

### Claude Code

Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "probe": {
      "command": "probe",
      "args": ["serve", "."]
    }
  }
}
```

### Cursor

Add to your MCP settings (Settings > MCP):

```json
{
  "mcpServers": {
    "probe": {
      "command": "probe",
      "args": ["serve", "."]
    }
  }
}
```

### Codex

Add to `~/.codex/config.toml` or project `.codex/config.toml`:

```toml
[mcp_servers.probe]
command = "probe"
args = ["serve", "."]
```

## Troubleshooting

**OOM on startup**: Use a lighter preset or reduce batch size.

**TEI won't start on CPU**: Use TEI v1.8.2+ (`cpu-1.8`). Versions 1.8.0-1.8.1 have MKL bugs with Qwen3.

**V100 not working**: V100 (compute 7.0) isn't supported. Use CPU mode or upgrade GPU.

**Switching presets**: Requires full reindex (each preset uses different vector dimensions).

## Two-Computer Setup

GPU box + laptop? Use SSH tunnels instead of exposing services:

```sh
# On laptop: forward ports from GPU box
ssh -N \
  -L 6333:127.0.0.1:6333 \
  -L 8080:127.0.0.1:8080 \
  -L 8083:127.0.0.1:8083 \
  user@gpu-desktop
```

Now your laptop talks to `127.0.0.1` — no auth needed.

## License

MIT
