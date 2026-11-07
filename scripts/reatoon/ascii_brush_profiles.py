"""Read only numeric brush-control arrays lost by Maya's unknown ASCII loader.

No MEL evaluation, scene mutation or script execution. Records are matched by
original node UUID, and only exact finite seven-number control rows are admitted.
"""
from functools import lru_cache
import math
from pathlib import Path
import re


def commands(lines):
    buffer=[];quoted=False;escaped=False;discard=False;block=False
    for line in lines:
        i=0
        while i<len(line):
            c=line[i]
            if block:
                if line[i:i+2]=='*/':block=False;i+=2
                else:i+=1
                continue
            if not quoted and line[i:i+2]=='/*':
                if not discard:buffer.append(' ')
                block=True;i+=2;continue
            if not quoted and line[i:i+2]=='//':break
            if quoted:
                if escaped:escaped=False
                elif c=='\\':escaped=True
                elif c=='"':quoted=False
            elif c=='"':quoted=True
            elif c==';':
                if not discard:yield ''.join(buffer)
                buffer=[];discard=False;i+=1;continue
            if not discard:
                buffer.append(c)
                if len(buffer)>1048576:buffer=[];discard=True
            i+=1
        if not discard:buffer.append('\n')


def parse_profiles(lines):
    result={};current=None;uid=None;curves={};total_points=0
    def save():
        if current=='PencilBrushDetail' and uid and curves:
            if uid.lower() not in result and len(result)>=4096:
                raise ValueError('ASCII brush profile node budget exceeded')
            result[uid.lower()]={key:dict(value) for key,value in curves.items()}
    for command in commands(lines):
        text=command.strip()
        created=re.match(r'^createNode\s+(\w+)\b',text)
        if created:
            save();current=created[1];uid=None;curves={};continue
        if current!='PencilBrushDetail':continue
        renamed=re.fullmatch(r'rename\s+-uid\s+"([A-Fa-f0-9-]+)"',text)
        if renamed:uid=renamed[1];continue
        matched=re.fullmatch(r'setAttr\s+(?:-s\s+\d+\s+)?"\.(srcps|sacps|srBezierControlPoints|saBezierControlPoints)\[(\d+)(?::(\d+))?\]"\s+(.+)',text,re.S)
        if not matched:continue
        start,end=int(matched[2]),int(matched[3] or matched[2])
        if not 0<=start<=end<=8191:continue
        try:values=[float(token) for token in matched[4].split()]
        except ValueError:continue
        if len(values)!=(end-start+1)*7 or not all(math.isfinite(v) for v in values):continue
        root={'srBezierControlPoints':'srcps','saBezierControlPoints':'sacps'}.get(matched[1],matched[1])
        rows=curves.setdefault(root,{})
        for i in range(start,end+1):
            if i not in rows:total_points+=1
            if total_points>131072:raise ValueError('ASCII brush profile control-point budget exceeded')
            rows[i]=tuple(values[(i-start)*7:(i-start+1)*7])
    save()
    return result


@lru_cache(maxsize=2)
def _read(path,size,mtime):
    with Path(path).open(encoding='utf8',errors='replace') as stream:return parse_profiles(stream)


def read_profiles(path):
    path=Path(path)
    if path.suffix.lower()!='.ma':return {}
    info=path.stat()
    return _read(str(path.resolve()),info.st_size,info.st_mtime_ns)
