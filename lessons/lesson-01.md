# Lesson 01 — Read the bytes, not the marketing

An order decodes without a single error, yet its stop price is nonsense.
Nothing crashed, so there is no stack trace to read. There is only a buffer of
bytes. Today you learn to read those bytes like a map, find the first wrong one,
and repair the line of code that wrote it.

**You will be able to:** label every byte of a 79-byte SBE order, locate its
fields, and fix an encoder so a checker reports HIT.
**Time:** about 33 minutes, in two sittings (18 now + 15 later). Stop at any card.
**You need:** C++17 basics, hexadecimal, and the two-minute check in
`labs/l01/README.md`. No Java.

## Primer: what SBE is (3 minutes)

**SBE (Simple Binary Encoding)** is a binary message format. Its specification
is published by the FIX Trading Community, the body behind the FIX trading
protocol. The specification says SBE is "optimized for low latency of encoding
and decoding". This course uses the real-logic reference implementation,
version 1.42.0, which generates code for Java, C, C++ and other languages.

**The problem it solves.** JSON represents numbers as text, and JSON objects carry member names. Protobuf represents fields as tagged records; many integer types use varints, while fixed32/sfixed32 and fixed64/sfixed64 use fixed-width encodings. A raw C++ struct’s object representation depends on implementation details such as padding and byte order. SBE specifies the wire representation in a schema. Fixed fields have known offsets within their block; repeating groups and variable-length data are traversed using their dimensions and lengths.

**The moving parts:**

```text
order-v0.xml  ──>  sbe-tool (the 1.42.0 jar)  ──>  Order.h (generated C++)
  schema            code generator                    flyweight class
                                                          │ wraps
your char buffer  <────────── reads/writes in place ──────┘
```

- **Schema:** an XML file that declares types and messages. Each message type
  has a number called its **template id**; the schema has its own **schema id**
  and **version**.
- **Generated flyweight:** a class that holds a pointer to *your* buffer plus
  a few offsets and lengths. Calling `o.quantity(100)` writes four bytes at a fixed spot.
  There is no separate message object and no copy.
- **Message shape:** header, then the fixed **root block**, then **repeating
  groups** (lists), then **variable-length data** (strings).

```text
[ header | root block (fixed fields) | groups (lists) | var data (strings) ]
```

**Byte order.** This schema is **little-endian**: the least significant byte
comes first. The two bytes `22 00` mean 0x0022, which is 34.

**What SBE is not.** It is not self-describing. No field names or tags travel
on the wire, so without the schema the bytes are just bytes. The header also
carries no total message length: finding where one message ends and the next
begins (**framing**) is a job for the layer around SBE.

A field in a schema may be marked **optional**: the message is allowed to have
no value for it. Keep that word in mind for the first card.

**How checks answer.** Every check prints one of three results. **HIT**
(exit 0): your work passes. **MISS** (exit 1): it fails, and the first failed
criterion is printed. **SETUP PROBLEM** (exit 2): the check could not run, for
example a wrong path or missing jar; fix that first, it is not a grade.

**Before the first card.** Try to recall before looking. This may feel harder
than rereading; familiarity is not the delayed performance we are checking.

### Card L01-P1 · Guess first
Q: Guess (no lesson needed): an optional int32 field is part of a message's layout, but this message has no value for it. Does the field take zero bytes or four? Commit to one before opening the key.
<details><summary>After your guess</summary>
Key:
- Four bytes. The writer stores a special "null" value in the field's slot, so every later field keeps its offset. (A field added only in a later schema version is a different case; lesson 03 covers it.)
</details>

### Concept L01-LAYOUT · A map before a microscope
Vocabulary: header = the first 8 bytes, naming the contract; root block = fixed fields at fixed offsets; group dimensions = 4 bytes giving entry width and entry count; var data = 2-byte length then bytes.

**Why the map has this shape.** In 2014 Martin Thompson wrote up where SBE
came from. The CME, a member of the FIX community, had commissioned him and
Todd Montgomery to build a reference implementation for fast market data.
Text formats were still common; he even called out markets sending XML.

His design rule was to move through a message without backtracking. So the
fixed fields come first, at offsets you can compute, and the variable-length
strings come last.

**The header.** In this course's schema the header is four uint16 values,
8 bytes. That size belongs to this schema, not to every SBE schema. Our packet
starts `22 00 01 00 5b 00 00 00`. Read each pair little-endian:

