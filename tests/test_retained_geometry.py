import unittest
import numpy as np
from reatoon.retained_geometry import candidates,camera_mask
from reatoon.gpu_geometry import GPUScene

class RetainedGeometryTests(unittest.TestCase):
    def test_incremental_paged_contacts_match_full_recompute(self):
        import copy
        from reatoon.gpu_paged import PagedGPUScene
        meshes=[]
        for x in (0,5,10):
            meshes.extend([dict(vertices=np.array([[-2,-2,0],[2,-2,0],[0,2,0]],float)+[x,0,0],faces=[[0,1,2]],triangles=[[0,1,2]],triangle_faces=[0]),
                           dict(vertices=np.array([[0,-1,-1],[0,1,-1],[0,0,1]],float)+[x,0,0],faces=[[0,1,2]],triangles=[[0,1,2]],triangle_faces=[0])])
        gpu=PagedGPUScene(copy.deepcopy(meshes),retain_planes=True)
        styles=[dict(intersections=True)];faces=[np.zeros(1,np.int32) for _ in meshes]
        def canonical(p):return sorted(tuple(sorted(tuple(np.round(v[:3],8)) for v in pair)) for pair in p.reshape(-1,2,4))
        try:
            gpu.configure_face_styles(faces,1);original=gpu.intersections(styles)[0];self.assertEqual(len(original),6)
            for step in (6.,1.,0.):
                changed=copy.deepcopy(meshes);changed[1]['vertices'][:,0]+=step
                gpu.update(np.concatenate([m['vertices'] for m in changed]),changed_meshes=[1]);gpu.configure_face_styles(faces,1)
                actual=gpu.intersections(styles)[0]
                fresh=PagedGPUScene(changed,retain_planes=True)
                try:
                    fresh.configure_face_styles(faces,1);expected=fresh.intersections(styles)[0]
                    self.assertEqual(canonical(actual),canonical(expected))
                finally:fresh.close()
        finally:gpu.close()

    def test_maya_degenerate_polygon_with_no_triangles(self):
        mesh=dict(vertices=[[0,0,0],[1,0,0],[0,1,0],[2,0,0]],faces=[[0,1,2],[0,3,1]],
                  triangles=[[0,1,2]],triangle_faces=[0])
        styles=[dict(outline=True,open_edges=True)];faces=np.zeros(2,np.int32)
        gpu=GPUScene([mesh])
        try:
            gpu.configure_face_styles([faces],1);data=candidates(mesh,faces,styles)
            for z in (-5,5):
                camera=dict(position=[0,0,z],target=[0,0,0]);points,_=gpu.edges(styles,camera)
                actual=data['points'][camera_mask(data,camera)]
                def keys(p):return sorted(tuple(sorted(tuple(x) for x in row)) for row in p.reshape(-1,2,3))
                self.assertEqual(keys(points[:,:3]),keys(actual))
        finally:gpu.close()
    def test_retained_intersection_planes_survive_paging_and_deformation(self):
        from reatoon.gpu_paged import PagedGPUScene
        meshes=[dict(vertices=[[-2,-2,0],[2,-2,0],[0,2,0]],faces=[[0,1,2]],triangles=[[0,1,2]],triangle_faces=[0]),
                dict(vertices=[[0,-1,-1],[0,1,-1],[0,0,1]],faces=[[0,1,2]],triangles=[[0,1,2]],triangle_faces=[0])]
        for target in (1,100):
            import copy
            gpu=PagedGPUScene(copy.deepcopy(meshes),page_triangle_target=target,retain_planes=True)
            try:
                gpu.configure_face_styles([np.zeros(1,np.int32),np.zeros(1,np.int32)],1)
                styles=[dict(intersections=True)]
                p,o,_=gpu.intersections(styles)
                self.assertEqual(len(o),1);self.assertEqual(gpu.cross_planes.shape,(1,2,4))
                self.assertTrue(np.allclose(np.linalg.norm(gpu.cross_planes[:,:,:3],axis=2),1))
                self.assertEqual(set(gpu.cross_planes[:,:,3].astype(int).ravel()),{0,1})
                direction=p[1,:3]-p[0,:3]
                self.assertTrue(np.allclose(gpu.cross_planes[0,:,:3]@direction,0))
                for page in gpu.pages:
                    if page.gpu:page.freeze()
                gpu._resident.clear();gpu.cross_cache=None
                points=np.concatenate([m['vertices'] for m in meshes]);points[3:,0]=5
                gpu.update(points,changed_meshes=[1]);p,o,_=gpu.intersections(styles)
                self.assertEqual(len(o),0)
            finally:gpu.close()

    def test_current_camera_matches_gpu_for_fold_and_style_changes(self):
        mesh=dict(vertices=[[-1,-1,0],[1,-1,0],[1,1,.6],[-1,1,0],[0,0,-2]],
                  faces=[[0,1,2,3],[0,4,1],[1,4,2],[2,4,3],[3,4,0]],
                  triangles=[[0,1,2],[0,2,3],[0,4,1],[1,4,2],[2,4,3],[3,4,0]],
                  triangle_faces=[0,0,1,2,3,4],material_ids=[0,0,1,1,0],hard_edges=[[0,1]])
        gpu=GPUScene([mesh])
        def canonical(points):
            return sorted(tuple(sorted(tuple(np.round(v,8)) for v in pair)) for pair in np.asarray(points).reshape(-1,2,3))
        try:
            faces=np.array([0,0,1,1,-1],np.int32)
            for settings in (dict(outline=True),dict(outline=True,open_edges=True,hard_edges=True),
                             dict(outline=True,crease=True,crease_angle=20,material_boundaries=True),dict(wireframe=True)):
                styles=[settings,dict(settings,crease_angle=150)]
                gpu.configure_face_styles([faces],2)
                data=candidates(mesh,faces,styles)
                for projection in ('perspective','orthographic'):
                    for i in range(17):
                        angle=i*.37;camera=dict(position=[6*np.cos(angle),3*np.sin(angle*.7),6*np.sin(angle)],target=[0,0,-.2],projection=projection)
                        expected,_=gpu.edges(styles,camera)
                        actual=data['points'][camera_mask(data,camera)]
                        self.assertEqual(canonical(expected[:,:3]),canonical(actual))
        finally:gpu.close()

    def test_explicit_edges_and_non_manifold_are_not_lost(self):
        mesh=dict(vertices=[[0,0,0],[1,0,0],[0,1,0]],faces=[[0,1,2]],triangles=[[0,1,2]],triangle_faces=[0])
        gpu=GPUScene([mesh]);styles=[dict(selected_edges=True)]
        try:
            selected={0:[[0,1]]};faces=np.array([-1],np.int32)
            gpu.configure_face_styles([faces],1,[selected]);data=candidates(mesh,faces,styles,selected)
            self.assertEqual(len(data['points']),1)
            mesh['faces']*=3;mesh['triangles']*=3;mesh['triangle_faces']=[0,1,2]
            with self.assertRaisesRegex(ValueError,'two incident'):candidates(mesh,[0,0,0],styles)
        finally:gpu.close()

if __name__=='__main__':unittest.main()
