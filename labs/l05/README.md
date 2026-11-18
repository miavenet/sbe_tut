# L05 workspace guide

Use this folder with `lessons/lesson-05.md` (about 71 minutes in four
sittings; the optional load pack adds 15). Pebble, the service in this lab,
is fictional. Its frame layout and its type numbers 60000 (Order) and 60001
(Control) are course inventions, not allocations from any real system.

Every check reads a workspace folder on stdin, compiles that folder's
`submission.hpp` with the supplied `api.hpp`, `codec.hpp` and `hash32.hpp`,
and runs it against `fixtures/`. Run checks from the course root; each prints
its first failed criterion. Running a check writes local logs under
`manifest/evidence/wp4/`. Nothing runs in the background.

| Folder | Cards | Marker | What is wrong |
|---|---|---|---|
| `completion/` | L05-C1, C2, C3 | `TODO(L05-C1)`, `TODO(L05-C2)`, `TODO(L05-C3)` | frame length and stamp order; back pressure; release gate |
| `work/` | L05-R1, R2, R3, C4 | `TODO(L05-R1)`, `TODO(L05-R2)`, `TODO(L05-R3)` | the same faults plus request dedup; `migration.json` reserved |
| `enum-work/` | L05-R4 | `TODO(L05-R4)` in `codec.hpp` | an unknown side becomes BUY |
| `independent/` | L05-T1 | one `TODO(L05-T1)` note at the top | three policy faults; `migration.json` reserved |
| `worked/` | none | none | complete reference (its `codec.hpp` is the L05-R4 answer); read it only after your attempt |

The checks: `checks/l05/chk_frame.sh`, `chk_replay.sh`, `chk_release.sh`,
`migration.py`, and the full suite `checks/chk_l05_sequencer.sh`. For example
(an untouched starter prints MISS):

```bash
printf '%s\n' labs/l05/work | checks/l05/chk_frame.sh
```

Lab policy: Order schema 91, template 1, versions 0 to 2 (version 2 only adds
fixed fields at the end of blocks); Control schema 93, template 2, version 0,
which logs the business rule (1 or 2) and the time. Unknown sides, missing required values and truncated or oversized frames are rejected before committing business or protocol-progress changes. Rejection sets the reader’s halted flag. The model is single
threaded: no consensus, network or power-loss durability is implemented.

`migration.json` is a proposal. The migration check grades only its numbers
and structure; card L05-T2 grades the reasoning by self-report.
