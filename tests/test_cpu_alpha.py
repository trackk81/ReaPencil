import unittest
from types import SimpleNamespace
import numpy as np
from reatoon.cpu_alpha import Region,Data,line_intervals,trim_intersections
from reatoon.cpu_depth import rasterize_mesh
from reatoon import renderer,cpu_visibility
from reatoon.intersections import IntersectionBatches


def square(a,b):return np.array([[a,a],[b,a],[b,b],[a,b]],float)


def card(region,z=2.):
    vertices=np.array([[-1,-1,z],[1,-1,z],[1,1,z],[-1,1,z]])
    tri=np.array([[0,1,2],[0,2,3]],np.int64);uv=np.array([[0,0],[1,0],[1,1],[0,1]])[tri].astype(float)
    return dict(vertices=vertices,triangles=tri,faces=tri,triangle_faces=np.arange(2),_cpu_alpha=Data([0,1],uv,[0,0],[False,False],[region]))


class CPUAlphaTests(unittest.TestCase):
    def test_native_acceleration_grid_matches_reference(self):
        from reatoon.native_cpu import alpha_grid
        t=np.linspace(0,2*np.pi,300,endpoint=False);radius=.36+.08*np.sin(t*11)
        r=Region(SimpleNamespace(loops=[np.column_stack((.5+radius*np.cos(t),.5+radius*np.sin(t))),square(.3,.7),square(.45,.55)]))
        size=256;expected=np.zeros((size,size),np.uint8);centers=(np.arange(size)+.5)/size
        for y in range(size):
            yy=(y+.5)/size;b=min(511,int(yy*512));e=r.edges[r.ids[r.starts[b]:r.starts[b+1]]]
            crossing=(e[:,0,1]>yy)!=(e[:,1,1]>yy);p,q=e[crossing,0],e[crossing,1]
            x=np.sort(p[:,0]+(yy-p[:,1])*(q[:,0]-p[:,0])/(q[:,1]-p[:,1]))
            expected[y]=np.searchsorted(x,centers,side='right')%2
        for e in r.edges:
            lo=np.maximum(0,np.floor(e.min(axis=0)*size-1e-8).astype(int));hi=np.minimum(size-1,np.floor(e.max(axis=0)*size+1e-8).astype(int))
            expected[lo[1]:hi[1]+1,lo[0]:hi[0]+1]=2
        np.testing.assert_array_equal(alpha_grid(r.native,size),expected)

    def test_bulk_edge_clip_preserves_partial_uv_faces_and_edge_order(self):
        from reatoon.cpu_alpha import clip_edges
        from reatoon.packed_segments import PackedSegments
        from reatoon.native_cpu import edges
        r=Region(SimpleNamespace(loops=[square(.1,.9),square(.3,.7)]))
        rng=np.random.default_rng(222);vertices=[];tris=[];uv=[]
        for i in range(80):
            base=len(vertices);vertices.extend((np.array([[-1,-1,2],[1,-1,2],[1,1,2],[-1,1,2]])+[i*3,0,0]).tolist())
            tris.extend([[base,base+1,base+2],[base,base+2,base+3]])
            uv.extend(rng.uniform(-.2,1.2,(2,3,2)))
        vertices=np.array(vertices);tri=np.array(tris,np.int64);lookup=np.arange(len(tri),dtype=np.int32);lookup[::7]=-1
        m=dict(name='bulk',vertices=vertices,triangles=tri,triangle_faces=np.arange(len(tri)),
            _cpu_alpha=Data(lookup,uv,np.zeros(len(tri),np.int32),np.ones(len(tri),bool),[r]))
        prepared=edges(vertices,tri.ravel(),np.full(len(tri),3),np.zeros(len(tri),np.int64))
        ids=np.arange(len(prepared['pairs']))[::-1];flags=np.where(ids%3,2,4).astype(np.uint8);style=dict(renderer.DEFAULTS)
        outputs=[]
        for limit in (127,len(ids)):
            parts=PackedSegments();unmasked=[]
            for start in range(0,len(ids),limit):unmasked.extend(clip_edges(m,prepared,ids[start:start+limit],flags,style,'line',0,parts).tolist())
            points=np.concatenate([p['points'] for p in parts.parts]);bits=np.concatenate([p['flags'] for p in parts.parts]);outputs.append((unmasked,points,bits))
        self.assertEqual(outputs[0][0],outputs[1][0]);np.testing.assert_allclose(outputs[0][1],outputs[1][1],rtol=0,atol=1e-12)
        np.testing.assert_array_equal(outputs[0][2],outputs[1][2])

    def test_contiguous_template_slices_match_gather_arithmetic(self):
        from reatoon.cpu_alpha import TemplatePoints
        rng=np.random.default_rng(222);source=rng.normal(size=(17,3,3));bary=rng.random((93,2,3));bary/=bary.sum(axis=2,keepdims=True)
        lazy=TemplatePoints(source,bary)
        for key in (slice(None),slice(3,12),slice(5,974),slice(93,975),slice(130,131),slice(0,0),slice(-12,None),slice(None,None,-3)):
            ids=np.arange(*key.indices(len(lazy)))
            expected=np.einsum('...sb,...bc->...sc',bary[ids%len(bary)],source[ids//len(bary)])
            np.testing.assert_array_equal(lazy[key],expected)
            start,stop,step=key.indices(len(lazy))
            if step==1:np.testing.assert_array_equal(np.asarray(lazy.slice_view(start,max(start,stop))),expected)

    def test_parallel_trim_matches_serial_native_intervals(self):
        import ctypes as c
        from reatoon import native_cpu
        r=Region(SimpleNamespace(loops=[square(.1,.9),square(.3,.7),square(.45,.55)]));m=card(r)['_cpu_alpha']
        rng=np.random.default_rng(222)
        uv=np.ascontiguousarray(rng.uniform(-.5,1.5,(997,2,2,2)))
        tids=np.zeros((len(uv),2),np.int64)
        m.wrap[:]=True
        ptr=c.byref(m.native)
        lib=native_cpu.library();fn=lib.rp_alpha_trim
        fn.argtypes=[c.c_void_p]*4+[c.c_int64,c.c_void_p,c.c_int64];fn.restype=c.c_int64
        count=fn(ptr,ptr,tids.ctypes.data,uv.ctypes.data,len(uv),None,0)
        expected=np.empty((count,3))
        self.assertEqual(fn(ptr,ptr,tids.ctypes.data,uv.ctypes.data,len(uv),expected.ctypes.data,count),count)
        actual=native_cpu.alpha_trim(ptr,ptr,tids,uv)
        np.testing.assert_array_equal(actual,expected)

    def test_mixed_part_batches_preserve_painter_order_and_pixels(self):
        from reatoon.packed_segments import PackedSegments
        from reatoon import cpu_segments
        cam=renderer._camera(dict(position=[0,0,0],target=[0,0,1],near=.1,far=10),96,96)
        rng=np.random.default_rng(222);s=PackedSegments();s.count=80
        for i in range(40):
            points=rng.uniform(-1,1,(2,2,3));points[:,:,2]+=3
            s.parts.append(dict(points=points,flags=np.array([1,4],np.uint8),count=2,
                settings=dict(renderer.DEFAULTS,line_width=2.3,line_color=rng.random(3).tolist()),line='a',mesh='a',mesh_index=0))
        depth=np.full((96,96),np.inf);planes=np.zeros((96,96,3));images=[];counts=[];old=cpu_segments._BATCH_SIZE
        try:
            for size in (1000,13):
                cpu_segments._BATCH_SIZE=size;image=np.zeros((96,96,4),np.float32)
                r=cpu_segments.render_segments(s,cam,depth,planes,image,None,1,collect_vectors=False)
                images.append(image);counts.append(r['visible_segments'])
        finally:cpu_segments._BATCH_SIZE=old
        np.testing.assert_array_equal(images[0],images[1]);self.assertEqual(counts[0],counts[1])

    def test_png_count_mode_matches_vectors_with_occlusion_and_elements_only(self):
        from reatoon import native_cpu
        n=10021
        rng=np.random.default_rng(222)
        points=rng.uniform(-2,2,(n,2,3));points[:,:,2]=3.
        widths=np.full(n,1.7);biases=np.zeros(n);colors=rng.random((n,3))
        only=np.arange(n)%11==0;enabled=np.ones(n,np.uint8);enabled[::17]=0
        depth=np.full((64,64),np.inf);depth[:,20:26]=1.;depth[:,40:46]=1.
        planes=np.zeros((64,64,3));planes[:,:,2]=1.
        images=[];counts=[];checks=[]
        for count_only in (False,True):
            image=np.zeros((64,64,4),np.float32);stats=np.zeros(2,np.int64)
            rows=native_cpu.segments(points,widths,biases,colors,only,enabled,depth,planes,image,
                1,False,1.,30.,.1,10.,None,np.zeros(3),np.eye(3),stats,
                raw_rows=True,count_only=count_only)
            counts.append(rows if count_only else np.count_nonzero(~only[rows[:,0].astype(np.intp)]))
            images.append(image);checks.append(stats)
        self.assertGreater(counts[0],0);self.assertEqual(counts[0],counts[1])
        np.testing.assert_array_equal(images[0],images[1]);np.testing.assert_array_equal(checks[0],checks[1])

    def test_nested_holes_and_wrap(self):
        r=Region(SimpleNamespace(loops=[square(.1,.9),square(.3,.7),square(.45,.55)]))
        self.assertEqual(r.contains([[.2,.5],[.4,.5],[.5,.5],[1.2,.5]],False).tolist(),[True,False,True,False])
        self.assertTrue(r.contains([[1.2,.5]],True)[0])
        np.testing.assert_allclose(r.intervals([[0,.5],[1,.5]],False),[[.1,.3],[.45,.55],[.7,.9]])

    def test_raster_and_exact_rays_share_hole(self):
        r=Region(SimpleNamespace(loops=[square(.1,.9),square(.3,.7)]));m=card(r)
        camera=renderer._camera(dict(position=[0,0,0],target=[0,0,1],up=[0,1,0],projection='orthographic',ortho_width=2,near=.1,far=10),64,64)
        camera.update(ortho=True,span=2)
        depth=np.full((64,64),np.inf);planes=np.zeros((64,64,3))
        rasterize_mesh(m['vertices'],m['triangles'],camera,depth,planes,alpha=m['_cpu_alpha'])
        self.assertTrue(np.isinf(depth[32,32]));self.assertAlmostEqual(depth[32,10],2.)
        ctx=cpu_visibility.prepare([m]);xy=np.array([[32.5,32.5],[10.5,32.5]])
        self.assertEqual(cpu_visibility.visible_samples(ctx,xy,np.array([3.,3.]),camera).tolist(),[True,False])

    def test_intersection_is_cut_on_both_surfaces(self):
        r=Region(SimpleNamespace(loops=[square(.1,.9),square(.3,.7)]));m=card(r)
        # A line on triangle 0, passing through the hole.
        points=np.array([[-.8,-.8,2.],[.8,-.8,2.]])
        np.testing.assert_allclose(line_intervals(m,0,points),[[0,1]],atol=1e-10)
        points=np.array([[-.5,-.5,2.],[.5,-.5,2.]])
        batches=IntersectionBatches();batches.add(0,1,np.array([[*points.ravel(),0,0]]))
        empty=Region(SimpleNamespace(loops=[]));other=card(empty)
        self.assertEqual(len(trim_intersections([m,other],batches)),0)

    def test_boundary_stays_on_original_triangle(self):
        r=Region(SimpleNamespace(loops=[square(.1,.9),square(.3,.7)]))
        b=r.boundary(np.array([[0,0],[1,0],[1,1]],float),False)
        self.assertTrue(np.all(b>=-1e-10));np.testing.assert_allclose(b.sum(axis=2),1.)
        self.assertLess(len(b),20)

    def test_collapsed_uv_still_has_opacity_crossings(self):
        r=Region(SimpleNamespace(loops=[square(.1,.9),square(.3,.7)]))
        uv=np.array([[0,.5],[1,.5],[.5,.5]])
        b=r.boundary(uv,False)
        self.assertEqual(len(b),4)
        np.testing.assert_allclose(b.sum(axis=2),1.)
        x=(b@uv)[:,:,0]
        np.testing.assert_allclose(x[:,0],x[:,1])
        np.testing.assert_allclose(np.sort(x[:,0]),[.1,.3,.7,.9])

    def test_grid_is_exact_including_clipped_perspective(self):
        loops=[np.array([[.05,.1],[.92,.27],[.73,.96],[.2,.88]]),square(.3,.7)]
        r=Region(SimpleNamespace(loops=loops));m=card(r)
        vertices=m['vertices'].copy();vertices[0,2]=.2;vertices[2,2]=4.
        cam=renderer._camera(dict(position=[0,0,0],target=[0,0,1],near=.5,far=3),160,130)
        outputs=[]
        for enabled in (True,False):
            m['_cpu_alpha'].native_masks[0].grid=r.grid.ctypes.data if enabled else None
            depth=np.full((130,160),np.inf);planes=np.zeros((130,160,3))
            rasterize_mesh(vertices,m['triangles'],cam,depth,planes,alpha=m['_cpu_alpha'])
            outputs.append((depth,planes))
        np.testing.assert_array_equal(outputs[0][0],outputs[1][0]);np.testing.assert_array_equal(outputs[0][1],outputs[1][1])

    def test_batched_crossings_match_polygon_reference(self):
        r=Region(SimpleNamespace(loops=[square(.1,.9),square(.3,.7),square(.45,.55)]));m=card(r)
        rng=np.random.default_rng(219)
        points=rng.uniform(-.95,.95,(90,2,3));points[:,:,2]=2.
        rows=np.column_stack((points.reshape(-1,6),np.zeros((len(points),2))))
        batch=IntersectionBatches();batch.add(0,1,rows)
        actual=trim_intersections([m,m],batch)
        result=np.concatenate([p[2] for p in actual.batches])[:,:6]
        expected=[]
        for p in points:
            for lo,hi in line_intervals(m,0,p):expected.append((p[0]+np.array([lo,hi])[:,None]*(p[1]-p[0])).ravel())
        np.testing.assert_allclose(result,expected,atol=1e-11)

    def test_streamed_template_pixels_match_expanded(self):
        from reatoon.cpu_alpha import TemplatePoints
        from reatoon.packed_segments import PackedSegments
        from reatoon import cpu_segments
        rng=np.random.default_rng(220);source=rng.uniform(-1,1,(25,3,3));source[:,:,2]+=4
        bary=np.array([[[1,0,0],[0,1,0]],[[0,1,0],[0,0,1]],[[0,0,1],[1,0,0]]],float)
        lazy=TemplatePoints(source,bary);expanded=np.einsum('sab,tbc->tsac',bary,source).reshape(-1,2,3)
        np.testing.assert_array_equal(lazy[:],expanded)
        cam=renderer._camera(dict(position=[0,0,0],target=[0,0,1],near=.1,far=10),100,100)
        depth=np.full((100,100),np.inf);planes=np.zeros((100,100,3));images=[];counts=[];old=cpu_segments._BATCH_SIZE;events=[]
        try:
            for size,points in ((1000,expanded),(13,lazy)):
                cpu_segments._BATCH_SIZE=size;s=PackedSegments();s.count=len(points)
                s.parts=[dict(points=points,flags=np.ones(len(points),np.uint8),count=len(points),settings=dict(renderer.DEFAULTS,line_width=1.8),line='test',mesh='test',mesh_index=0)]
                image=np.zeros((100,100,4),np.float32)
                result=cpu_segments.render_segments(s,cam,depth,planes,image,None,1,collect_vectors=False,progress=lambda *args:events.append(args))
                images.append(image);counts.append(result['visible_segments'])
        finally:cpu_segments._BATCH_SIZE=old
        np.testing.assert_array_equal(images[0],images[1]);self.assertEqual(counts[0],counts[1])
        self.assertEqual(events[-1],('strokes',len(expanded),len(expanded)))
        self.assertEqual([e[1] for e in events],sorted(e[1] for e in events))


if __name__=='__main__':unittest.main()
