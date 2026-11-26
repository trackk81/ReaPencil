import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reatoon import brush_maps as m, renderer as r
from reatoon.packed_segments import PackedSegments
from reatoon.cpu_brush import _clip_packed_depth

class MapTests(unittest.TestCase):
    def camera(self,ortho=False):
        return r._camera(dict(position=[0,0,0],target=[0,0,1],near=1,far=10,
            projection='orthographic' if ortho else 'perspective',ortho_width=4),100,100)
    def part(self,points):
        return dict(points=np.array([points],float),flags=np.array([4],np.uint8),count=1,
            mesh='m',mesh_index=0,line='l',settings=dict(r.DEFAULTS,line_width=2,
            brush_maps={'color':dict(texture_id='ramp',enabled=True,amount=1.)}),
            profile_u=np.array([[.2,.8]]),map_uvs={'':np.array([[[0.,0.],[1.,1.]]])})
    def test_bilinear_centres_clamp_and_domain(self):
        texture=dict(pixels=np.array([[[0,0,0],[1,1,1]],[[0,0,0],[1,1,1]]]),repeat=False,uv_domain=[0,0,1,1])
        np.testing.assert_allclose(m.sample(texture,[[0,.5],[.5,.5],[1,.5]])[:,0],[0,.5,1])
        with self.assertRaisesRegex(ValueError,'0..1'):m.sample(texture,[[2,0]])
    def test_near_clip_interpolates_world_uv_and_screen_profile(self):
        p=self.part([[-1,0,.5],[1,0,2.5]]);packed=PackedSegments();packed.parts=[p];packed.count=1
        q=_clip_packed_depth(packed,self.camera(),1).parts[0]
        np.testing.assert_allclose(q['map_uvs'][''][0,0],[.25,.25])
        self.assertAlmostEqual(q['profile_u'][0,0],.2+.6*.625)
        np.testing.assert_allclose(p['map_uvs'][''][0,0],[0,0])
    def test_perspective_uv_is_not_raster_linear(self):
        p=self.part([[0,0,2],[1,0,8]])
        tex=dict(pixels=np.repeat(np.linspace(0,1,256)[None,:,None],256,axis=0).repeat(3,axis=2),repeat=False)
        pieces=list(m._piece_batches(p,self.camera(),1,{'ramp':tex}))
        rows=np.concatenate([v['mapped_colors'] for v in pieces])
        # Mid-screen lies near UV .2, not .5, with depths2 and8.
        self.assertLess(rows[len(rows)//2,0],.3)
        self.assertTrue(all(v['count']<=m.BATCH_SIZE for v in pieces))
    def test_colour_and_size_mix_and_original_profile_coordinates(self):
        p=self.part([[-1,0,2],[1,0,2]])
        p['settings'].update(line_color=[.2,.4,.6],line_width=12,
            brush_maps={'color':dict(texture_id='c',amount=.5),'width':dict(texture_id='c',amount=.5)})
        tex={'pixels':np.full((2,2,3),[.8,.1,.3]),'repeat':False}
        q=list(m._piece_batches(p,self.camera(True),1,{'c':tex}))[0]
        np.testing.assert_allclose(q['mapped_colors'],np.tile([.5,.25,.45],(q['count'],1)),atol=1e-7)
        np.testing.assert_allclose(q['mapped_widths'],12*.7,atol=1e-7)
        self.assertAlmostEqual(q['profile_u'][0,0],.2)
        self.assertAlmostEqual(q['profile_u'][-1,1],.8)
    def test_screen_clipping_bounds_allocation(self):
        p=self.part([[-1e8,0,2],[1e8,0,2]])
        tex={'pixels':np.ones((2,2,3)),'repeat':False}
        q=list(m._piece_batches(p,self.camera(True),1,{'ramp':tex}))
        self.assertLess(sum(v['count'] for v in q),250)
    def test_disabled_and_zero_maps_inactive(self):
        self.assertFalse(m.active({'brush_maps':{'color':{'enabled':False}}}))
        self.assertFalse(m.active({'brush_maps':{'width':{'amount':0}}}))
    def test_missing_texture_and_uv_fail_explicitly(self):
        p=self.part([[0,0,2],[1,0,2]])
        with self.assertRaisesRegex(ValueError,'evaluated'):list(m._piece_batches(p,self.camera(),1,{}))
        p.pop('map_uvs')
        with self.assertRaisesRegex(ValueError,'UVs unavailable'):list(m._piece_batches(p,self.camera(),1,{'ramp':{}}))

if __name__=='__main__':unittest.main()
