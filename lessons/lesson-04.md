# Lesson 04 — Find the first wrong cursor

Imagine a capture reader reporting a trader whose name is thirteen bytes of
binary confetti. The bytes arrived intact. Your reader just went to the wrong
address. Today you'll make it confess.

By the end you can walk groups and variable data in the right order, reject a
hostile length before it touches memory, and prove a diagnosis with a byte dump.

**Time: about 60 minutes, in four sittings of 11–17 minutes.** Stop after any card.
**You need from L01–L03:** the header fields (blockLength, version) and the
header + root block + groups + data layout.

## Sitting A — the cursor (15 minutes)

### Card L04-P1 · Guess first
Q: Cold guess (a number): the v1 packet's trader string is "pat", so its true length is 3. A buggy reader skips the fills group and reads trader straight after the fixed root block. What number will it read as trader's length?
<details><summary>Commit your guess and confidence first</summary>
Key:
- 13. Straight after the root block (byte 46) sits the fills group's entry width, 13; the buggy reader treats those two bytes as a string length.
</details>

### Concept L04-CURSOR · The cursor is a bookmark, not a search engine
Vocabulary: cursor = the decoder's current byte position; group dimensions = the 4 bytes (entry width, entry count) before a group's entries; precedence = the order in which generated accessors must be called.

**Why would anyone build it this way?** Speed, on purpose. Lesson 01 gave
Martin Thompson's rule: read sequentially, with no need to backtrack. In the
same 2014 post he explained that chasing pointers to strings costs
instructions and can lose hardware prefetching. So SBE puts the fixed root
first, groups next, and strings at the very end, and you never chase a
pointer. Inside one block you can still jump around: "SBE can allow
arbitrary access to any field within a given block," he told a reader.
Across blocks, you follow the bookmark.

Fixed fields within the same block may be read in either order. Precedence
checks guard structural traversal—for example, reading a fill before `next()`,
or reading `trader` before finishing `fills`. They do not require fixed-field
getters to follow schema order.

Groups and data both follow the cursor, but they are not the same tool:

| | Repeating group | Variable-length data |
|---|---|---|
| Holds | N entries with the same fixed fields | one string or blob |
| Prefix | entry width + count (4 bytes here) | length (2 bytes here) |
| Position | after the fixed fields of its level | after the groups of its level |
| Wrong-choice smell | text squeezed into a group of 1-byte entries | records packed into a string and parsed by hand |

Repeated structured records belong in a group; one free-form string belongs in data.

A generated SBE decoder reads **fixed fields** at fixed offsets: in this
Order schema, `quantity` is 16 bytes into the root block. The first group's
dimensions start after the root block. Later entries and data depend on earlier
counts and lengths.
So the decoder keeps a **cursor** (`sbePosition()` in C++)
and moves it forward as you read:

- `fills()` reads the group dimensions at the cursor and moves past them;
- each `next()` selects the entry at the current cursor, then advances the shared cursor past that entry’s fixed block;
- `getTraderAsString()` reads a 2-byte length at the cursor, then that many bytes.

The v1 packet (`labs/l04/fixtures/order-v1.bin`, 85 bytes), from the
offset dump you will use later:

```text
offset:  0       8           46     50        63        76         81        85
         header  root (38)   dims   fill 0    fill 1    trader     note      end
                             13, 2  (13 B)    (13 B)    03 00 pat  02 00 hi
```

After dimensions, the shared cursor is 50. The first `next()` selects entry offset 50 and advances the shared cursor to 63. The second selects entry offset 63 and advances it to 76.

The supplied reader (`read_order` in `labs/l04/worked/submission.hpp`) walks it
in schema order:

```cpp
tut::v1::Order o; o.wrapForDecode(b, 8, u16(b,0), u16(b,6), received);
auto& g = o.fills();                          // dims at 46, cursor -> 50
while (g.hasNext()) { g.next();               // selects entry; cursor advances past its fixed block
    out.prices.push_back(g.fillPrice()); out.sizes.push_back(g.fillQty()); }
out.trader = o.getTraderAsString();           // length at 76
out.note   = o.getNoteAsString();             // length at 81
```

