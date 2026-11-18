// [claim: WP1-ALLOCATION]
#include <string>
volatile unsigned escaped_byte;
void escape_string(const std::string& s){escaped_byte=static_cast<unsigned char>(s.at(s.size()-1));}
