import sys,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reatoon.brush_profiles import profile_table,evaluate_profile,validate_profile
from reatoon.cpu_brush import draw_runs
from reatoon.profile_strokes import assign_coordinates
from reatoon import renderer

class CurveCPU(unittest.TestCase):
    curve=[[2,0,.1,0,.1,.05,.85],[2,.7,.15,1,.9,1,.9]]

    def test_cubic_inverse_against_independent_bisection(self):
        x=np.linspace(0,1,1001);lo=np.zeros_like(x);hi=np.ones_like(x)
        for _ in range(60):
            t=(lo+hi)/2;s=1-t;bx=3*s*s*t*.05+3*s*t*t*.7+t**3
            lo=np.where(bx<x,t,lo);hi=np.where(bx>=x,t,hi)
        t=(lo+hi)/2;s=1-t;y=s**3*.1+3*s*s*t*.85+3*s*t*t*.15+t**3*.9
        self.assertLess(float(np.max(np.abs(evaluate_profile(self.curve,x)-y))),1.01e-6)

    def test_stored_spline_and_break_handles(self):
        for kind in (1,3):
            curve=[list(r) for r in self.curve]
            for r in curve:r[0]=kind
            np.testing.assert_array_equal(evaluate_profile(curve,np.linspace(0,1,100)),evaluate_profile(self.curve,np.linspace(0,1,100)))

    def test_domain_hold_overshoot_clamp_and_bad_input(self):
        curve=[[2,0,0,.2,.2,.4,2],[2,.6,2,.8,.2,1,0]]
        y=evaluate_profile(curve,[0,.1,.2,.5,.8,.9,1])
        np.testing.assert_allclose(y,[.2,.2,.2,1,.2,.2,.2])
        for bad in ([[0]*6],[[0,0,0,0,float('nan'),0,0]],[[0]*7,[0]*7]):
            with self.assertRaises(ValueError):validate_profile(bad)
        for t in (0,-1,float('nan')):
            with self.assertRaises(ValueError):profile_table([],t)

    def test_native_alpha_nearest_point_not_max_capsule_bias(self):
        layer=np.zeros((170,40,4),np.float32);alpha=[[0,0,0,0,0,0,0],[0,1,1,1,1,1,1]]
        runs=[[20,5,20,165,.2,.4,.8]]
        draw_runs(layer,runs,[20,5,20,165],0,1,20,profile_table([]),profile_table(alpha))
        expected=(np.arange(5,165)+.5-5)/160
        np.testing.assert_allclose(layer[5:165,20,3],expected,atol=5e-8)
        np.testing.assert_allclose(layer[5:165,20,0],expected*.2,atol=2e-8)

    def test_native_diagonal_row_strip_matches_full_brute_force(self):
        layer=np.zeros((80,90,4),np.float32);a=np.array([5.,74.]);b=np.array([83.,4.]);base=12.
        draw_runs(layer,[[*a,*b,0,0,0]],[*a,*b],0,1,base,profile_table(self.curve),profile_table(self.curve))
        yy,xx=np.mgrid[:80,:90];p=np.stack([xx+.5,yy+.5],-1);v=b-a;t=np.clip((p-a)@v/np.dot(v,v),0,1);q=a+t[...,None]*v
        size=evaluate_profile(self.curve,t);expected=np.clip(base*size/2+.5-np.linalg.norm(p-q,axis=-1),0,1)*size
        np.testing.assert_allclose(layer[...,3],expected,atol=6e-8)

    def test_collinear_vertex_chains_preserve_coordinate_and_order(self):
        camera=renderer._camera(dict(position=[0,0,10],target=[0,0,0],up=[0,1,0],projection="orthographic",ortho_width=6),400,400)
        style=dict(width_profile=self.curve,profile_direction=-30.)
        rows=[dict(a=[0,0,0],b=[0,2,0],_vertex_ids=(1,2),settings=style,line='a',mesh_index=0,features=['hard']),dict(a=[0,0,0],b=[0,-2,0],_vertex_ids=(1,0),settings=style,line='a',mesh_index=0,features=['hard'])]
        result=assign_coordinates(rows,camera,renderer._project)
        np.testing.assert_allclose(result[0]['_profile_u'],[.5,1]);np.testing.assert_allclose(result[1]['_profile_u'],[.5,0])
        # Coincident disconnected vertex IDs must not join.
        rows[1]['_vertex_ids']=(3,4);result=assign_coordinates(rows,camera,renderer._project)
        np.testing.assert_allclose(result[0]['_profile_u'],[0,1]);np.testing.assert_allclose(result[1]['_profile_u'],[1,0])

    def test_full_native_profile_stage_matches_reference_png(self):
        scene=dict(camera=dict(position=[0,0,10],target=[0,0,0],projection='orthographic',ortho_width=6),
            meshes=[dict(vertices=[[-2,-2,0],[2,-2,0],[2,2,0],[-2,2,0]],faces=[[0,1,2,3]])])
        cfg=dict(width=120,height=100,supersample=2,line_only=True,line_width=5.,wireframe=True,intersections=False,
                 auxiliary_outputs=False,width_profile=self.curve,alpha_profile=self.curve)
        with tempfile.TemporaryDirectory() as folder:
            for orthographic in (True,False):
                scene['camera']['projection']='orthographic' if orthographic else 'perspective'
                for direction in (-30,90):
                    a=renderer.render(scene,str(Path(folder)/'fast'),dict(cfg,profile_direction=direction))
                    b=renderer.render(scene,str(Path(folder)/'ref'),dict(cfg,profile_direction=direction,compiled_segments=False))
                    self.assertEqual(a['stats']['segment_backend'],'native-cpu-profile-segments')
                    self.assertEqual(Path(a['paths']['beauty']).read_bytes(),Path(b['paths']['beauty']).read_bytes())

    def test_screen_angle_corner_threshold_and_continuous_distance(self):
        camera=renderer._camera(dict(position=[0,0,10],target=[0,0,0],projection='orthographic',ortho_width=6),400,400)
        style=dict(width_profile=self.curve,profile_direction=-30.,profile_split_angle=90.)
        rows=[dict(a=[-1.5,-1,0],b=[1.5,-1,0],_vertex_ids=(0,1),settings=style,line='a',mesh_index=0,features=['hard']),dict(a=[1.5,-1,0],b=[1.5,1,0],_vertex_ids=(1,2),settings=style,line='a',mesh_index=0,features=['hard'])]
        result=assign_coordinates(rows,camera,renderer._project)
        np.testing.assert_allclose(result[0]['_profile_u'],[0,.6]);np.testing.assert_allclose(result[1]['_profile_u'],[.6,1])
        style['profile_split_angle']=89.;result=assign_coordinates(rows,camera,renderer._project)
        for r in result:np.testing.assert_allclose(r['_profile_u'],[0,1])
        # Camera-projected turn is 45 degrees, while its 3D turn is 75 degrees.
        rows[0].update(a=[-1.5,-1,0],b=[.5,-1,1]);rows[1].update(a=[.5,-1,1],b=[1.5,0,0]);style['profile_split_angle']=60.
        result=assign_coordinates(rows,camera,renderer._project)
        fraction=2/(2+2**.5)
        np.testing.assert_allclose(result[0]['_profile_u'],[0,fraction]);np.testing.assert_allclose(result[1]['_profile_u'],[fraction,1])

    def test_closed_rectangle_direction_and_stable_anchor_under_permutation(self):
        camera=renderer._camera(dict(position=[0,0,10],target=[0,0,0],projection='orthographic',ortho_width=6),400,400)
        points=[[-1.5,-1,0],[1.5,-1,0],[1.5,1,0],[-1.5,1,0]]
        style=dict(alpha_profile=self.curve,profile_direction=-30.,profile_split_angle=90.,profile_loop_direction=0)
        rows=[dict(a=points[i],b=points[(i+1)%4],_vertex_ids=(i,(i+1)%4),settings=style,line='a',mesh_index=0,features=['hard']) for i in range(4)]
        expected={0:[1,.7],1:[.7,.5],2:[.5,.2],3:[.2,0]}
        for order in ([0,1,2,3],[2,0,3,1],[3,2,1,0]):
            result=assign_coordinates([rows[i] for i in order],camera,renderer._project)
            for i,r in zip(order,result):np.testing.assert_allclose(r['_profile_u'],expected[i],atol=1e-15)
        style['profile_loop_direction']=1
        expected={0:[.2,.5],1:[.5,.7],2:[.7,1],3:[0,.2]}
        for i,r in enumerate(assign_coordinates(rows,camera,renderer._project)):np.testing.assert_allclose(r['_profile_u'],expected[i],atol=1e-15)

    def test_pencil_width_correction_after_relative_size_and_multiplier(self):
        from reatoon.brush_profiles import stroke_tables
        profile=[[0,0,.1,0,.1,0,.1],[0,1,.9,1,.9,1,.9]]
        scene=dict(meshes=[dict(vertices=[[0,0,0]],faces=[],line_set='a')],line_sets={'a':dict(width_profile=profile,pencil_profile_width=True,line_width=20.,brush_size_scale=.25,relative_line_size=True)})
        style=renderer.line_style_passes(scene,dict(width=1280))[0]['styles'][0]
        self.assertEqual(style['line_width'],10.5)
        table,_=stroke_tables(style)
        np.testing.assert_allclose(table[:,1],[.1,.9])
        radius=style['line_width']*.5*table[:,1]
        np.testing.assert_allclose(np.where(radius<1,radius**2,2*radius-1),[.525**2,8.45])
        # With correction disabled, retain the independent mathematical width.
        scene['line_sets']['a']['pencil_profile_width']=False
        self.assertEqual(renderer.line_style_passes(scene,dict(width=1280))[0]['styles'][0]['line_width'],10.)

    def test_subpixel_pencil_brush_coverage_keeps_faint_strokes(self):
        layer=np.zeros((20,20,4),np.float32);table=np.array([[0,.5],[1,.5]])
        draw_runs(layer,[[10,2,10,18,0,0,0]],[10,2,10,18],0,1,4,table,profile_table([]),smoothing=2.)
        self.assertAlmostEqual(float(layer[10,10,3]),.25)
        self.assertAlmostEqual(float(layer[10,9,3]),.25)
        self.assertEqual(float(layer[10,8,3]),0.)
        layer.fill(0)
        draw_runs(layer,[[10,2,10,18,0,0,0]],[10,2,10,18],0,1,2,table,profile_table([]),smoothing=2.)
        self.assertAlmostEqual(float(layer[10,10,3]),.0625)

    def test_analytic_diagonal_pixel_coverage_matches_dense_quadrature(self):
        layer=np.zeros((40,40,4),np.float32);a=np.array([-50.,-25.]);b=np.array([90.,45.]);radius=.3
        draw_runs(layer,[[*a,*b,0,0,0]],[*a,*b],0,1,2*radius,profile_table([]),profile_table([]),smoothing=1.)
        normal=np.array([-1.,2.])/np.sqrt(5.)
        f=(np.arange(256)+.5)/256
        yy,xx=np.meshgrid(f,f,indexing='ij');offsets=np.stack([xx,yy],-1)
        for x,y in ((20,10),(19,9),(21,11),(20,11)):
            expected=np.clip(radius-np.abs((offsets+[x,y]-a)@normal),0,1).mean()
            self.assertAlmostEqual(float(layer[y,x,3]),float(expected),delta=3e-6)

if __name__=='__main__':unittest.main()
