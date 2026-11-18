// [claim: WP4-ALLOC]
#include <new>
#include <cstdlib>
#include <cstddef>
#include <cstdint>
#include <string>
#include <cstdio>
static bool measuring=false;
static std::uint64_t allocations=0;
extern "C" void count_begin(){allocations=0;measuring=true;}
extern "C" std::uint64_t count_end(){measuring=false;return allocations;}
static void* allocate(std::size_t n,std::size_t alignment=0){
    void* p=nullptr;
    if(alignment){ if(posix_memalign(&p,alignment,n?n:1))p=nullptr; }
    else p=std::malloc(n?n:1);
    if(!p)throw std::bad_alloc();
    if(measuring)++allocations;
    return p;
}
void* operator new(std::size_t n){return allocate(n);}
void* operator new[](std::size_t n){return allocate(n);}
void* operator new(std::size_t n,const std::nothrow_t&) noexcept{try{return allocate(n);}catch(...){return nullptr;}}
void* operator new[](std::size_t n,const std::nothrow_t&) noexcept{try{return allocate(n);}catch(...){return nullptr;}}
void* operator new(std::size_t n,std::align_val_t a){return allocate(n,static_cast<std::size_t>(a));}
void* operator new[](std::size_t n,std::align_val_t a){return allocate(n,static_cast<std::size_t>(a));}
void* operator new(std::size_t n,std::align_val_t a,const std::nothrow_t&) noexcept{try{return allocate(n,static_cast<std::size_t>(a));}catch(...){return nullptr;}}
void* operator new[](std::size_t n,std::align_val_t a,const std::nothrow_t&) noexcept{try{return allocate(n,static_cast<std::size_t>(a));}catch(...){return nullptr;}}
void operator delete(void* p)noexcept{std::free(p);}
void operator delete[](void* p)noexcept{std::free(p);}
void operator delete(void* p,std::size_t)noexcept{std::free(p);}
void operator delete[](void* p,std::size_t)noexcept{std::free(p);}
void operator delete(void* p,const std::nothrow_t&)noexcept{std::free(p);}
void operator delete[](void* p,const std::nothrow_t&)noexcept{std::free(p);}
void operator delete(void* p,std::align_val_t)noexcept{std::free(p);}
void operator delete[](void* p,std::align_val_t)noexcept{std::free(p);}
void operator delete(void* p,std::size_t,std::align_val_t)noexcept{std::free(p);}
void operator delete[](void* p,std::size_t,std::align_val_t)noexcept{std::free(p);}
void operator delete(void* p,std::align_val_t,const std::nothrow_t&)noexcept{std::free(p);}
void operator delete[](void* p,std::align_val_t,const std::nothrow_t&)noexcept{std::free(p);}
extern void escape_string(const std::string&);
extern "C" std::size_t owning_control(const char* p,std::size_t n){
    std::string s(p,n);
    // Escape into an opaque external TU: keep the allocation observable at -O2.
    escape_string(s);return s.size();
}
