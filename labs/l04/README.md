# L04 workbench

Use this folder with `lessons/lesson-04.md`. Do each card's pretest before
opening any worked code. The checks generate C++ codecs from the pinned SBE jar
with precedence checks on, compile your workspace with
`-DSBE_ENABLE_PRECEDENCE_CHECKS`, and run it against the fixtures. They never
replace your file with the worked one.

| Folder | Card | What you do | Marker in `submission.hpp` |
|---|---|---|---|
| `completion/` | L04-C1 | add the missing `next()` call | `TODO(L04-C1)` |
| `work/` | L04-R1 | write the whole fills loop | `TODO(L04-R1)` |
| `validation-completion/` | L04-C2 | add the minimum-root check | `TODO(L04-C2)` |
| `independent/` | L04-T1 | write `read_nested` | `TODO(L04-T1)` |
| `worked/` | none | complete reference; read it only after your attempt | none |

Run every check from the course root, passing the workspace folder on stdin.
An untouched starter prints MISS (exit 1):

```bash
printf '%s\n' labs/l04/work | checks/chk_l04_order.sh
```

That command runs every mode. Each card names the focused check it uses:
`checks/l04/chk_order.sh`, `chk_validate.sh` or `chk_nested.sh`.

Lab policy, which is this course's choice rather than SBE's: the validator
accepts Order schema 91, template 1, versions 0 to 2, where version 2 may add
only fixed fields at the end of blocks; and Capture schema 92, template 2,
version 0. Frames are capped at 262144 bytes. A tape stores each frame after
a little-endian uint32 byte count that includes the 8-byte SBE header. Always
pass the received length, never the slot capacity.

Fixtures: `fixtures/order-v0.bin`, `order-v1.bin`, `nested.bin`,
`nested-bad-length.bin`, and the five broken schemas `fixtures/bad/e1.xml` to
`e9.xml` described in lesson 04 (card L04-P3).
