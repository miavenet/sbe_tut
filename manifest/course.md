# Bounded, versioned SBE inside a sequenced application

Grain: given the supplied starter, pinned schemas and fault fixtures, build and
debug a bounded C++17 message path. Five load-bearing ideas: layout; ownership
and explicit initialization; compatible evolution; ordered traversal and validation;
framing and deterministic replay. Prerequisites: edit/compile C++17, binary integers,
and shell commands. Start with labs/l01/README.md's prerequisite exercise; Java
programming and access to a production system are not prerequisites.

Retention target: usable a month later with project-use maintenance, without a
promise of permanent retention. Proposed first exposures: days 1,3,6,10,14.
Time cost: an estimated 8 hours of listed work (463 estimated minutes: setup 1,
first-pass lessons 239, one encounter with all 46 graded reviews 138, and
the delayed exam 85). First-pass lessons take about 33, 35, 40, 60 and 71
minutes. The first pass includes the three-minute primer before lesson 01's
cards. Proposed first exposures fall on days 1, 3, 6, 10 and 14, with the
exam no earlier than day 21. Later repetitions and repairs add time. The
twelve five-minute review slots are reservations, not a bound on required
review time. Four optional packs add 60 minutes. Learner completion time
remains unmeasured.
Source: [Evidence](manifest/claims.tsv)

Literal tiers: [T0, T1, T2, T3]
T0: ordered cards with covered keys and manual date tracking. T1: offline driver,
actual submitted-work checks and honest bullet-level self-report. T2: optional
model tutor protocol with explicit T1 fallback in the offline driver. T3: anchored variants
under PROTOCOL.md; the model cannot change executable grades or the schedule.
Source: [Evidence](manifest/claims.tsv)

| Objective | Production | Varied transfer | Grading |
|---|---|---|---|
| WP1-O1: exact offsets/bytes | L01-R1,R2,I1 | L01-T1: big-endian Quote with different widths | Executable plus explanation self-report |
| WP1-O2: stable bytes/ownership/allocation | L02-R1,R2,I1 | L02-T1: copied audit ownership after source-object and receive-buffer overwrite | Executable plus explanation self-report |
| WP2-O3: four-way compatibility | L03-R1,R2,R3 | L03-T1: mixed archived frames/raw preservation | Executable plus explanation self-report |
| WP3-O4: ordered/bounded decoding | L04-R1,R2,R3 | L04-J1,T1,T2: judgement and nested malformed tape | Executable plus explanation self-report |
| WP4-O5: sequenced/replayed state | L05-R1,R2,R3,R4 | L05-J1,T1,T2: judgement, torn archive and migration proposal | Executable plus explanation self-report |

The exact conditions and binary criteria are in `manifest/objectives.tsv`; `manifest/schedule.json`
maps every phase exactly once. The driver requires all mapped production and
transfer cards at the delayed exam, no earlier than L05+7 days. First review is
+1 day; confident successful later gaps are +3,+7,+14; misses/partial/unsure/hints
return +1 day. Confident misses are reviewed first. Overdue work stays due.
At most six new concepts are introduced per calendar day. Same-day repairs do not earn delayed mastery.
Source: [Evidence](manifest/claims.tsv)

Lesson format: `### Card ID · label` and `### Concept ID · label` are the only
machine-readable headings. `cards.json` has exactly one row per heading, keyed by
stable ID. Each row holds `kind`, `lesson`, `type`, `topic`, `minutes`, `Source`,
`AcceptIf`, and `RejectIf`. Concept rows use null `type` and `topic`.
Empty grading fields mean self-grade; `check(path)`
runs an executable; guarded `regex(...)` fields grade a typed answer. Questions,
teaching, and folded keys stay in the lessons. `schedule.json` orders the IDs.

`claims.tsv` records sources and verification for course claims and stories.
Course-specific byte and replay claims are exercised by the fixtures and checks in
this repository. `bash manifest/verify.sh` checks the public edition's local structure.
The generated-code jar is downloaded and hash-verified during setup.
