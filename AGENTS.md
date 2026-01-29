# Probe

We're building a powerful RAG memory for agentic coders that uses native MCP for Claude, Cursor, and Codex. It needs to be stupid simple to install and use for the end user.

> **What goes here**: Development principles, build/test commands, contributor boundaries, git workflow.
> **What goes in README.md**: User installation, configuration, troubleshooting.
> **What goes in RECON_REPORT.md**: Architecture, file structure, module guide (auto-generated, do not modify).

---

## Principles

### The Core Problem
These principles are counterweights. Applied in isolation, each creates its own pathology:

| Principle alone | What goes wrong |
|-----------------|-----------------|
| KISS alone | Monolithic files, everything dumped together |
| SRP alone | Hundreds of tiny fragments, impossible to trace flow |
| DRY alone | Wrong abstractions that couple unrelated things |
| YAGNI alone | No structure, chaos accumulates |

**The goal is equilibrium, not maximizing any single principle.**

### Hierarchy
1. **YAGNI** — Gate: Should we build this at all?
2. **KISS** — Ceiling: Is this simple enough to understand?
3. **SRP** — Boundaries: Does each piece have one reason to change?
4. **DRY** — Refinement: Is this duplication actually the same concept?

Work top-to-bottom. Don't jump to DRY before passing through YAGNI and KISS.

### YAGNI (The Gate)
> "Do I need this today, or am I designing for a hypothetical future?"

**Signs**: "We might need to swap this out later", "What if we need to support X?", "Let's make this configurable just in case", interface with one implementation.

**Fix**: Build the concrete thing. Refactor when (if) the second use case actually arrives.

### KISS (The Ceiling)
> "Could someone new understand this in under 5 minutes?"

Not about fewer files or shorter code — it's about cognitive load. One 400-line file can be simpler than ten 40-line files if the logic is sequential.

**Signs**: Need a diagram to explain file structure, understanding one function requires jumping through 5 files, abstractions exist to "organize" rather than solve, you're proud of how clever it is.

**Fix**: Inline the abstraction. Flatten the hierarchy. Make the common path obvious.

### SRP (The Boundaries)
> "Does this module have one reason to change?"

Not "one function" — one *reason to change*. A file can have multiple functions if they change together.

**Good boundaries**:
- External service changes → one client module changes
- Data schema changes → one types/models module changes
- Algorithm changes → one core module changes
- Protocol/API changes → one handler module changes

**Signs**: File imports from everywhere, unrelated features touch same file, can't name file without "and" or "utils".

**Fix**: Split along axis of change, not arbitrary lines.

### DRY (Apply Last)
> "Is this duplication accidental (same concept) or incidental (looks similar, different purpose)?"

Two pieces of code that look identical may serve different purposes, evolve differently, or be coincidentally similar today.

**Rule of Three**: Don't extract until you've seen the same concept 3 times AND those copies would change together.

**Extract**: Config loading, error handling, service clients, validation logic.
**Don't extract**: Things that look similar but serve different domains, "just in case" abstractions, tiny utilities that obscure more than help.

### Decision Framework
```
1. YAGNI: Do I need this now?
   No  → Don't build it
   Yes ↓

2. KISS: Is the simplest approach sufficient?
   Yes → Do that
   No  ↓

3. SRP: What's the minimal structure needed?
   → Create only the boundaries required

4. DRY: Am I repeating the same concept 3+ times?
   No  → Duplication is fine
   Yes → Extract it
```

### Litmus Tests
| Test | Question |
|------|----------|
| Explain | Can I describe what this file does in one sentence? |
| Change | If requirement X changes, how many files do I touch? (1-2 target) |
| Delete | Could I delete this module without cascading changes? |
| Onboard | Could a new dev understand this without explanation? |

### Meta-Principle
**Optimize for deletion, not extension.**

Write code so that when requirements change, you can delete cleanly rather than modify carefully.

- Small, focused modules → safe to delete
- Clear boundaries → deletions don't cascade
- No premature abstractions → nothing sacred to preserve
- Concrete implementations → easy to rip out and replace

If your code is easy to delete, it's maintainable. If deleting something is terrifying, you've over-coupled.

### File Size
| Situation | Guideline |
|-----------|-----------|
| Too big | Can't hold file's purpose in head → split |
| Too small | Understanding requires many jumps → merge |
| Sequential logic | Keep together (200-500 lines fine) |
| Independent concerns | Split even if small |

