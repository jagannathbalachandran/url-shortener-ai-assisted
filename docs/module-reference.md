# Module reference

`docs/architecture.md` shows the system from a distance: layers, the data
model, and two sequence diagrams. This document is the close-up: every
module under `src/shortener/`, every class and function in it, who calls
whom, and a single request traced end to end through actual code paths.
After reading it you should be able to say what each file is for, explain
why the codebase is shaped this way, and know exactly which file(s) a given
change would touch.

## How to read this document

- "Module" means one `.py` file under `src/shortener/`. Each is small and
  single-purpose (CLAUDE.md's "single responsibility per function/class").
- Citations like `validation.py:21` point at the current line in that file;
  line numbers drift as the code changes, the file name doesn't.
- Protocols (`typing.Protocol`) appear throughout instead of concrete
  classes in constructor signatures. This is the project's dependency
  -injection style (CLAUDE.md: "inject dependencies rather than
  constructing them internally") -- a class declares the *shape* of
  collaborator it needs, not which concrete class provides it, so tests can
  substitute a fake without touching the class under test, and swapping an
  implementation later (e.g. a different database, a different code
  generator) never requires changing the class that depends on it.

## Module map

| Module | Layer | Responsibility |
|---|---|---|
| `db.py` | Infra | SQLAlchemy `Base`, engine/session-factory construction, per-dialect connection fixups |
| `models.py` | Infra | ORM models (`Link`, `Click`) and the UTC-safe datetime column type |
| `repository.py` | Repository | Persistence and aggregate queries for links and clicks |
| `validation.py` | Service (pure) | URL and expiry validation |
| `codegen.py` | Service (pure) | Short-code generation |
| `referrer.py` | Service (pure) | Referer-header -> host extraction |
| `rate_limit.py` | Service (pure) | In-memory fixed-window rate limiter |
| `exceptions.py` | Domain | Typed exceptions raised across the service layer |
| `schemas.py` | API | Pydantic request/response models |
| `service.py` | Service | `LinkService`, `StatsService`, and the background click-recording function |
| `dependencies.py` | API wiring | FastAPI `Depends()` providers connecting layers per request |
| `config.py` | Infra | `Settings` (env-sourced configuration) |
| `errors.py` | API | The one JSON error shape, and exception -> response mapping |
| `routes.py` | API | `/api/v1/links` endpoints |
| `redirects.py` | API | `GET /{code}` redirect endpoint |
| `health.py` | API | `/health`, `/ready` |
| `app.py` | API wiring | FastAPI application factory |
| `main.py` | Entrypoint | ASGI `app` object uvicorn serves |

Alongside these, `alembic/versions/*.py` holds the three migrations that
evolve the schema `models.py` describes (`0001` links, `0002` clicks,
`0003` `expires_at`) -- not a "module" in the import-graph sense, but the
only place the live database schema is allowed to change (CLAUDE.md: no
`create_all` in application code).

## Modules in depth

### `db.py` -- engine and session construction

- `Base(DeclarativeBase)`: the one declarative base every ORM model
  inherits. Having a single `Base` is what lets Alembic's autogenerate (and
  `Base.metadata`) see every table in one place.
- `create_session_factory(database_url: str) -> sessionmaker[Session]`:
  builds an `Engine` for the given URL and returns a `sessionmaker` bound
  to it. Two private helpers attach dialect-specific connection-time fixups
  via SQLAlchemy's `connect` event:
  - `_force_utc_session_timezone`: on Postgres only, runs
    `SET TIME ZONE 'UTC'` on every new connection. Without it,
    `ClickRepository.clicks_per_day`'s `date()` bucketing would follow the
    Postgres server's configured zone instead of UTC.
  - `_enable_sqlite_foreign_keys`: on SQLite only, runs
    `PRAGMA foreign_keys=ON`. SQLite ignores foreign-key constraints
    (including `clicks.link_id`'s `ON DELETE CASCADE`) unless this is set
    per connection; Postgres always enforces them.
  This is the only place connection-level, dialect-specific behavior lives
  -- every other module treats SQLite and Postgres identically.
- Called from exactly two places: `app.py` (the real app, once per
  process) and test fixtures that need an independent, durably-committing
  session alongside the app's own.

### `models.py` -- ORM models

- `UTCDateTime(TypeDecorator[datetime])`: makes every stored timestamp
  round-trip as timezone-aware UTC on both SQLite and Postgres.
  `process_bind_param` rejects a naive `datetime` outright (`raise
  ValueError`) rather than guessing its zone; `process_result_value`
  normalizes whatever the driver returns to UTC. SQLite drops tzinfo on
  read by default -- without this type, code reading `created_at` back
  from SQLite would silently get a naive datetime that compares unequal to
  an aware one.
- `Link(Base)`: `id` (PK), `code` (`String(7)`, unique, indexed),
  `original_url`, `created_at` (`UTCDateTime`, defaults to `now(UTC)`),
  `expires_at` (`UTCDateTime`, nullable, defaults to `None`).
- `Click(Base)`: `id` (PK), `link_id` (FK -> `links.id`,
  `ON DELETE CASCADE`, indexed), `clicked_at` (`UTCDateTime`), and
  `referrer_host` (`String(253)` -- `MAX_REFERRER_HOST_LENGTH`, the
  practical DNS hostname maximum). There is no IP, user-agent, or full
  referrer URL column -- the Privacy NFR is enforced at the schema level,
  not just by what application code happens to write (see
  `tests/test_click_repository.py::test_click_table_has_no_ip_user_agent_or_full_referrer_url_column`).
- `CODE_LENGTH = 7`, `MAX_ORIGINAL_URL_LENGTH = 2048`,
  `MAX_REFERRER_HOST_LENGTH = 253`: the named constants other modules
  import rather than repeating magic numbers (`codegen.py`,
  `validation.py`, `referrer.py`, `service.py`'s format-check regex all
  reference these).

### `repository.py` -- persistence and aggregates

- `ping_database(session)`: runs `SELECT 1`. Used by `/ready` only; it's a
  plain function, not a class, because it has no state to hold.
- `LinkRepository(session)`:
  - `add(link) -> Link`: `session.add` + `commit`; on `IntegrityError`
    (the unique constraint on `code`) it rolls back and raises
    `CodeCollisionError` -- translating a SQLAlchemy-specific exception
    into a domain one, so nothing above the repository layer needs to know
    SQLAlchemy exists. Commits *inside* the repository, not the caller, so
    `LinkService.create_link` can retry on collision without worrying
    about transaction state.
  - `get_by_code(code) -> Link | None`: a plain `SELECT ... WHERE code =`.
- `ClickRepository(session)`:
  - `add(click) -> Click`: same commit pattern as `LinkRepository.add`.
  - `total_clicks`, `clicks_per_day`, `top_referrers`: every one of these
    is a `GROUP BY`/`COUNT` query executed in the database. No click rows
    are ever loaded into Python for counting (a T-06 constraint, so stats
    queries stay cheap regardless of click volume). `clicks_per_day` uses
    `func.date(...)` for UTC-day bucketing (correct because of `db.py`'s
    timezone fixup); `top_referrers` breaks count ties alphabetically by
    host for deterministic output.
- Both repository classes take a `Session` in `__init__` and hold nothing
  else -- a new one is constructed per request (or per background task) by
  `dependencies.py`, never shared or cached.

### `validation.py` -- pure input validation

- `validate_url(url) -> str`: rejects empty/oversized input, whitespace or
  control characters (checked on the *raw* string, before any parsing, so
  a value that `urlsplit` would otherwise clean up silently is rejected
  instead -- see `validation.py:18`'s docstring), non-`http(s)` schemes,
  and missing hosts (`parsed.hostname`, not `parsed.netloc` -- a
  userinfo-or-port-only "host" doesn't count; this was T-06 Phase A's
  defect fix). Returns the input unchanged -- never trimmed or normalized
  -- so the exact submitted string is what gets stored.
- `validate_expiry(raw_expires_at, now) -> datetime | None`: `None` passes
  through unchanged (no expiry). Otherwise parses ISO 8601, requires a time
  zone, converts to UTC, and requires the result to be strictly after
  `now` -- all failure modes collapse into one `InvalidExpiryError` so a
  client can't distinguish "malformed" from "in the past" (same
  information-hiding rationale as `LinkNotFoundError`, below).
- Both functions are free functions with no dependencies beyond their
  arguments -- pure, synchronous, trivially unit-testable, and reused
  identically by `LinkService.create_link` regardless of which
  repository/DB is behind it.

### `codegen.py` -- short-code generation

- `CodeGenerator(Protocol)`: one method, `generate() -> str`.
- `SecureCodeGenerator`: draws `length` (default `CODE_LENGTH`, 7)
  characters from `BASE62_ALPHABET` using `secrets.choice` -- a
  cryptographically secure RNG, not `random`, so codes are non-guessable
  (ADR-001 D1). Stateless beyond its length/alphabet configuration.

### `referrer.py` -- referrer-host extraction

- `extract_referrer_host(referer: str | None) -> str`: parses the
  `Referer` header with `urlsplit`, returns the lowercase hostname, or the
  constant `DIRECT_REFERRER = "(direct)"` for anything missing, malformed,
  host-less, or longer than `MAX_REFERRER_HOST_LENGTH`. By construction,
  scheme, port, userinfo, path, query string and fragment are all
  discarded -- only ever a hostname (or the direct-fallback) reaches
  `Click.referrer_host`.

### `rate_limit.py` -- in-memory rate limiter

- `RateLimitResult(NamedTuple)`: `allowed: bool`,
  `retry_after_seconds: float` -- the limiter's only output type.
- `_Bucket`: a key's `window_start` and `count`, private to this module.
- `RateLimiter(max_requests, window_seconds, clock=time.monotonic)`:
  - `allow(key) -> RateLimitResult`: increments `key`'s bucket, resetting
    it first if its window has elapsed; returns whether the incremented
    count is still within `max_requests`.
  - Two independent eviction mechanisms keep memory bounded: `allow`
    always resets *the calling key's own* stale bucket immediately
    (doesn't wait for a sweep), and `_maybe_sweep`/`_evict_stale` run a
    full pass over every key, but at most once per window, so an idle key
    that never calls `allow` again is still eventually reclaimed.
  - Thread-safe via a single `threading.Lock` around the whole `allow`
    body -- deliberately coarse-grained, since the critical section is
    tiny (dict lookup/update) and correctness under concurrent requests
    matters more than lock granularity here.
  - `clock` is injected (defaults to `time.monotonic`) specifically so
    tests can control time deterministically (`FakeClock` in the tests)
    without `sleep`-based tests.

### `exceptions.py` -- domain exceptions

Every exception inherits `ShortenerError(Exception)`, so application code
can catch "any domain error" in one `except` if it ever needs to (it
currently doesn't -- `errors.py` registers a specific handler per type
instead, which is the point: no bare `except`, no generic handling that
could mask a bug). Each carries only the context its handler needs:

| Exception | Raised by | Carries |
|---|---|---|
| `CodeCollisionError` | `LinkRepository.add` | `code` |
| `InvalidUrlError` | `validate_url` | `url` |
| `InvalidExpiryError` | `validate_expiry` | `expires_at` |
| `LinkExpiredError` | `LinkService.resolve_for_redirect` | `code` |
| `LinkCreationExhaustedError` | `LinkService.create_link` | `attempts` |
| `LinkNotFoundError` | `LinkService.resolve` | `code` |
| `DatabaseUnavailableError` | `get_database_health` | -- |
| `RateLimitExceededError` | `enforce_create_rate_limit` | `retry_after_seconds` |

Note `LinkNotFoundError` is raised for *both* a malformed code and an
unknown-but-well-formed one (`service.py:92-96`) -- one exception, one
message, so a client response never leaks which codes are syntactically
valid versus which specific codes exist.

### `schemas.py` -- API request/response shapes

Pydantic models define the wire format independently of the ORM models
(`Link`/`Click` never cross the API boundary directly):

- `CreateLinkRequest`: `url: str`, `expires_at: str | None` (left as a raw
  string here -- parsing happens in `validate_expiry`, which needs an
  injected clock the schema layer doesn't have access to).
- `LinkResponse`: `code`, `short_url`, `original_url`, `created_at`,
  `expires_at`; `from_link(link, base_url)` builds `short_url` by joining
  `base_url` and `link.code` -- the one place a short URL string is
  assembled.
- `ClicksPerDayEntry`, `ReferrerCountEntry`: the two row shapes inside
  stats.
- `LinkStatsResponse`: `code`, `total_clicks`, `clicks_per_day`,
  `top_referrers`, `expires_at`; `from_stats(code, stats)` converts the
  domain `LinkStats` dataclass (see `service.py`) into these wire types.

Keeping `from_link`/`from_stats` as classmethods on the response model
(rather than, say, building dicts in `routes.py`) means the mapping from
domain object to wire shape lives in exactly one place per response type.

### `service.py` -- domain logic

This is the largest module and the one with the most collaborators, so
each piece:

- **`LinkWriter` / `LinkReader` (Protocols):** the minimal persistence
  surface `LinkService` needs -- `add(link)` and `get_by_code(code)`
  respectively. `LinkRepository` happens to satisfy both, but `LinkService`
  never imports `LinkRepository`; it only knows these two protocols. Test
  doubles throughout the test suite implement just one or the other (e.g.
  a reader that always returns a fixed link, paired with a writer that
  asserts it's never called).
- **`LinkService(repository, code_generator, reader, clock=real UTC now)`:**
  - `create_link(url, expires_at=None) -> Link`: `validate_url` →
    `validate_expiry` (using the injected `clock` for "now") → a loop of
    up to `MAX_CODE_GENERATION_ATTEMPTS` (5) that generates a code and
    calls `repository.add`, catching `CodeCollisionError` to retry; raises
    `LinkCreationExhaustedError` if every attempt collides.
  - `resolve(code) -> Link`: a format check first (base62, exactly 7 chars
    -- `_is_valid_code_format`, built from the same `CODE_LENGTH`/
    `BASE62_ALPHABET` constants `codegen.py` uses) so a malformed code
    never reaches the database; then `reader.get_by_code`. Either failure
    mode raises `LinkNotFoundError`.
  - `resolve_for_redirect(code) -> Link`: calls `resolve()`, then raises
    `LinkExpiredError` if `clock() >= link.expires_at`. Kept as a separate
    method (not a flag on `resolve`) specifically so `GET
    /api/v1/links/{code}` (details) and the stats endpoint can keep
    returning data for an expired link while only the redirect route
    blocks on expiry (ADR-002 D4).
- **`record_click_in_background(session_factory, link_id, referrer_host)`:**
  a free function, not a method, because it runs as a FastAPI
  `BackgroundTasks` callable, scheduled by `redirects.py` *after* the
  request's own session is already slated to close. It opens its *own*
  session from `session_factory` (never reuses the request's), wraps the
  write in `try/except SQLAlchemyError` (logs `link_id` only -- never the
  referrer -- and swallows the failure), and always closes its session in
  `finally`. A failed click write must never surface to the client; by the
  time this runs, the 302 has already been sent.
- **`LinkResolver` / `ClickReader` (Protocols), `DailyClickCount`,
  `ReferrerCount`, `LinkStats` (frozen dataclasses):** the analogous
  minimal-interface pattern for stats -- `StatsService` only needs
  something that can `resolve(code)` (satisfied by `LinkService` itself)
  and something that can answer the three aggregate queries (satisfied by
  `ClickRepository`).
- **`StatsService(link_resolver, click_reader, clock)`:**
  `get_stats(code) -> LinkStats` resolves the link (reusing
  `LinkService.resolve`, so a stats 404 is identical to a details 404 by
  construction, not by coincidence), computes the 30-day window start via
  `_clicks_per_day_window_start` (UTC midnight of `today - 29 days` --
  calendar-aligned, not a rolling 720-hour window), and assembles the three
  aggregate results into one `LinkStats`.

### `dependencies.py` -- per-request wiring

Every function here is a FastAPI `Depends()` provider; this module is
where the layers actually get connected for a live request. None of it
contains business logic -- it only constructs and hands off collaborators:

- `get_session(request)`: yields a `Session` from
  `request.app.state.session_factory`, closes it in `finally`. The
  fundamental per-request resource every DB-touching dependency builds on.
- `get_link_service(session, code_generator, clock)`: builds one
  `LinkRepository(session)` and passes it to `LinkService` as *both*
  `repository` and `reader` -- one object satisfying two protocols, which
  is fine since `LinkService` only ever calls the protocol methods it
  declared needing.
- `get_stats_service(link_service, session)`: wires `StatsService` with
  `link_service` as its resolver and a fresh `ClickRepository(session)` as
  its reader.
- `enforce_create_rate_limit(request, limiter)`: the dependency attached
  via `dependencies=[Depends(...)]` on the create route (not global
  middleware -- see `routes.py`); keys on `request.client.host`, raising
  `RateLimitExceededError` if over limit.
- `get_database_health(session)`: calls `ping_database`, translating any
  `SQLAlchemyError` into `DatabaseUnavailableError` -- used only by
  `/ready`.
- `get_session_factory(request)`: returns the *factory* itself (not a
  session) -- the one dependency that exists purely so a background task
  can later open its own independent session.
- `get_referrer_host(request)`: reads the `Referer` header and delegates
  to `referrer.extract_referrer_host`.
- `get_clock()`: returns `lambda: datetime.now(UTC)` -- overridden in
  tests (`app.dependency_overrides[get_clock]`) to pin "now" for
  expiry-boundary tests.

### `config.py` -- configuration

- `Settings(BaseSettings)`: `database_url`, `base_url`,
  `rate_limit_max_requests`, `rate_limit_window_seconds`, sourced from
  environment variables or a `.env` file (pydantic-settings). A
  `field_validator` strips a trailing slash from `base_url` so short URLs
  never get a double slash.
- `get_settings()`: `@lru_cache`d singleton constructor -- called once per
  process by `app.py` unless a test passes its own `Settings` directly to
  `create_app`.

### `errors.py` -- the one error shape

- `ErrorDetail(TypedDict)`: `{loc, msg}` -- deliberately excludes the
  submitted value (pydantic's `"input"` key is dropped in
  `_validation_details`), so invalid input is never echoed back.
- `build_error_body` / `error_response`: assemble
  `{"error": {"code", "message", "details"?}}` and wrap it in a
  `JSONResponse`, optionally with headers (used for `Retry-After` on 429
  and `Cache-Control: no-store` on 410).
- One `_handle_*` function per exception type (`InvalidUrlError` -> 422,
  `LinkNotFoundError` -> 404, `LinkExpiredError` -> 410,
  `RateLimitExceededError` -> 429, `DatabaseUnavailableError` -> 503, ...),
  plus handlers for Starlette's `HTTPException` (unmatched routes, wrong
  methods) and FastAPI's `RequestValidationError`. `_handle_unhandled_exception`
  is the catch-all: logs the method and path (`request.url.path` only --
  no query string, no client host, no body) with the traceback, and
  returns a generic 500 that never includes `str(exc)`.
- `register_exception_handlers(app)`: called once by `app.py`, wiring
  every handler above onto the `FastAPI` instance via
  `add_exception_handler`.

### `routes.py` -- `/api/v1/links` endpoints

Three thin handlers, each following the same shape: resolve dependencies,
call one service method, map the domain result through a schema's
`from_*` classmethod. No handler contains a conditional, a loop, or a
try/except -- all of that lives in `service.py`/`errors.py`.

- `POST /api/v1/links` (`create_link`): the only route with
  `dependencies=[Depends(enforce_create_rate_limit)]` on its decorator.
- `GET /api/v1/links/{code}` (`get_link_details`): calls
  `LinkService.resolve` (expiry-blind).
- `GET /api/v1/links/{code}/stats` (`get_link_stats`): calls
  `StatsService.get_stats`.

### `redirects.py` -- the hot path

A single handler, deliberately separate from `routes.py` (different
router, no `/api/v1` prefix, registered last in `app.py`):

- `redirect_to_original`: calls `resolve_for_redirect` (so this is the one
  route that can raise `LinkExpiredError`), percent-encodes the stored URL
  into `Location` via `quote(..., safe=_LOCATION_SAFE_CHARS)` (every
  printable non-space ASCII character is "safe", i.e. left alone; only
  bytes outside Latin-1 that would otherwise crash `Response`'s header
  encoding get percent-escaped), schedules the click write via
  `background_tasks.add_task(...)`, and returns the `Response` directly
  (not Starlette's `RedirectResponse`, which would re-quote an
  already-encoded URL).
- `REDIRECT_STATUS_CODE = 302` and `NO_STORE_CACHE_CONTROL` are named
  constants referencing ADR-001 D3 directly in code, not just in docs.

### `health.py` -- liveness and readiness

- `health()`: returns a fixed body, no dependencies at all -- it cannot
  fail for a DB reason, by construction.
- `ready(Depends(get_database_health))`: the dependency itself does all the
  work (ping + exception translation); the route body is just the success
  case.

### `app.py` -- the application factory

`create_app(settings=None) -> FastAPI`:
1. Resolves `Settings` (passed in, e.g. by tests, or `get_settings()`).
2. Builds the `FastAPI` instance and stores `settings`, a
   `session_factory` (via `db.create_session_factory`), and a
   `RateLimiter` on `app.state` -- the three pieces of app-wide state
   every dependency provider reads back out.
3. Calls `register_exception_handlers(app)`.
4. Includes routers in a specific, commented order: health first, then
   `/api/v1/links`, then the `/{code}` redirect router *last*. Order
   matters because `/{code}` is a single-segment catch-all; registered
   first, it would shadow `/health`, `/ready`, `/docs`, and
   `/openapi.json`.

### `main.py` -- entrypoint

One line of substance: `app = create_app()`. This is the only module
`uvicorn shortener.main:app` imports; everything else is reached through
`create_app`'s wiring.

## End-to-end walkthrough

A marketer shortens a blog post with a two-day expiry, someone clicks it
from a newsletter, and the marketer checks stats. Every step below is a
real call in the actual code, in order.

### 1. Create: `POST /api/v1/links`

Request body:
```json
{"url": "https://blog.example.com/launch-announcement",
 "expires_at": "2026-10-03T00:00:00+00:00"}
```

1. FastAPI parses the body into a `CreateLinkRequest` (`schemas.py`) --
   if `url` were missing or the wrong type, this step itself would raise
   `RequestValidationError`, handled by `errors.py`'s
   `_handle_validation_error` (422 `validation_error`), and nothing below
   would run.
2. Dependency resolution, in order: `enforce_create_rate_limit` runs first
   (it's on the route decorator, not a parameter, so FastAPI resolves it
   before the handler body) -- it calls `get_rate_limiter` (reads
   `app.state.rate_limiter`) then `RateLimiter.allow(request.client.host)`.
   Under the limit, so it returns `None` and the request proceeds. Then
   `get_link_service` resolves: `get_session` yields a fresh `Session`,
   `get_code_generator` returns a `SecureCodeGenerator()`, `get_clock`
   returns the real-time lambda; `get_link_service` builds one
   `LinkRepository(session)` and passes it to `LinkService` as both
   `repository` and `reader`. `get_current_settings` resolves `Settings`
   from `app.state`.
3. `routes.create_link` runs: `service.create_link(body.url, body.expires_at)`.
4. Inside `LinkService.create_link`:
   - `validate_url(url)` (`validation.py`): well-formed `https://` URL
     with a real host, under 2048 chars, no whitespace/control
     characters -- returns it unchanged.
   - `validate_expiry("2026-10-03T00:00:00+00:00", now)`: parses, has a
     time zone, converts to UTC, is after `now` -- returns that `datetime`.
   - Loop (up to 5 attempts): `code_generator.generate()`
     (`SecureCodeGenerator`, `codegen.py`) draws 7 `secrets.choice`
     characters from the base62 alphabet, e.g. `"k7Qp2Rx"`. A `Link(code="k7Qp2Rx",
     original_url=..., expires_at=...)` is built and passed to
     `repository.add(link)`.
   - `LinkRepository.add` (`repository.py`): `session.add` + `session.commit()`.
     No collision (astronomically unlikely at any realistic link count --
     ADR-001 D1), so the insert succeeds, `session.refresh(link)` populates
     `link.id` and `link.created_at` from the database, and the committed
     `Link` is returned up through `create_link`.
5. Back in `routes.create_link`: `LinkResponse.from_link(link, settings.base_url)`
   builds `short_url = f"{base_url}/k7Qp2Rx"`.
6. FastAPI serializes the `LinkResponse` and returns `201`.

At this point the link is durably committed -- a client that sees the 201
is guaranteed the link already exists for the very next request (T-03
AC2), because the commit happened inside the repository, before the
response was ever built.

### 2. Redirect: `GET /k7Qp2Rx`

Two days later (still before expiry), someone clicks the link from a
newsletter: `Referer: https://mail.example.com/campaigns/launch`.

1. This request matches `redirects.py`'s catch-all route (it's registered
   last, so `/health`, `/ready`, and `/api/v1/...` are all checked first
   and don't match `/k7Qp2Rx` anyway).
2. Dependencies resolve: `get_link_service` as before; `get_session_factory`
   returns the app-wide factory (not a session); `get_referrer_host` reads
   the `Referer` header and calls `extract_referrer_host`
   (`referrer.py`), which parses `https://mail.example.com/campaigns/launch`
   and returns `"mail.example.com"` (host only -- path and scheme
   discarded).
3. `redirect_to_original` calls `service.resolve_for_redirect("k7Qp2Rx")`:
   - `resolve("k7Qp2Rx")`: format check passes (7 base62 chars);
     `reader.get_by_code("k7Qp2Rx")` finds the row.
   - Expiry check: `now < link.expires_at` (2 days < the window), so no
     `LinkExpiredError`.
4. `location = quote(link.original_url, safe=_LOCATION_SAFE_CHARS,
   encoding="utf-8")` -- the URL is pure ASCII, so this is a no-op here
   (it would percent-encode anything outside printable ASCII, e.g. an IDN
   host).
5. `background_tasks.add_task(record_click_in_background, session_factory,
   link.id, "mail.example.com")` -- this *schedules* the call; it does not
   run yet.
6. The handler returns `Response(302, headers={"Location": "https://blog.example.com/launch-announcement",
   "Cache-Control": "no-store"})`. Starlette sends this response to the
   client now.
7. *After* the response has been sent, Starlette runs the scheduled
   background task: `record_click_in_background(session_factory, link.id,
   "mail.example.com")` opens its own `Session` (independent of the
   request's, which is already closing), builds `Click(link_id=link.id,
   referrer_host="mail.example.com")`, and `ClickRepository.add` commits
   it. If this insert fails for any reason, the exception is caught,
   logged with `link_id` only, and swallowed -- the client already has its
   redirect and never knows.

### 3. Stats: `GET /api/v1/links/k7Qp2Rx/stats`

The marketer checks performance a few days later.

1. `get_stats_service` wires a `StatsService` from the already-resolved
   `LinkService` (as `link_resolver`) and a fresh `ClickRepository(session)`
   (as `click_reader`).
2. `StatsService.get_stats("k7Qp2Rx")`:
   - `link_resolver.resolve("k7Qp2Rx")` -- the *same* `LinkService.resolve`
     the details endpoint uses; if the link had expired by now, this would
     still succeed (expiry-blind), unlike step 2's `resolve_for_redirect`.
   - `since = _clicks_per_day_window_start(now)` -- UTC midnight of
     `today - 29 days`.
   - Three repository calls, each a `GROUP BY` query:
     `click_reader.total_clicks(link.id)` -> e.g. `1`;
     `click_reader.clicks_per_day(link.id, since)` -> `[(2026-10-01, 1)]`;
     `click_reader.top_referrers(link.id, 5)` -> `[("mail.example.com", 1)]`.
   - Assembled into one `LinkStats(total_clicks=1, clicks_per_day=[...],
     top_referrers=[...], expires_at=link.expires_at)`.
3. `LinkStatsResponse.from_stats("k7Qp2Rx", stats)` converts the dataclass
   into the wire shape; FastAPI serializes and returns `200`.

### What this trace demonstrates

- The **only** place a DB write happens for link creation is
  `LinkRepository.add`; the **only** place for a click is
  `ClickRepository.add`, called from exactly one caller each
  (`LinkService.create_link` and `record_click_in_background`). Grep
  either method's callers to find every write path in the system.
- **No handler function ever touches a `Session`, a SQL statement, or a
  domain exception's HTTP status.** Those three concerns sit in
  `dependencies.py`/repositories, `service.py`, and `errors.py`
  respectively -- the layering from `architecture.md` isn't just a
  diagram, it's enforced by which module imports what (routers import
  services and schemas; services import repositories and validation;
  nothing above the repository layer imports SQLAlchemy).
- The redirect's **response and its side effect are decoupled on
  purpose**: the 302 is built and returned before the click write is even
  attempted, and the write's failure mode (swallow + log) is designed so
  it can never turn into a failed redirect.

## Why it's designed this way

- **Layering (api -> service -> repository -> DB) with Protocol-typed
  dependencies:** every service class depends on a `Protocol`
  (`LinkWriter`, `LinkReader`, `LinkResolver`, `ClickReader`, ...), not a
  concrete repository class. This is what makes `LinkService` testable
  with a two-line fake instead of a real database, and what would let a
  future alternate storage backend be swapped in by writing a new class
  that satisfies the same protocol -- `LinkService` would not change.
- **Side effects pushed to the edges:** `validation.py`, `codegen.py`,
  `referrer.py` are pure functions; `LinkService`/`StatsService` orchestrate
  but never touch SQL directly; only `repository.py` (and `db.py`'s
  connection fixups) talk to the database. This is why, e.g., T-06 Phase
  A's defect fix (`validation.py:27`, one line) needed zero changes
  anywhere else -- the bug and the fix were both fully contained in a pure
  function with no collaborators.
- **Specific exceptions, one handler each:** rather than a generic
  "service error" with a status-code field, each failure mode is its own
  exception type (`exceptions.py`) mapped by its own handler
  (`errors.py`). Adding a new failure mode means adding one exception and
  one handler -- existing ones are untouched and can't regress.
- **A new code (and a new row) per create, never reused across requests:**
  this is ADR-001 D2's decision reflected in code -- `create_link` has no
  "look up an existing link for this URL" path at all, which is also why
  it never needs a unique index on `original_url`.
- **Click recording as a background task, with its own session:** the
  alternative (write the click before responding) would put a DB insert
  on the redirect's hot path, directly contradicting the performance NFR.
  Giving the task its own session (rather than trying to reuse the
  request's) is what makes this safe -- the request's session is already
  scheduled to close by the time the task runs.

## How to extend this codebase

Each recipe names every file that changes and, as important, which ones
don't -- the layering is what keeps a change's blast radius small.

**Add a new field to link creation** (e.g. a client-supplied tag): add it
to `CreateLinkRequest` and `LinkResponse` (`schemas.py`); add a column to
`Link` (`models.py`) and a migration (`alembic revision`); thread it
through `LinkService.create_link`'s signature and the `Link(...)`
construction (`service.py`); update `LinkResponse.from_link`. Nothing in
`repository.py`, `routes.py`, `dependencies.py`, `errors.py`, or
`redirects.py` needs to change -- they don't know link fields exist as
individual names.

**Add a new endpoint** (e.g. `DELETE /api/v1/links/{code}`): add a method
to `LinkService` (and a `delete` method to the `LinkWriter` protocol and
`LinkRepository`, if it needs one); add the route handler to `routes.py`;
add any new exception + handler pair if it has a new failure mode. The
existing create/details/stats handlers are untouched -- routes don't share
state beyond the dependencies they each individually declare.

**Replace the in-process rate limiter with a shared store (e.g. Redis)**
(the README's stated production path): write a new class satisfying
whatever interface `enforce_create_rate_limit` is changed to depend on
(currently it depends on the concrete `RateLimiter`, not a protocol --
introducing a `RateLimiterProtocol` first would be the enabling step);
swap what `get_rate_limiter` (`dependencies.py`) constructs. `routes.py`
and every other module are unaffected, since they only see
`enforce_create_rate_limit`'s raise-or-pass behavior.

**Move click recording to a message queue** (ADR-001 D4's stated
production path): replace `record_click_in_background`'s body (`service.py`)
with "publish a message" instead of "open a session and insert"; add a
separate consumer process that calls `ClickRepository.add` (reusable
as-is). `redirects.py` doesn't change at all -- it only knows it's
scheduling *some* callable via `add_task`; swapping what that callable
does is entirely internal to `service.py`.

**Add authentication / owner-scoped links** (currently out of scope,
A-2): a new dependency (e.g. `get_current_user`) added to
`dependencies.py`; an `owner_id` column on `Link` plus a migration; every
service method that currently takes just a `code` would need an owner
check added -- this is the one extension that *does* touch multiple
layers, because ownership is a cross-cutting concern the current design
doesn't model at all. Expect `LinkReader`/`LinkWriter`'s protocol shape,
`LinkService`'s methods, and every route to change.

**Change what counts as a valid URL or expiry:** `validation.py` only --
both functions are pure and independently unit-tested
(`tests/test_validation.py`); nothing else references validation rules
directly.

**Change the error response shape or add a new error code:** `errors.py`
only (plus the exception itself in `exceptions.py`, if it's a new failure
mode). Every route already goes through `register_exception_handlers`, so
no per-route changes are needed.

## Quick reference: "I need to change..."

| ...this | Start in |
|---|---|
| What a valid URL/expiry looks like | `validation.py` |
| How short codes are generated | `codegen.py` |
| What's stored/returned for a link or click | `models.py`, `schemas.py` |
| Business rules for create/resolve/expiry | `service.py` (`LinkService`) |
| Stats calculation or windows | `service.py` (`StatsService`), `repository.py` (`ClickRepository`) |
| The JSON error shape or a status code | `errors.py` |
| An API route's path, method, or status code | `routes.py` / `redirects.py` / `health.py` |
| How a dependency is constructed per request | `dependencies.py` |
| Rate-limit thresholds or algorithm | `config.py` (thresholds), `rate_limit.py` (algorithm) |
| DB connection behavior (timeouts, dialect quirks) | `db.py` |
| Router registration order, app-wide state | `app.py` |
| The schema itself | `models.py` + a new `alembic` migration |

Every change above still ends at the same gate: `scripts/check.py` (ruff,
ruff format, mypy --strict, pytest with coverage, pip-audit) must pass,
and CLAUDE.md's "every change ships with tests" applies regardless of
which module it touches.