```text
22 00 -> blockLength = 34   size of the root block, header NOT included
01 00 -> templateId  = 1    which message: Order
5b 00 -> schemaId    = 91   which schema
00 00 -> version     = 0    which schema version wrote it
```

**The root block** follows the header. Its fields sit back to back, in schema
order, so each offset is the sum of the widths before it:

```text
field      type                 width  root offset
orderId    uint64                 8     0
price      Decimal (composite)    8     8
quantity   uint32                 4    16
stopPrice  int32, optional        4    20
symbol     char[8]                8    24
side       char enum              1    32
flags      uint8 bitset           1    33
```

A **composite** is one field built from several smaller types. `price` is a
Decimal composite: an int64 mantissa (8 bytes) plus an exponent (more in the
next concept). A root offset counts from the root's first byte. To get the
**packet offset** (from the very first byte), add the 8-byte header.

**After the root** come the `fills` group and two strings, `trader` then
`note`. A group starts with 4 bytes of dimensions: entry width (uint16), then
entry count (uint16). Each fill entry here is fillPrice (int64) + fillQty
(uint32). Each string starts with a uint16 length.

The common wrong belief: "blockLength is the message length." It is not. It
counts only the root's fixed fields: no header, no groups, no strings.

Predict: with the 8-byte header and a 34-byte root, at which packet offset do the fills group dimensions begin?

<details><summary>Worked map — open after predicting</summary>

At 8 + 34 = 42. Here is every byte of the real 79-byte packet
`labs/l01/fixtures/order-v0.bin`, produced with this command and labelled from
`labs/l01/fixtures/golden-layout.tsv`:

```bash
python3 -B checks/l04/dump.py labs/l01/fixtures/order-v0.bin
```

```text
pkt  bytes (hex)               part         value
0    22 00                     header       blockLength = 34
2    01 00                     header       templateId = 1
4    5b 00                     header       schemaId = 91
6    00 00                     header       version = 0
8    88 77 66 55 44 33 22 11   root +0      orderId = 0x1122334455667788
16   39 30 00 00 00 00 00 00   root +8      price mantissa = 12345
24   64 00 00 00               root +16     quantity = 100
28   00 00 00 80               root +20     stopPrice = null
32   41 41 50 4c 00 00 00 00   root +24     symbol = "AAPL" + 4 zero bytes
40   42                        root +32     side = 'B' (BUY)
41   05                        root +33     flags = bits 0 and 2 set
42   0c 00                     fills dims   entry width = 12
44   02 00                     fills dims   entry count = 2
46   34 30 00 00 00 00 00 00   fill 0       fillPrice = 12340
54   3c 00 00 00               fill 0       fillQty = 60
58   39 30 00 00 00 00 00 00   fill 1       fillPrice = 12345
66   28 00 00 00               fill 1       fillQty = 40
70   03 00                     trader       length = 3
72   70 61 74                  trader       "pat"
75   02 00                     note         length = 2
77   68 69                     note         "hi"
```

So: header 8, root 34, **body** (everything after the header) 71, packet 79.
The header's blockLength says 34, not 71 or 79. Fixed fields have offsets you
can compute without reading anything else. To find the trader string you must
step over the group: 42 + 4 + 2 × 12 = 70. The schema order is always fixed
fields, then groups, then var data, and the same order repeats inside each
group entry.
</details>

Elaborate: Why does the root block length (34) differ from the total packet length (79)?

### Card L01-C1 · Complete the repair
Q: Three parts, about the 79-byte packet:
  (a) Fill the blanks: fills dimensions start at 8 + __ = __; trader starts at __ + 4 + 2 × __ = __. Submit JSON with the keys root_bytes, group_at, entry_bytes and trader_at, each holding an integer value.
  (b) Explain in one sentence why the root length 34 cannot tell you where this packet ends.
  (c) Say what you must do instead to find the end.
In the driver, type the JSON for (a) on one line at the prompt; after a HIT the
driver asks for your (b) and (c) answer. On paper, run the command below, paste
the JSON, press Enter, then Ctrl-D. Correct JSON gives HIT; any wrong value
gives MISS.

```bash
checks/l01/chk_complete_offsets.sh
```

<details><summary>Check your completed trace</summary>
Key:
- (a) 8 + 34 = 42 and 42 + 4 + 2 × 12 = 70, so {"root_bytes":34,"group_at":42,"entry_bytes":12,"trader_at":70}.
- (b) Explain: The root length counts only the fixed root fields; it excludes the header, the group dimensions and entries, and the strings.
- (c) Explain: Walk the structure: read the group dimensions and step over the entries, then read each string's length. (Or get the length from the framing around the packet.)
</details>

