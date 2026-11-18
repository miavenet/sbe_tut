#!/usr/bin/env python3
# [claim: WP1-CHECKS]
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json,os,shutil,csv
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tools'))
from harness import Run,InfraError,compile_argv,generation_argv,java_argv,workspace_from_stdin,result,emit_result
sys.path.insert(0,str(R/'checks/l01'))
from oracle import packet,LAYOUT,first_difference,layout_matches


def child(run,name,argv,stdin='',learner=False):
    c=run.start(name,[str(x) for x in argv],cwd=R,stdin=stdin)
    # Waiting twice can misclassify a process that exits between polls.
    # Wait on the atomic completion predicate first; bounded by Run timeout.
    run.until(lambda: c.poll() is not None, description=name+" completion")
    rc=run.wait(c)
    text=c.log.read_text()
    if rc<0: raise InfraError(f'{name}: unexpected signal {rc}; {c.log}')
    if rc and not learner:raise InfraError(f'{name}: exit {rc}; {c.log}\n{text[-1500:]}')
    return rc,text


def setup(run,lesson):
    if not (shutil.which('clang++') or shutil.which('g++')):
        raise InfraError('missing C++17 compiler (clang++ or g++)')
    child(run,'setup',[R/'tools/setup.sh','--check'])
    schema=R/('labs/l01/order-v0.xml' if lesson=='l01' else 'labs/l02/order-padded.xml')
    gen=run.path/'cpp'
    schemas=[schema]+([R/'labs/l01/market.xml'] if lesson=='l01' else [])
    child(run,'generate',generation_argv(gen,*schemas))
    cases=json.loads((R/f'labs/{lesson}/fixtures/cases.json').read_text())
    lines=['#include "api.hpp"','const std::array<Input,4> cases = {{']
    for x in cases:
        fs=','.join('{'+f"{f['price']}LL,{f['qty']}U,{f['venue']}"+'}' for f in x['fills'])
        fs+=(',' if fs else '')+','.join('{}' for _ in range(2-len(x['fills']))) if len(x['fills'])<2 else ''
        vals=[str(x['id'])+'ULL',str(x['price'])+'LL',str(x['qty'])+'U',str(x['has_stop']).lower(),str(x['stop']),json.dumps(x['symbol']),repr(x['side'])]+[str(x[k]).lower() for k in ('ioc','post_only','hidden')]+[str(x['tag'])+'U','{{'+fs+'}}',str(len(x['fills'])),json.dumps(x['trader']),json.dumps(x['note'])]
        lines.append('{'+','.join(vals)+'},')
    lines.append('}};')
    (run.path/'cases.hpp').write_text('\n'.join(lines)+'\n')
    if lesson=='l01':
        child(run,'java-generate',generation_argv(run.path/'java',schema,language='Java'))
        classes=run.path/'classes';classes.mkdir()
        child(run,'javac',['javac','-cp',R/'labs/lib/sbe-all-1.42.0.jar','-d',classes,*sorted((run.path/'java').rglob('*.java')),R/'checks/l01/Fixture.java'])
        child(run,'java-fixture',java_argv('Fixture',run.path/'java.bin',classpath=[classes]))
        data=(run.path/'java.bin').read_bytes()
        if data!=packet(cases[0]) or data!=(R/'labs/l01/fixtures/order-v0.bin').read_bytes():raise InfraError('Java/independent/pinned golden mismatch')
        at=0
        with (R/'labs/l01/fixtures/golden-layout.tsv').open() as f:
            for row in csv.DictReader(f,delimiter='\t'):
                n=int(row['width'])
                if int(row['packet_start'])!=at or data[at:at+n].hex()!=row['hex']:raise InfraError('independent label mismatch: '+row['field'])
                at+=n
        if at!=len(data):raise InfraError('unlabelled golden bytes')
    return gen,cases


