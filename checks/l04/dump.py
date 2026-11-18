#!/usr/bin/env python3
# [claim: WP3-INSPECT]
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import struct,json

def inspect(b):
    lines=[]
    for p in range(0,len(b),16):lines.append(f'{p:04x} ({p:3d}): '+b[p:p+16].hex(' '))
    if len(b)<8:raise ValueError('header truncated')
    root,template,schema,version=struct.unpack_from('<HHHH',b)
    lines.append(f'header root={root} template={template} schema={schema} version={version} received={len(b)}')
    if (schema,template)!=(91,1) or version>2:raise ValueError('unsupported contract')
    p=8
    def take(n):
        nonlocal p
        if n>len(b)-p:raise ValueError(f'offset={p} requested={n} remaining={len(b)-p}')
        p+=n
    take(root);lines.append(f'root end={p} remaining={len(b)-p}')
    at=p;take(4);width,count=struct.unpack_from('<HH',b,at)
    lines.append(f'fills dimensions @{at}: width={width} count={count} cursor={p}')
    if width<12 or count>65534 or count>(len(b)-p)//width:raise ValueError('invalid group dimensions')
    for i in range(count):take(width);lines.append(f'fills[{i}] end={p} remaining={len(b)-p}')
    for name in ('trader','note'):
        at=p;take(2);n=struct.unpack_from('<H',b,at)[0];take(n)
        lines.append(f'{name} length @{at}={n} end={p} remaining={len(b)-p}')
    if p!=len(b):raise ValueError('unconsumed tail')
    return '\n'.join(lines)
def main():
    try:
        if len(sys.argv)==4 and sys.argv[1]=='--diff':
            a=Path(sys.argv[2]).read_bytes();b=Path(sys.argv[3]).read_bytes()
            diffs=[{'offset':i,'left':a[i] if i<len(a) else None,'right':b[i] if i<len(b) else None} for i in range(max(len(a),len(b))) if a[i:i+1]!=b[i:i+1]]
            print(json.dumps({'differences':diffs},sort_keys=True));return 0
        if len(sys.argv)!=2:raise ValueError('usage: dump.py FRAME | --diff LEFT RIGHT')
        print(inspect(Path(sys.argv[1]).read_bytes()));return 0
    except (OSError,ValueError) as e:print('REJECT '+str(e));return 1
if __name__=='__main__':sys.exit(main())
