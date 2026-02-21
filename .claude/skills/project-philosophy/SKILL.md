---
name: project-philosophy
description: Design philosophy for TasteBud. Guiding principles behind every architectural decision.
disable-model-invocation: false
user-invocable: false
---

# Design Philosophy

These principles guide every decision in TasteBud. They are non-negotiable.

## 1. Plan Before Code

Before implementing a non-trivial feature, **discuss the design first**:

- Clarify requirements and edge cases with the user
- Propose architecture and ask questions before writing code
- Identify which layers are affected and how dependencies flow
- Only start coding after alignment on the approach

## 2. Value Chain as Architecture

The core value chain **Collect → Analyze → Score → Feedback → Learn** maps directly to the codebase:

- **collector/** — Fetches content from external sources. Pure I/O.
- **analyzer/** — Extracts and normalizes tags from collected content.
- **engine/** — Scores content against user preferences.
- **services/** — Orchestrates feedback processing and recommendation.
- **api/** — HTTP interface. Thin layer over services.
- **core/** — Shared infrastructure: config, database, exceptions, logging.

Each layer has exactly one job. Data flows forward through the chain.

## 3. Repository Pattern for Data Access

All database access goes through repository classes. Never use SQLAlchemy sessions directly in services or API routes.

- `BaseRepository[T]` — generic CRUD operations
- Concrete repos add domain-specific queries
- Repositories receive sessions via dependency injection

## 4. Async All the Way

All I/O is `async/await`. Database sessions, HTTP clients, file operations — everything async from the ground up.

SQLAlchemy async engine + `asyncio` sessions. `httpx.AsyncClient` for external APIs.

## 5. Configuration via Environment

`pydantic-settings` loads config from environment variables and `.env` files. One `Settings` class, no scattered `os.getenv()` calls.

SQLite is the default database — zero setup for development. PostgreSQL can be swapped in via `DATABASE_URL`.

## 6. Self-Validating Layers

Each layer validates its own inputs. The collector validates API responses, the analyzer validates tag formats, the scorer validates weight ranges.

No central validation layer. Each boundary is responsible for its own contracts.

## 7. Guard Clause Style

Prefer positive `if` → do work → return. Errors and edge cases go at the bottom. Happy path reads top-down.

## 8. Convention Over Configuration

- Consistent naming: `*Repository`, `*Service`, `*Collector`, `*Analyzer`
- Predictable file locations: `models/user.py` has the `User` model
- No factory registries — import what you need directly

## 9. No Empty `__init__.py`

Only create `__init__.py` when package-level exports are genuinely needed. Empty init files are noise.

## 10. Preserve Existing Logic

Never accidentally delete or overwrite working code. When modifying a file, understand what exists first, then make targeted changes.

## 11. Code Does Mechanics, AI Does Decisions

In future AI-powered features (smart recommendations, content analysis), code handles traversal, I/O, and formatting. AI handles interpretation and judgment.

## 12. Minimal Dependencies

Only add dependencies that earn their keep. Prefer stdlib solutions when they're adequate. Every dependency is a maintenance burden.
