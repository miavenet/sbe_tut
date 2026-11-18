package demo;

import org.agrona.concurrent.UnsafeBuffer;
import java.nio.ByteBuffer;
import java.nio.file.*;

public class Demo
{
    static void dump(final String name, final UnsafeBuffer buf, final int len) throws Exception
    {
        final byte[] b = new byte[len];
        buf.getBytes(0, b);
        Files.write(Paths.get("out", name), b);
        final StringBuilder sb = new StringBuilder(name + " (" + len + " bytes)\n");
        for (int i = 0; i < len; i++)
        {
            if (i % 16 == 0) sb.append(String.format("%04x: ", i));
            sb.append(String.format("%02x ", b[i]));
            if (i % 16 == 15 || i == len - 1) sb.append('\n');
        }
        System.out.print(sb);
    }

    static int encodeV0(final UnsafeBuffer buf)
    {
        final tut.v0.MessageHeaderEncoder hdr = new tut.v0.MessageHeaderEncoder();
        final tut.v0.OrderEncoder order = new tut.v0.OrderEncoder();
        order.wrapAndApplyHeader(buf, 0, hdr)
            .orderId(0x1122334455667788L)
            .quantity(100)
            .stopPrice(tut.v0.OrderEncoder.stopPriceNullValue())
            .symbol("AAPL")
            .side(tut.v0.Side.BUY);
        order.price().mantissa(12345);
        order.flags().clear().ioc(true).hidden(true);
        final tut.v0.OrderEncoder.FillsEncoder fills = order.fillsCount(2);
        fills.next().fillPrice(12340).fillQty(60);
        fills.next().fillPrice(12345).fillQty(40);
        order.trader("pat");
        order.note("hi");
        return tut.v0.MessageHeaderEncoder.ENCODED_LENGTH + order.encodedLength();
    }

    static int encodeV1(final UnsafeBuffer buf)
    {
        final tut.v1.MessageHeaderEncoder hdr = new tut.v1.MessageHeaderEncoder();
        final tut.v1.OrderEncoder order = new tut.v1.OrderEncoder();
        order.wrapAndApplyHeader(buf, 0, hdr)
            .orderId(0x1122334455667788L)
            .quantity(100)
            .stopPrice(tut.v1.OrderEncoder.stopPriceNullValue())
            .symbol("AAPL")
            .side(tut.v1.Side.BUY)
            .clientTag(0xCAFEBABEL);
        order.price().mantissa(12345);
        order.flags().clear().ioc(true).hidden(true);
        final tut.v1.OrderEncoder.FillsEncoder fills = order.fillsCount(2);
        fills.next().fillPrice(12340).fillQty(60).venue((short)7);
        fills.next().fillPrice(12345).fillQty(40).venue((short)9);
        order.trader("pat");
        order.note("hi");
        return tut.v1.MessageHeaderEncoder.ENCODED_LENGTH + order.encodedLength();
    }

    static void decodeWithV0(final UnsafeBuffer buf)
    {
        final tut.v0.MessageHeaderDecoder hdr = new tut.v0.MessageHeaderDecoder();
        final tut.v0.OrderDecoder order = new tut.v0.OrderDecoder();
        hdr.wrap(buf, 0);
        System.out.println("  header: blockLength=" + hdr.blockLength() + " templateId=" + hdr.templateId() +
            " schemaId=" + hdr.schemaId() + " version=" + hdr.version());
        order.wrapAndApplyHeader(buf, 0, hdr);
        System.out.println("  orderId=0x" + Long.toHexString(order.orderId()) +
            " price=" + order.price().mantissa() + "e" + order.price().exponent() +
            " qty=" + order.quantity() +
            " stopPriceIsNull=" + (order.stopPrice() == tut.v0.OrderDecoder.stopPriceNullValue()) +
            " symbol='" + order.symbol() + "' side=" + order.side() + " flags=" + order.flags());
        for (final tut.v0.OrderDecoder.FillsDecoder f : order.fills())
        {
            System.out.println("  fill: px=" + f.fillPrice() + " qty=" + f.fillQty());
        }
        System.out.println("  trader='" + order.trader() + "' note='" + order.note() + "' encodedLength=" + order.encodedLength());
    }

