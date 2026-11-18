# Learn SBE by reading and repairing bytes

Simple Binary Encoding (SBE) puts structured messages into compact bytes. Here you learn to read those bytes, find a mistake, and repair the code that made it. The course takes an estimated 8 hours (an author estimate from card costs; learner completion time has not been measured), spread across short sittings and spaced reviews over at least three weeks. Lessons 01–04 teach the SBE core; lesson 05 puts it inside a small sequenced system. You can pause after any card and pick up where you left off.

## Quick start

From this directory, copy these commands:

```bash
bash tools/setup.sh
python3 drive.py --today "$(date +%F)" --minutes 15 --init
```

On later days, resume with:

```bash
python3 drive.py --today "$(date +%F)" --minutes 15
```

## How a sitting goes

Try to recall before looking. This may feel harder than rereading; familiarity is not the delayed performance we are checking. The driver repeats this reminder at the start of every sitting.

The driver shows one card at a time. Type a prediction or answer; for a lab card, edit the named workspace first and press Enter to run its check there. A check says HIT when the work passes, MISS with the first observed mismatch, or SETUP PROBLEM when it could not grade the work. After a MISS, edit and type `retry`; the first try still determines the review schedule. After a passing check, compare your answer or explanation with each key bullet. At the driver's prompt, enter `:quit` or `/stop` to pause; `:help` lists commands. Your place is saved after each step. Tomorrow, rerun the resume shell command above. Runnable reviews use a fresh copy of the workspace as it was when the first card using that folder opened, so it shows the TODOs of every card that shares the folder; rebuild the repairs that card's check needs and report whether you reconstructed them. Lesson 1 usually takes two or three 15-minute sittings. Reviews normally use up to five minutes; a longer due card may use its full estimate and reduce the time available for new material.

Add `--new-session` to the shell command to start another sitting after exhausting the budget. The driver introduces at most six new concepts per calendar day, across all sittings; after that it offers due reviews and asks you to return tomorrow for new material. Due reviews start with any answer you were sure of but got wrong. For due reviews run `python3 drive.py --today "$(date +%F)" --mode quick --new-session`. For an unlocked exam run `python3 drive.py --today "$(date +%F)" --mode exam --new-session`. Use the same `--progress` path for every sitting belonging to one course history.

## Setup and supported environment

The course was tested on macOS arm64 with Python 3.12.2 (full test run, 2026-11-14); the self-tests and release verification were also run on Python 3.14.6, with Temurin Java/Javac 26.0.1, and Apple Clang 21.0.0. Other platforms and toolchain versions are untested. You need Python 3.9 or newer, Java/Javac 17 or newer (`java` and `javac` on PATH), a compiler that accepts C++17 (the minimums are requirements, not tested versions; only the versions above were run), Bash, and curl for the first download. The Java minimum comes from the pinned jar's `SbeTool.class` class-file version 61. Java programming is not required. The setup script downloads SBE 1.42.0 from Maven Central into `labs/lib/` and checks its pinned SHA-1 and SHA-256. Later runs can use the verified local copy. If setup fails, it prints a next step for macOS and Linux.

## Other ways to study

For paper study, open [Lesson 01](lessons/lesson-01.md) in a Markdown preview so answers remain folded, and follow the check commands on the lab cards. Record each card, date, answer, confidence, result, and next review date in your own notes. The [course map](manifest/course.md) lists objectives and cards. [PROTOCOL.md](PROTOCOL.md) is optional instructions for an AI tutor; this course works without one. Author and tool metadata live in [cards.json](manifest/cards.json); sources and verification notes live in [claims.tsv](manifest/claims.tsv).

Use `python3 drive.py --help` for all driver options, including a different progress file, review-only mode, and the delayed exam. To run the checks on the course files, use `python3 -B tools/test_driver.py`, `python3 -B tools/test_setup.py`, `python3 -B tools/test_scripted_l01.py`, `python3 -B tools/test_verify.py`, and `bash manifest/verify.sh`. After editing lesson costs, run `python3 -B tools/refresh_estimates.py`. Lab diagnostics accumulate in `manifest/evidence/`; you can delete that directory after a sitting. The xxHash32 adaptation carries the [xxHash notice](LICENSES/xxHash.txt); the FIX SBE schema carries its Creative Commons licence link in [sbe.xsd](labs/common/sbe.xsd).