**Warning**: >600 lines = probably too much. <50 lines = probably over-fragmented. "utils" growing unbounded = concepts are leaking.

### Common Traps
| Trap | Looks like | Fix |
|------|------------|-----|
| Premature abstraction | Interface with 1 impl | Use concrete type |
| Utility drawer | utils.py grows forever | Split by concept or inline |
| Config explosion | Everything configurable | Hardcode defaults |
| Inheritance hierarchy | Base class with template methods | Composition with plain functions |
| DRY zealotry | Abstraction serves 2 needs poorly | Duplicate and diverge |

### Summary
```
┌─────────────────────────────────────────────────────┐
│  Don't build it              (YAGNI)                │
│       ↓                                             │
│  Build it simply             (KISS)                 │
│       ↓                                             │
│  Split by reason to change   (SRP)                  │
│       ↓                                             │
│  Extract only proven duplication   (DRY)            │
└─────────────────────────────────────────────────────┘
```
**A little duplication is cheaper than the wrong abstraction.**

---

## Commands

### Install
```sh
uv sync
```

### Test
```sh
pytest
```

### Type Check
```sh
mypy .
```

### Lint
```sh
ruff check . --fix
```

### Docker
```sh
docker compose --profile lite up -d
docker compose --profile balanced up -d
docker compose --profile pro up -d
```

### CLI
```sh
probe init
probe serve --watch
probe scan
probe prune --older-than 30d
probe doctor
```

## File-Scoped

```sh
mypy <file>                     # Type check
ruff check <file> --fix         # Lint
pytest <file>                   # Test
```

---

## Environment

### Requirements
| Tool | Version |
|------|---------|
| Python | 3.12+ |
| uv | latest (recommended) |
| Docker | GPU or CPU |

---

## Verification

### Before Commit
- [ ] `pytest` passes
- [ ] `mypy .` passes
- [ ] `ruff check .` passes

### Before PR
- [ ] `probe doctor` healthy
- [ ] Affected MCP tools tested

---

## Boundaries

### ✅ Always
- Run tests before commit
- Use preset-specific collection names
- Resolve symlinks before file reads
- Validate paths against project root

### ⚠️ Ask First
- Qdrant collection schema changes
- Docker profile modifications
- Adding/removing MCP tools
- SQLite manifest schema changes

### 🚫 Never
- Bind to 0.0.0.0 in default profile
- Store source code in Qdrant payloads
- Skip sandbox validation in open_file
- Use content hash in point IDs
- Commit secrets

---

## Git

### Branches
`feature/<desc>` · `fix/<desc>` · `docs/<desc>`

### Commits
`feat:` · `fix:` · `docs:` · `refactor:` · `test:` · `chore:`

---

## Project-Specific

### Constraints
- Each preset = separate collection (dimensions differ)
- Workspace ID = UUID in `.probe/config.json`
- Point IDs = UUIDv5 from position, not content
- BM25 uses `language="none"` (no stemming)
- Switching presets requires full reindex

---

## Codebase Overview

MCP server providing semantic code search for AI assistants. Indexes codebases using text embeddings (TEI), stores vectors in Qdrant, and supports hybrid dense+sparse retrieval with optional cross-encoder reranking.

**Stack**: Python 3.12+, Qdrant, TEI, Docker

**Structure**:
- `probe/chunking/` — File → semantic chunks (tree-sitter, markdown, structured, line-based)
- `probe/indexing/` — Workspace scan → chunk → embed → store
- `probe/retrieval/` — Dense + sparse search → fusion → rerank → results
- `probe/storage/` — Qdrant vectors + SQLite manifest
- `probe/server/` — MCP tools (search, open_file, index_status)
- `probe/cli/` — Commands (init, serve, scan, prune, doctor)

For detailed architecture and health analysis, see [docs/RECON_REPORT.md](docs/RECON_REPORT.md).

---

## References

### Internal
| Doc | Purpose |
|-----|---------|
| README.md | User install & config |
| plan.md | Architecture |
| docs/RECON_REPORT.md | Auto-generated structure & health |

### External
| Resource | URL |
|----------|-----|
| Qdrant | https://qdrant.tech/documentation/ |
| TEI | https://huggingface.co/docs/text-embeddings-inference |
| MCP | https://modelcontextprotocol.io/ |
| MCP Python SDK | https://github.com/modelcontextprotocol/python-sdk |
| uv | https://docs.astral.sh/uv/ |
