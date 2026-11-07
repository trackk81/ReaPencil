import sys, unittest
import numpy as np
from reatoon import alpha_tessellation as tess
from reatoon import alpha_geometry as ag

@unittest.skipUnless(sys.platform=='win32','Windows system GLU')
class AlphaTessellationTests(unittest.TestCase):
    @staticmethod
    def contains(tris,xy):
        cross=ag._cross(np.roll(tris,-1,axis=1)-tris,np.array(xy)-tris)
        return bool(np.any(np.all(cross>=-1e-12,axis=1)|np.all(cross<=1e-12,axis=1)))
    @staticmethod
    def area(tris):return float(np.abs(ag._cross(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0])).sum()/2)
    def test_many_holes_preserve_area_and_occupancy(self):
        loops=[np.array([[0,0],[1,0],[1,1],[0,1]],float)]
        for y in range(20):
            for x in range(20):
                lo=np.array([x,y])/20+.01;loops.append(lo+np.array([[0,0],[.02,0],[.02,.02],[0,.02]]))
        result=tess.triangulate(loops)
        self.assertAlmostEqual(self.area(result),1-400*.02**2,places=10)
        self.assertTrue(self.contains(result,[.005,.005]))
        for y in range(20):
            for x in range(20):self.assertFalse(self.contains(result,np.array([x,y])/20+.02))
    def test_nested_island_winding_and_empty(self):
        square=np.array([[0,0],[1,0],[1,1],[0,1]],float)
        loops=[square,square*.6+.2,square*.2+.4]
        for data in (loops,[p[::-1] for p in loops[::-1]]):
            result=tess.triangulate(data)
            self.assertAlmostEqual(self.area(result),.68,places=10)
            self.assertTrue(self.contains(result,[.5,.5]));self.assertFalse(self.contains(result,[.3,.5]))
        self.assertEqual(tess.triangulate([]).shape,(0,3,2))
    def test_crossing_contour_creates_combined_vertex(self):
        result=tess.triangulate([np.array([[0,0],[1,1],[0,1],[1,0]],float)])
        self.assertAlmostEqual(self.area(result),.5,places=10)
        self.assertTrue(np.any(np.all(np.isclose(result,[.5,.5]),axis=2)))
    def test_nan_rejected(self):
        with self.assertRaises(ValueError):tess.triangulate([[[0,0],[1,0],[0,float('nan')]]])

if __name__=='__main__':unittest.main()
