# Layout workspace

Folders, in the order lesson 01 uses them:

- `work/`: card L01-C2. Edit the lines marked `TODO(L01-C2)` in
  `submission.hpp` and two numbers in `layout.json`.
- `completion/`: an untouched copy of `work/`. `cp completion/* work/`
  restores the starter (and overwrites your edits).
- `independent/`: cards L01-I1 (lines marked `TODO(L01-I1)`, plus
  `layout.json`) and L01-T1 (`decode_market`, marked `TODO(L01-T1)`). Try them
  without opening `worked/`.
- `worked/`: the finished solution, for after your attempt.
- `fixtures/faults/`: deliberately broken encoders; their checks report MISS.

A workspace holds `submission.hpp` and `layout.json` and uses the supplied
`api.hpp`. Input symbols are at most eight bytes, there are at most two fills,
and the strings fit the supplied buffer. These are bounded exercise inputs, not
an untrusted-network validator.

Compile primer: XML describes the wire contract; the pinned generator produces
C++ headers. A header is included into the supplied runner's translation unit;
`clang++ -std=c++17 -O2` compiles it, and the resulting executable calls your
functions with the supplied cases. The check handles generation, include paths,
compilation, execution and byte comparison; you edit no Java. Build diagnostics
name the source/line to repair.

Prerequisite quick check (two minutes, included in the lesson estimate): explain
why a pointer plus a length is different from an owning array; write `0x0102` as
two little-endian bytes; locate `encode`'s return type and arguments in the
starter. Cover the next paragraph until you have tried.

<details><summary>Prerequisite key</summary>

The pointer refers to existing bytes; an owning array supplies storage. The bytes
are `02 01`. The starter returns `std::size_t` and takes `const Input&`, `char*`
and `std::size_t`. If the declarations are unfamiliar, use the worked function
to identify input, output buffer and capacity before starting the independent
repair.
</details>

The four-uint16 header, v0/v1 schemas and golden packets are copied from the
common package. The extra market schema is a course-local Quote exercise, not
an exchange feed contract. Its binary records are independently packed in
big-endian order and decoded by the generated C++ accessors in the worked
submission.
