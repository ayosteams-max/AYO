# Mission 23 — Airport Dispatch Architecture

Standard and Premium keep separate versioned queue/service policies. Inputs include
airport/terminal/pickup-zone, staging lease, access, approved vehicle/language capability,
congestion/closure, scheduled commitment and fresh flight-context boundary.

Drop-off-to-pickup is only a pre-dispatch candidate when completion, access, staging and
queue fairness permit. Eligibility comes from Safety/Eligibility. Closure/confusion pauses
offers, protects commitments and uses approved fallback zones. No fare, fee or bonus is
calculated.