An empty group still has its 4 dimension bytes (count 0), so you still call
`fills()` before trader.

**Precedence checks** make the codec police that order. They take two
separate switches:

1. Generate with `-Dsbe.generate.precedence.checks=true`. The generator then
   writes a small state machine (`Order::CodecState`) into each codec.
2. Compile with `-DSBE_ENABLE_PRECEDENCE_CHECKS`. Without this macro the
   checks compile away to nothing. (Switch names and the accessor below are from SBE 1.42.0.)

Here is the start of the generated `fillPrice()` accessor (SBE 1.42.0, this schema):

```cpp
SBE_NODISCARD std::int64_t fillPrice() const
{
#if defined(SBE_ENABLE_PRECEDENCE_CHECKS)
    onFillPriceAccessed();   // throws AccessOrderError if called out of order
#endif
    std::int64_t val;
    std::memcpy(&val, m_buffer + m_offset + 0, sizeof(std::int64_t));
```

`AccessOrderError` derives from `std::logic_error`. The L04 and L05 checks
generate and compile with both switches on.

Predict: With checks OFF, your reader reads fill 0, skips the second next(), and calls getTraderAsString(). From which byte does it read the length, and what value does it get?

<details><summary>Worked answer — open after predicting</summary>

The cursor is still at **63**, the start of fill 1. Fill 1's price is
12345 (`39 30 ...`), so the reader takes `39 30` = **12345** as trader's length.
Jumping is the bookmark confidently opening the wrong chapter.

