"""Read verified Maya 2025 FOR8 brush-control payloads without loading Pencil.

Only the observed PencilBrushDetail node ID, CREA UUID layout and finite CMPD
double rows are decoded. Unknown variants fail closed; this is not a general
Maya Binary reader. Geometry payloads are skipped by seeking, never scanned.
"""
from functools import lru_cache
import math
from pathlib import Path
import re
import struct
import uuid

BRUSH_DETAIL_TYPE=bytes.fromhex('00124f83')


def decode_curve(payload):
    name,sep,tail=payload.partition(b'\0')
    match=re.fullmatch(rb'(srcps|sacps)\[(\d+)(?::(\d+))?\]',name)
    if not sep or not match or not tail or tail[0]!=0x24:return None
    first,last=int(match[2]),int(match[3] or match[2])
    if not 0<=first<=last<=8191:return None
    count=(last-first+1)*7
    if len(tail)!=1+count*8:return None
    values=struct.unpack('>'+str(count)+'d',tail[1:])
    if not all(math.isfinite(value) for value in values):return None
    return match[1].decode('ascii'),{i:tuple(values[(i-first)*7:(i-first+1)*7]) for i in range(first,last+1)}


def parse_profiles(stream,size):
    result={};chunks=0;points=0
    def header(offset,end):
        nonlocal chunks
        if offset+16>end:raise ValueError('Truncated FOR8 chunk header')
        chunks+=1
        if chunks>1000000:raise ValueError('Maya Binary chunk budget exceeded')
        stream.seek(offset);raw=stream.read(16)
        if len(raw)!=16:raise ValueError('Truncated FOR8 header')
        length=int.from_bytes(raw[8:16],'big');a=offset+16;b=a+length
        if b>end:raise ValueError('FOR8 chunk exceeds its parent')
        nxt=b if raw[:4]==b'FOR8' else a+((length+7)//8)*8
        if nxt>end:raise ValueError('FOR8 chunk padding exceeds its parent')
        return raw[:4],raw[4:8],a,b,nxt
    def node(a,b):
        nonlocal points
        uid=None;curves={};hints={};blocked=set()
        while a<b:
            tag,flags,start,end,nxt=header(a,b)
            if tag==b'CREA' and end-start<=4096:
                stream.seek(start);payload=stream.read(end-start)
                # Observed non-DAG node: flags byte, NUL-terminated name, then
                # four little-endian UUID words (not RFC bytes_le ordering).
                if payload[:1]==b'\x80':
                    split=payload.find(b'\0',1)
                    if split>1 and len(payload)-split-1==16:
                        words=struct.unpack('<4I',payload[-16:])
                        uid=str(uuid.UUID(hex=''.join('%08x'%word for word in words)))
            # The four opaque header bytes vary across original files and are
            # not a payload type discriminator. Validate CMPD's own row marker.
            elif tag==b'FLGS' and end-start<=128:
                stream.seek(start);name,sep,tail=stream.read(end-start).partition(b'\0')
                if name in (b'srcps',b'sacps'):
                    root=name.decode('ascii')
                    if not sep or len(tail)!=5 or tail[0]!=0x2c or root in hints:
                        blocked.add(root)
                    else:hints[root]=int.from_bytes(tail[1:],'big')
            elif tag==b'DBLE' and end-start<=1048576:
                stream.seek(start);name=stream.read(min(end-start,128)).partition(b'\0')[0]
                match=re.match(rb'(srcps|sacps)\[',name)
                if match:blocked.add(match[1].decode('ascii'))
            elif tag==b'CMPD':
                stream.seek(start)
                payload=stream.read(end-start if end-start<=1048576 else 128)
                decoded=decode_curve(payload) if end-start<=1048576 else None
                if decoded:
                    root,rows=decoded;target=curves.setdefault(root,{})
                    points+=len(set(rows)-set(target))
                    if points>131072:raise ValueError('Binary brush control-point budget exceeded')
                    if set(rows)&set(target):raise ValueError('Overlapping binary brush control rows')
                    target.update(rows)
                else:
                    match=re.match(rb'(srcps|sacps)\[',payload.partition(b'\0')[0])
                    if match:blocked.add(match[1].decode('ascii'))
            a=nxt
        curves={root:rows for root,rows in curves.items() if root not in blocked and len(rows)==hints.get(root)}
        if uid and curves:
            if uid in result:raise ValueError('Ambiguous duplicate binary brush UUID')
            if len(result)>=4096:raise ValueError('Binary brush node budget exceeded')
            result[uid]=curves
    def walk(a,b,depth):
        if depth>32:raise ValueError('Maya Binary group depth exceeded')
        while a<b:
            tag,flags,start,end,nxt=header(a,b)
            if tag==b'FOR8':
                if end-start<4:raise ValueError('Missing FOR8 group type')
                stream.seek(start);kind=stream.read(4)
                if kind==BRUSH_DETAIL_TYPE:node(start+4,end)
                else:walk(start+4,end,depth+1)
            a=nxt
    if size<20:raise ValueError('Truncated Maya Binary file')
    stream.seek(0);root=stream.read(20)
    if root[:4]!=b'FOR8' or root[16:20]!=b'Maya' or int.from_bytes(root[8:16],'big')+16!=size:
        raise ValueError('Only the verified Maya FOR8 layout is supported')
    walk(20,size,0)
    return result


@lru_cache(maxsize=2)
def _read(path,size,mtime):
    with Path(path).open('rb') as stream:result=parse_profiles(stream,size)
    info=Path(path).stat()
    if (info.st_size,info.st_mtime_ns)!=(size,mtime):
        raise ValueError('Binary source changed while reading brush snapshot')
    return result


def read_profiles(path):
    path=Path(path)
    if path.suffix.lower()!='.mb':return {}
    info=path.stat()
    return _read(str(path.resolve()),info.st_size,info.st_mtime_ns)
