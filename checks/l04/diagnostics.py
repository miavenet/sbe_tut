#!/usr/bin/env python3
# [claim: WP3-ORDER] [claim: WP3-IR] [claim: WP3-XSD]
import sys
sys.dont_write_bytecode=True
import json,zipfile,concurrent.futures
from pathlib import Path
from check import R,L,Run,child,prepare,compile_argv,generation_argv,InfraError

def probes(run):
    inc=prepare(run)
    def compile_one(on):
        return child(run,'precedence-compile-'+str(on),compile_argv(R/'checks/l04/precedence.cpp',run.path/('precedence-'+str(on)),includes=inc,checked=on))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for rc,out in pool.map(compile_one,[False,True]):assert rc==0,out
    for on in (False,True):
        for mode in ('ordered','skip','before-next','partial','swap','incomplete'):
            rc,out=child(run,'precedence-'+str(on)+'-'+mode,[run.path/('precedence-'+str(on)),L/'fixtures/order-v1.bin',mode])
            expected=1 if on and mode!='ordered' else 0
            assert rc==expected,(on,mode,rc,out)
            assert ('CAUGHT' if expected else 'ACCEPTED') in out
            if mode=='ordered':assert 'trader=pat cursor=81' in out and 'note=hi cursor=85 body=77' in out
            if mode=='skip' and not on:assert 'trader_length=13' in out
            if mode=='swap' and not on:assert 'note=pat trader=hi' in out
            if expected:assert ('fully encoded' if mode=='incomplete' else 'access') in out.lower(),out
    # XML -> serialized tokens -> generated Java, exact file identity except description.
    rc,out=child(run,'xml-ir',generation_argv(run.path/'java',L/'order-v1.xml',language='Java',ir=True));assert rc==0,out
    ir=run.path/'java/order-v1.sbeir'
    rc,out=child(run,'ir-java',generation_argv(run.path/'from-ir',ir,language='Java'));assert rc==0,out
    left=run.path/'java/tut/v1';right=run.path/'from-ir/tut/v1'
    assert {p.name for p in left.iterdir()}=={p.name for p in right.iterdir()}
    differences=[]
    for p in sorted(left.iterdir()):
        q=right/p.name
        if p.read_bytes()!=q.read_bytes():
            differences.append(p.name)
            assert p.name=='package-info.java'
            assert p.read_text().replace('Tutorial order schema, version 1','null')==q.read_text()
    assert differences==['package-info.java']
    (run.path/'ir-diff.json').write_text(json.dumps({'different':differences,'identical_other_files':len(list(left.iterdir()))-1}))
    classes=run.path/'classes';classes.mkdir()
    jar=R/'labs/lib/sbe-all-1.42.0.jar'
    rc,out=child(run,'ir-javac',['javac','-cp',jar,'-d',classes,R/'checks/l04/InspectIr.java']);assert rc==0,out
    rc,out=child(run,'ir-tokens',[R/'tools/sbe_tool.sh','--run',classes,'InspectIr',ir]);assert rc==0,out
    for line in ('schema=91 version=1','BEGIN_FIELD quantity offset=16','BEGIN_GROUP fills','BEGIN_VAR_DATA trader','BEGIN_VAR_DATA note'):assert line in out,line
    rc,out=child(run,'ir-without-opens',['java','-cp',str(classes)+':'+str(jar),'InspectIr',ir]);assert rc==1 and 'IllegalAccessError' in out,(rc,out)
    # Raw jar behavior is tested independently of the strict wrapper.
    xsd=run.path/'sbe.xsd'
    with zipfile.ZipFile(jar) as z:xsd.write_bytes(z.read('fpl/sbe.xsd'))
    for e,diagnostic in ((1,'sinceVersion'),(2,'field node specified after'),(7,'bogus'),(8,'maxValue must be set'),(9,'Message header not found')):
        outdir=run.path/f'raw-e{e}'
        rc,out=child(run,f'raw-e{e}',['java',f'-Dsbe.output.dir={outdir}',f'-Dsbe.validation.xsd={xsd}','-jar',jar,L/f'fixtures/bad/e{e}.xml'])
        assert rc==(0 if e==7 else 255) and diagnostic in out,(e,rc,out)
        if e==7:assert list(outdir.rglob('OrderDecoder.java'))
        strict=run.path/f'strict-e{e}'
        rc,out=child(run,f'strict-e{e}',generation_argv(strict,L/f'fixtures/bad/e{e}.xml'))
        assert rc!=0 and not strict.exists(),(e,rc,out)
    rc,out=child(run,'stale-property',[R/'tools/sbe_tool.sh',f'-Dsbe.output.dir={run.path / "stale"}','-Dsbe.generate.access.order.checks=true',L/'order-v1.xml'])
    assert rc==2 and 'stale property' in out and not (run.path/'stale').exists()
    rc,out=child(run,'bad-classpath',[R/'tools/sbe_tool.sh','--run',str(classes)+'-missing','InspectIr',ir])
    assert rc==1 and 'ClassNotFoundException' in out
    return {'stale_property_rejected':True,'bad_classpath_rejected':True,'precedence_cases':12,'ir_equivalent_except_package_description':True,'ir_tokens':True,'missing_opens_rejected':True,'schema_faults':5,'strict_no_promotion':True}

def main():
    try:
        with Run('wp3-diagnostics',parent=R/'manifest/evidence/wp3',timeout=40) as run:
            result=probes(run)
        print(json.dumps(dict(status='PASS',**result,artifacts=str(run.path.relative_to(R)))));return 0
    except (AssertionError,InfraError,OSError) as e:print(json.dumps(dict(status='FAIL',detail=str(e))));return 1
if __name__=='__main__':sys.exit(main())