    static void decodeWithV1(final UnsafeBuffer buf)
    {
        final tut.v1.MessageHeaderDecoder hdr = new tut.v1.MessageHeaderDecoder();
        final tut.v1.OrderDecoder order = new tut.v1.OrderDecoder();
        hdr.wrap(buf, 0);
        System.out.println("  header: blockLength=" + hdr.blockLength() + " templateId=" + hdr.templateId() +
            " schemaId=" + hdr.schemaId() + " version=" + hdr.version());
        order.wrapAndApplyHeader(buf, 0, hdr);
        final long tag = order.clientTag();
        System.out.println("  orderId=0x" + Long.toHexString(order.orderId()) +
            " qty=" + order.quantity() + " symbol='" + order.symbol() + "' side=" + order.side() +
            " clientTag=" + (tag == tut.v1.OrderDecoder.clientTagNullValue() ? "NULL(" + tag + ")" : "0x" + Long.toHexString(tag)));
        for (final tut.v1.OrderDecoder.FillsDecoder f : order.fills())
        {
            final short v = f.venue();
            System.out.println("  fill: px=" + f.fillPrice() + " qty=" + f.fillQty() +
                " venue=" + (v == tut.v1.OrderDecoder.FillsDecoder.venueNullValue() ? "NULL(" + v + ")" : "" + v));
        }
        System.out.println("  trader='" + order.trader() + "' note='" + order.note() + "' encodedLength=" + order.encodedLength());
    }

    public static void main(final String[] args) throws Exception
    {
        final UnsafeBuffer b0 = new UnsafeBuffer(ByteBuffer.allocateDirect(256));
        final UnsafeBuffer b1 = new UnsafeBuffer(ByteBuffer.allocateDirect(256));
        final int len0 = encodeV0(b0);
        final int len1 = encodeV1(b1);

        System.out.println("== 1. v0 encoder output");
        dump("order-v0.bin", b0, len0);
        System.out.println("== 2. v0 bytes read by v0 decoder");
        decodeWithV0(b0);
        System.out.println("== 3. v1 encoder output");
        dump("order-v1.bin", b1, len1);
        System.out.println("== 4. v1 bytes read by v1 decoder");
        decodeWithV1(b1);
        System.out.println("== 5. BACKWARD compat: OLD v0 bytes read by NEW v1 decoder (new fields -> null)");
        decodeWithV1(b0);
        System.out.println("== 6. FORWARD compat: NEW v1 bytes read by OLD v0 decoder (extra bytes skipped via blockLength)");
        decodeWithV0(b1);

        System.out.println("== 7. PITFALL: ignore header blockLength (wrap v1 bytes with v0 compiled BLOCK_LENGTH)");
        final tut.v0.OrderDecoder bad = new tut.v0.OrderDecoder();
        bad.wrap(b1, tut.v0.MessageHeaderDecoder.ENCODED_LENGTH, tut.v0.OrderDecoder.BLOCK_LENGTH, tut.v0.OrderDecoder.SCHEMA_VERSION);
        final tut.v0.OrderDecoder.FillsDecoder bf = bad.fills();
        System.out.println("  group header misread: count=" + bf.count() + " actingBlockLength=" + bf.actingBlockLength());

        System.out.println("== 8. PITFALL: var-data read out of schema order (note() before trader())");
        final tut.v0.MessageHeaderDecoder hdr = new tut.v0.MessageHeaderDecoder();
        final tut.v0.OrderDecoder o = new tut.v0.OrderDecoder().wrapAndApplyHeader(b0, 0, hdr);
        for (final tut.v0.OrderDecoder.FillsDecoder f : o.fills()) { f.fillQty(); }
        System.out.println("  note()='" + o.note() + "' then trader()='" + o.trader() + "'   <-- swapped, no error");

        System.out.println("== 9. PITFALL: skip the group, go straight to var-data");
        final tut.v0.OrderDecoder o2 = new tut.v0.OrderDecoder().wrapAndApplyHeader(b0, 0, hdr);
        System.out.println("  traderLength() without iterating fills = " + o2.traderLength() + "   <-- actually the group's blockLength field");

        System.out.println("== 10. sbeSkip()/sbeDecodedLength and toString");
        final tut.v0.OrderDecoder o3 = new tut.v0.OrderDecoder().wrapAndApplyHeader(b0, 0, hdr);
        System.out.println("  sbeDecodedLength=" + o3.sbeDecodedLength());
        System.out.println("  " + o3);
    }
}