The course probe runs four wrong orders on this packet, with the macro off
and on (SBE 1.42.0; the strings below are that jar's output):

| Wrong order | Checks off (prints) | Checks on |
|---|---|---|
| trader before `fills()` | `trader_length=13` | throws: `Cannot access field "trader" in state: V1_BLOCK` |
| one `next()` of two | `trader_length=12345` | throws: `... "trader" in state: V1_FILLS_N_BLOCK` |
| `fillPrice()` before `next()` | `price=281865818800166` | throws: `... "fills.fillPrice" in state: V1_FILLS_N` |
| note before trader | `note=pat trader=hi` | throws |

The wrong-order probe deliberately pads its backing buffer to 65536 bytes and passes that capacity, allowing the unchecked examples to complete without reading outside the allocation. Its printed garbage is not a guarantee that arbitrary wrong-order reads fail safely. To re-check this table after changing the jar or compiler, rerun the same probe with the macro off and on and compare.

The common wrong belief: "the bytes are valid, so my read is valid." Valid
bytes read in the wrong order give confident garbage, not an error. The checks
are about **order only**. They do not check prices, sides, or whether the
packet is truncated.

**Rule:** visit every group entry with `next()`, then the data fields, in schema order.
</details>

Elaborate: Why does advancing once fail, even though you can name the second fill's fixed fields?

### Card L04-C1 · Complete the repair
Open `labs/l04/completion/submission.hpp`. In `read_order`, the loop has a
marker `/* TODO(L04-C1) ... */` where one call is missing. The check reads a v0,
a v1 and a compatible v2 packet. Untouched, it prints MISS with
`FAIL Illegal field access order. Cannot access field "fills.fillPrice" in state: V0_FILLS_N`.
Repaired, it prints HIT (detail `PASS mode=order valid=3 rejected=0`).

```bash
printf '%s\n' labs/l04/completion | checks/l04/chk_order.sh
```

Q: Replace the TODO(L04-C1) marker in labs/l04/completion/submission.hpp with the one call that selects each entry and advances the shared cursor past its fixed block, then run the check. Your answer is the edited file.
<details><summary>After your repair</summary>
Key:
- Call `g.next();` at the top of the loop body, before `g.fillPrice()` and `g.fillQty()`.
</details>

### Card L04-R1 · Recall and repair
Close the worked file. `labs/l04/work/submission.hpp` has a line marked
`// TODO(L04-R1)` where the whole fills loop should be. Untouched, the check
prints MISS with `Cannot access field "trader" in state: V0_FILLS_N`.

```bash
printf '%s\n' labs/l04/work | checks/l04/chk_order.sh
```

Q: (a) At TODO(L04-R1) in labs/l04/work/submission.hpp, write the loop that collects every fill price and size, then run the check. (b) Explain in one sentence why the header's root blockLength alone cannot take you to trader.
<details><summary>After independent production</summary>
Key:
- (a) `while(g.hasNext()){ g.next(); ...push fillPrice and fillQty... }` before trader and note; the check prints HIT.
- (b) Explain: Header size 8 plus root blockLength 38 only locates the group dimensions (byte 46 in v1). Neither number walks the entries or the data after them; an empty group still has its 4 dimension bytes.
</details>

## Sitting B — the boundary (17 minutes)

### Card L04-P2 · Guess first
Q: Cold guess (yes/no): your receive slot holds 262144 bytes, but this receive delivered only 80. The v1 packet needs 85. May your reader trust a length field that sends it to byte 84?
<details><summary>Commit first</summary>
Key:
- No. Only the 80 received bytes belong to this frame. Bytes 80–84 are leftovers in spare capacity, not proof that anything arrived.
</details>

### Concept L04-BOUNDS · Validate the ticket before admitting the guest
Vocabulary: received = bytes this frame actually delivered; capacity = size of the buffer, used or not; contract = the schema/template/version family you accept; staged result = output not yet committed to application state.

**A true story: Heartbleed.** On 7 April 2014 OpenSSL published a fix for
CVE-2014-0160. A missing heartbeat bounds check could expose up to 64 KB of
memory to a connected peer. A heartbeat message carries a 2-byte payload
length, much like trader's. The vulnerable code read that length and copied
that many bytes into its reply (`memcpy(bp, pl, payload)`). It never asked how many bytes had
actually arrived. The TLS fix first rejects records shorter than the type,
length and minimum padding, before reading the length. It then rejects a
declared payload that cannot fit in the received record, including padding.
Either failure silently discards the message.

A month later, a reader of Thompson's SBE post asked about Heartbleed-like
attacks on the C++ codec. Thompson favored bounds checks by default. He also
warned that the caller might pass the wrong length, so external input still
needs validation. Three days later he reported that Todd had added bounds
checking to the C++ codec. Both halves still apply to you.

Guess before reading on: in this lab, which number plays the part of
`rrec.length`? It is **received**, the bytes this frame delivered. Never the
slot's capacity.

The generated codec is not a complete hostile-input validator. Its position checks use the buffer length you supply, but fixed-field getters do not individually validate their reads, and this pinned `getTraderAsString()` copies the declared data before its final position check. Pass the actual received length and independently validate the complete structure before calling accessors. Passing slot capacity can admit stale bytes. The lab therefore validates the whole frame against received before decoding.
Its `validate_order` (worked file) does this, in order:

```cpp
require(received<=262144,"frame bound");         // adapter's frame cap
Cursor c{b,received}; c.take(8);                  // 8-byte header present?
auto root=u16(b,0), version=u16(b,6);
require(root<65535,"null root length");
require(u16(b,2)==1 && u16(b,4)==91 && version<=2,"unsupported contract");
/* minimum-root check for this version: you write it in L04-C2 */ c.take(root);
auto width=c.word(), count=c.word();              // group dimensions
// ...width minimum and maximum, count maximum...
c.entries(count,width);                           // all entries fit?
c.data(tut::v1::VarStringEncoding::lengthMaxValue());   // trader (max 65534)
c.data(tut::v1::VarStringEncoding::lengthMaxValue());   // note
require(c.p==received,"extra bytes outside contract");
```

`Cursor` (in `labs/l04/api.hpp`) never trusts a sum. With `p` = cursor and
`n` = received:

- `take(len)` first requires `p <= n` and `len <= n - p`, then advances with `p += len`. The subtraction-based check proves the addition stays within n before the addition is performed.
- `entries(count,width)` requires `p <= n`, nonzero `width`, and `count <= (n - p) / width` **before** it multiplies.

Worked numbers on the real v1 packet (n = 85). After the dimensions, p = 50,
so 35 bytes remain:

```text
count 2, width 13:      2 <= 35/13 = 2   yes -> take 26, p = 76
trader length 3 at 76:  p = 78,  3 <= 85-78 = 7   yes -> p = 81
note length 2 at 81:    p = 83,  2 <= 85-83 = 2   yes -> p = 85 = n  accept
hostile count 65534:    65534 <= 35/13 = 2   no  -> reject, nothing multiplied
received only 80:       trader: 3 <= 80-78 = 2   no  -> reject
```

Two more facts come from this schema's generated code. The largest legal
uint16 length, width or count is **65534**. **65535 is the null value**, so it
is rejected even when enough bytes exist. And a `size_t` sum can wrap: with
p = 50, a wide length of `SIZE_MAX - 10` makes `p + len` equal 39, which looks
small. The uint16 wire fields cannot wrap that way on a 64-bit `size_t`; the
rule matters for wider inputs, and the check calls `entries()` with `SIZE_MAX`.

| | Trust the declared length | Check it against received first |
|---|---|---|
| Work performed | skips up-front structural validation | checks prefixes, bounds and the contract in a structural walk before decoding; measure the cost in your workload |
| A lying length | reads bytes that never arrived: stale slot bytes, or memory past the buffer | rejected before any accessor runs |
| Code smell | capacity passed to `wrapForDecode`; a length used before any `n - p` test | one validator walks the frame, then the reader decodes |

If the bytes came from outside your process, check every length against received before you read through it.

Predict: A version-1 packet declares root blockLength 34. Do all v1 root fields fit? State the minimum root length for v1.

<details><summary>Worked answer — open after predicting</summary>

No. The v0 root fields are 8+8+4+4+8+1+1 = **34** bytes. Version 1 adds the
4-byte `clientTag` at offset 34, so v1 needs **38**. Entries follow the same
pattern: v0 needs 12 bytes (price 8 + qty 4), v1 needs 13 (adds `venue`).
The worked line is:

```cpp
require(root>=(version?38:34),"short root");
```

The common wrong belief is "if `received >= root`, the root is fine." Enough
total bytes says nothing about whether the declared block holds every field
this version has. With a 34-byte v1 root, `clientTag` would read the group
dimensions.

The check truncates every prefix of the v0 and v1 packets. It also tries null
lengths, short blocks, unsupported contracts and an overflow-shaped count. Each
must throw and leave the harness state untouched: results are committed only
after the staged parse succeeds. Business checks (is this price sane?) stay the
application's job.

**Rule:** check received bytes, the contract and every length before you decode; stage, then commit.
</details>

Elaborate: Why must "known schema" and "enough received bytes" both pass before decode?

### Card L04-C2 · Complete the repair
Open `labs/l04/validation-completion/submission.hpp`. In `validate_order`,
the marker `/* TODO(L04-C2) ... */` stands where the minimum-root check belongs.
Untouched, the check prints MISS with `FAIL accepted malformed v1 minimum root`.
Repaired, it prints HIT (detail `PASS mode=validate valid=11 rejected=203`).

```bash
printf '%s\n' labs/l04/validation-completion | checks/l04/chk_validate.sh
```

Q: Replace the TODO(L04-C2) marker in labs/l04/validation-completion/submission.hpp with a require() that rejects a root block shorter than the fields present in the packet's version, then run the check. Your answer is the edited file.
<details><summary>After your attempt</summary>
Key:
- `require(root>=(version?38:34),"short root");` placed after the contract/version check and before `c.take(root)`.
</details>

### Card L04-R2 · Recall and repair
Q: From memory, write three short answers. (a) The validation steps, in order, before a decoded result may change state. (b) Overflow-safe tests for one length and for a count of fixed-width entries. (c) Why "the checked codec didn't throw" does not prove the frame is valid.
<details><summary>Self-grade every bullet</summary>
Key:
- (a) Check the received length, frame cap and header. Admit the schema, template and version. Check widths, counts and data lengths against both schema limits and remaining bytes, and require exact consumption. Keep decoded output staged until every check passes.
- (b) Length: `p <= n && len <= n - p`. Entries: `p <= n && width != 0 && count <= (n - p) / width`. Only then add or multiply.
- (c) Precedence checks guard structural traversal; they do not check received length, the contract or business values.
</details>

### Card L04-J1 · Judge the design
An AI assistant was asked for a "faster" v1 Order reader for this lab's
receive path. Each receive lands in a reused 262144-byte `slot`; `received`
is how many bytes this receive delivered. It removed the validator and wrote:

```cpp
inline ViewResult fast_read(std::vector<char>& slot, std::size_t received) {
    char* b = slot.data();
    tut::v1::Order o; o.wrapForDecode(b, 8, u16(b,0), u16(b,6), slot.size());
    ViewResult out; auto& g = o.fills();
    while (g.hasNext()) { g.next(); out.prices.push_back(g.fillPrice()); out.sizes.push_back(g.fillQty()); }
    out.trader = o.getTraderAsString(); out.note = o.getNoteAsString();
    return out;
}
```

Q: Judge it for this receive path, in three short answers. (a) Right or wrong here, and why, in one sentence. (b) The first thing you would check in the code. (c) The test that would settle it.
<details><summary>Self-grade each part</summary>
Key:
- (a) Wrong here: the traversal order is fine, but it bounds decoding by the slot's capacity instead of the bytes this receive delivered, and nothing validates the frame first, so a short frame can decode leftover bytes from an older frame as if they had arrived.
- (b) Check which length reaches `wrapForDecode` (`received`, never `slot.size()`) and whether a validator checks the contract, minimum root, every count and every length against received before any accessor runs.
- (c) Put the full 85-byte v1 packet in the slot, then deliver only its first 80 bytes: a correct reader rejects the frame, while this one accepts it and returns trader "pat" and note "hi".
</details>

## Sitting C — evidence (11 minutes)

### Card L04-P3 · Guess first
Five broken schemas live in `labs/l04/fixtures/bad/`. Each changes one thing in
`labs/l04/order-v1.xml`:

| Case | File | What is wrong |
|---|---|---|
| E1 | `e1.xml` | `sinceVersion="2"` on two fields, but the schema is version 1 |
| E2 | `e2.xml` | the fixed field `clientTag` is placed after the `fills` group |
| E7 | `e7.xml` | an unknown XML attribute, `bogus="1"`, on `orderId` |
| E8 | `e8.xml` | the var-data length type is changed to `uint32` with no `maxValue` |
| E9 | `e9.xml` | the header composite is renamed, so `messageHeader` cannot be found |

The diagnostics pack invokes the raw jar with XSD validation explicitly requested: `java -Dsbe.validation.xsd=PATH_TO_XSD -Dsbe.output.dir=NEW_DIR -jar labs/lib/sbe-all-1.42.0.jar SCHEMA.xml`. The course wrapper
`tools/sbe_tool.sh` is a **strict gate**. It first validates the XML against
the jar's XSD and stops on any error. Then it generates into a temporary
folder and moves that folder into place only on success.

Q: Cold guess (yes/no): with XSD validation requested, raw E7 prints an XSD error but exits 0. Would you publish the code it generated? Then: what would make your answer stop being true, and how would you find out?
<details><summary>Commit first</summary>
Key:
- No. In the diagnostics pack’s invocation (sbe-tool 1.42.0), `-Dsbe.validation.xsd=...` makes raw E7 print `Attribute 'bogus' is not allowed`, but it still exits 0 and proceeds to generation. Without that property, this unknown attribute is silently accepted. The strict wrapper rejects E7.
- Stop being true: raw-jar message text, exit code and the no-property behaviour were seen on 1.42.0 only; other jar versions are untested here. Find out: rerun the diagnostics pack on a new jar and check the wrapper still rejects E7. Rely on the wrapper's gate, not the raw jar.
</details>

### Concept L04-DIAGNOSTICS · One hypothesis, one byte, one repair
Vocabulary: dump = bytes printed with their offsets; IR = SBE's intermediate representation, the parsed schema saved as a flat list of tokens; strict gate = a step that stops publication on any error.

Debug like a scientist: one hypothesis, one byte to look at, one repair, rerun.
Three tools help.

**1. The offset dump.** From the course root:

```bash
python3 -B checks/l04/dump.py labs/l04/fixtures/order-v1.bin
```

It prints hex rows, then one line per structure: where the root ends, where
the group dimensions sit, where each entry ends, and each data length's offset.
`dump.py --diff LEFT RIGHT` lists every byte offset where two files differ.

**2. The IR.** The generator first parses the XML into IR tokens such as
`BEGIN_FIELD`, `BEGIN_GROUP` and `BEGIN_VAR_DATA`. Each token has a name, an
offset, a length and a version. `-Dsbe.generate.ir=true` saves them as a
`.sbeir` file, and the generator can read that file back instead of the XML.
Selected BEGIN tokens for this schema, with intervening tokens omitted:

```text
BEGIN_MESSAGE Order offset=0 length=38 version=0
BEGIN_FIELD orderId offset=0 length=8 version=0
BEGIN_FIELD price offset=8 length=8 version=0
```

**3. The diagnostics pack** runs the rest for you: the precedence probe with
the macro off and on, XML to IR to code regeneration, and the five broken
schemas through the raw generator and the strict gate.

```bash
python3 -B checks/l04/diagnostics.py
```

It prints one JSON line with `"status": "PASS"` and an `artifacts` folder.
In that folder, `ir-tokens.log` lists every token and `ir-diff.json` compares
the code generated from XML with the code generated from IR.

One more precedence call matters on the **encoding** side. With precedence checks generated and enabled, `checkEncodingIsComplete()` verifies that encoding reached an allowed final traversal state. In this schema, writing trader but omitting note leaves V1_TRADER_DONE and throws. The check does not prove that every fixed field was initialized or that field values are valid. With the macro off, the call does nothing.

Predict: Your reader returns a 13-byte trader. Hypothesis: it read the group's entry width as trader's length. Which offset in the dump confirms it, and what value should sit there?

<details><summary>Worked answer — open after predicting</summary>

Offset **46** should hold **13** (`0d 00`). The real dump prints:

```text
header root=38 template=1 schema=91 version=1 received=85
root end=46 remaining=39
fills dimensions @46: width=13 count=2 cursor=50
fills[0] end=63 remaining=22
fills[1] end=76 remaining=9
trader length @76=3 end=81 remaining=4
note length @81=2 end=85 remaining=0
```

So the bytes are fine (trader's real length 3 sits at 76). The fault is your
accessor order. The opposite case is a correct order with a wrong byte; then
`--diff` against a known-good file names the offset.

For the broken schemas the pack records: raw E1, E2, E8 and E9 exit 255.
With XSD validation requested, raw E7 exits 0 and writes code. The strict gate rejects all five and leaves
no output folder. The wrong belief here is "exit 0 means valid." For E7 it
only means "the generator kept going."

Regenerating from IR matches generating from XML in every file but one:
`package-info.java`, whose schema description comes back as `null`.

**Rule:** state one hypothesis, find the one byte that tests it, repair one thing, rerun.
</details>

Elaborate: If your packet dump is correct but your trader string is wrong, what do you inspect next?

### Card L04-C3 · Complete the repair
Run the diagnostics pack (command in the concept above), then open
`ir-tokens.log` and `ir-diff.json` in the `artifacts` folder it prints. Read
quantity's offset, the group name, the data field names in order, and the one
file that differs. On paper, run the command below, type the JSON, press
Enter, then Ctrl-D. In the driver, type the JSON on one line.

```bash
checks/l04/chk_ir.py
```

Q: (a) Complete and submit this JSON from those two files: `{"quantity_offset":0,"group":"?","data":["?","?"],"difference":"?"}`. (b) After the check passes, explain whether the differing file establishes a wire-layout change, and what evidence would establish one.
<details><summary>After reading the evidence</summary>
Key:
- {"quantity_offset":16,"group":"fills","data":["trader","note"],"difference":"package-info.java"}
- Explain: No. This difference is package documentation. Inspect message-token offsets, lengths and versions, then compare encoded bytes and decoder behavior to assess a wire-layout change.
</details>

### Card L04-R3 · Recall and repair
Q: You may look up switch names. Explain three decisions: (a) You regenerated checked codecs, but illegal traversal still succeeds—what build step might be missing? (b) An encoder omits `quantity` but passes `checkEncodingIsComplete()`—does that prove the message is complete? (c) E7 generated code with exit 0—may you publish it?
<details><summary>Self-grade each part</summary>
Key:
- (a) The C++ build must enable the generated checks; regeneration alone is insufficient.
- (b) No. That call checks structural traversal, not whether every fixed field was initialized. Check the encoded bytes and values too.
- (c) No. Require the strict XSD gate to pass before promoting generated output.
</details>

## Sitting D — a nested capture (17 minutes)

### Card L04-P4 · Guess first
Q: Cold guess (yes/no): a capture has two batches; the first has two ticks and a label. Can you move to the second batch right after reading the first batch's fixed channel field?
<details><summary>Commit first</summary>
Key:
- No. The first batch's ticks and its label sit between its channel and the second batch, so you must read them first.
</details>

### Concept L04-NESTED · Finish the child before visiting its sibling
Vocabulary: nested group = a group inside each entry of another group; depth-first = finish everything inside an entry before the next entry; tape = several frames stored back to back, each with its own length prefix.

The capture schema (`labs/l04/nested.xml`, schema 92) nests a group:

```xml
<sbe:message name="Capture" id="2">
 <field name="captureId" id="1" type="uint32"/>
 <group name="batches" id="10" dimensionType="groupSizeEncoding">
  <field name="channel" id="11" type="uint16"/>
  <group name="ticks" id="20" dimensionType="groupSizeEncoding">
   <field name="price" id="21" type="int64"/>
   <field name="size" id="22" type="uint32"/>
  </group>
  <data name="label" id="30" type="varStringEncoding"/>
 </group>
 <data name="note" id="40" type="varStringEncoding"/>
</sbe:message>
```

Inside each batch entry, the same order rule applies as at the top level:
fixed fields, then groups, then data. The generated accessors are
`batches()`, `channel()`, `ticks()`, `price()`, `size()`,
`getLabelAsString()` and `getNoteAsString()`.

An outer entry's fixed width (here 2 bytes, just `channel`) covers only its
fixed fields. It cannot skip the ticks or the label, because their size
depends on their own count and length. If the outer group is empty, no child
dimensions appear on the wire at all.

The tape format is this course's choice, not SBE: each frame is preceded by
a little-endian uint32 byte count, which includes the 8-byte SBE header. It
is separate from SBE's root and entry block lengths. The supplied `read_tape`
validates each frame against its own count and stages all results.

Predict: In labs/l04/fixtures/nested.bin, the first batch's second tick ends at byte 46. What must you read there before the second batch's channel?

<details><summary>Worked answer — open after predicting</summary>

The first batch's **label**: its length (2) at byte 46, then `AB`. The full
walk of the 63-byte fixture:

```text
 0  header: root 4, template 2, schema 92, version 0
 8  captureId = 44
12  batches dims: width 2, count 2
16    batch 0 channel = 7
18    ticks dims: width 12, count 2
22      tick 0: price 100, size 3
34      tick 1: price -200, size 5
46    label length 2, "AB"
50    batch 1 channel = 9
52    ticks dims: width 12, count 0     (no tick entries)
56    label length 0
58  note length 3, "end"                -> end at 63
```

The common wrong belief: "the entry width tells me where the next batch
starts." It tells you only where this batch's fixed fields end.

**Rule:** depth-first: channel, all its ticks, its label; then the next batch; note last.
</details>

Elaborate: Why can a fixed entry width skip unknown fixed tail fields but not a nested subtree?

### Card L04-C4 · Complete the repair
Q: Fill the two blanks and answer (b). (a) batches.next(); channel; ticks(); ____; ____; next batch. (b) When do you read the message's note, including when there are zero batches?
<details><summary>After your answer</summary>
Key:
- (a) Visit every tick with next() and read its price and size; then read this batch's label.
- (b) Only after the last batch; with zero batches, read note right after the outer dimensions.
</details>

### Card L04-T1 · Apply it elsewhere
Open `labs/l04/independent/submission.hpp`. `validate_nested` and `read_tape`
are supplied; `read_nested` (marked `// TODO(L04-T1)`) only throws. Model it
on `read_order`, not on the worked nested reader. Untouched, the check prints
MISS with `FAIL TODO walk a validated capture depth first`. It tests the
fixture, an all-empty capture, every truncation, corrupted fields and a
two-frame tape.

```bash
printf '%s\n' labs/l04/independent | checks/l04/chk_nested.sh
```

Q: Implement read_nested in labs/l04/independent/submission.hpp: validate first, then walk the capture depth-first, filling channels, prices, sizes, labels, note and end. Run the check until it prints HIT.
<details><summary>After independent repair</summary>
Key:
- Call `validate_nested(b,received)` first; wrap with `wrapForDecode(b,8,u16(b,0),u16(b,6),received)`; for each batch: next(), channel, every tick (next(), price, size), label; then note; `end = 8 + encodedLength()`.
</details>

### Card L04-T2 · Apply it elsewhere
Compare the good and the corrupted capture with the dump tool's diff mode:

```text
python3 -B checks/l04/dump.py --diff labs/l04/fixtures/nested.bin labs/l04/fixtures/nested-bad-length.bin
```

Use the byte walk in the nested concept to name the field. Write the field as
a schema path: entry index in brackets, names joined by dots, and `.length`
for a data length prefix (for example `batches[1].channel`). On paper, run
the command below, type the JSON, press Enter, then Ctrl-D.

```bash
checks/l04/chk_diagnose.py
```

Q: Submit JSON with keys offset (where the first affected field starts), field (its schema path) and action ("reject-before-commit" or "decode").
<details><summary>After your diagnosis</summary>
Key:
- {"offset":46,"field":"batches[0].label.length","action":"reject-before-commit"}
</details>

### Card L04-INT · Connect the ideas
Q: A new-version record decodes without exceptions, but replaying it gives a different result. Write one question each for (a) the cursor, (b) the frame boundary and (c) the behaviour.
<details><summary>Self-grade each part</summary>
Key:
- (a) Cursor: did I use the wire's root and entry block lengths and acting version, and does a checked build plus a dump show the first wrong transition?
- (b) Frame: did I bound everything by this frame's received bytes and the admitted contract before staging a result?
- (c) Behaviour: a clean decode does not prove the application behaves the same; what else changed between the two runs?
</details>

## Close

Remember three rules. Walk groups with `next()` and read data in schema order.
Bound every length by **received** bytes, never capacity. Prove a diagnosis
with one byte from a dump. Misses are scheduled for tomorrow. Start your next sitting with due reviews. Optional
practice: `labs/l04/deeper-pack.md` (15 minutes). Next: lesson 05 puts these
frames inside a small sequenced service.
