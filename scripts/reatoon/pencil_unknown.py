"""Read saved Pencil attributes from Maya unknown nodes without its runtime.

Unknown nodes can store names such as ``lnd[1].eolo`` as a literal generic
attribute. MEL plug-path parsing cannot address it; the attribute MObject can.
Only known Pencil classes are interpreted. Source nodes are never changed.
"""
import re
from maya import cmds
from maya.api import OpenMaya as om
from .pencil_schema import SCHEMA,REFERENCE_VERSION

def kind(node):
    value=cmds.nodeType(node)
    if value in ('unknown','unknownDag','unknownTransform'):
        try:return cmds.unknownNode(node,query=True,realClassName=True)
        except RuntimeError:return value
    return value

def is_unknown(node):
    return cmds.nodeType(node) in ('unknown','unknownDag','unknownTransform') and kind(node) in SCHEMA


def saved_profile_points(node,prefix):
    """Saved-file snapshot fallback, never an evaluation of source MEL."""
    if not is_unknown(node) or kind(node)!='PencilBrushDetail':return None
    if cmds.listConnections(node,source=True,destination=False):return None
    path=cmds.file(query=True,sceneName=True)
    if not path:return None
    from pathlib import Path
    suffix=Path(path).suffix.lower()
    if suffix=='.ma':from .ascii_brush_profiles import read_profiles
    elif suffix=='.mb':from .binary_brush_profiles import read_profiles
    else:return None
    try:
        uid=(cmds.ls(node,uuid=True) or [''])[0].lower()
        rows=read_profiles(path).get(uid,{}).get({'sr':'srcps','sa':'sacps'}[prefix])
    except (OSError,ValueError):return None
    if not rows:return None
    return [list(row) for _,row in sorted(rows.items())]


def saved_profile(node,prefix):
    rows=saved_profile_points(node,prefix)
    return None if rows is None else [(row[0],row[3],row[4]) for row in rows]


def saved_ascii_profile(node,prefix):
    """Compatibility entry for existing ASCII-specific diagnostics."""
    if not cmds.file(query=True,sceneName=True).lower().endswith('.ma'):return None
    return saved_profile(node,prefix)

class Reader:
    def __init__(self,node):
        self.node=node;self.kind=kind(node);self.schema=SCHEMA.get(self.kind,{})
        selection=om.MSelectionList();selection.add(node)
        self.fn=om.MFnDependencyNode(selection.getDependNode(0))
        self.attrs={}
        for i in range(self.fn.attributeCount()):
            attr=self.fn.attribute(i);fn=om.MFnAttribute(attr)
            self.attrs[fn.name]=attr;self.attrs[fn.shortName]=attr

    def alias(self,path):
        aliases=self.schema.get('aliases',{})
        return re.sub(r'[A-Za-z_]\w*',lambda m:aliases.get(m[0],m[0]),path)

    def plug(self,path):
        for text in (path,self.alias(path)):
            if text in self.attrs:return self.fn.findPlug(self.attrs[text],False)
            match=re.fullmatch(r'([^\[.]+)\[(\d+)\]',text)
            if match and match[1] in self.attrs:
                p=self.fn.findPlug(self.attrs[match[1]],False)
                if p.isArray and int(match[2]) in p.getExistingArrayAttributeIndices():
                    return p.elementByLogicalIndex(int(match[2]))
        return None

    def get(self,path,default=None):
        p=self.plug(path)
        if p is not None:
            try:
                value=p.asMObject()
                if value.hasFn(om.MFn.kNumericData):
                    result=om.MFnNumericData(value).getData()
                    return list(result) if isinstance(result,tuple) else result
                if value.hasFn(om.MFn.kStringData):return om.MFnStringData(value).string()
            except (RuntimeError,TypeError):pass
            if p.isCompound:
                try:return [p.child(i).asDouble() for i in range(p.numChildren())]
                except RuntimeError:pass
            for method in ('asDouble','asString'):
                try:return getattr(p,method)()
                except RuntimeError:pass
        # Binary Maya saves numeric compounds as separate child attributes.
        # Resolve their public names via the recorded schema, including short
        # aliases such as gra[2].gracvr. Never replace a saved color with grey.
        prefix,sep,leaf=path.rpartition('.')
        children=self.schema.get('children',{}).get(leaf,[])
        paths=[prefix+sep+child for child in children]
        if paths and any(self.plug(child) is not None for child in paths):
            return [self.get(child,0.) for child in paths]
        return self.schema.get('defaults',{}).get(path,default)

    def indices(self,path):
        values=set();p=self.plug(path)
        if p is not None and p.isArray:
            values.update(p.getExistingArrayAttributeIndices())
        for prefix in (path,self.alias(path)):
            pattern=re.compile('^'+re.escape(prefix)+r'\[(\d+)\]')
            for name in self.attrs:
                match=pattern.match(name)
                if match:values.add(int(match[1]))
        return sorted(values)

    def incoming(self,path):
        aliases=(path,self.alias(path));result=[]
        # Inspect real DG links; do not depend on MEL interpreting dotted names.
        for plug in self.fn.getConnections():
            local=plug.name().split('.',1)[1]
            if not any(local==a or local.startswith(a+'[') for a in aliases):continue
            for source in plug.connectedTo(True,False):
                result.append(om.MFnDependencyNode(source.node()).name())
        return list(dict.fromkeys(result))
