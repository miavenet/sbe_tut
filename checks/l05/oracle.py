#!/usr/bin/env python3
# [claim: WP4-CHECKSUM]
"""Independent one-shot checksum/envelope oracle; does not import the C++ port."""
import struct,json
from pathlib import Path
P1,P2,P3,P4,P5=2654435761,2246822519,3266489917,668265263,374761393
M=2**32-1
def rot(x,n):
    x&=M
    return ((x<<n)|(x>>(32-n)))&M
def xxh(data):
    p=0;n=len(data)
    if n>=16:
        v=[(P1+P2)&M,P2,0,(-P1)&M]
        while p+16<=n:
            for i,x in enumerate(struct.unpack_from('<4I',data,p)):v[i]=rot(v[i]+x*P2,13)*P1&M
            p+=16
        h=sum(rot(x,r) for x,r in zip(v,[1,7,12,18]))&M
    else:h=P5
    h=(h+n)&M
    while p+4<=n:h=rot(h+struct.unpack_from('<I',data,p)[0]*P3,17)*P4&M;p+=4
    for x in data[p:]:h=rot(h+x*P5,11)*P1&M
    h^=h>>15;h=h*P2&M;h^=h>>13;h=h*P3&M;return h^(h>>16)
def frame(payload,seq=1,epoch=7,kind=60000,origin=9):
    h=bytearray(struct.pack('<QIIIIHHI',seq,origin,1,0,epoch,kind,len(payload),0))
    struct.pack_into('<I',h,16,xxh(h[:16]+h[20:]+payload));return bytes(h)+payload
def build(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    lab=Path(__file__).resolve().parents[2]/'labs/l05'
    # Independent offset assertions, not generated-code constants.
    p=(lab/'fixtures/order-v1.bin').read_bytes();f=frame(p)
    assert len(p)==85 and len(f)==117
    assert struct.unpack_from('<H',f,26)[0]==85 and f[32:40]==bytes.fromhex('260001005b000100')
    assert xxh(b'')==0x02cc5d05 and xxh(b'a')==0x550d7456 and xxh(b'abc')==0x32d153ff
    (out/'envelope.bin').write_bytes(f)
    future=struct.pack('<4H',40,1,91,2)+p[8:46]+b'\xa1\xa2'+struct.pack('<2H',14,2)+p[50:63]+b'\xb1'+p[63:76]+b'\xb2'+p[76:]
    (out/'order-v2-tail.bin').write_bytes(future)
    state=struct.pack('<QQIqII',6,20,2,-5,2,2)+struct.pack('<QQq',11,10,3)+struct.pack('<QQq',12,20,-5)
    (out/'business-digest.txt').write_text(str(xxh(state))+'\n')
    vectors=[{'hex':bytes((i*17+3)%256 for i in range(n)).hex(),'hash':xxh(bytes((i*17+3)%256 for i in range(n)))} for n in [0,1,3,15,16,17,31,32,1408]]
    (out/'vectors.json').write_text(json.dumps(vectors,indent=2)+'\n')
    return {'bytes':len(f),'checksum':struct.unpack_from('<I',f,16)[0]}
if __name__=='__main__':
    import sys
    print(json.dumps(build(sys.argv[1]),sort_keys=True))
