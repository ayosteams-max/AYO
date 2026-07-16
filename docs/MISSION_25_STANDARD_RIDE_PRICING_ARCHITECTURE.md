# Mission 25 — Standard Ride Pricing Architecture

Configuration dimensions support city/zone, Immediate or Scheduled Standard,
accessibility/assisted, business, and third-party/diaspora payer context. A service
variant changes price only through an approved, disclosed cost/service policy—not a
person's protected characteristic.

The deterministic component graph may include approved base, distance, duration,
minimum, traffic/pickup-cost, scheduled service, approved extras, promotion and tax.
Each component has a calculation order, applicability predicate, rounding rule, cap and
explanation key. No numeric launch values are defined here.

Route-provider failure uses a policy-approved bounded estimate or returns
`ESTIMATE_UNAVAILABLE`; it must not silently invent distance. Weak-network clients may
display a previously signed unexpired quote but cannot recalculate it. Corrected
distance/duration requires provenance, materiality rules and a new linked decision.

