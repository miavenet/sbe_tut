# Optional: evolution under a microscope — 15 minutes estimated

Cover the worked answer and choose one fault from `fixtures/bad/`: mid-block,
composite, group-add, group-data or data-insert. Predict the first changed offset
or cursor, then inspect its difference from `order-v1.xml`. The exercise checks
whether generation accepts the bad schema and whether the separate regression rejects it.
Source: [Evidence](../../manifest/claims.tsv)
Spend five minutes on a field/composite case, five on group/data, then five explaining
why successful code generation was the wrong acceptance criterion. To execute the
bounded fault pack with its built-in correct and wrong controls:

```bash
python3 -B checks/l03/acceptance.py
```

The pack returns PASS only if correct work passes and each deliberate fault is detected.
It checks the submitted reader faults separately from the XML regression. The structural
regression is a deliberately limited course policy, not a full implementation of every
permitted SBE evolution. Source: [Evidence](../../manifest/claims.tsv)
Production checkpoint: explain why a new group before trader violates this lab’s contract,
and why appending fixed venue bytes works where inserting a per-entry memo does not.
Give each bullet HIT/PARTIAL/MISS and bring misses back tomorrow.

<details><summary>After answering</summary>

Key:
- This lab’s readers have no counts or traversal support for discovering a newly inserted group before trader. Their expected next structure would be wrong.
- A larger fixed entry blockLength lets an older reader skip appended fixed venue bytes. It does not describe a per-entry variable-length memo or tell this reader how to skip it.
- These are restrictions of this lab’s contract and readers, not universal bans in SBE.

</details>
For an extra preservation diagnosis, explain the raw-loss fault against L03-T1's key.
