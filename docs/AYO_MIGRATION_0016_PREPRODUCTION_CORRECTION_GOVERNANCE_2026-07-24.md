# Migration 0016 PRE-PRODUCTION Correction Governance

Date: 2026-07-24
Environment: **PRE-PRODUCTION ONLY**
Decision: **APPROVED CONTROLLED HISTORICAL CORRECTION**
Production activation: **NOT APPROVED / NEVER ACTIVATED**

## Approval and scope

The Founder and CTO approve the current corrected form of migration `0016` as a
single controlled PRE-PRODUCTION historical correction.

This decision applies only to:

```text
database/migrations/versions/20260716_0016_canonical_ride_request.py
```

It is not general authority to modify historical migrations, renumber revisions,
rewrite published Git history, or represent different migration bytes as
equivalent.

## Controlled hashes

| Form | Git blob |
| --- | --- |
| Original committed form | `c09fc7efec392e8068c7adf62e32fbe2f7b4ecfd` |
| Approved corrected form | `3c1e4b8400567b154582ffbb5f7426d933db1d23` |

The original and corrected forms are distinct controlled artifacts.

## Semantic correction

The original revision created the historical Ride Request tables directly from
the repository's live SQLAlchemy metadata. Later canonical Subject work added
requester/passenger foreign-key objects to that same live metadata. During a clean
replay, revision `0016` runs before revision `0045` creates
`ayo.canonical_subjects` and before revision `0049` governs installation of the
Ride Request Subject foreign keys.

The corrected revision:

1. identifies only foreign-key constraints whose referenced table is
   `ayo.canonical_subjects`;
2. temporarily removes those future constraints from each historical table;
3. creates the table with the historically valid structure; and
4. restores the constraints to the in-process metadata object after creation.

It does not change the revision identifier, predecessor, permission seed,
downgrade sequence, data policy, indexes, or unrelated constraints.

## Why a forward migration alone cannot repair this failure

A new forward migration executes only after all preceding revisions have
succeeded. The compatibility failure occurs while a clean database is executing
revision `0016`, before any new forward revision can run. Consequently, a later
forward migration cannot repair the inability to create the historical table.

The approved correction is therefore a narrowly governed replay correction for
the PRE-PRODUCTION migration line, not a schema evolution shortcut. Once the
reviewed certification checkpoint is created, the corrected bytes become
permanently immutable and every later schema correction must use a new forward
migration.

## Environment evidence

Repository evidence identifies:

- local/disposable PostgreSQL 17.10 certification runs through earlier migration
  heads;
- a fresh PRE-PRODUCTION PostgreSQL 17.10 migration certification reaching
  revision `0045`;
- a later PRE-PRODUCTION migration certification reaching revision `0049`;
- the Ride Request Increment 1 CTO gate explicitly documenting that corrected
  `0016` excluded only future canonical-Subject foreign keys;
- no approved deployment, public activation, real-customer database, production
  database, or externally controlled non-disposable environment.

The original committed form may have been executed by earlier local/disposable
certification environments before future Subject constraints existed in live
metadata. The corrected form was exercised by later disposable PRE-PRODUCTION
full-chain certification. No evidence establishes a production or externally
controlled non-disposable database dependent on either form.

If contrary evidence is later discovered, this exception is insufficient: work
must stop for incident, migration-lineage, retention and rebuild review.

## Database lineage and rebuild control

Every disposable or shared PRE-PRODUCTION database whose migration lineage cannot
be proven against the corrected blob is **UNCERTIFIED**.

Such a database must not be promoted or used as certification evidence. It must be:

1. disposed of when safe and authorized;
2. rebuilt from an empty approved PostgreSQL 17/PostGIS 3.6 environment;
3. upgraded through the complete corrected migration chain; and
4. validated against the reviewed commit and evidence manifest.

No data from an uncertified database may be represented as certified lineage.
Where test data must be retained for defect investigation, the database remains
quarantined and clearly non-certifying until disposal is authorized.

## Final certification requirements

The eventual PostgreSQL baseline must:

- start from a clean disposable database;
- use the approved pinned PostgreSQL 17/PostGIS 3.6 image;
- bind evidence to the reviewed certification checkpoint;
- verify the corrected `0016` blob before migration;
- replay every revision in sequence through the single current head;
- validate the migration, metadata, constraint and rollback contracts authorized
  by the Repository Quality Contract; and
- retain redacted immutable evidence.

Prior PostgreSQL 17.10 results are historical technical evidence for the
compatibility rationale. They are not substitutes for the pending checkpoint-bound
PostgreSQL 17/PostGIS 3.6 baseline.

## Permanent rule after checkpoint

After the reviewed certification checkpoint records corrected blob
`3c1e4b8400567b154582ffbb5f7426d933db1d23`:

- revision `0016` is permanently immutable;
- no silent or retroactive modification is permitted;
- every future schema correction uses a new forward migration;
- migrations are not renumbered;
- published Git history is not rewritten; and
- original and corrected forms remain separately identified in governance
  chronology.
