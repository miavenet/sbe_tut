#!/usr/bin/env python3
# [claim: WP1-CHECKS]
import sys
sys.dont_write_bytecode=True
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'checks/l01'))
from check import Run,child,generation_argv,java_argv
import json

def probe_passes(rc, output):
    lines = output.strip().splitlines()
    return (rc == 0 and len(lines) == 2 and lines[0] == 'COPY_BYTES 0'
            and lines[1].startswith('OWNING_BYTES ')
            and lines[1][13:].isdigit() and int(lines[1][13:]) > 0)


def main():
    with Run('wp1-java',parent=R/'manifest/evidence/wp1',timeout=30) as run:
        rc,out=child(run,'generate',generation_argv(run.path/'java',R/'labs/l02/order-padded.xml',language='Java'))
        if rc != 0: raise RuntimeError('Java generation failed: '+out)
        (run.path/'classes').mkdir()
        rc,out=child(run,'compile',['javac','-cp',R/'labs/lib/sbe-all-1.42.0.jar','-d',run.path/'classes',*sorted((run.path/'java').rglob('*.java')),R/'checks/l02/Allocation.java'])
        if rc != 0: raise RuntimeError('Java compile failed: '+out)
        rc,out=child(run,'probe',java_argv('Allocation',classpath=[run.path/'classes']))
        print(out,end='')
        if not probe_passes(rc,out): raise RuntimeError('Java allocation probe failed')
        print(json.dumps({'status':'PASS','probe':'java-allocation','copy_zero':True,'owning_positive':True},sort_keys=True))


if __name__ == '__main__': main()
