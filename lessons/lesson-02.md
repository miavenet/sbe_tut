# Lesson 02 — The buffer remembers

Hypothetical incident: “The order decoded successfully. Why did its stop price
come from the previous customer?” The buffer has an excellent memory and
terrible discretion. Today you make its memory irrelevant.

**You will be able to:** encode into a dirty, reused buffer and get exact bytes;
keep a value safely after its buffer is overwritten; and tell when "zero
allocations" is real evidence.
**Time:** about 35 minutes, in two sittings (20 + 15). Start with due reviews.
**You need:** lesson 01's layout, null values and the cheat-sheet calls.
**Word for today:** to **wrap** a buffer is to point a generated flyweight at
it, for example with `wrapAndApplyHeader`.

### Card L02-P1 · Guess first
Q: Guess three values. A buffer is filled with byte 0xAA and wrapped; what does stopPrice read? Then a zero-filled buffer is wrapped; what does it read? Then the code explicitly writes stopPriceNullValue(); what does it read? Commit all three before opening the key.
<details><summary>Reveal after all three guesses</summary>
Key:
- -1431655766, then 0, then -2147483648 (measured by this lab's runner). Wrapping wrote nothing into stopPrice: the four bytes `aa aa aa aa` read as int32 0xAAAAAAAA = -1431655766, and four zero bytes read as 0, which is a real price, not "absent".
</details>

### Concept L02-INITIALIZATION · Reset meaning, not just memory
Vocabulary: flyweight = a view that reads and writes bytes in your buffer; reused slot = a buffer that still holds the previous message; padding = reserved bytes with no business meaning.

**Wrapping writes almost nothing.** Here is what the generated
`wrapAndApplyHeader` does (1.42.0, trimmed):

```cpp
hdr.blockLength(sbeBlockLength()).templateId(sbeTemplateId())
.schemaId(sbeSchemaId()).version(sbeSchemaVersion());
m_buffer = buffer;                       // remember YOUR buffer
m_offset = offset + messageHeader::encodedLength();
```

It writes the 8 header bytes and remembers where the root starts. Every other
byte still holds whatever was there before. In a reused slot, that is the
previous order.

**Why so little?** It is the design, not laziness. The SBE authors put copying
and allocation avoidance among their design goals. The flyweight reads and
writes the caller's buffer directly. A window does not wash the glass.
Whatever the last message left on it, you still see.

**The schema here.** This lab uses **v1**, version 1 of the order schema: v0
plus two optional fields, `clientTag` (uint32, end of the root) and `venue`
(uint8, end of each fill). Lesson 03 explains versions. The course's
`labs/l02/order-padded.xml` also declares `blockLength="40"` on the message:
its fields fill 38 bytes, so root bytes 38 and 39 (packet 46 and 47) are
**padding**. No setter exists for padding; only your code can define it.

```text
reused slot: [header][required fields][optional slots][padding][groups/data]
wrap writes:  yes     no               no              no       no
```

**The common wrong belief:** "memset the slot to zero first and you are
safe." Zero is a value. An absent stopPrice must be the null value
`00 00 00 80`, and zero-filling writes `00 00 00 00`.

Predict: if your encoder only adds `o.flags().clear()` before setting flags, what does that fix in a dirty slot, and what stale bytes would it leave?

<details><summary>Worked repair</summary>

`clear()` makes all 8 flag bits defined. It leaves every other unwritten byte
stale: an absent stop, the padding, and anything else not written. The worked
encoder (`labs/l02/worked/submission.hpp`) writes every byte:

```cpp
o.stopPrice(in.has_stop ? in.stop : tut::v1::Order::stopPriceNullValue());
char symbol[8]{};                        // zero tail for short symbols
std::memcpy(symbol, in.symbol.data(), in.symbol.size());
o.putSymbol(symbol);
o.flags().clear().ioc(in.ioc).postOnly(in.post_only).hidden(in.hidden);
o.clientTag(in.tag);
std::memset(b + 8 + 38, 0, 2);           // the two padding bytes of THIS schema
```

It then encodes the group dimensions, every fill field and both strings. The
offset 8 + 38 belongs to this padded schema only; do not copy it to another.
The check fills the slot with 0xAA before each encode, so any byte you forget
shows up as `aa`.
</details>

Elaborate: Why does zero-filling the slot fail to encode an absent optional stop?

### Card L02-C1 · Complete the repair
Q: Repair the two TODO(L02-C1) holes in labs/l02/work/submission.hpp (the absent stop, and the two padding bytes) so the full check reports HIT.
Nothing to prepare: the folder ships ready (`cp labs/l02/completion/*
labs/l02/work/` restores the starter and overwrites your edits). In the driver,
press Enter to run the check; on paper, run the command below. The untouched
starter prints MISS, with lines such as
`wire-0: case 0 (B without stop): byte 31 = stopPrice: observed 00, expected 80`
and `wire-1: case 1 (SELL, present zero stop): byte 46 = root or tail: observed aa, expected 00`.

```bash
printf '%s\n' labs/l02/work | checks/chk_l02_buffers.sh
```

<details><summary>Completion criteria</summary>
Key:
- `o.stopPrice(in.has_stop ? in.stop : tut::v1::Order::stopPriceNullValue());` keeps a present 0 and writes the sentinel only when absent.
- `std::memset(b + 8 + 38, 0, 2);` defines the two padding bytes; with both lines the check reports HIT on a slot that starts full of 0xAA.
</details>

### Card L02-R1 · Recall and repair
Q: Two parts, with the code closed:
  (a) List every kind of byte a reused slot needs written before you publish this order.
  (b) The fault folder labs/l02/fixtures/faults/zero-only writes stopPrice(0) always. Predict its first mismatch for case 0 (packet offset and observed/expected byte), then run the command below.
The command reports MISS on purpose: the folder is a broken encoder.

```bash
printf '%s\n' labs/l02/fixtures/faults/zero-only | checks/chk_l02_buffers.sh
```

<details><summary>Recall key</summary>
Key:
- (a) Every required field, each optional field's value or null value, all bitset bits, the fixed string's tail bytes, the padding, the group dimensions and entries, and the var data.
- (b) Byte 31, the last byte of stopPrice: observed 00, expected 80 (the null value is -2147483648, bytes 00 00 00 80).
</details>

### Card L02-P2 · Guess first
Q: Guess: you keep a pointer to order A's trader string inside the buffer, then encode order B into the same buffer (which stays allocated). Does your pointer still show A's trader? Yes or no.
<details><summary>After your prediction</summary>
Key:
- No. The pointer still points into the same bytes, and those bytes now hold B's data. The buffer is alive, so this is not a use-after-free; it is a value overwritten under you.
</details>

### Concept L02-OWNERSHIP · A view is a window, not a photograph
Vocabulary: view = pointer (or pointer + length) into bytes someone else owns; owned copy = bytes copied into storage you control.

**What the generated getters return.** For a var-data field such as `trader`,
the 1.42.0 code offers both:

These are alternatives. Use one on a decoder positioned at trader; do not call them consecutively on the same cursor. Each consumes that variable-data field.

```cpp
const char* p = o.trader();            // view: pointer INTO the buffer
std::string_view v = o.getTraderAsStringView(); // view, with length
o.getTrader(dst, dstLength);           // copy: memcpy into YOUR dst
std::string s = o.getTraderAsString(); // owned copy; may allocate
```

**Why this is your job.** SBE's authors wrote the rule down. Their wiki's
Allocation-Free principle ends: "If fields from the message need to be
retained beyond the scope of processing a message then they must be stored
separately (i.e. copied out)." The codec is fast because it does not copy. The
price is that keeping anything is your decision.

**The lab's result type** (`labs/l02/audit.hpp`):

```cpp
struct Audit {
std::array<char,256> storage{};    // owned bytes
const char* borrowed = nullptr;    // a view
std::size_t length = 0;
bool owns = false;
const char* data() const { return owns ? storage.data() : borrowed; }
};
```

**The test.** The runner encodes order 1 (trader "pat"), calls your
`capture`, then re-encodes the same buffer with trader "amy" (other cases use
X's), and only then reads `audit.data()`. It is a delayed audit after the
slot was reused.

**The common wrong belief:** "I kept the pointer, so I kept the value." A
pointer keeps a place, not its contents.

Predict: a borrowed-view Audit and an owned-copy Audit both captured "pat". After the slot is re-encoded with "amy", what does each one's data() show?

<details><summary>Worked timeline and copy</summary>

```text
capture:  slot [pat] <── borrowed view        owned storage [pat]
reuse:    slot [amy] <── same pointer         owned storage [pat]
audit:    view shows "amy"                    copy shows "pat"
```

The worked `capture` (`labs/l02/worked/submission.hpp`) steps over the fills
to reach the trader, then copies:

```cpp
auto& f = o.fills(); while (f.hasNext()) f.next();
Audit a;
a.length = o.traderLength();
o.getTrader(a.storage.data(), a.storage.size()); // copy the bytes
a.owns = true;                                   // data() returns storage
return a;
```

The copy goes into the Audit's own fixed array, so it does not touch the heap.
The other safe option is to keep the whole buffer unchanged until every reader
is done; this runner reuses the slot at once, so it needs the copy.

| | view (`trader()`, `getTraderAsStringView()`) | owned copy (`getTrader(dst, n)` into your array) |
|---|---|---|
| Costs | no payload copy; returns a pointer or pointer-and-length view | copies bytes into storage you control |
| Guarantees | the bytes as they are now | the bytes as they were, after any reuse |
| Right when | you finish reading before the slot is reused | the value outlives the message: an audit, a queue, a log |
| Smell of the wrong pick | a delayed reader that sees the next message | copying in a hot loop that reads once and forgets |

One question decides it: will anyone read this after the slot is reused? Yes
means copy. No means a view is enough.
</details>

Elaborate: Which object owns the bytes the delayed audit reads, and why does that matter after reuse?

### Card L02-C2 · Complete the repair
Q: Three parts, in your own words:
  (a) Complete: “I can keep a borrowed view until ____.”
  (b) Complete: “If the audit runs after the slot is reused, I must ____.”
  (c) Which two lines of the worked capture establish ownership?
<details><summary>Compare the boundary, not keywords</summary>
Key:
- (a) Until the bytes it points at are overwritten or freed. A live pointer does not preserve the value.
- (b) Copy the needed bytes into storage I control, or keep the whole buffer unchanged until the audit has read it.
- (c) `o.getTrader(a.storage.data(), a.storage.size());` copies into Audit.storage, and `a.owns = true;` makes data() return that storage.
</details>

### Card L02-I1 · Recall and repair
Q: Repair capture in labs/l02/independent/submission.hpp (marked TODO(L02-I1)) so the ownership check reports HIT: every audit must still show its original trader after the slot is reused, including the empty and the 160-byte trader.
The starter keeps a borrowed pointer. In the driver, press Enter to run the
check; on paper, run the command below. The untouched starter prints MISS:
`audit-0`, `audit-1` and `audit-3` fail (the empty trader of case 2 passes by
accident). The second independent fault (in `consume`) is for card L02-T1.

```bash
printf '%s\n' labs/l02/independent | checks/l02/chk_ownership.sh
```

<details><summary>Independent criteria</summary>
Key:
- capture copies the trader with `o.getTrader(a.storage.data(), a.storage.size())` and sets `a.owns = true`, so data() returns the Audit's own storage, not the slot.
- The ownership check reports HIT: all four audits match their original trader after reuse.
</details>

## Second sitting

Start with due reviews. First recall, without notes: null versus zero, and
window versus photograph.

### Card L02-P3 · Guess first
Q: Guess: a codec loop reports zero heap allocations. What extra observation would convince you the counter is actually connected?
<details><summary>After naming a control</summary>
Key:
- A deliberate allocation, measured the same way, must make the counter go up. Without that, zero could mean "not counting". Here the control builds a 160-character std::string and must count at least one allocation. Run this control again after any change of compiler or standard library; it is how you find out whether zero still means zero.
</details>

### Concept L02-ALLOCATION · Check the smoke alarm's battery
Vocabulary: measurement scope = the exact code region being counted; positive control = a deliberate allocation that must be counted; counted allocation = a call through this probe’s replaced operator new family; direct malloc calls are outside its measurement.

**How the counter works.** `checks/l02/alloc.cpp` replaces C++'s global
`operator new` family (plain, array, aligned and nothrow forms). Each call
adds one while counting is switched on:

```cpp
void* operator new(std::size_t n){return allocate(n);}
// allocate(): p = malloc(n); if(measuring) ++allocations; return p;
extern "C" void count_begin(){allocations=0;measuring=true;}
extern "C" std::uint64_t count_end(){measuring=false;return allocations;}
```

**The scope** (`checks/l02/runner.cpp`): 100 warm-up encode+consume
iterations, then `count_begin()`, then 1,000 measured iterations over the four
cases, then `count_end()`. Setup, file output and error paths sit outside.
Direct `malloc`/`free` calls are not counted at all.

**The control:** with counting on, the runner builds a `std::string` from the
160-byte trader. It must count more than zero; otherwise a zero from the loop
proves nothing.

**The common wrong belief:** "zero allocations means SBE never allocates."
It means zero calls to the replaced operators, in this loop, with this code.
Your consumer can still allocate.

**Why anyone counts.** The SBE wiki gives the reason: allocation can disturb
the CPU cache, and C++ memory pools may use locks. In a latency-sensitive
loop, that variance is the enemy.

Predict: inside the measured loop, which of these two lines can increase the count: `o.getTraderAsStringView()` or `o.getTraderAsString()`?

<details><summary>Observed control and repair</summary>

`getTraderAsString()` builds a `std::string`, which may call operator new;
the fault folder `labs/l02/fixtures/faults/allocating` uses it in `consume`
and fails the loop criterion. `getTraderAsStringView()` returns a view into
the buffer and allocates nothing (SBE 1.42.0 generated code). In `consume` the value is used before the
slot is reused, so a view is safe there.

```text
warm up x100 → count ON [encode → consume in slot] x1000 → count OFF → must be 0
               count ON [160-char std::string]           → count OFF → must be > 0
```

The delayed audit from the last concept still needs its own copy; a view is
right only where the bytes stay unchanged until you finish reading.

Thompson's 2014 post called SBE "totally allocation free". The 1.42.0 C++
code still offers `getTraderAsString()` as a convenience. That getter is one
place allocation sneaks back in, so measure instead of trusting the brochure.
</details>

Elaborate: Why does a zero count need both a named measurement scope and a positive control?

### Card L02-C3 · Complete the repair
Q: Fill three blanks in words: (a) after warm-up, count around ____; (b) switch counting off before ____; (c) treat zero as invalid if ____.
<details><summary>Scope key</summary>
Key:
- (a) The 1,000 measured encode/consume iterations.
- (b) Reporting, file output and diagnostics.
- (c) The deliberate 160-character std::string control does not increase the count.
</details>

### Card L02-T1 · Apply it elsewhere
Q: Three parts:
  (a) Finish labs/l02/independent: repair consume (marked TODO(L02-T1)) so it allocates nothing in the measured loop, keep your I1 capture repair, and get HIT from the full check.
  (b) Now change the ownership boundary: capture an Audit, copy it to a saved Audit, overwrite the original Audit.storage and reuse the receive buffer. Predict whether saved.data() must still expose the original trader, then test your prediction with the full check.
  (c) Explain why keeping a pointer into the original Audit object would fail even though that object once owned the bytes.
Then, to see the alarm ring, run the second command: the `allocating` fault
folder must report MISS on the `alloc-loop` criterion. In the driver, press
Enter to run the full check on your workspace.

```bash
printf '%s\n' labs/l02/independent | checks/chk_l02_buffers.sh
printf '%s\n' labs/l02/fixtures/faults/allocating | checks/chk_l02_buffers.sh
```

<details><summary>Transfer and production criteria</summary>
Key:
- (a) consume uses `o.getTraderAsStringView()` (a view, used before reuse) instead of `getTraderAsString()`; capture still copies into Audit.storage. The full check reports HIT, including zero measured allocations and a counted control.
- (b) Copying Audit must preserve ownership in the saved object's own storage. `saved.data()` must expose the original trader after both overwrites; the full check's copied-audit criteria test this.
- (c) Explain: A pointer into the original Audit's storage still points there after copying; overwriting that storage changes the bytes it sees. The saved object's `data()` must use its own array.
</details>

### Card L02-R2 · Recall and repair
Q: Two parts, without notes:
  (a) State the measured region, which allocation calls are counted, what is left out, and the required control.
  (b) Does a zero from this loop tell you anything about a delayed audit that builds an owned string that may allocate? Yes or no, and why.
<details><summary>Recall key</summary>
Key:
- (a) The 1,000 warmed encode/consume iterations; calls to the replaced operator new family; setup, output, error paths and direct malloc/free are left out; a 160-character std::string must be counted.
- (b) No. The zero covers only the code inside the loop; a different consumer is a different measurement.
</details>

### Card L02-INT · Connect the ideas
Q: An AI assistant rewrites the lab's capture as below and says: "zero-copy and allocation-free, just as SBE's design principles recommend." Is it right for this lab's delayed audit? Answer in three short sentences: (a) your verdict and where this code would be fine; (b) the first thing you would check; (c) the evidence that settles it.

```cpp
inline Audit capture(char* b, std::size_t received) {
tut::v1::MessageHeader h(b, received);
tut::v1::Order o;
o.wrapForDecode(b, 8, h.blockLength(), h.version(), received);
auto& f = o.fills(); while (f.hasNext()) f.next();
std::string_view v = o.getTraderAsStringView();
Audit a; a.borrowed = v.data(); a.length = v.size(); a.owns = false;
return a;
}
```

<details><summary>Judgement key</summary>
Key:
- (a) Wrong here: it is a view, and this runner reuses the slot before the audit reads data(). The same view is fine in consume, which finishes reading before the slot changes.
- (b) Check first: whether anything writes to the buffer between capture and the last read of audit.data().
- (c) The ownership check settles it: like the L02-I1 starter, this capture gets MISS on audit-0, audit-1 and audit-3. The SBE authors' own rule agrees: fields kept beyond processing the message must be copied out.
</details>

## Close

Remember: wrapping writes only the header, so write every byte yourself.
A view keeps a place, a copy keeps a value. Zero allocations counts only with
a named scope and a control that rings. Tomorrow today's graded cards come back
for review. Next: lesson 03, where a new schema version meets an old reader.