def grade(run,lesson,work,gen,cases,name='submission',mode='all',allocator=None):
    criteria=[]
    def add(id,ok,detail):criteria.append(dict(id=id,pass_=bool(ok),detail=detail))
    def finish():
        c=[{'id':v['id'],'pass':v['pass_'],'detail':v['detail']} for v in criteria]
        code=0 if all(v['pass'] for v in c) else 1
        return result(code,c,next_action='All criteria pass.' if code==0 else 'Use the first failed criterion; predict the byte/value, repair one cause, rerun.',artifacts=str(run.path.relative_to(R)))
    if not (work/'submission.hpp').is_file():add('submission',False,'workspace needs submission.hpp');return finish()
    exe=run.path/name
    flags=[]
    if lesson=='l02':flags=[str(allocator or R/'checks/l02/alloc.cpp'),str(R/'checks/l02/escape.cpp')]
    rc,out=child(run,name+'-compile',compile_argv(R/f'checks/{lesson}/runner.cpp',exe,includes=[work,R/f'labs/{lesson}',gen,run.path],flags=flags),learner=True)
    if rc:add('compile',False,out[-2000:]);return finish()
    args=[exe]+([R/f'labs/l01/fixtures/market-{i}.bin' for i in range(2)] if lesson=='l01' else [])
    rc,out=child(run,name+'-run',args,learner=True)
    if rc:add('runtime',False,out[-2000:]);return finish()
    rows={}
    for line in out.splitlines():
        p=line.split(' ',2)
        if len(p)>=2:
            if p[0] in ('WIRE','REUSED','MARKET','AUDIT','COPIED','NULL','ACCESS'):rows[(p[0],p[1])]=p[2] if len(p)>2 else ''
            else:rows[(p[0],'')]=' '.join(p[1:])
    if mode in ('all','wire','init'):
        for i,x in enumerate(cases):
            raw=rows.get(('WIRE',str(i)),'')
            try:actual=bytes.fromhex(raw)
            except ValueError:actual=b''
            expected=packet(x,lesson=='l02')
            label = 'SELL, present zero stop' if x['side']=='S' and x['has_stop'] and x['stop']==0 else x['side'] + (' with stop' if x['has_stop'] else ' without stop')
            diff = first_difference(actual,expected)
            if actual!=expected and diff.startswith('byte '):
                at=int(diff.split(':',1)[0].split()[1])
                field=('header' if at<8 else 'stopPrice' if 28<=at<32 else 'symbol' if 32<=at<40 else 'root or tail')
                diff=f'case {i} ({label}): byte {at} = {field}: '+diff.split(': ',1)[1]
            add('wire-'+str(i),actual==expected,'exact bytes match' if actual==expected else diff)
    if lesson=='l02' and mode in ('all','init'):
        for i,x in enumerate(cases):add('reuse-'+str(i),rows.get(('REUSED',str(i)))==packet(x,True).hex(),'exact bytes restored after slot reuse')
    if lesson=='l01':
        if mode in ('all','wire'):
            for i,x in enumerate(cases):add('fixed-access-'+str(i),rows.get(('ACCESS',str(i)))==f"{x['qty']} {x['id']}",'quantity before orderId: fixed offsets support independent field access')
            try:layout=json.loads((work/'layout.json').read_text())
            except (OSError,ValueError):layout=None
            observed=layout if isinstance(layout,dict) else {}
            mismatches=[f'{key}: actual {observed.get(key)!r}, expected {want!r}' for key,want in LAYOUT.items() if key != 'source' and observed.get(key)!=want]
            matched=layout_matches(layout)
            add('layout',matched,'layout matches' if matched else '; '.join(mismatches) or 'layout annotation has an invalid type or extra field')
        if mode in ('all','transfer'):
            for i,want in enumerate(['123456 -3 17 424f4e44','-7654 -3 513 46580000']):
                got=rows.get(('MARKET',str(i)))
                add('market-'+str(i),got==want,f'market-{i}: actual {got!r}, expected {want!r}')
    else:
        if mode in ('all','ownership'):
            for i,x in enumerate(cases):add('audit-'+str(i),rows.get(('AUDIT',str(i)))==x['trader'].encode().hex(),'deferred audit must retain first trader after same slot overwritten')
        if mode == 'all':
            for i,x in enumerate(cases):add('copied-audit-'+str(i),rows.get(('COPIED',str(i)))==x['trader'].encode().hex(),'saved Audit must keep its own trader after the source Audit storage and receive slot are overwritten')
        if mode in ('all','init'):
            for i,v in enumerate([-1431655766,0,-2147483648]):add('null-'+str(i),rows.get(('NULL',str(i)))==str(v),'dirty/zero/explicit probe '+str(v))
        if mode in ('all','allocation'):
            want=sum(x['qty']+len(x['trader'])+len(x['note']) for x in cases)*250
            add('alloc-loop',rows.get(('LOOP',''))==f'0 {want}','warmed 1000 encode/decode operations: zero intercepted new calls and exact checksum '+str(want))
            try:control=int(rows.get(('CONTROL',''),'0'))
            except ValueError:control=0
            add('alloc-control',control>0,'long owning string must hit instrumented allocation counter')
    return finish()


def main():
    lesson=sys.argv[1];mode=sys.argv[2] if len(sys.argv)>2 else 'all'
    try:
        if mode not in ({'all','wire','transfer'} if lesson=='l01' else {'all','init','ownership','allocation'}):raise InfraError('unknown check mode')
        work=workspace_from_stdin()
        with Run('wp1-'+lesson,parent=R/'manifest/evidence/wp1',timeout=25) as run:
            gen,cases=setup(run,lesson)
            res=grade(run,lesson,work,gen,cases,mode=mode)
    except (InfraError,OSError) as e:res=result(2,[dict(id='infrastructure',**{'pass':False},detail=str(e))])
    emit_result(res);return res['exit_code']
if __name__=='__main__':sys.exit(main())
