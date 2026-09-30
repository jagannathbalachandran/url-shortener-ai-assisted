# Requirements — URL Shortener

## 1. Problem statement
Long URLs are hard to share in emails and chat. Users submit a long URL and get
a short link; anyone opening the short link is redirected to the original URL.
Marketing needs usage stats per link to see how traffic is channelled.

**How it works:** each long URL is saved with a short random code. Opening the
short link looks up the code and redirects to the saved URL. The code does not
contain the URL itself.

## 2. Functional requirements
| ID | Requirement | Phase |
|---|---|---|
| FR-1 | Create a short URL for a valid long URL | Greenfield |
| FR-2 | Redirect a short URL to its original URL | Greenfield |
| FR-3 | Return 404 for unknown short codes | Greenfield |
| FR-4 | Look up a link's details without redirecting | Greenfield |
| FR-5 | Record each redirect as a click | Brownfield |
| FR-6 | Stats per link: total clicks, clicks per day, top referrers | Brownfield |
| FR-7 | Links can expire | Ambiguous |

## 3. Non-functional requirements
- **Performance:** redirects are the hot path (see A-1); target p95 < 50 ms at the
  app layer. Analytics must never slow a redirect.
- **Security:** only `http`/`https` URLs, max 2,048 chars; non-guessable codes;
  rate limiting on creation; no secrets in code.
- **Privacy:** no raw IP addresses stored.
- **Reliability:** health endpoint; consistent JSON errors; a link is saved
  before its short URL is returned.
- **Portability:** runs locally with no external services (SQLite); Postgres in
  production, verified in CI.

## 4. Out of scope
User accounts/auth, deleting or editing links, custom aliases, web UI,
malicious-URL scanning, multi-region deployment.

## 5. Assumptions
- A-1 Reads outnumber writes ~1000:1.
- A-2 Creators are anonymous; production auth is handled by an API gateway.
- A-3 Links are permanent unless given an expiry.
- A-4 Design scale ~10M links; prototype is single-node.

## 6. Open questions → decisions
| # | Question | Decision |
|---|---|---|
| Q-1 | Same URL submitted twice: same or new code? | New code per create (ADR-001 D2) |
| Q-2 | Redirect: 301 or 302? (301 is cached, hiding repeat clicks) | 302 (ADR-001 D3) |
| Q-3 | Stats: total clicks or unique visitors? | Total clicks; unique visitors deferred (privacy) |
| Q-4 | Code format, length, generation method? | Random 7-char base62 (ADR-001 D1) |
| Q-5 | Record clicks synchronously or in the background? | Background task; queue in production (ADR-001 D4) |
| Q-6 | Expiry behaviour (who sets it, expired-link response, default)? | Optional `expires_at` set by creator; default never; expired → 410 Gone; stats still available (ADR-002) |