### Card L01-R1 · Recall and repair
Q: Close the completed byte map. Use these format facts: an 8-byte header; root-field widths 8, 8, 4, 4, 8, 1, 1; two 12-byte fills after 4 dimension bytes; strings of 3 and 2 bytes, each with a 2-byte length. Derive the layout. Submit JSON with integer values named header, root, body and packet, and an array offsets giving the root offsets of orderId, price, quantity, stopPrice, symbol, side and flags. After the check passes, explain the difference between a root offset and a packet offset.
In the driver, type the JSON on one line at the prompt. On paper, run the command
below, paste the JSON, press Enter, then Ctrl-D.

```bash
checks/l01/chk_recall_offsets.sh
```

<details><summary>Compare each item, then restate any correction</summary>
Key:
- {"header":8,"root":34,"body":71,"packet":79,"offsets":[0,8,16,20,24,32,33]}: each offset is the sum of the widths before it (8, 8, 4, 4, 8, 1).
- Explain: These are root offsets. Add the 8-byte header for packet offsets: stopPrice is root 20, packet 28.
</details>

### Card L01-P2 · Guess first
Q: Guess: price is a composite with an int64 mantissa 12345 and an int8 exponent of -2 that is declared constant in the schema. What decimal value is it, and how many bytes does the composite take on the wire?
<details><summary>After committing value and width</summary>
Key:
- 12345 × 10^-2 = 123.45, and 8 bytes. A constant's value lives in the schema, so the exponent adds no ninth byte.
</details>

### Concept L01-SEMANTICS · Three meanings of “nothing”
Vocabulary: presence = required / optional / constant; null value (sentinel) = the reserved value meaning "absent"; constant = value fixed in the schema, zero wire bytes; bitset = flags packed one per bit.

Open `labs/l01/order-v0.xml`. A `<type>` names an encoding, a `<field>` uses
one. Each field has a **presence**:

```xml
<type name="exponent" primitiveType="int8" presence="constant">-2</type>
<field name="stopPrice" id="4" type="int32" presence="optional"/>
```

**Required** (the default): always a real value. **Optional**: the slot is
always there; "absent" is written as the type's **null value**, also called a
**sentinel**. For int32 it is -2147483648 (-2^31), bytes `00 00 00 80`.
**Constant**: the value lives in the schema; the generated `exponent()` just
returns -2 and no byte is written.

**Why meaning lives in the schema.** On 23 September 1999 NASA lost the Mars
Climate Orbiter. Its inquiry board traced the root cause to one ground-software
file.
An interface specification set that file's format and units: thruster impulse
in newton-seconds. The program that wrote it used pound-force seconds instead.
The navigation software read the file as specified, underestimated the
thrusters' effect on the trajectory by a factor of 4.45, and computed a wrong
trajectory.

Bytes carry numbers, not meaning. In SBE the agreement on meaning, such as
"price is the mantissa times 10^-2", sits in the schema that both sides
generate code from. The schema cannot stop a writer from putting a wrong value
in a field. It does make the agreement explicit, shared and compiled in.

**A concrete trap.** A trader sends an order with a stop price of exactly 0.
If your code writes 0 for "no stop", that order and an order with no stop are
now identical bytes. Zero is a value; null is the sentinel.

**Other fixed fields.** `symbol` is char[8]: always 8 bytes. This encoder pads
short symbols with zero bytes, and the check requires every byte defined.

Quick choice before the table: your venue defines a code of exactly four
letters, and orders also carry a free-text comment of anything up to a few
hundred characters. Which one is a fixed field?

| | fixed `char[8]` (symbol) | var data (trader) |
|---|---|---|
| Wire cost | always 8 bytes; short values padded | 2-byte length + the actual bytes |
| Locating what follows | Later fixed fields in the same block have schema-defined offsets | The next variable item follows this item's length prefix and payload |
| Right when | the value has a small, hard maximum | the length really varies |
| Smell of the wrong pick | truncated values, or junk in the padding | a reader walking past strings to reach a short code |

The four-letter code is the fixed field; the comment is var data. Thompson's
own advice: SBE's sweet spot is "mostly fixed size fields", and strings carry
restrictions some users find "a usability issue".

