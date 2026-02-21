# TasteBud — Project Instructions

## What is this?

TasteBud is a multi-user content curation platform. Core value chain: **Collect → Analyze → Score → Feedback → Learn**.

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy (async), SQLite (default), Pydantic
- **Frontend**: React + TypeScript + Vite
- **Tooling**: uv (package manager), ruff (linter/formatter), mypy (type checker), pytest (tests)

## Project Layout

```
backend/                 Python backend (独立项目)
  src/tastebud/          Python package (src layout)
    core/                Config, database, exceptions, logging
    models/              SQLAlchemy ORM models
    repositories/        Data access layer (BaseRepository pattern)
    collector/           Content ingestion from external sources
    analyzer/            Tag extraction and normalization
    engine/              Scoring engine
    services/            Business logic orchestration
    api/                 FastAPI routes (versioned under v1/)
    main.py              FastAPI application entry point
  tests/                 pytest tests
  pyproject.toml         Python project config + dependencies
  uv.lock                Dependency lock file

frontend/                React frontend (独立项目)
  src/                   React + TypeScript source
  package.json           Node project config + dependencies
  vite.config.ts         Vite config
```

## Commands

```bash
# Backend (run from backend/)
cd backend
uv run pytest                    # Run tests
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run mypy src/                 # Type check
uv run python -m tastebud        # Start server
# Frontend (run from frontend/)
cd frontend
npm install                      # Install dependencies
npm run dev                      # Dev server
npm run build                    # Production build
```

## Conventions

- All I/O is async (`async/await` everywhere)
- SQLite-compatible types only in ORM models
- All database access through repository classes, never raw sessions in routes
- API responses use Pydantic schemas, not ORM models
- Absolute imports: `from tastebud.core.config import settings`
- No empty `__init__.py` files
- Structlog for logging
- Guard clause style: happy path first, errors at bottom
