# Lesson 05 — The order was encoded. Was it promised?

Imagine an exchange that accepts an order, smiles at the client, then
discovers its replica never received it. (Hypothetical incident; very real
distinction.) Today's question: **which boundary did your acknowledgement promise?**

You will repair a tiny sequenced message path built around SBE: frame it,
fan it out, replay it, and decide when it may be acknowledged.

**Time: about 71 minutes, in four sittings of 12–21 minutes.** Stop after any card.
**You need from L01–L04:** null versus zero, block length versus frame
length, and reading in schema order.

## Read this first: what is SBE here, and what is not

Most of this lesson is **system design**, not SBE. SBE encodes one message.
It says nothing about sequence numbers, replicas or acknowledgements. Its
authors drew that line on purpose: Thompson's introduction calls SBE "an OSI
layer 6 presentation", and the project's design principles assume messages
travel "encapsulated within a framing protocol". The framing is yours to
build. Each part is labelled **[SBE]** or **[system]** so you know which is which.

The fictional service for the whole lesson is **Pebble**, a toy order
service. Nothing here describes a real exchange:

```text
client order --> [stamper] --> fan-out queue (2 slots) --> consumer A
   (SBE bytes)    adds sequence,                      \--> consumer B
                  epoch, checksum                      \-> tape file --> fresh replay
```

The stamper is the single writer that numbers every message. Consumers A and
B are two copies of the business logic that must end in the same state. The
tape is a file of every accepted frame, used to rebuild state from scratch.

## Sitting 1 — frame and validate (20 minutes)

### Card L05-P1 · Guess first
Q: Cold guess (a number): the SBE encoder for one Order reports encodedLength() = 77. Pebble wraps every SBE message in its own outer header. How many bytes do you guess the whole frame is on the wire?
<details><summary>Reveal after your guess and confidence</summary>
Key:
- 117: Pebble's 32-byte outer header + the 8-byte SBE header + the 77-byte body. encodedLength() does not count the SBE header.
</details>

### Concept L05-FRAME · Two lengths, one boundary
Vocabulary: payload = the SBE message (8-byte SBE header plus body); envelope = Pebble's 32-byte outer header; checksum = a 32-bit fingerprint of bytes; stamp = write sequence and epoch into the envelope, then the checksum.

**[SBE] Two lengths.** `encodedLength()` counts the body only, not the 8-byte
SBE header. It also grows as you encode: a fresh v1 Order encoder reports 38
(just the root block). A complete Order with an empty group and empty strings
is a 54-byte payload: 8 header + 38 root + 4 group dimensions + 2 + 2 string
lengths. For the fixture order, body 77 means payload **85**.

**[system] The envelope.** Pebble puts a 32-byte header in front of the
payload. This layout is the lab's own invention, little-endian:

| Offset | Field | Fixture value |
|---|---|---|
| 0 | sequence (u64) | 1 |
| 8 | origin (u32): where the request entered Pebble | 9 |
| 12 | stream (u32), must be 1 | 1 |
| 16 | checksum (u32) | 3170967930 |
| 20 | epoch, the leadership term (u32) | 7 |
| 24 | msg_type (u16): 60000 Order, 60001 Control | 60000 |
| 26 | length (u16) = payload bytes | 85 |
| 28 | reserved (u32), must be 0 | 0 |
| 32 | payload | 85 bytes, frame ends at 117 |

The type numbers 60000/60001 are made up for this lab, not allocated by anyone.

**[system] Imagine a damaged message.** One bit changes a valid quantity into
another valid quantity. The message still parses, but its meaning has changed.
Structural validation alone cannot detect every accidental change; Pebble
therefore checks a checksum as well.

**[system] The checksum** is a fingerprint. Change any covered byte and the
fingerprint almost surely changes. It catches accidental damage; it is not a
security signature. Pebble uses an adaptation of xxHash32 over everything
except the checksum field itself (supplied in `labs/l05/api.hpp`):

