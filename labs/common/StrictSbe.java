import java.io.File;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.SchemaFactory;
import org.xml.sax.ErrorHandler;
import org.xml.sax.SAXParseException;
import uk.co.real_logic.sbe.SbeTool;

// Validates ALL XML inputs before SbeTool can publish any generated file.
public class StrictSbe {
    public static void main(String[] args) throws Exception {
        SchemaFactory factory = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        var xsd = SbeTool.class.getResource("/fpl/sbe.xsd");
        if (xsd == null) throw new IllegalStateException("pinned jar has no fpl/sbe.xsd");
        var schema = factory.newSchema(xsd);
        for (String input : args) {
            if (!input.endsWith(".xml") && !input.endsWith(".sbeir"))
                throw new IllegalArgumentException("expected .xml or .sbeir input");
            if (input.endsWith(".xml")) {
                var validator = schema.newValidator();
                validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
                validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
                validator.setErrorHandler(new ErrorHandler() {
                    public void warning(SAXParseException e) throws SAXParseException { throw e; }
                    public void error(SAXParseException e) throws SAXParseException { throw e; }
                    public void fatalError(SAXParseException e) throws SAXParseException { throw e; }
                });
                validator.validate(new StreamSource(new File(input)));
            }
        }
    }
}
