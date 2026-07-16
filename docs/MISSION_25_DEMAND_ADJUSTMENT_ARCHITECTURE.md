# Mission 25 — Demand Adjustment Architecture

| Approach | Rider/driver impact | Risk and operating cost | Position |
|---|---|---|---|
| No adjustment | Maximum predictability; supply may lag | Low | Pilot default proposal |
| Capped zone/time adjustment | May improve availability | Fairness, disclosure, gaming | Future approval only |
| Rider wait-linked adjustment | Direct service signal | Can penalize underserved riders | Not recommended |
| Driver supply incentive only | Protects rider price | Cost and gaming | Controlled experiment candidate |
| Capped hybrid | Can balance both sides | Highest complexity | Defer until evidence |

Any future adjustment is deterministic, zone-scoped, capped, expiring, versioned,
visible before confirmation, emergency-restricted, fairness-reviewed and instantly
rollback-capable. Marketplace Health may open a review recommendation; authorized
maker-checker publication is required. AI never sets, publishes or personalizes demand
adjustment. Zero supply does not justify an uncapped price.

