# ADR-002: Link expiry (resolves Q-6)

Status: Accepted
Context: FR-7 "Links can expire" leaves who, how, and what-happens open.
Assumption A-3: links are permanent unless given an expiry. ADR-001 D3
(302, not cached) means an expired link can stop working immediately.

## D1: Who sets expiry, and in what form
Options: A. creator at creation; B. system-wide fixed lifetime; C. admin
Format options: absolute `expires_at` or duration `expires_in_seconds`
Decision: A, optional `expires_at` in the create request: ISO 8601 with a
time zone, stored in UTC, must be in the future.
Rationale: no accounts or admins exist (out of scope). An absolute time is
unambiguous and doesn't depend on the server clock at creation.
Rejected: B contradicts A-3; C needs auth. A duration was rejected as less
explicit for clients.

## D2: Default
Decision: no expiry (NULL = never expires). Consistent with A-3; existing
links are unaffected.

## D3: Response for an expired link
Options: A. 404 Not Found; B. 410 Gone
Decision: B, 410 in the standard error shape (code: link_expired).
Rationale: tells the visitor the link existed but has ended, rather than
suggesting a typo. The existence "leak" is negligible: the creator shared
the link publicly.
Boundary: expired when now >= expires_at.

## D4: Behaviour around expiry
- Clicks on expired links are not recorded (FR-5 counts successful
  redirects only).
- Details and stats remain available after expiry, showing expires_at,
  since campaign stats are needed after a link ends.
- Expiry is checked at request time; expired links are kept (no cleanup
  job), preserving their stats.
- Expiry cannot be changed after creation (editing is out of scope).

## Trade-offs accepted
- Expired rows accumulate. Production would add archival or cleanup.
- No maximum expiry horizon; a creator may set a far-future date.

Revisit if: authentication is added (owner-managed expiry), or storage
growth from expired links becomes significant.