---
name: project-style
description: Implementation details and code conventions for TasteBud. Architecture, contracts, and style rules.
disable-model-invocation: false
user-invocable: false
---

# Implementation Details

Concrete contracts, patterns, and style rules for TasteBud.

## Architecture

```
src/tastebud/
├── core/              Shared infrastructure
│   ├── config.py      pydantic-settings
│   ├── database.py    async SQLAlchemy engine + session
│   ├── exceptions.py  business exception hierarchy
│   └── logging.py     structlog setup
├── models/            SQLAlchemy ORM models
│   ├── base.py        declarative base + mixins
│   ├── user.py        User
│   ├── content.py     Content
│   ├── tag.py         Tag, ContentTag
│   └── feedback.py    UserFeedback, UserTagPreference
├── repositories/      Data access layer
│   ├── base.py        BaseRepository[T] generic ABC
│   ├── content.py     ContentRepository
│   ├── tag.py         TagRepository
│   └── feedback.py    FeedbackRepository
├── collector/         Content ingestion
│   ├── base.py        BaseCollector ABC
│   └── danbooru/      DanbooruCollector
├── analyzer/          Tag extraction and normalization
│   ├── base.py        BaseAnalyzer ABC
│   └── source_tag/    SourceTagAnalyzer
├── engine/            Scoring
│   └── scorer.py      TagScorer
├── services/          Business logic orchestration
│   ├── recommendation.py
│   └── feedback.py
├── api/               FastAPI routes
│   ├── deps.py        Depends factories
│   └── v1/            Versioned endpoints
└── main.py            FastAPI app with lifespan
```

## Dependency Direction

```
api → services → repositories → models
        ↑             ↑
     engine        core (config, database, exceptions)
        ↑
   collector → analyzer
```

- API routes depend on services, never on repositories directly.
- Services orchestrate repositories and engine.
- Collector and analyzer are independent subsystems invoked by services.
- Core is shared infrastructure imported by all layers.

## Base Class Contracts

```python
# repositories/base.py
class BaseRepository(Generic[T]):
    async def get(self, id: int) -> T | None
    async def get_many(self, *, offset: int, limit: int) -> list[T]
    async def create(self, **kwargs) -> T
    async def update(self, id: int, **kwargs) -> T
    async def delete(self, id: int) -> None

# collector/base.py
class BaseCollector(ABC):
    async def collect(self, **kwargs) -> list[RawContent]
    def parse_tags(self, raw: RawContent) -> list[TagResult]

# analyzer/base.py
class BaseAnalyzer(ABC):
    async def analyze(self, content: RawContent) -> list[TagResult]

# engine/scorer.py
class TagScorer:
    def score(self, user_prefs: list[UserTagPreference],
              content_tags: list[ContentTag]) -> float
```

## Data Flow: Collect → Score

```
1. collector.collect()        → list[RawContent]
2. analyzer.analyze(raw)      → list[TagResult]
3. repository.create(content) → Content (persisted)
4. scorer.score(prefs, tags)  → float (0-100)
5. service.get_feed(user_id)  → list[ScoredContent]
```

## Code Style

- Python 3.12+ type hints (`str | None`, `type` aliases)
- `async/await` for all I/O
- No empty `__init__.py`
- Imports: stdlib → third-party → local, separated by blank lines
- Absolute imports: `from tastebud.core.config import settings`
- Catch specific exceptions; bare `except Exception` only with `logger.exception()`
- Logger per module: `structlog.get_logger()` bound with module name
- Never log secrets
- SQLite-compatible types only in models (no PostgreSQL-specific columns)
- All API responses use Pydantic schemas (not ORM models directly)
