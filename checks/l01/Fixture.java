// [claim: WP1-WIRE]
import org.agrona.concurrent.UnsafeBuffer;
import java.nio.file.*;
public class Fixture {
    public static void main(String[] args)throws Exception {
        UnsafeBuffer b=new UnsafeBuffer(new byte[2048]);
        tut.v0.OrderEncoder o=new tut.v0.OrderEncoder();
        o.wrapAndApplyHeader(b,0,new tut.v0.MessageHeaderEncoder());
        o.orderId(0x1122334455667788L).quantity(100).stopPrice(tut.v0.OrderEncoder.stopPriceNullValue()).symbol("AAPL").side(tut.v0.Side.BUY);
        o.price().mantissa(12345);o.flags().clear().ioc(true).hidden(true);
        var f=o.fillsCount(2);f.next().fillPrice(12340).fillQty(60);f.next().fillPrice(12345).fillQty(40);
        o.trader("pat").note("hi");int n=8+o.encodedLength();byte[] out=new byte[n];b.getBytes(0,out);
        Files.write(Path.of(args[0]),out);System.out.println("JAVA_BYTES "+n);
    }
}