```cpp
inline std::uint32_t checksum(const Frame& f) noexcept {
    Hash32 x; x.update(f.bytes.data(),16);        // bytes 0..15: sequence..stream
    x.update(f.bytes.data()+20,12);               // bytes 20..31: epoch..reserved
    x.update(f.bytes.data()+32,f.size-32);        // the payload
    return x.digest();
}
```

**`make_frame`** builds a frame from a payload of `n` bytes. It checks `n`,
copies the payload into a staged frame, fully decodes it (validation), writes
origin, stream, type and length, and only then copies the staged frame out.
Any exception means "return false", leaving the output untouched.
**`stamp`** then assigns the sequence and epoch, and finally the checksum.

A checksum is not the only kind of fingerprint. Compare it with a message
authentication code (MAC) such as HMAC, which mixes in a secret key that
sender and receiver share:

| | Checksum (Pebble's xxHash32) | Keyed MAC (e.g. HMAC) |
|---|---|---|
| Needs a secret key | no: anyone can recompute it | yes |
| Built to resist a deliberate forger | no: xxHash "is not meant to avoid intentional collisions" | yes, that is its job |
| Proves the frame is well-formed | no | no |

Use a checksum to catch accidents on a path you already trust; reach for a keyed MAC when someone could tamper; and keep your length and payload checks either way.

Predict: If stamp() computes the checksum first and writes sequence 1 and epoch 7 afterwards, will the frame match the 117-byte fixture? Why?

<details><summary>Worked answer — open after predicting</summary>

No. The checksum covers bytes 0–15 and 20–31, which include the sequence and
the epoch. Computed before they are written, it fingerprints zeros. The
fixture's checksum 3170967930 is `7a 21 01 bd` on the wire, so the check
reports the first wrong byte:

```text
byte 16 checksum: observed 160, expected 122
```

Two wrong beliefs to drop:

- "The length field holds `encodedLength()`." Write 77 and every reader cuts
  off the last 8 bytes of the payload. The field holds the payload size, 85.
- "A valid checksum proves the frame is complete." The check builds a frame
  whose length field says 38, recomputes the checksum, and the reader must
  still reject it. A matching checksum is a consistency check, not proof that the bytes are unchanged: collisions are possible, and xxHash is not authentication. A sender can also stamp a structurally invalid frame. The reader must independently check length = received − 32 and validate the payload.

**Rule:** length = whole SBE payload (header included); stamp sequence and epoch, then checksum.
</details>

Elaborate: Why must both the length check and the checksum check exist? If only the second frame of a stream fails, which value do you inspect first?

### Card L05-C1 · Complete the repair
Open `labs/l05/completion/submission.hpp`. Two lines are marked
`TODO(L05-C1)`: the length written in `make_frame`, and the order inside
`stamp`. The frame check also tests the validator and price conversion; those
are already correct here. Untouched, it prints MISS with
`FAIL criterion=independent envelope/checksum bytes: byte 16 checksum: observed 160, expected 122`.
Repaired, it prints HIT.

```bash
printf '%s\n' labs/l05/completion | checks/l05/chk_frame.sh
```

Q: Repair both TODO(L05-C1) lines in labs/l05/completion/submission.hpp, then run the frame check. Your answer is the edited file.
<details><summary>Key after your attempt</summary>
Key:
- Write `n` (the whole SBE payload size) into the length at byte 26, not `n-8`; frame size is 32 + n.
- In `stamp`, write sequence and epoch first, then compute and write the checksum.
</details>

### Card L05-R1 · Recall and repair
Close the worked file. `labs/l05/work/submission.hpp` has the same two
framing faults, marked `TODO(L05-R1)`. Its other markers belong to later
cards. Untouched, the frame check prints the same byte-16 MISS.

```bash
printf '%s\n' labs/l05/work | checks/l05/chk_frame.sh
```

Q: (a) Repair the TODO(L05-R1) lines in labs/l05/work/submission.hpp and run the frame check. (b) Explain why a frame with a valid checksum can still be invalid.
<details><summary>Key after your attempt</summary>
Key:
- (a) Length field = `n`; in `stamp`, sequence and epoch before checksum; the frame check prints HIT.
- (b) Explain: A matching checksum does not prove structural validity or unchanged bytes. A wrongly constructed or re-stamped frame can match its checksum, and collisions are possible. Check the declared length against the received bytes and validate the payload independently.
</details>

### Card L05-R4 · Recall and repair
**[SBE] Unknown enum values.** `Side` allows only `B` (BUY) and `S` (SELL). A
newer sender might send `?`. What the generated C++ does depends on a
generator property. In sbe-tool 1.42.0 the default is off, so `Side::get` throws:

```cpp
throw std::runtime_error("unknown value for enum Side [E103]");
```

Generated with `-Dsbe.decode.unknown.enum.values=true`, it instead returns
`Side::SBE_UNKNOWN`. **[system]** Pebble rejects the order either way, before committing business or protocol progress; a rejected receive sets its halted flag. It must never guess BUY. The frame check builds with the
default mode; the author suite `checks/l05/acceptance.py` also runs the
tolerant mode. After changing the sbe-tool version, run both again to see which behaviour you now get; this course did not test other versions.

In `labs/l05/enum-work/codec.hpp`, the line marked `TODO(L05-R4)` skips the
generated accessor and reads the side byte itself (payload byte 40 = 8-byte
header + root offset 32). Anything that is not `S` becomes `B`. Untouched,
the frame check prints MISS with `FAIL criterion=unknown enum adapter reject`.

```bash
printf '%s\n' labs/l05/enum-work | checks/l05/chk_frame.sh
```

Q: Repair the TODO(L05-R4) line in labs/l05/enum-work/codec.hpp so an unknown side is rejected before business or protocol progress while BUY and SELL stay valid, then run the frame check until it prints HIT.
<details><summary>Key after your attempt</summary>
Key:
- Use the generated accessor (`e.side=char(o.side());`, which throws on `?` in default mode; a later line rejects anything but B/S) or reject any byte other than `B`/`S` explicitly. Never map an unknown value to BUY.
</details>

## Sitting 2 — fan out and replay (18 minutes)

### Card L05-P2 · Guess first
Q: Cold guess (yes/no): two consumers decode identical bytes for a buy of quantity 3. One applies business rule "multiplier 1", the other "multiplier 2". Must they end with the same running total?
<details><summary>Reveal after commitment</summary>
Key:
- No. The lab's counterexample gives totals 3 and 6. Identical bytes do not force identical behaviour when other inputs differ and are not in the log.
</details>

### Concept L05-REPLAY · The log is the recipe
Vocabulary: back pressure = a full queue refuses new items instead of overwriting; protocol duplicate = the same frame delivered again; business duplicate = the same client request sent again in a new frame; latch = stop after a bad frame and refuse everything after it; deterministic replay = rebuilding the same state from the log alone.

All of this is **[system]**. Only the Control message (`labs/l05/control.xml`,
schema 93) is SBE: it logs a rule change and the current time.

**Back pressure.** Pebble's fan-out queue has 2 slots and one read position
per consumer. A slot can be reused only after **both** consumers have passed
it. Example: write position 2, A has read 1, B has read 0. Measured against
the slower reader, 2 − 0 = 2 slots are in use, so the queue is full. Writing
now would overwrite slot 0 before B reads it. So `offer` returns false; the
caller keeps the exact frame and retries later. Measured against A alone,
2 − 1 = 1, which wrongly looks like room.

**Sequence, epoch, latch.** Each consumer expects sequence numbers 1, 2, 3…
and the current epoch (7 in the lab). `receive` checks, in order: frame
length, stream and reserved, checksum, epoch, then sequence. A checksum
fault, a gap, a wrong epoch, a conflicting request or a malformed payload
**latches** the reader: it stops and refuses every later frame until it is
rebuilt from trusted input. It never silently skips. The check tries 96 such bad inputs and requires each to set `halted=true` while leaving business results, deduplication records and protocol progress unchanged.

**Two kinds of duplicate.**

- Protocol duplicate: the exact last frame arrives again (same sequence,
  same bytes). Ignore it; nothing changes, not even the expected sequence.
- Business duplicate: a client resends request 11 from the same origin, so
  the stamper gives it a new sequence. It uses up that sequence number but
  has no business effect. If the same origin and request ID arrive with
  different order bytes, that is a conflict: reject (and latch).

Side by side, with what `receive` does with each:

| What arrives | Looks like | Pebble's `receive` |
|---|---|---|
| Protocol duplicate | sequence one below expected, same bytes as the last frame | ignore; nothing changes |
| Business duplicate | expected sequence, known origin + request ID, same order bytes | consume the sequence; no business effect |
| Conflict | known origin + request ID, different order bytes | reject and latch |
| Gap or stale sequence | any other sequence than expected | reject and latch: missing frames may have changed state |

A duplicate is something you already have; a gap is something you never got, and skipping it lets two replicas disagree without anyone noticing.

**The log is the recipe.** The business rule and time are inputs, so they
are logged as Control records, not read from a config file or clock. The
check's tape, sequences 1 to 5:

```text
1 Control rule=1 time=10
2 Order request 11, buy 3     -> total  3
3 Order request 11 again      -> business duplicate, no effect
4 Control rule=2 time=20
5 Order request 12, sell 4    -> total 3 - 4*2 = -5
outputs (request:time:total):  11:10:3, 12:20:-5
```

Both consumers and a fresh replay of the tape must print exactly that.

Predict: Consumer A has read slot 0; consumer B has not. Both slots are full. Can the producer overwrite slot 0 in this two-slot queue?

<details><summary>Worked answer — open after predicting</summary>

No. B has not read slot 0 yet. The worked `offer` measures against the
slower reader:

```cpp
inline bool offer(Queue& q,const Frame& f) noexcept {
    auto slow=q.read[0]<q.read[1]?q.read[0]:q.read[1];
    if(q.write-slow>=q.slots.size())return false;   // full: refuse, change nothing
    q.slots[q.write%q.slots.size()]=f;++q.write;return true;
}
```

The check pauses B, asserts the refusal leaves both slots unchanged, lets B
read at an explicit point, then retries **the same frame**. Retrying with a
new request ID would describe a new business request. Everything is single
threaded; there is no network or real ring buffer.

The common wrong belief: "the fast consumer is the one that matters." The
slowest reader decides when a slot is free.

**Rule:** refuse at capacity measured by the slowest reader; log every input
that affects results; latch on anything you cannot explain.
</details>

Elaborate: Which state advances for a business duplicate? Which state must stay unchanged on a malformed payload?

### Card L05-C2 · Complete the repair
Open `labs/l05/completion/submission.hpp`. The `offer` line marked
`TODO(L05-C2)` measures against consumer 0 only. Do L05-C1 first: the replay
check needs working frames. After C1 but before this fix, it prints MISS with
`FAIL criterion=slow consumer backpressure`. Repaired, it prints HIT.

```bash
printf '%s\n' labs/l05/completion | checks/l05/chk_replay.sh
```

Q: Repair the TODO(L05-C2) line of offer in labs/l05/completion/submission.hpp so it measures against the slower of the two read positions, then run the replay check. Your answer is the edited file.
<details><summary>Key after your attempt</summary>
Key:
- Compare the write position with the minimum of `q.read[0]` and `q.read[1]`; return false at capacity before writing any slot.
</details>

### Card L05-R2 · Recall and repair
Close the worked file. In `labs/l05/work/submission.hpp`, two lines are marked
`TODO(L05-R2)`: one in `offer`, one in the request-dedup loop of `receive`.
Do L05-R1 first. With only `offer` fixed, the replay check prints MISS with
`FAIL criterion=independent output oracle`.

```bash
printf '%s\n' labs/l05/work | checks/l05/chk_replay.sh
```

Q: (a) Repair both TODO(L05-R2) lines in labs/l05/work/submission.hpp and run the replay check. (b) Explain which key identifies a protocol duplicate and which identifies a business duplicate.
<details><summary>Key after your attempt</summary>
Key:
- (a) `offer` uses the slower read position; the dedup loop scans all `s.used` seen requests; the replay check prints HIT.
- (b) Explain: Protocol duplicate: the frame one before the expected sequence with exactly the same bytes as the last frame. Business duplicate: same origin and request ID with an equal payload; the same pair with a different payload is a conflict and rejects.
</details>

### Card L05-J1 · Judge the design
An AI assistant reviews Pebble's `receive` and says: "Latching on a gap is
too brittle; real systems resync." It proposes replacing the sequence check
with this:

```cpp
if (seq != s.next) {               // gap: log it and resync
    log_warning("sequence gap", s.next, seq);
    s.next = seq;                  // jump to the new sequence and keep going
}
```

Context: consumers A and B must end in the same state, and a fresh replay of
the tape must print `11:10:3, 12:20:-5`.

Q: Judge the proposal for Pebble, in three short answers. (a) Right or wrong here, and why, in one sentence. (b) What you would ask first about the frames it skips. (c) Using the check's tape, one concrete result that would make you reject it.
<details><summary>Self-grade each part</summary>
Key:
- (a) Wrong for Pebble: the skipped frames may have changed state, so a consumer that resyncs silently disagrees with one that saw them, and a stale sequence would even move `next` backwards.
- (b) Could any skipped frame change results, such as a Control record or an order? If yes, the reader must latch and be rebuilt from trusted input, not guess.
- (c) If sequence 4 (the rule change to 2, time 20) is the one lost, request 12 is applied with rule 1 at time 10, so the output becomes `12:10:-1` instead of `12:20:-5`.
</details>

## Sitting 3 — when may we say yes? (12 minutes)

### Card L05-P3 · Guess first
Pebble runs three nodes: the leader and two followers, one of them its named
"secondary". It can choose one of three release policies:

- **non-gated**: release as soon as the record is stamped;
- **pair**: wait until the leader and the named secondary have both stored it;
- **quorum**: wait until the leader and either follower have stored it.

Q: Cold guess: a record is stamped and stored by the leader; the secondary is paused, but the other follower stored it. Which of the three policies may release it now?
<details><summary>Reveal after commitment</summary>
Key:
- Non-gated and quorum may release; pair waits for its named secondary.
</details>

### Concept L05-RELEASE · A stamp is not a promise
Vocabulary: persist = written to stable storage (here a modelled yes/no); follower = a node that keeps a copy; quorum = a majority, here leader plus either follower; epoch = the leadership term number; fencing = ignoring a leader whose epoch is old; release = permission to apply and then acknowledge; acknowledge = the promise sent to the client.

All of this is **[system]**; SBE plays no part. Each step proves something
different:

```text
encode -> enqueue -> stamp -> persist/replicate -> release -> apply -> ack
bytes     local      order    copies exist         gate       effect   promise
```

**Imagine a fenced leader.** The old leader (epoch 7) loses its network link.
The others elect a new leader, epoch 8. The old leader does not know yet and
keeps stamping. Every frame it stamps says epoch 7, so everyone fences it:
nothing it stamps is released, even if each node stored it. The lab models
the election as a given input; it does not implement one.

The lab models each record's evidence as a struct (in `labs/l05/api.hpp`):

```cpp
struct Boundary {bool stamped=false,local_persisted=false,
                 secondary_persisted=false,other_persisted=false;
                 std::uint32_t leader_epoch=7,current_epoch=7;};
```

`release(policy, boundary)` returns `{apply, ack}`. All three policies first
require `stamped` and `leader_epoch == current_epoch`. Then non-gated says
yes; pair needs local and secondary; quorum needs local and (secondary or
other). The check tries all 96 combinations (16 flag sets × current/stale
epoch × 3 policies), then a 12-event story in
`labs/l05/fixtures/release-traces.hpp`.

Predict: Both followers lose record 101 after it is stamped, and the leader never stores it. Does the non-gated policy still acknowledge it? What is lost if the leader then fails?

<details><summary>Worked answer — open after predicting</summary>

Yes. Non-gated releases at stamping, so the client was promised an order
that now exists nowhere. The fixture's story (abridged), with the policies
allowed to release after each event:

```text
record event                        non-gated  pair  quorum
101    stamped; replication lost        yes      -      -
101    primary lost; fenced (7 vs 8)     -       -      -
102    new epoch stamped                yes      -      -
102    local persist                    yes      -      -
102    other follower persists          yes      -     yes
102    secondary resumes and persists   yes     yes    yes
102    same-identity retry              yes     yes    yes   (no second effect)
103    stale leader, all stored          -       -      -
```

Released records: non-gated {101, 102}, pair {102}, quorum {102}. The
common wrong belief: "it is in the queue, so it is safe." Enqueue success
proves only that this process holds it. The lab models none of: power-loss
durability, networks, elections or production failover.

**Rule:** acknowledge only what your chosen policy has proven, and never for a fenced leader.
</details>

Elaborate: State the promise each policy makes in one sentence. Why is enqueue success insufficient for all three?

### Card L05-C3 · Complete the repair
Open `labs/l05/completion/submission.hpp`. In `release`, the line marked
`TODO(L05-C3)` starts with `true||`, so every stamped, current-epoch record bypasses the persistence gate. Untouched,
the release check prints MISS with `FAIL criterion=release decision set`.

```bash
printf '%s\n' labs/l05/completion | checks/l05/chk_release.sh
```

Q: Repair the TODO(L05-C3) line of release in labs/l05/completion/submission.hpp so it applies the declared non-gated/pair/quorum gate, then run the release check. Your answer is the edited file.
<details><summary>Key after your attempt</summary>
Key:
- Remove `true||`: non-gated releases; pair needs local + secondary; quorum needs local + (secondary or other). The stamped and epoch test above it stays first.
</details>

### Card L05-R3 · Recall and repair
Close the worked file. `labs/l05/work/submission.hpp` has the same release
fault, marked `TODO(L05-R3)`.

```bash
printf '%s\n' labs/l05/work | checks/l05/chk_release.sh
```

Q: (a) Repair the TODO(L05-R3) line in labs/l05/work/submission.hpp and run the release check. (b) Explain what an acknowledgement promises the client under each of the three policies.
<details><summary>Key after your attempt</summary>
Key:
- (a) The release check prints HIT, including stale-epoch and follower combinations.
- (b) Explain: Non-gated: only that the order was stamped in the current epoch; it may exist nowhere else. Pair: the leader and the named secondary stored it. Quorum: the leader and at least one follower stored it. All three assume the apply succeeded and the model's membership and fencing; none proves real power-loss survival.
</details>

## Sitting 4 — plan the migration (21 minutes)

### Card L05-P4 · Guess first
Q: Cold guess (yes/no): to signal a new Order version, could you write a version number into the envelope's reserved field and upgrade only the writers?
<details><summary>Reveal after commitment</summary>
Key:
- No. Every reader in the lab rejects a frame whose reserved field is not 0, so an un-upgraded reader would refuse every new frame. Versions belong in the SBE header (schema, template, version), and readers must be upgraded before writers.
</details>

### Concept L05-MIGRATE · A proposal with an honest border
Vocabulary: mapping = an explicit rule for each field (convert, keep or drop); CODE = an implementation exercised by tests; SPEC = a documented contract, whether or not implemented; PLAN = deferred implementation work; archive = stored old frames that must stay readable.

Suppose Pebble's toy Order must move into a fictional richer service,
**Pebble v2**. Its rules:

- prices are integers in units of 1e-4;
- Each order also needs a timestamp, an external request ID distinct from `orderId`, execution instructions beyond the three `OrderFlags` bits, and order-level venue extensions distinct from `fills.venue`. The toy cannot supply these additional requirements.
- old readers accept only message types they know and reject the rest;
- reserved bytes stay zero; readers and writers deploy separately;
- stored frames must stay readable; rule changes must be in the log.

**[SBE] Price scaling.** The toy `Decimal` stores a mantissa on the wire
and a **constant** exponent of −2 in the schema, so mantissa 12345 means
123.45. In units of 1e-4 that is 12345 × 100. Multiplying can overflow
int64, so check first (the lab's `price_e4`, already correct in your files):

```cpp
constexpr std::int64_t factor=100;
if(p>INT64_MAX/factor||p<INT64_MIN/factor)return false;   // reject, don't wrap
out=p*factor;return true;
```

**[SBE] Null is not zero.** An optional stop price that is null means "no
stop price", so it maps to absence, never to 0.

**[system] A true story about reusing a field.** In 2012 Knight Capital
deployed new code to its order router, SMARS, for an NYSE retail program.
According to the SEC's order, the new code "repurposed a flag that was
formerly used to activate" an old function called Power Peg, unused for
years but still present. A technician did not copy the new code to one of
the eight SMARS servers, and no second technician reviewed the deployment.
On 1 August, orders carrying the repurposed flag reached that eighth server,
which still read the flag with its old meaning and ran Power Peg. In about
45 minutes SMARS sent millions of child orders; Knight lost $460
million. An old reader met a field whose meaning had changed, and it acted
instead of rejecting. Pebble keeps reserved bytes at zero and gives an
incompatible meaning a new type, which its old readers reject.

**[system] Deploy readers first.** If writers upgrade first, old readers
receive a message type they reject. **Archives:** keep the raw framed bytes
and a decoder that reads them, rather than re-encoding them.

**[system] Honest status.** Label every part of the proposal: the lab's frame
codec and replay test are CODE (you ran them); the 32-byte layout is SPEC;
leader election and snapshots are PLAN. Reading a test's source is not
running it.

The proposal lives in `migration.json`. The check grades only its structure
and numbers, for example:

```json
"reserved": 0, "source_exponent": -2, "target_scale": 10000,
"conversion_multiplier": 100, "overflow_policy": "reject-before-multiply",
"toy_only": ["fills", "trader", "note", "clientTag"]
```

Predict: Toy mantissa 12345 at exponent −2 becomes what integer at Pebble v2's 1e-4 scale?

<details><summary>Worked answer — open after predicting</summary>

**1234500**: 123.45 × 10000, which is mantissa × 100, after the overflow
check. The common wrong belief is “the toy Order is a drop-in replacement.”
Those additional requirements have no source fields in the toy, while fills,
trader, note and clientTag have no destination in this exercise. State each
missing or dropped mapping explicitly.
`labs/l05/worked/migration.json` is a complete example, including the
omitted and toy-only fields.

**Rule:** map every field explicitly, check before you scale, deploy readers
before writers, and label CODE, SPEC and PLAN honestly.
</details>

Elaborate: Which migration decision protects old archives, and which protects replay after a business-rule change?

### Card L05-C4 · Complete the repair
`labs/l05/work/migration.json` has one wrong number. Untouched, the
migration check prints MISS with `migration-structure: repair reserved`.

```bash
printf '%s\n' labs/l05/work | checks/l05/migration.py
```

Q: Correct the reserved value in labs/l05/work/migration.json and run the migration check. Your answer is the edited file.
<details><summary>Key after your attempt</summary>
Key:
- `"reserved": 0`. The other numbers (`envelope_bytes` 32, `payload_limit` 1408, `conversion_multiplier` 100) already match.
</details>

### Card L05-T1 · Apply it elsewhere
Switch to `labs/l05/independent/`. Its framing, queue and enum code is
correct. Three **policy** faults hide in `receive` and `release` (marked
only by one `TODO(L05-T1)` note at the top), plus a wrong `reserved` in its
`migration.json`. The full suite also replays an old v0 frame followed by a
torn v1 frame: the v0 order must apply, the torn one must not. Untouched it
prints MISS with `FAIL criterion=independent output oracle`.

```bash
printf '%s\n' labs/l05/independent | checks/chk_l05_sequencer.sh
```

Q: In labs/l05/independent, repair four parts and run the full suite until it prints HIT: (a) the request-dedup loop, (b) rule handling in receive, (c) stale-leader fencing in release, and (d) the reserved value in migration.json.
<details><summary>Key after your attempt</summary>
Key:
- (a) Request dedup must scan the seen requests (`i<s.used`, not `i<0`).
- (b) `receive` must not reset the logged rule (remove `staged.rule=1;` before `apply`).
- (c) `release` must fence a stale leader (`b.leader_epoch!=b.current_epoch` returns no release).
- (d) `migration.json` has `"reserved": 0`.
</details>

### Card L05-T2 · Apply it elsewhere
Q: From memory, write a four-part plan to move the toy Order into Pebble v2 (or a service of your own): (a) framing and dispatch, (b) field mapping, (c) archives and deployment, (d) CODE, SPEC or PLAN for each part.
<details><summary>Key after your attempt</summary>
Key:
- (a) Keep the frame contract and reserved = 0; get a real message type through the destination's own process; dispatch by outer type, then schema/template/version; old readers reject unknown types.
- (b) Scale prices with an overflow check; null stays absence, not zero. Map quantity, side, symbol and the three flags explicitly. Identify the additional v2 requirements the toy cannot supply, and the toy-only fields v2 drops.
- (c) Keep raw framed archives plus a decoder for them; upgrade readers before writers; log rule changes so replay reproduces behaviour.
- (d) The lab's frame codec and replay test are CODE; the frame layout is SPEC; election and snapshots are PLAN. Say which parts you ran.
</details>

### Card L05-INT · Connect the ideas
Q: Your teammate says: "The bytes decode, the checksum passes and the client got an acknowledgement, so replay and failover are solved." Give one counterexample each for (a) decoding, (b) the checksum, and (c) acknowledgement.
<details><summary>Key after your attempt</summary>
Key:
- (a) Decodes: a reader with an unlogged rule change decodes the same bytes and computes a different total (3 versus 6).
- (b) Checksum passes: a frame can carry a stale epoch, a wrong length or an unknown side and still have a valid checksum.
- (c) Acknowledged: under the non-gated policy, record 101 was acknowledged and then lost with the leader.
</details>

## Close

Remember three rules. Length means the whole SBE payload, and the checksum
comes last. Log every input that changes results. Acknowledge only what your
policy has proven. Misses are scheduled for tomorrow. Start your next sitting with due reviews. The mixed exam
opens a week after you started this lesson.

## Optional deeper pack — load and release (15 minutes extra)

Predict which configuration will build a backlog, then run the supplied
simulation:

```bash
python3 -B checks/l05/performance.py
```

It offers 1 or 4 frames per tick to the two-slot queue for 50 ticks and
drains 1 or 2 per tick. At 4 offers and drain 1 it reports 51 accepted, 149
refused, 4386 accepted frame bytes and a peak backlog of 2. Its timings are
observations of this local simulation, not a throughput target.

Checkpoint: why is 51 accepted out of 200 not an SBE throughput number?

<details><summary>After answering</summary>

Key: it counts one two-slot queue under one drain schedule. Encoding,
queueing, persistence and release are separate costs; a codec timing cannot
tell you when a client receives a durable acknowledgement.
</details>
