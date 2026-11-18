# [claim: WP1-CHECKS]
"""Independent positional oracle: no generated codec or reference solution import."""
import struct
from decimal import Decimal, InvalidOperation

def packet(x, padded=False):
    p=lambda fmt,*a:struct.pack('<'+fmt,*a)
    root=p('QqIi8scB',x['id'],x['price'],x['qty'],x['stop'] if x['has_stop'] else -2147483648,
           x['symbol'].encode(),x['side'].encode(),int(x['ioc'])+2*int(x['post_only'])+4*int(x['hidden']))
    if padded: root+=p('I',x['tag'])+b'\0\0'
    out=p('HHHH',40 if padded else 34,1,91,1 if padded else 0)+root+p('HH',13 if padded else 12,len(x['fills']))
    for f in x['fills']:
        out+=p('qI',f['price'],f['qty'])
        if padded: out+=p('B',f['venue'])
    for k in ('trader','note'):
        s=x[k].encode();out+=p('H',len(s))+s
    return out

LAYOUT={'header_bytes':8,'root_bytes':34,'body_bytes':71,'total_bytes':79,'price_exponent':-2,'exponent_wire_bytes':0,'root_offsets':{'orderId':0,'price':8,'quantity':16,'stopPrice':20,'symbol':24,'side':32,'flags':33},'group_header_at':42,'group_entry_bytes':12,'trader_length_at':70,'note_length_at':75,'price_decimal':'123.45'}

def first_difference(actual,expected):
    for i,(a,b) in enumerate(zip(actual,expected)):
        if a!=b:return f'byte {i}: observed {a:02x}, expected {b:02x}'
    return f'length {len(actual)}, expected {len(expected)}'

LAYOUT['source']='[claim: WP1-WIRE]'


def layout_matches(actual):
    if not isinstance(actual, dict):
        return False
    expected = {k: v for k, v in LAYOUT.items() if k != 'source'}
    supplied = {k: v for k, v in actual.items() if k != 'source'}
    if set(supplied) != set(expected):
        return False
    if type(supplied['price_decimal']) is not str:   # JSON number 123.45 is a float, not the documented decimal string
        return False
    try:
        if Decimal(str(supplied['price_decimal'])) != Decimal(expected['price_decimal']):
            return False
    except (InvalidOperation, ValueError, TypeError):
        return False

    def same(a, b):
        if isinstance(b, dict):
            return isinstance(a, dict) and set(a) == set(b) and all(same(a[k], b[k]) for k in b)
        return type(a) is type(b) and a == b

    return all(same(supplied[k], expected[k]) for k in expected if k != 'price_decimal')
