"""Atomic user-owned shape/brush library, outside the installed package."""
import json,math,os,tempfile,uuid,shutil
from pathlib import Path

SHAPE={'line_image','line_pattern','pattern_period','pattern_amplitude','dash_length','dash_gap'}
BRUSH={'brush_image','brush_stamp_spacing','brush_preset','brush_roughness','brush_density','brush_width_scale'}
RANGES=dict(brush_stamp_spacing=(2,10000),line_pattern=(0,7),pattern_period=(2,10000),pattern_amplitude=(0,1000),dash_length=(0,10000),dash_gap=(-1,10000),brush_preset=(0,4),brush_roughness=(0,3),brush_density=(0,1),brush_width_scale=(.1,3))

def path():
    from maya import cmds
    return Path(cmds.internalVar(userAppDir=True))/'ReaPencil/presets/strokes.json'

def settings(kind,values):
    keys=SHAPE if kind=='shape' else BRUSH if kind=='brush' else None
    if keys is None or not isinstance(values,dict) or set(values)-keys:raise ValueError('Invalid preset settings')
    result={}
    for key,value in values.items():
        if key in ('line_image','brush_image'):
            from .png_pattern import validate
            result[key]=validate(value);continue
        a,b=RANGES[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not a<=value<=b:raise ValueError('Invalid preset value: '+key)
        if key in ('line_pattern','brush_preset') and int(value)!=value:raise ValueError('Preset type must be an integer')
        result[key]=value
    if ('line_pattern' if kind=='shape' else 'brush_preset') not in result:raise ValueError('Missing preset type')
    if kind=='shape' and result.get('line_pattern')==7 and not result.get('line_image'):raise ValueError('Import a PNG line pattern before saving')
    if kind=='brush' and result.get('brush_preset')==4 and not result.get('brush_image'):raise ValueError('Import a PNG brush before saving')
    return result

def load(destination=None):
    destination=Path(destination) if destination is not None else path()
    if not destination.exists():return dict(format='reapencil-stroke-library',version=1,items=[])
    value=json.loads(destination.read_text(encoding='utf8'))
    if not isinstance(value,dict) or value.get('format')!='reapencil-stroke-library' or value.get('version')!=1 or not isinstance(value.get('items'),list):raise ValueError('Unsupported preset library; original file was kept')
    seen=set()
    for item in value['items']:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or item['id'] in seen or not isinstance(item.get('name'),str):raise ValueError('Invalid preset library entry')
        settings(item['kind'],item['settings']);seen.add(item['id'])
    return value

def _write(value,destination=None):
    destination=Path(destination) if destination is not None else path();destination.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='strokes_',suffix='.pending',dir=str(destination.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
        if destination.exists():shutil.copy2(destination,destination.with_suffix('.backup.json'))
        os.replace(name,destination)
    finally:
        if os.path.exists(name):os.remove(name)

def save(kind,name,values,identity=None,destination=None):
    name=str(name).strip()
    if not name or len(name)>80 or any(c in name for c in '\r\n'):raise ValueError('Use a preset name of1–80 characters')
    data=load(destination);item=dict(id=identity or uuid.uuid4().hex,kind=kind,name=name,settings=settings(kind,values))
    previous=next((i for i in data['items'] if i['id']==item['id']),None)
    if previous is not None and previous['kind']!=kind:raise ValueError('Cannot change a preset category')
    data['items']=[i for i in data['items'] if i['id']!=item['id']]+[item];_write(data,destination);return item

def remove(identity,destination=None):
    data=load(destination);remaining=[i for i in data['items'] if i['id']!=identity]
    if len(remaining)==len(data['items']):return False
    data['items']=remaining;_write(data,destination);return True
