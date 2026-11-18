// [claim: WP3-IR]
import uk.co.real_logic.sbe.ir.*;
public class InspectIr {
    public static void main(String[] args) throws Exception {
        try (IrDecoder decoder = new IrDecoder(args[0])) {
            Ir ir = decoder.decode();
            System.out.println("schema="+ir.id()+" version="+ir.version());
            for (Token t : ir.getMessage(1))
                System.out.println(t.signal()+" "+t.name()+" offset="+t.offset()+" length="+t.encodedLength()+" version="+t.version());
        }
    }
}
