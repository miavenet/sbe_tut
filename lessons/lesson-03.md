# Lesson 03 — The decoder smiled. The archive lost six bytes.

Hypothetical incident: you upgrade an order writer, see a successful decode,
and declare victory. Tomorrow's audit asks where the new fields went.
Your decoder is a polite tourist: reading a sign does not mean it can
reproduce the city.

**You will be able to:** add fields to a schema without breaking old readers,
decode any version with the values the header gives you, and archive frames
without losing bytes you cannot read.
**Time:** about 40 minutes, in two sittings (20 + 20). Start with due reviews.
**You need:** lesson 01's header and layout, lesson 02's null values and v1.

## Sitting A — changing a contract (20 minutes)

### Card L03-P1 · Guess first
Q: Guess: version 1 of the order schema inserts a new required uint32 field between price and quantity. The code generator accepts it without error. Can a reader built from version 0 still read quantity correctly from the new messages? Yes or no.
<details><summary>After your attempt</summary>
Key:
- No. In the supplied file `fixtures/bad/mid-block.xml`, sbe-tool 1.42.0 generates code without error, yet quantity moves from root offset 16 to 20. A v0 reader still reads offset 16. "It generated" checks that the schema is valid, not that it is compatible.
</details>

### Concept L03-CONTRACT · Append, never insert
Vocabulary: schema version = the number in the schema's version attribute, sent in every header; sinceVersion = attribute saying which version added an element (it is not sent on the wire); extension = an element added in a later version; compatible = old and new readers can still parse each other's messages.

**What the SBE specification allows.** Its Schema Extension Mechanism section
says, in short:

```text
fields may be added to the root or to a group, but appended to the END of a block
existing fields cannot change type or move
a new group goes after the existing groups
new variable-length data goes after the existing variable-length data
the message header encoding cannot change
```

