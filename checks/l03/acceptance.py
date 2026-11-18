#!/usr/bin/env python3
# [claim: WP2-CHECKS] [claim: WP2-MUTATIONS]
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json,struct,re,concurrent.futures,shutil
from check import R,L,Run,child,fixtures,oracle,evaluate,generation_argv,compile_argv,atomic_json,compatible,InfraError

def main():
    outcomes=[]
    def expect(name,rc,want,output,needle=''):
        if rc!=want or needle not in output:raise AssertionError((name,rc,want,needle,output))
        outcomes.append({'case':name,'expected_exit':want,'actual_exit':rc,'observed':output})
    with Run('wp2-acceptance',parent=R/'manifest/evidence/wp2',timeout=30) as run:
        rc,out=child(run,'setup',[R/'tools/setup.sh','--check']);expect('setup',rc,0,out)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            res=list(pool.map(lambda v:child(run,'base'+str(v),generation_argv(run.path/('v'+str(v)),L/f'order-v{v}.xml')),range(2)))
        for v,(rc,out) in enumerate(res):expect('generate-v'+str(v),rc,0,out)
        prepared=(run.path/'v0',run.path/'v1')
        cases=[('worked',L/'worked',0,'PASS'),('alternative',L/'fixtures/alternative',0,'PASS'),('extra-data-omitted',L/'fixtures/extra-data-omitted',1,'exercise contract')]
        cases += [(p.name,p,1,'FAIL') for p in sorted((L/'fixtures/faults').iterdir())]
        def run_case(c):
            name,path,want,needle=c
            with Run('wp2-'+name,parent=run.path,timeout=30) as sub:
                rc,out=evaluate(path,sub,prepared=prepared)
                return name,rc,want,out,needle
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for args in pool.map(run_case,cases):expect(*args)
        # The public stdin ABI gets end-to-end positive, negative and INFRA controls.
        for name,stdin,want in [('abi-good','labs/l03/worked\n',0),('abi-bad','labs/l03/work\n',1),('abi-missing','/missing/wp2\n',2)]:
            rc,out=child(run,name,[R/'checks/chk_l03_compat.sh'],stdin=stdin)
            expect(name,rc,want,out,['"HIT"','"MISS"','"INFRA"'][want])
        for name,stdin,want in [('schema-worked','labs/l03/worked\n',0),
                                 ('schema-deleted-extensions','checks/l03/fixtures/deleted-extensions\n',1),
                                 ('schema-renamed-extension','checks/l03/fixtures/renamed-extension\n',1)]:
            rc,out=child(run,name,[R/'checks/l03/chk_schema.sh'],stdin=stdin)
            expect(name,rc,want,out,'exercise contract' if want else '"HIT"')
        # Completion schema can be repaired independently before the reader holes.
        errors=compatible(L/'order-v0.xml',L/'completion/order-v1.xml')
        expect('completion-schema',int(bool(errors)),1,'; '.join(errors),'sinceVersion')
        def bad_gen(p):
            name=p.stem
            rc,out=child(run,'bad-'+name,generation_argv(run.path/('bad-'+name),p))
            errors=compatible(L/'order-v0.xml',p)
            return name,rc,out,errors
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for name,rc,out,errors in pool.map(bad_gen,sorted((L/'fixtures/bad').glob('*.xml'))):
                expect('codegen-'+name,rc,0,out)
                expect('regression-'+name,int(bool(errors)),1,'; '.join(errors))
        # Pin generated offsets by compiling actual release-generated metadata.
        probe=run.path/'offset.cpp';probe.write_text('#include "tut_v1/Order.h"\n#include <iostream>\nint main(){auto n=tut::v1::Order::quantityEncodingOffset();std::cout<<"quantity_offset="<<n<<"\\n";return n==20?0:1;}\n')
        rc,out=child(run,'offset-build',compile_argv(probe,run.path/'offset',includes=[run.path/'bad-mid-block']));expect('offset-build',rc,0,out)
        rc,out=child(run,'offset-run',[run.path/'offset']);expect('mid-block-offset',rc,0,out,'quantity_offset=20')
        rc,out=child(run,'transform',generation_argv(run.path/'transform',L/'order-v1.xml',properties={'sbe.schema.transform.version':'*:0'}));expect('E6-generation',rc,0,out)
        transformed=(run.path/'transform/tut_v1/Order.h').read_text()
        assert 'clientTag(' not in transformed and 'venue(' not in transformed
        probe=run.path/'transform.cpp';probe.write_text('#include "tut_v1/Order.h"\n#include <iostream>\nint main(){using O=tut::v1::Order;std::cout<<O::sbeBlockLength()<<" "<<O::sbeSchemaVersion()<<"\\n";return O::sbeBlockLength()==34 && O::sbeSchemaVersion()==0?0:1;}\n')
        rc,out=child(run,'transform-build',compile_argv(probe,run.path/'transformed',includes=[run.path/'transform']));expect('transform-build',rc,0,out)
        rc,out=child(run,'transform-run',[run.path/'transformed']);expect('E6-metadata',rc,0,out,'34 0')
        fixtures(run.path/'wire');b=oracle(0,1)
        (run.path/'wire/group-add.bin').write_bytes(b[:76]+struct.pack('<HHi',4,1,777)+b[76:])
        (run.path/'wire/group-data.bin').write_bytes(b[:63]+b'\x01\x00X'+b[63:76]+b'\x01\x00Y'+b[76:])
        (run.path/'wire/data-insert.bin').write_bytes(b[:76]+b'\x01\x00Z'+b[76:])
        rc,out=child(run,'probes-build',compile_argv(R/'checks/l03/probes.cpp',run.path/'probes',includes=[L/'worked',L,*prepared]));expect('probes-build',rc,0,out)
        rc,out=child(run,'probes-run',[run.path/'probes',run.path/'wire']);expect('bounded-drift-probes',rc,0,out,'count=51966')
        # Source-policy false rejects: metadata correction and safe trailing data.
        original=(L/'order-v1.xml').read_text()
        for name,text in [('description',original.replace('Tutorial order schema','Corrected description')),('trailing-data',original.replace('    </sbe:message>','        <data name="extra" id="22" type="varStringEncoding" sinceVersion="1"/>\n    </sbe:message>'))]:
            p=run.path/(name+'.xml');p.write_text(text)
            errors=compatible(L/'order-v0.xml',p);expect('positive-'+name,int(bool(errors)),0,'; '.join(errors))
        atomic_json(run.path/'outcomes.json',outcomes)
    print(json.dumps({'status':'PASS','cases':len(outcomes),'artifacts':str(run.path.relative_to(R))},sort_keys=True))
if __name__=='__main__':main()
