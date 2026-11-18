# Optional nested/hostile-input pack — 15 minutes estimated

Only after the core lesson: predict one failure, run it, then repair a fresh copy
of the corresponding fixture. The enclosing test below verifies correct work
passes and plausible wrong work fails. Read `outcomes.json` under its reported
artifacts directory for each failed criterion; the enclosing PASS means the
faults were caught, not that their code was correct.

```bash
python3 -B checks/l04/acceptance.py
```

Choose `fixtures/faults/short-root`, `short-entry`, `null-length`, `skip-nested`
or `tape-capacity` under labs/l04. Their checks isolate missing minimum block,
null length, traversal and framing repairs. Diagnose hypothesis → bytes/cursor
→ one repair → rerun. Explain why your repair also preserves the empty-group
and compatible-v2 controls.

Source: [acceptance suite](../../checks/l04/acceptance.py), [fault fixtures](fixtures/faults/)