Why the end of a block works: the header (and each group's dimensions) sends
the block length on the wire. An old reader knows its own fields, then jumps by
the wire's block length, skipping bytes it does not know.

**Why the rules exist.** The SBE authors knew that a whole network cannot
upgrade at once. Old readers will meet new messages, and new readers will meet
old ones. Every rule above protects one of those two directions.

Quick check: old reader meets new message, or new reader meets old message.
Which direction needs an added field to be optional? Answer in the next
paragraph.

**What this course's checker adds.** `checks/l03/evolution.py` is stricter on
purpose. An added field must be `presence="optional"` with `sinceVersion` equal
to the new version, so an old message reads as null, not as garbage. Martin
Thompson's 2014 post introducing SBE gives the reason: "Extension fields must be
optional otherwise a newer template reading an older message would not work."

No existing type or composite may change. Our header and group dimensions carry no
count of groups or var-data fields, so a reader cannot discover new ones; the
checker therefore also rejects a new group before trailing data and new var
data inside a group. Those two are rules of this lab, not of the specification.

**The common wrong belief:** "I only added a byte to the price composite."
Price sits before quantity. A 9-byte price pushes quantity and everything after
it one byte later: that is moving existing fields.

Predict: v1 adds clientTag (uint32) at the end of the root and venue (uint8) at the end of each fill entry. Which existing offsets change?

<details><summary>Worked example — open after predicting</summary>

None. Only the block ends grow. The two added lines in
`labs/l03/worked/order-v1.xml` (the schema also says `version="1"`):

```xml
<field name="clientTag" id="8" type="uint32" presence="optional" sinceVersion="1"/>
<field name="venue" id="13" type="uint8" presence="optional" sinceVersion="1"/>
```

```text
root:   [old 34 bytes][clientTag 4] -> 38
entry:  [old 12 bytes][venue 1]     -> 13
existing offsets stay put; only the block ends grow
```

The v1 packet `labs/l03/fixtures/order-v1.bin` is 85 bytes: header 8, root 38,
fills dimensions at 46 with width 13, two entries, then trader and note.

**Append, or start a new message?**

| | append an optional field | new message type (new template id) |
|---|---|---|
| Costs | new readers see null from old writers | readers handling the new type need its template |
| Guarantees | every existing offset stays put | the old message's contract is untouched |
| Right when | an order without the field is still a valid order | the field is mandatory, or the structure changes |
| Smell of the wrong pick | a "required" field that old writers never sent | a whole new template for one optional extra |

The wiki draws the same line: new mandatory fields or a structural change need
"a new message type". The specification says a template changed in an
incompatible way must get a new template id. Plain advice: if old messages
without the field are still good business messages, append it as optional.
</details>

Elaborate: Why is appending clientTag to the root safe while adding a member to the price composite is not, when quantity follows price?

### Card L03-C1 · Complete the repair
Q: In labs/l03/completion/order-v1.xml, repair the two declarations marked TODO(L03-C1) so the schema check reports HIT.
Change only those two lines. The untouched starter prints MISS with lines such
as `schema-append: Order: sinceVersion must be 1 (found 0)` and
`schema-append: Order: added field must be optional`. In the driver, press Enter
to run it; on paper, run the command below. Get HIT here before card L03-C2,
which uses the same folder.

```bash
printf '%s\n' labs/l03/completion | checks/l03/chk_schema.sh
```

<details><summary>After your attempt</summary>
Key:
- Both lines become `presence="optional" sinceVersion="1"`, at the same place (end of the root, end of the fill entry); the schema stays `version="1"`, and the check reports HIT.
</details>

### Card L03-R1 · Recall and repair
Q: The schema in labs/l03/composite-work/order-v1.xml adds one member to an existing type (see its TODO(L03-R1) note). Use the schema check to find it, remove it while keeping clientTag and venue, and get HIT.
The code generator accepts this schema, so only the compatibility check catches
it. The untouched file prints MISS with `schema-append: type/composite changed:
...` naming the type. In the driver, press Enter to run it.

```bash
printf '%s\n' labs/l03/composite-work | checks/l03/chk_schema.sh
```

<details><summary>After your attempt</summary>
Key:
- Remove `<type name="scaleTag" primitiveType="uint8"/>` from the Decimal composite; with it, price is 9 bytes, quantity moves from root offset 16 to 17 and the root grows to 39. After removal the check reports HIT.
</details>

### Card L03-P2 · Guess first
Q: Guess: a v0 reader receives a v1 message. To find the fills group, should it skip its compiled root length (34) or the header's blockLength (38)? Pick one.
<details><summary>After your attempt</summary>
Key:
- The header's 38: it describes what this writer actually sent. With 34 the reader lands on clientTag's bytes `be ba fe ca` and reads a fill count of 0xcafe = 51966. Likewise each fill entry is stepped by the wire's 13, not the compiled 12.
</details>

### Concept L03-ACTING · Trust the header, not your memory
Vocabulary: acting version = the version in this message's header; acting block length = the root length in this message's header; compiled constant = a value baked into your generated code, such as sbeBlockLength(); received length = how many bytes actually arrived.

**Two sources of truth.** Your generated class knows its own schema:
`tut::v1::Order::sbeBlockLength()` returns 38. The header of the message in
your hand may say 34 (an old writer) or 42 (a newer one). Decode with the
header's values:

```cpp
tut::v0::MessageHeader h(b, 0, received, 0);   // (buffer, offset, length, actingVersion)
o.wrapForDecode(b, 8, h.blockLength(), h.version(), received);
```

The 4-argument header constructor takes the buffer, the offset where the header
starts, how many bytes arrived, and a version for the header itself (0 here).

**What the generated code does with them** (1.42.0, `tut_v1/Order.h`):

```cpp
std::uint32_t clientTag() const {
if (m_actingVersion < 1) { return UINT32_C(0xffffffff); } // field not sent
... read 4 bytes at root offset 34 ...
}
```

Group decoding reads each group's width from its wire dimensions, so
`g.next()` steps by the writer's entry width (13 for v1, 12 for v0). Never
step entries by your own compiled width.

**The common wrong belief:** "my reader is v1, so the bytes are v1." The
header decides. Give a v1 reader the compiled 38 on a v0 message and it reads
the group dimensions four bytes too late.

Predict: a v1 reader decodes a v0 message using the header's values. Does clientTag return the next four bytes after flags, or something else?

<details><summary>Worked example — open after predicting</summary>

Something else: the acting version is 0, so clientTag() returns its null value
4294967295 (0xffffffff) and venue() returns 255, without reading any byte.
Those are "not sent", not zero. The worked `read_record` in
`labs/l03/worked/submission.hpp` then walks every fill, the trader and the note,
and records the final cursor. The matrix check runs every writer/reader pair:

```text
writer → reader      v0→v0   v0→v1   v1→v0   v1→v1
message end offset     79      79      85      85
clientTag readable?    no      no      no     yes
root / entry bytes   34/12   34/12   38/13   38/13
```

The end offsets include the 8-byte header and hold for this fixture only.
</details>

Elaborate: Why are both the header's block length and its version needed? Give a different failure for each one being wrong.

### Card L03-C2 · Complete the repair
Q: In labs/l03/completion/submission.hpp, fill the two TODO(L03-C2) arguments of wrapForDecode so the matrix check reports HIT (after your C1 schema repair in the same folder).
The matrix check generates v0 and v1 codecs, then decodes four inputs for all
four writer/reader pairs. In the driver, press Enter to run it.

```bash
printf '%s\n' labs/l03/completion | checks/l03/chk_matrix.sh
```

<details><summary>After your attempt</summary>
Key:
- `o.wrapForDecode(b,8,h.blockLength(),h.version(),received);` (the header's block length and version, and the received length as the bound); the matrix check then reports HIT for all 16 combinations.
</details>

## Sitting B — recall, then preserve the archive (20 minutes)

Start with due reviews. Close the worked example before the next two cards.

### Card L03-R2 · Recall and repair
Q: Two parts, without the worked solution:
  (a) Repair labs/l03/work/submission.hpp (see TODO(L03-R2)) so the matrix check reports HIT.
  (b) Explain in one sentence why the value you changed must come from the header.
In the driver, the check runs first; after a HIT it asks for your (b) sentence.
The untouched file prints MISS with
`FAIL case=0 writer=0 reader=1: fill count`. Use that line to locate the
mistake: a v0 message, read by the v1 reader. In the driver, press Enter to run
the check.

```bash
printf '%s\n' labs/l03/work | checks/l03/chk_matrix.sh
```

<details><summary>After your attempt</summary>
Key:
- (a) Replace `O::sbeBlockLength()` (compiled 38 in the v1 reader) with `h.blockLength()` in wrapForDecode; the matrix check reports HIT.
- (b) Explain: The writer's version decides how long its root is: a v0 message has a 34-byte root, so the compiled 38 makes the reader look for the fills four bytes too late.
</details>

### Card L03-R3 · Recall and repair
Q: Without code, give the job of each value in one line: (a) the header's block length, (b) a group's entry block length, (c) the header's version, (d) the received length.
<details><summary>After your attempt</summary>
Key:
- (a) Where the root ends, so the reader finds the first group even when the root has fields it does not know.
- (b) How far to step per entry, including any unknown entry extensions.
- (c) Which fields were sent: for an older version, newer fields return their null value.
- (d) The bound on reading: only bytes that arrived, not the buffer's spare capacity.
</details>

### Card L03-P3 · Guess first
Q: Guess: a v0 reader decodes a v1 message correctly, then writes the fields it knows back out with a v0 writer. Are the output bytes identical to the input? Yes or no.
<details><summary>After your attempt</summary>
Key:
- No. The 85-byte v1 message comes back as 79 bytes, and a v1 reader of the result sees null clientTag and venue. Reading correctly did not preserve what the old schema cannot represent.
</details>

### Concept L03-ARCHIVE · Keep the original, not your reading of it
Vocabulary: frame = one message plus the outer length prefix that delimits it; raw preservation = keeping the original bytes; projection = the decoded values you understood.

**Framing.** SBE messages have no delimiter and our header has no total length
(lesson 01). This course's archive puts a little-endian uint32 length, which
counts the whole SBE message including its header, in front of each message:

```text
[len][v0 message][len][v1 message][len][v2 message]
```

The tape holds three records: a v0, a v1, and a synthetic v2 with 4 unknown
root bytes and 2 unknown bytes per fill entry. This reader accepts versions 0
to 2 only; that is a local policy for this fixture, not a promise about future
versions.

**The loop, already written for you** (`labs/l03/api.hpp` supplies `read32`
and `append_frame`):

```cpp
auto n = read32(tape.data() + p); p += 4;
if (n < 8 || n > 1024 || n > tape.size() - p) throw std::runtime_error("bad frame length");
std::vector<char> frame(tape.begin() + p, tape.begin() + p + n);
out.records.push_back(decode_v1(frame.data(), frame.size()));
// ... what goes into out.raw here?
p += n;
```

**The common wrong belief:** "I decoded it, so I can re-create it." You can
only re-create what your schema knows.

Predict: what should the archive append to out.raw for each record, and where does the next record start?

<details><summary>Worked example — open after predicting</summary>

Append the original frame, prefix included, and start the next record at the
outer frame boundary (p + n), not at the decoded cursor:

```cpp
append_frame(out.raw, frame);   // same 4-byte prefix + original bytes
```

```text
tape  ── decode known values ──> owned audit records (projection)
      └─ copy original frames ─> exact archive, unknown tails included
```

The audit records and the archive hold different information, and both are
correct. The records are owned copies, so both survive the input buffer being
overwritten.
</details>

Elaborate: Why can the audit projection and the preserved archive differ without either being corrupt?

### Card L03-C3 · Complete the repair
Q: Fill two blanks in words: (a) after decoding the frame, append ____ to out.raw; (b) advance p by ____.
<details><summary>After your attempt</summary>
Key:
- (a) The original frame with its length prefix: `append_frame(out.raw, frame)`.
- (b) By n, the outer frame length, after the 4-byte prefix was consumed; never by the decoded cursor.
</details>

### Card L03-T1 · Apply it elsewhere
Q: Repair archive_tape in labs/l03/independent/submission.hpp (see TODO(L03-T1)) so the archive check reports HIT: the raw archive must equal the input tape byte for byte, unknown extensions included.
The starter decodes each frame with the v0 reader and re-encodes it, so it
prints MISS with `FAIL raw unknown extension preservation including frame
prefixes`. The check also overwrites the input after archiving, and rejects
truncated prefixes and frames. In the driver, press Enter to run it.

```bash
printf '%s\n' labs/l03/independent | checks/l03/chk_archive.sh
```

<details><summary>After your attempt</summary>
Key:
- Replace the decode_v0/encode_v0 pair with `append_frame(out.raw, frame);`, keeping the v1 decode for the records; the check reports HIT.
- All three records decode with the v1 reader (old records show null extensions), and the raw tape matches exactly.
</details>

### Card L03-INT · Connect the ideas
Q: Two parts. Use this hypothetical service (or one of your own): legacy readers accept only their existing message type and reject unknown types; reserved bytes must stay zero; readers and writers deploy separately; stored frames must stay readable.
  (a) An AI assistant proposes this v2 change, saying "it is appended at the end of the root, so it is safe": set version="2" and add `<field name="account" id="9" type="uint32" sinceVersion="2"/>` right after clientTag. Is it right here? In two sentences: what it gets right, and what makes you reject it.
  (b) In one sentence each, contrast a null value (L02), the header's block length, and the outer frame length.
<details><summary>After your attempt</summary>
Key:
- (a) Appending preserves existing offsets. Reject the required field because old frames contain no account: make it optional, or introduce a new message type and deploy supporting readers before writers.
- (b) A null sentinel means an optional slot was sent without a value; a field absent from an older layout has no slot. The header’s block length locates the end of the root. The outer frame length locates the end of the complete framed record.
</details>

## Close

Remember: append optional, versioned fields at a block's end and never move
old ones. Decode with the header's block length and version, bounded by what
arrived. Archive the original frames, not your reading of them. Tomorrow
today's graded cards come back for review. Next: lesson 04, hostile input.
