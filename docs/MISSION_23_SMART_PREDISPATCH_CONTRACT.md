# Mission 23 — Smart Pre-Dispatch Contract

Preconditions: current ride healthy; drop-off projection authorized; completion plus
buffer fresh/confident; next pickup near drop-off; no overlap; driver eligible; rider is
told the driver is finishing a trip; driver explicitly accepts without distraction.

Record both ride IDs, prediction/version/confidence, buffer, proximity band, expiry,
acceptance, release triggers and audit. Only a future opportunity is reserved. The next
ride begins after server-confirmed current completion. Delay, route change, safety event,
cancellation, stale data, weak network or conflict releases/replans idempotently.
