"""Differential coverage for ordered intersection batches and CPU filtering."""
import unittest
import numpy as np
from reatoon import renderer,intersections
from reatoon.accelerator import enable
enable()

class RenderOptimizationTests(unittest.TestCase):
    def test_box_filter_matches_numpy_for_every_supersample(self):
        from reatoon._image_kernel import down_float32
        rng=np.random.default_rng(197)
        for ss in (2,3,4):
            image=rng.random((30*ss,40*ss,4),dtype=np.float32)
            expected=image.reshape(30,ss,40,ss,4).mean(axis=(1,3))
            np.testing.assert_array_equal(down_float32(image,ss),expected)

    def test_ordered_batches_keep_multicolor_target_priority_and_fallback(self):
        rng=np.random.default_rng(22)
        meshes=[]
        for i in range(3):
            verts=rng.normal(size=(18,3))
            tris=np.arange(18).reshape(-1,3)
            meshes.append(dict(name=str(i),vertices=verts,triangles=tris,faces=tris,triangle_faces=np.arange(6),
                line_passes=[dict(line='a',priority=0,face_line_sets=['r','b',None,'b','r','b']),
                             dict(line='z',priority=1,face_line_sets=['b','r','b',None,'r',None])]))
        scene=dict(meshes=meshes,camera=dict(position=[0,0,5],target=[0,0,0]),
                   line_sets=dict(r=dict(line_color=[1,0,0]),b=dict(line_color=[0,0,1])))
        settings=dict(intersections=True,self_intersections=True,wireframe=True,width=64,height=64)
        reference=renderer.world_line_segments(scene,settings)['segments']
        packed=renderer.world_line_segments(scene,settings,packed=True)['segments']
        actual=list(packed)
        self.assertEqual(len(reference),len(actual))
        for a,b in zip(reference,actual):
            for key in ('a','b'):np.testing.assert_array_equal(a[key],b[key])
            for key in ('mesh','features','settings','line'):self.assertEqual(a[key],b[key])
        # Unsupported segment styles use the same lazy sequence for full CPU
        # fallback; collected vectors must preserve intersection feature names.
        from reatoon.cpu_segments import render_segments
        camera=renderer._camera(scene['camera'],64,64)
        images=[];results=[]
        for lines in (reference,packed):
            layer=np.zeros((64,64,4),np.float32)
            results.append(render_segments(lines,camera,np.full((64,64),np.inf),np.zeros((64,64,3)),layer,layer.copy(),1))
            images.append(layer)
        np.testing.assert_array_equal(images[0],images[1]);self.assertEqual(results[0],results[1])

    def test_batches_allow_implicit_fan_triangulation(self):
        meshes=[dict(name='a',vertices=[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],faces=[[0,1,2,3]]),
                dict(name='b',vertices=[[0,-2,-1],[0,2,-1],[0,2,1],[0,-2,1]],faces=[[0,1,2,3]])]
        for mesh in meshes:mesh['line_passes']=[dict(line='a',priority=0,face_line_sets=['r'])]
        scene=dict(meshes=meshes,line_sets=dict(r={}))
        a=renderer.world_line_segments(scene)['segments']
        b=list(renderer.world_line_segments(scene,packed=True)['segments'])
        self.assertEqual(len(a),len(b))
        for left,right in zip(a,b):
            for field in ('a','b'):np.testing.assert_array_equal(left[field],right[field])
            self.assertEqual(left['features'],right['features'])

    def test_query_cache_obeys_masks_and_geometry_generation(self):
        rng=np.random.default_rng(11)
        meshes=[]
        for i in range(2):
            meshes.append(dict(vertices=rng.normal(size=(36,3)),triangles=np.arange(36).reshape(-1,3),
                               triangle_faces=np.arange(12),_render_geometry={}))
        def query(mask):
            return list(intersections.find_intersections(meshes,self_intersections=True,merge_segments=False,
                        triangle_masks=[mask,mask],array_output=True))
        def points(rows):return np.asarray([[*r['a'],*r['b']] for r in rows])
        full=query(np.ones(12,bool));self.assertGreater(len(full),0)
        self.assertEqual(query(np.zeros(12,bool)),[])
        np.testing.assert_array_equal(points(full),points(query(np.ones(12,bool))))
        meshes[1]['vertices']+=100;meshes[1]['_render_geometry']={}
        cached=query(np.ones(12,bool))
        intersections.clear_query_cache()
        fresh=query(np.ones(12,bool))
        np.testing.assert_array_equal(points(cached),points(fresh))

if __name__=='__main__':unittest.main()
