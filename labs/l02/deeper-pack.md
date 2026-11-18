# Optional allocation/lifetime pack — 15 additional minutes, estimated

Use this after L02-T1. Stop after any of these three five-minute tasks; this is
extra time, not part of the 35-minute core.

1. Predict which audit survives: copying a pointer, copying trader's bytes, or
   retaining the whole buffer until the audit finishes. Draw the release point;
   then repeat L02-I1 with the 160-byte trader. Copying a pointer still aliases
   the slot; copying bytes or retaining ownership through the read preserves the
   value. Our runner immediately reuses the slot, so its contract needs a copy.

2. Predict whether an allocation counter that never increments can prove a loop
   allocation-free. Read the separate positive control in `checks/l02/runner.cpp`,
   then restore `getTraderAsString()` in your repaired independent workspace.
   The allocation criterion must fail, while the content checksum still passes.
   Restore the view afterward. A disconnected counter fails the control gate.

3. Before running the Java probe, predict which path allocates: copy into a
   preallocated destination, or produce an owning String. The supplied Java
   example warms both paths, then measures each on its current thread. On the
   configured runtime, the gate requires zero allocated bytes for the copy
   path and a positive count for the owning String path. The exact positive
   count is runtime-dependent. This is separate evidence from the C++ counter.

```bash
python3 checks/l02/java_probe.py
```

Close the source and produce the two scope statements: which operations and
which allocator are counted in C++ vs Java? Check: C++ replaces the declared new
family around the warmed encode/decode loop; Java uses per-thread allocated-byte
measurement around the two warmed trader-access loops. Neither certifies all
application paths. Mark any missing boundary for tomorrow's review.

