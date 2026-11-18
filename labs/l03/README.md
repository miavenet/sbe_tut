# L03 workspace map

Use from the course root. Budget: 40 minutes estimated in the lesson; troubleshooting is extra.
`worked/` is the full solution; `completion/` has two schema declarations and two reader
arguments to repair; `work/` is the independent matrix fault; `independent/` is the
mixed-archive transfer fault. Edit your selected workspace, then submit its directory.
The check generates codecs from that workspace's `order-v1.xml` and the fixed v0 schema,
compiles its `submission.hpp`, and runs it. The matrix grades the supplied v1 field set;
adding an unrelated field is outside that exercise even if a general extension could be compatible. It never replaces your work with the solution.
Source: [Evidence](../../manifest/claims.tsv)
Run the starter to collect its first diagnostic (untouched work returns MISS/exit 1):

```bash
printf '%s\n' labs/l03/work | checks/l03/chk_matrix.sh
```

For completion, test the schema before filling the reader holes:

```bash
printf '%s\n' labs/l03/completion | checks/l03/chk_schema.sh
printf '%s\n' labs/l03/completion | checks/l03/chk_matrix.sh
```

The untouched completion is deliberately incomplete and returns MISS/exit 1.
After your repair, aim for HIT/exit 0. Use the transfer check on the archive workspace:

```bash
printf '%s\n' labs/l03/independent | checks/l03/chk_archive.sh
```

The untouched transfer loses raw extensions and returns MISS/exit 1.
For a complete worked control, the whole suite returns HIT/exit 0:

```bash
printf '%s\n' labs/l03/worked | checks/chk_l03_compat.sh
```

Each result includes the first failed criterion and a run directory with compiler/runtime
logs. Exit 2 means infrastructure failure and is ungraded. No network is needed after
successfully running `bash tools/setup.sh`. The corpus is bounded; allocating strings/vectors here are for diagnosis and archive
ownership, not a zero-allocation claim. The supplied reader is for trusted lab fixtures;
L04 adds full hostile-input validation. Source: [Evidence](../../manifest/claims.tsv)