`side` is an enum stored as one char: 'B' or 'S'.
`flags` is a **bitset**: ioc = bit 0, postOnly = bit 1, hidden = bit 2, so
ioc + hidden = 0b101 = `05`.

This is an API fragment. A complete encoder must also initialize every other required field and supply the intended values for every group entry.

**Cheat-sheet: the generated C++ calls the labs use** (from `Order.h` that
sbe-tool 1.42.0 generates from this schema):

```cpp
tut::v0::Order o;
o.wrapAndApplyHeader(b, 0, capacity);  // writes the 8-byte header, aims o at the root
o.orderId(in.id);                      // fixed field: writes at its fixed offset
o.price().mantissa(in.price);          // composite: price() gives the Decimal part
o.stopPrice(tut::v0::Order::stopPriceNullValue()); // optional field's null value
o.putSymbol(symbol);                   // copies exactly 8 chars
o.flags().clear().ioc(true);           // clear() zeroes all bits, then set some
auto& f = o.fillsCount(n);
for (std::uint16_t i = 0; i < n; ++i)
    f.next().fillPrice(p).fillQty(q);  // illustrative repeated values
o.putTrader(ptr, len);
o.putNote(notePtr, noteLen);          // even an empty note writes its length
std::size_t total = 8 + o.encodedLength();
// decoding: read the header, then wrap with ITS values
tut::v0::MessageHeader h(b, received);
o.wrapForDecode(b, 8, h.blockLength(), h.version(), received);
std::uint32_t qty = o.quantity();      // getter = same name, no argument
```

Every schema gets its own namespace (from `package`) and class (from the
message name). Getters convert from the schema's byte order for you.

Predict: an order has zero fills, an empty trader and an empty note. Which bytes, if any, remain on the wire after the root block?

<details><summary>Worked empty tail</summary>

They do not vanish. Each structure keeps its own little header:

```text
pkt 42..45   0c 00 00 00   fills: entry width 12, count 0
pkt 46..47   00 00         trader: length 0
pkt 48..49   00 00         note: length 0
```

The whole packet is 8 + 34 + 4 + 2 + 2 = 50 bytes. A reader needs those
lengths to know the group and strings are empty. Nothing, it turns out, has
several rather specific outfits: a null sentinel (4 bytes here), a constant
(0 bytes), and an empty group or string (its count or length, still written).
</details>

Elaborate: Why does an absent optional field take four bytes while the constant exponent takes none?

## Second sitting

Start with any due reviews. Before going on, say aloud the difference between
root length, body length and packet length.

### Card L01-C2 · Complete the repair
Q: Repair the workspace labs/l01/work so the check reports HIT: fix the two TODO(L01-C2) lines in submission.hpp, and the two wrong numbers in layout.json (root_bytes and exponent_wire_bytes).
What to change: in `submission.hpp`, `stopPrice` must keep a present value
(including 0) and write the null value when absent; `encode` must return the
whole packet length. In `layout.json`, two annotations are wrong. Nothing to
prepare: the folder ships ready. (To start over, `cp labs/l01/completion/*
labs/l01/work/` restores the starter and overwrites your edits.)
In the driver, press Enter to run the check; on paper, run the command below
from the course folder. The untouched starter prints MISS with lines such as
`wire-0: case 0 (B without stop): byte 31 = stopPrice: observed 00, expected 80`
and `layout: root_bytes: actual 35, expected 34`. It regenerates the codecs,
compiles your header and compares every byte with a Java-produced fixture and an
independent byte oracle .

```bash
printf '%s\n' labs/l01/work | checks/chk_l01_wire.sh
```

<details><summary>After attempting the repair</summary>
Key:
- `o.stopPrice(in.has_stop ? in.stop : tut::v0::Order::stopPriceNullValue());` keeps a present 0 and writes the sentinel only when absent.
- `return 8 + o.encodedLength();` because encodedLength() excludes the 8-byte header.
- In layout.json: root_bytes 34 and exponent_wire_bytes 0 (a constant takes no bytes).
</details>

### Card L01-I1 · Recall and repair
Q: Without opening worked/, repair the encoder in labs/l01/independent so the encoder check reports HIT for all four inputs in fixtures/cases.json: fix the three TODO(L01-I1) lines in submission.hpp and the two wrong numbers in layout.json.
The inputs include a SELL order with a present stop of 0, a negative price,
an order with no fills and empty strings, and a full 8-character symbol. Leave
`decode_market` for the next card. Run after your edit (untouched starter:
MISS; repaired: HIT). In the driver, press Enter to run it.

