// [claim: WP1-JAVA]
import java.lang.management.ManagementFactory;
import org.agrona.concurrent.UnsafeBuffer;
import tut.v1.*;
public class Allocation {
    static volatile Object escape;
    static volatile int consumed;
    public static void main(String[] args) {
        var mx=(com.sun.management.ThreadMXBean)ManagementFactory.getThreadMXBean();
        if(!mx.isThreadAllocatedMemorySupported())throw new IllegalStateException("unsupported allocation counter");
        mx.setThreadAllocatedMemoryEnabled(true);
        var b=new UnsafeBuffer(new byte[512]);
        var e=new OrderEncoder();e.wrapAndApplyHeader(b,0,new MessageHeaderEncoder());
        e.fillsCount(0);e.trader("a".repeat(160));e.note("");
        var d=new OrderDecoder();byte[] dst=new byte[256];
        for(int i=0;i<20000;i++) {
            d.wrap(b,8,40,1);d.fills();consumed=d.getTrader(dst,0,dst.length);
            d.wrap(b,8,40,1);d.fills();escape=d.trader();
        }
        long tid=Thread.currentThread().threadId();
        long before=mx.getThreadAllocatedBytes(tid);
        for(int i=0;i<1000;i++){d.wrap(b,8,40,1);d.fills();consumed=d.getTrader(dst,0,dst.length);}
        long copied=mx.getThreadAllocatedBytes(tid)-before;
        before=mx.getThreadAllocatedBytes(tid);
        for(int i=0;i<1000;i++){d.wrap(b,8,40,1);d.fills();escape=d.trader();}
        long owning=mx.getThreadAllocatedBytes(tid)-before;
        System.out.println("COPY_BYTES "+copied);System.out.println("OWNING_BYTES "+owning);
        if(copied!=0 || owning<=0)throw new IllegalStateException("counter/control criteria failed");
    }
}
