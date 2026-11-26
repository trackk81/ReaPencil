import unittest
import numpy as np
from reatoon import alpha_geometry as ag,alpha_compact as ac
from test_alpha_geometry import AlphaGeometryTests

class CompactInheritedTests(AlphaGeometryTests):
    def cut(self,mask,**kwargs):
        region=ac.Region(ag.contours(mask,simplify=0))
        return ac.cut_mesh(self.vertices,self.triangles,[0,0],self.vertices[self.triangles,:2],{0:region},**kwargs)

class CompactTests(unittest.TestCase):
    def test_ring_has_no_false_internal_open_edges(self):
        y,x=np.mgrid[:128,:128];radius=np.hypot(x-63.5,y-63.5)
        loops=ag.contours(((radius>25)&(radius<54)|(radius<8)).astype(float),simplify=.25)
        vertices=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],float);tri=np.array([[0,1,2],[0,2,3]])
        cut=ac.cut_mesh(vertices,tri,[0,0],vertices[tri,:2],{0:ac.Region(loops)})
        p=cut['vertices'];t=cut['triangles'];edges=np.sort(np.concatenate((t[:,[0,1]],t[:,[1,2]],t[:,[2,0]])),axis=1)
        e,count=np.unique(edges,axis=0,return_counts=True);boundary=e[count==1]
        expected=sum(np.linalg.norm(p-np.roll(p,-1,axis=0),axis=1).sum() for p in loops)
        self.assertAlmostEqual(np.linalg.norm(p[boundary[:,1]]-p[boundary[:,0]],axis=1).sum(),expected,places=9)

    def test_authored_edge_descendants_match_reference(self):
        vertices=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],float);tri=np.array([[0,1,2],[0,2,3]])
        mask=np.ones((32,32));mask[8:24,8:24]=0
        cut=ac.cut_mesh(vertices,tri,[0,0],vertices[tri,:2],{0:ac.Region(ag.contours(mask,simplify=0))})
        ids=cut['bind_ids'];weights=cut['bind_weights'];expected={}
        for face in cut['faces']:
            for a,b in zip(face,face[1:]+face[:1]):
                support={int(ids[v,j]) for v in (a,b) for j,w in enumerate(weights[v]) if abs(w)>1e-9}
                if len(support)==2:expected.setdefault(tuple(sorted(support)),set()).add(tuple(sorted((a,b))))
        self.assertEqual(ac.source_edge_map(cut['triangles'],ids,weights),expected)

    def test_area_matches_reference_and_uses_fewer_triangles(self):
        rng=np.random.default_rng(218)
        mask=np.zeros((32,32));mask[2:30,2:30]=1;mask[6:13,5:25]=0;mask[18:25,5:25]=0
        loops=ag.contours(mask,simplify=.25);region=ac.Region(loops)
        cells=ag.filled_cells(loops)
        for uv in (np.array([[0,0],[1,0],[0,1.]]),np.array([[1,0],[0,0],[0,1.]]),
                   np.array([[-.3,-.1],[1.3,.1],[.2,1.2]]), *rng.uniform(.1,.9,(12,3,2))):
            old=ag.triangulate_uv(uv,cells,True)
            old_area=sum(abs(ag._cross(p[:,1:],np.roll(p[:,1:],-1,axis=0)).sum())*.5 for p in old)
            new=region.clip(uv,True)
            area=np.abs(ag._cross(new[:,1,1:]-new[:,0,1:],new[:,2,1:]-new[:,0,1:])).sum()*.5
            self.assertAlmostEqual(old_area,area,places=8)
            self.assertLessEqual(len(new),sum(1 if len(p)==3 else len(p) for p in old))

    def test_mirrors_mixed_materials_deformation_and_budget(self):
        vertices=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],float);tri=np.array([[0,1,2],[0,2,3]])
        mask=np.zeros((16,16));mask[3:12,3:12]=1;region=ac.Region(ag.contours(mask,simplify=0))
        for mirror in (False,True):
            uv=vertices[tri,:2].copy()
            if mirror:uv[:,:,0]=1-uv[:,:,0]
            cut=ac.cut_mesh(vertices,tri,[0,1],uv,{0:region})
            self.assertTrue(np.allclose(cut['vertices'],np.einsum('ij,ijk->ik',cut['bind_weights'],vertices[cut['bind_ids']])))
            p=cut['vertices'][cut['triangles']]
            self.assertTrue(np.all(np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])[:,2]>0))
            self.assertIn(1,cut['source_faces'])
            with self.assertRaises(ValueError):ac.cut_mesh(vertices,tri,[0,1],uv,{0:region},triangle_budget=1)

if __name__=='__main__':unittest.main()