```bash
printf '%s\n' labs/l01/independent | checks/l01/chk_encode.sh
```

<details><summary>Independent criteria</summary>
Key:
- The stop line keeps a present value and writes `stopPriceNullValue()` when absent; the flags line clears the bitset and then sets ioc, postOnly and hidden from the input; the return value is `8 + o.encodedLength()`.
- layout.json: root_bytes 34 and exponent_wire_bytes 0; with these the check reports HIT for all four byte comparisons and the layout.
</details>

### Card L01-T1 · Apply it elsewhere
Q: In labs/l01/independent, implement decode_market (marked TODO(L01-T1)) for the Quote schema in labs/l01/market.xml, so the full check reports HIT.
Quote is a different contract: big-endian (most significant byte first), a
4-byte int32 price mantissa with a constant exponent of -3, a uint16 size and a
4-char ticker. The runner passes you the two packets `fixtures/market-0.bin`
and `market-1.bin`. Use the generated `market::MessageHeader` and
`market::Quote` classes, exactly like the decoding lines in the cheat-sheet;
`q.getTicker(dst, 4)` copies the ticker. The full check also re-checks your
I1 repair. In the driver, press Enter to run it.

```bash
printf '%s\n' labs/l01/independent | checks/chk_l01_wire.sh
```

<details><summary>Transfer criteria</summary>
Key:
- The two records decode as mantissa/exponent/size/ticker = 123456/-3/17/"BOND" and -7654/-3/513/"FX" plus two zero bytes.
- Quote's root is 10 bytes (4 + 2 + 4). The generated getters handle the big-endian order; copying the Order decoder's offsets or reading bytes little-endian gives wrong values.
</details>

### Card L01-R2 · Recall and repair
Q: Two parts, without the XML:
  (a) In one sentence each, how many wire bytes do the constant exponent, an absent optional int32, and an empty group take, and why?
  (b) The fault folder labs/l01/fixtures/faults/null-zero writes 0 for an absent stop. Predict the first wrong packet byte (offset and value) for the first case, then run the command below to compare.
The command reports MISS on purpose: this folder is a deliberately broken
encoder.

```bash
printf '%s\n' labs/l01/fixtures/faults/null-zero | checks/chk_l01_wire.sh
```

<details><summary>Check each distinction</summary>
Key:
- (a) Constant exponent: 0 bytes, its value is in the schema. Absent optional int32: 4 bytes holding the null value -2147483648. Empty group: its 4 dimension bytes, count 0 (an empty string keeps its 2-byte length).
- (b) Packet byte 31 (the last byte of stopPrice, packet 28..31): observed 00, expected 80.
</details>

### Card L01-INT · Connect the ideas
Q: An AI assistant proposes replacing the generated Order encoder with the code below, "because it is the same 34 bytes and faster". Is it right for this course's Order? Answer in three short sentences: (a) your verdict, including what it gets right; (b) the first thing you would check; (c) what makes you reject or accept it.

```cpp
#pragma pack(push, 1)
struct OrderWire {
std::uint64_t orderId; std::int64_t priceMantissa;
std::uint32_t quantity; std::int32_t stopPrice;
char symbol[8]; char side; std::uint8_t flags;
};
#pragma pack(pop)
std::memcpy(buf + 8, &w, sizeof w);   // after writing the 8-byte header
```

<details><summary>Judgement key</summary>
Key:
- (a) Wrong as this message's encoder, though it is closer than it looks: on a little-endian machine whose compiler honours `#pragma pack`, those 34 bytes can match the schema's root block exactly.
- (b) Check first: compare its output byte for byte with an independent expected packet such as order-v0.bin, and check sizeof(OrderWire) is 34; without the pragma the compiler may add padding (Apple Clang 21.0.0 on arm64 makes it 40; other compilers untested).
- (c) Reject: the struct covers only the root. Fill entries and strings depend on counts and lengths; the bytes follow the host's byte order, so the same trick breaks for a big-endian schema such as Quote; and the absent stop still needs the null value written by hand.
</details>

## Close

Remember: fixed offsets come from field widths; find later data by walking
counts and lengths. blockLength counts only the root.
Absent is a null value, constant is zero bytes, empty still keeps its length.
Tomorrow today's graded cards come back for review (the driver schedules them;
on paper, write tomorrow's date beside each one). Next: lesson 02, where a
reused buffer remembers the previous order.
