#!/usr/bin/env python3
"""Course contract regression, deliberately narrower than a general SBE validator."""
# [claim: WP2-MUTATIONS]
import xml.etree.ElementTree as E

def compatible(old_path,new_path):
    old,new=E.parse(old_path).getroot(),E.parse(new_path).getroot()
    errors=[]
    def require(ok,why):
        if not ok:errors.append(why)
    def sig(x):
        return (x.tag,tuple(sorted((k,v) for k,v in x.attrib.items() if k not in ('description','semanticType'))),x.text.strip() if x.text and x.text.strip() else '',tuple(sig(y) for y in x))
    for k,default in [('id',''),('byteOrder','littleEndian'),('headerType','messageHeader')]:
        require(old.get(k,default)==new.get(k,default),'header/schema contract '+k)
    ov,nv=int(old.get('version','0')),int(new.get('version','0'))
    require(nv>ov,'increment schema version')
    ot={x.get('name'):x for x in old.find('types')};nt={x.get('name'):x for x in new.find('types')}
    for name,t in ot.items():require(name in nt and sig(t)==sig(nt[name]),'type/composite changed: '+name)
    def block(a,b,path):
        ac=list(a);bc=list(b);oldids=[x.get('id') for x in ac]
        common=[x for x in bc if x.get('id') in oldids]
        require([x.get('id') for x in common]==oldids,path+': removed/reordered existing elements')
        bm={x.get('id'):x for x in bc}
        for x in ac:
            if x.get('id') not in bm:continue
            y=bm[x.get('id')]
            # Names/descriptions may change; wire definitions may not.
            attrs=lambda z:{k:v for k,v in z.attrib.items() if k not in ('name','description','semanticType','blockLength')}
            require(x.tag==y.tag and attrs(x)==attrs(y),path+': changed existing field '+x.get('id'))
            require(int(y.get('blockLength','0'))>=int(x.get('blockLength','0')),path+': shrunk block')
            if x.tag=='group':block(x,y,path+'/'+x.get('name'))
        fields=[x for x in ac if x.tag=='field'];groups=[x for x in ac if x.tag=='group'];data=[x for x in ac if x.tag=='data']
        for i,x in enumerate(bc):
            if x.get('id') in oldids:continue
            require(int(x.get('sinceVersion','0'))==nv,path+f': sinceVersion must be {nv} (found {x.get("sinceVersion", "missing")})')
            if x.tag=='field':
                require(x.get('presence','required')=='optional',path+': added field must be optional')
                require(all(bc.index(bm[y.get('id')])<i for y in fields if y.get('id') in bm),path+': field inserted mid-block')
            elif x.tag=='group':
                require(not data and all(bc.index(bm[y.get('id')])<i for y in groups if y.get('id') in bm),path+': unsafe group addition before trailing data/groups')
            elif x.tag=='data':
                require(a.tag!='group',path+': new variable data inside group is not fixed-block skippable')
                require(all(bc.index(bm[y.get('id')])<i for y in groups+data if y.get('id') in bm),path+': data inserted before existing structure')
        # Code generation separately validates schema order/offsets/XSD.
    om=next(x for x in old if x.tag.endswith('message'));nm=next(x for x in new if x.tag.endswith('message'))
    require(om.get('id')==nm.get('id'),'template contract changed')
    block(om,nm,'Order')
    return errors


def exercise_contract(path,expected):
    """The matrix oracle grades the supplied v1 contract, not arbitrary extensions."""
    a,b=E.parse(path).getroot(),E.parse(expected).getroot()
    def shape(x):
        return (x.tag,x.get('name'),x.get('id'),x.get('type'),x.get('presence','required'),
                x.get('sinceVersion','0'),tuple(shape(y) for y in x))
    am=next(x for x in a if x.tag.endswith('message'))
    bm=next(x for x in b if x.tag.endswith('message'))
    return a.get('version')==b.get('version') and shape(am)==shape(bm)
