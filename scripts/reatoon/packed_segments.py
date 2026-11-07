"""Internal CPU batches; preserve the reference segment iteration order."""
from bisect import bisect_right
import numpy as np


class PackedSegments:
    def __init__(self):
        self.parts=[]
        self.tail=[]
        self.count=0
        self.intersection_count=0
        self.ends=[]

    def __len__(self):return self.count

    def append(self,segment):
        self.tail.append(segment)
        self.count+=1
        self.intersection_count+=int('intersection' in segment['features'])

    def _flush(self):
        if self.tail:
            self.parts.append(dict(records=self.tail,count=len(self.tail)))
            self.tail=[]

    def add_edges(self,mesh,index,prepared,indices,flags,style,line):
        self._flush()
        if not len(indices):return
        points=prepared['vertices'][prepared['pairs'][indices]]
        self.parts.append(dict(points=points,flags=flags[indices],settings=style,
            mesh=mesh.get('name','mesh'),mesh_index=index,line=line,count=len(indices)))
        if style.get('connect_collinear_dashes',False):
            self.parts[-1]['vertex_ids']=prepared['pairs'][indices]
        self.count+=len(indices)

    def add_intersections(self,mesh,index,rows,style,line):
        self._flush()
        if not len(rows):return
        self.parts.append(dict(points=rows[:,:6].reshape(-1,2,3),flags=np.full(len(rows),128,np.uint8),
            settings=style,mesh=mesh.get('name','mesh'),mesh_index=index,line=line,count=len(rows),intersection=True))
        self.count+=len(rows);self.intersection_count+=len(rows)

    def styles(self):
        self._flush()
        result={}
        for part in self.parts:
            if 'records' in part:
                for record in part['records']:result[id(record['settings'])]=record['settings']
            else:result[id(part['settings'])]=part['settings']
        return result.values()

    def arrays(self):
        self._flush()
        points=np.empty((self.count,2,3),np.float64)
        widths=np.empty(self.count,np.float64);biases=np.empty(self.count,np.float64)
        colors=np.empty((self.count,3),np.float64)
        only=np.empty(self.count,np.bool_);enabled=np.empty(self.count,np.bool_)
        start=0;self.ends=[]
        for part in self.parts:
            end=start+part['count'];sl=slice(start,end)
            if 'records' in part:
                records=part['records']
                points[sl]=np.asarray([[s['a'],s['b']] for s in records])
                widths[sl]=[max(0.,float(s['settings']['line_width'])) for s in records]
                biases[sl]=[float(s['settings']['depth_bias']) for s in records]
                colors[sl]=[s['settings']['line_color'] for s in records]
                only[sl]=[s['settings'].get('output_to_elements_only',False) for s in records]
                enabled[sl]=[bool(s['features']) for s in records]
            else:
                style=part['settings'];points[sl]=part['points']
                widths[sl]=max(0.,float(style['line_width']));biases[sl]=float(style['depth_bias'])
                colors[sl]=style['line_color'];only[sl]=style.get('output_to_elements_only',False)
                enabled[sl]=part['flags']!=0
            start=end;self.ends.append(end)
        np.clip(colors,0,1,out=colors)
        return points,widths,biases,colors,only,enabled

    def _record(self,part,index):
        if 'records' in part:return part['records'][index]
        from .renderer import EDGE_FEATURES
        result=dict(a=part['points'][index,0].tolist(),b=part['points'][index,1].tolist(),
            features=['intersection'] if part.get('intersection') else [name for bit,name in enumerate(EDGE_FEATURES) if int(part['flags'][index])&(1<<bit)],
            mesh_index=part['mesh_index'],mesh=part['mesh'],settings=part['settings'],line=part['line'])
        if 'vertex_ids' in part:result['_vertex_ids']=tuple(int(v) for v in part['vertex_ids'][index])
        return result

    def __getitem__(self,index):
        part_index=bisect_right(self.ends,index)
        return self._record(self.parts[part_index],index-(self.ends[part_index-1] if part_index else 0))

    def __iter__(self):
        self._flush()
        for part in self.parts:
            for index in range(part['count']):yield self._record(part,index)
