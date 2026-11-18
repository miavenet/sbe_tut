# Ownership workspace

Folders, in the order lesson 02 uses them:

- `work/`: card L02-C1. Edit the two lines marked `TODO(L02-C1)`.
- `completion/`: an untouched copy of `work/`; `cp completion/* work/`
  restores the starter (and overwrites your edits).
- `independent/`: card L02-I1 (`capture`, marked `TODO(L02-I1)`) and card
  L02-T1 (`consume`, marked `TODO(L02-T1)`).
- `worked/`: the finished solution, for after your attempt.
- `fixtures/faults/`: deliberately broken encoders; their checks report MISS.

`api.hpp` defines the bounded inputs; `audit.hpp` supplies a 256-byte result
buffer and an ownership flag. The tested trader lengths are 3, 3, 0 and 160;
the runner overwrites each slot with another trader of the same length before
reading the saved result.

`order-padded.xml` is a course-owned variant of v1, with a 40-byte root and two
explicit trailing padding bytes. Use it only for this exercise; the immutable
v1 fixture copied here has the original 38-byte root. Do not conflate their
wire lengths. The exact-byte oracle checks all fields and padding on dirty and
reused slots; it does not grade by successful decoding alone.

The normal-priority runner warms 100 iterations, then measures 1,000 bounded
encode/decode iterations with four cases. Direct C allocation APIs and VM calls
are outside the counter; setup, errors, logs and I/O are outside the interval.
An owning long-string control must hit. Check the lesson for the full scope
before calling this “zero allocation.”
