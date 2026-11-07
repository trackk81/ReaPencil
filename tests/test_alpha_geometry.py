import unittest
import numpy as np
from reatoon import alpha_geometry as ag

class AlphaGeometryTests(unittest.TestCase):
    def setUp(self):
        self.vertices=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],float)
        self.triangles=np.array([[0,1,2],[0,2,3]])

    def cut(self,mask,**kwargs):
        cells=ag.filled_cells(ag.contours(mask,simplify=0))
        return ag.cut_mesh(self.vertices,self.triangles,[0,0],self.vertices[self.triangles,:2],{0:cells},**kwargs)

    def test_hole_and_disconnected_island_are_not_filled(self):
        mask=np.zeros((16,16));mask[2:14,2:14]=1;mask[5:11,5:11]=0;mask[7:9,7:9]=1
        result=self.cut(mask)
        p=result['vertices'][result['triangles']];centers=p.mean(axis=1)
        # Ray containment at deliberately non-boundary sample points.
        def contains(x,y):
            q=np.array([x,y]);a=p[:,:,:2];d=ag._cross(np.roll(a,-1,axis=1)-a,q-a)
            return bool(np.any(np.all(d>=-1e-10,axis=1)|np.all(d<=1e-10,axis=1)))
        self.assertTrue(contains(.2,.2));self.assertFalse(contains(.38,.5));self.assertTrue(contains(.5,.5))
        self.assertFalse(contains(.02,.5))

    def test_no_internal_open_edges_or_t_junctions(self):
        yy,xx=np.mgrid[:32,:32];mask=((xx-15)**2+(yy-14)**2<125).astype(float)
        result=self.cut(mask);counts={}
        for face in result['faces']:
            for a,b in zip(face,face[1:]+face[:1]):
                edge=tuple(sorted((a,b)));counts[edge]=counts.get(edge,0)+1
        self.assertTrue(all(n<=2 for n in counts.values()))
        for (a,b),n in counts.items():
            if n!=1:continue
            mid=(result['vertices'][a]+result['vertices'][b])*.5
            # No open edges on the original quad's triangulation diagonal.
            self.assertLess(abs(np.linalg.norm(mid[:2]*32-[15.5,17.5])-np.sqrt(125)), 2.)

    def test_barycentric_deformation_and_winding(self):
        mask=np.zeros((8,8));mask[1:7,2:6]=1;r=self.cut(mask)
        self.assertTrue(np.allclose(r['vertices'],np.sum(self.vertices[r['bind_ids']]*r['bind_weights'][:,:,None],axis=1)))
        moved=self.vertices.copy();moved[2,2]=1
        actual=np.sum(moved[r['bind_ids']]*r['bind_weights'][:,:,None],axis=1)
        self.assertGreater(float(actual[:,2].max()),.5)
        p=r['vertices'][r['triangles']]
        self.assertTrue(np.all(np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])[:,2]>0))

    def test_full_and_empty_masks_and_mirrored_uvs(self):
        self.assertEqual(len(self.cut(np.zeros((4,4)))['triangles']),0)
        for mirror in (False,True):
            uv=self.vertices[self.triangles,:2].copy()
            if mirror:uv[:,:,0]=1-uv[:,:,0]
            cells=ag.filled_cells(ag.contours(np.ones((8,8)),simplify=0))
            r=ag.cut_mesh(self.vertices,self.triangles,[0,0],uv,{0:cells})
            p=r['vertices'][r['triangles']];area=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])[:,2].sum()/2
            self.assertAlmostEqual(area,1.,places=9)

    def test_batched_cells_match_clipper_at_tolerance_and_tiled_uvs(self):
        rng=np.random.default_rng(151)
        cells=np.concatenate((rng.uniform(-.1,1.1,(48,3,2)),np.array([
            [[.1,.1],[.2,.1],[.1,.2]],
            [[.8,.8],[.9,.8],[.8,.9]],
            [[0,-5e-12],[.4,-5e-12],[0,.4]],
            [[.1,.1],[.1+1e-12,.1],[.4,.2]],
        ])))
        for tri in (np.array([[0,0],[1,0],[0,1]],float),
                    np.array([[0,1],[1,0],[0,0]],float),
                    np.array([[-.4,.1],[1.4,.2],[.2,1.3]],float)):
            expected=ag.triangulate_uv(tri,list(cells),wrap=True)
            actual=ag.triangulate_uv(tri,cells,wrap=True)
            self.assertEqual(len(actual),len(expected))
            for a,b in zip(actual,expected):self.assertTrue(np.array_equal(a,b))

    def test_bilinear_saddle_keeps_islands_or_connects_by_sign(self):
        separate=ag.contours(np.array([[.9,.2],[.1,.6]]),.5,0)
        joined=ag.contours(np.array([[1.,.4],[.4,1.]]),.5,0)
        self.assertEqual(len(separate),2)
        self.assertEqual(len(joined),1)

if __name__=='__main__':unittest.main()
