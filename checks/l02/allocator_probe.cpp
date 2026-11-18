// [claim: WP1-ALLOCATION]
#include <new>
#include <cstddef>
#include <cstdint>
#include <cstdio>
extern "C" void count_begin();
extern "C" std::uint64_t count_end();
int main(){
    count_begin();
    void* p[8];
    p[0]=::operator new(80);p[1]=::operator new[](80);
    p[2]=::operator new(80,std::nothrow);p[3]=::operator new[](80,std::nothrow);
    p[4]=::operator new(80,std::align_val_t(64));p[5]=::operator new[](80,std::align_val_t(64));
    p[6]=::operator new(80,std::align_val_t(64),std::nothrow);p[7]=::operator new[](80,std::align_val_t(64),std::nothrow);
    auto n=count_end();
    ::operator delete(p[0]);::operator delete[](p[1]);
    ::operator delete(p[2],std::nothrow);::operator delete[](p[3],std::nothrow);
    ::operator delete(p[4],std::align_val_t(64));::operator delete[](p[5],std::align_val_t(64));
    ::operator delete(p[6],std::align_val_t(64),std::nothrow);::operator delete[](p[7],std::align_val_t(64),std::nothrow);
    std::printf("NEW_FAMILIES %llu\n",static_cast<unsigned long long>(n));return n==8?0:1;
}
