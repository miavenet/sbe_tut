// [claim: WP4-CODEC]
#include "tut_v1/Side.h"
#include <iostream>
int main(){try{
 auto value=tut::v1::Side::get('?');
#ifdef TOLERANT
 if(value!=tut::v1::Side::SBE_UNKNOWN)return 1;
 std::cout<<"unknown=SBE_UNKNOWN; application must reject\n";return 0;
#else
 (void)value;return 1;
#endif
}catch(const std::exception& e){
#ifdef TOLERANT
 return 1;
#else
 std::cout<<"unknown throws: "<<e.what()<<"\n";return 0;
#endif
}}
