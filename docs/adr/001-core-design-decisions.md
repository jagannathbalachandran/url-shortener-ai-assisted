# ADR-001: Core design decisions

Status: Accepted · Date: 2026-09-28
Context: requirements.md §6 (Q-1, Q-2, Q-4, Q-5); assumptions A-1 (reads ≫ writes)
and A-4 (~10M links).

---

## D1 (Q-4): Short code generation
**Options considered**
- A. Random 7-char base62 code from `secrets`, DB unique constraint, retry on collision
- B. Base62-encoded auto-increment ID
- C. Pre-generated key pool (key generation service)

**Decision:** A — random 7-char base62, unique constraint, max 5 retries.

**Rationale:** 62^7 ≈ 3.5 trillion codes; at 10M links a collision is ~1 in 350,000
per create and is handled by retry. Codes are non-sequential, satisfying the
"non-guessable" security requirement.

**Rejected:** B produces sequential, enumerable codes (anyone could crawl all links).
C adds a refill job, concurrency control and monitoring for not much measurable benefit
at this write volume.

---

## D2 (Q-1): Duplicate long URLs
**Options considered**
- A. Always issue a new code
- B. Return the existing code for the same URL

**Decision:** A — every create issues a new code.

**Rationale:** separate codes per share keep analytics separable by channel/campaign i.e. user can create multiple codes for the same url mapping to each channel.
(FR-6); no lookup by long URL is needed on create.

**Rejected:** B merges stats across channels and complicates expiry (one expiry
would affect every sharer of that URL across channels).

**Trade-off accepted:** some duplicate rows for identical URLs; negligible storage.

---

## D3 (Q-2): Redirect status
**Options considered**
- A. 301 Moved Permanently
- B. 302 Found

**Decision:** B — 302.

**Rationale:** every click reaches the service, so analytics are complete (FR-5/6)
and expired links stop working immediately (FR-7).

**Rejected:** 301 is cached by browsers — repeat clicks bypass the service, hiding
them from analytics, and an expired link would keep redirecting from cache.

**Trade-off accepted:** every repeat visit costs one request to the service; this is
the hot path, which is why redirect performance is a first-class requirement, must meet stringent performance requirements.

---

## D4 (Q-5): Click recording
**Options considered**
- A. Synchronous insert before redirecting
- B. Background task after the response is sent (in-process)
- C. Message queue (e.g. Kafka/Redis) with a separate consumer

**Decision:** B for the prototype; C is the production path.

**Rationale:** the redirect returns without waiting for the click write, meeting
"analytics must never slow a redirect" without extra infrastructure.

**Rejected:** A adds a DB write to every redirect on the hot path. C is the right
production design but adds infrastructure beyond the prototype's scope.

**Trade-off accepted:** a click can be lost if the process crashes between response
and write. Acceptable because click counts are analytics, not business-critical data
(contrast: link creation is always persisted before responding).

**Revisit if:** analytics become billing- or compliance-relevant, or click volume
exceeds what in-process writes can sustain → move to C.