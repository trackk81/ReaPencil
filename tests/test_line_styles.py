"""Pure CPU graph targeting: original adjacency and independent style passes."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reatoon import renderer


class LineStyleTests(unittest.TestCase):
    def test_flat_width_scale_renders_and_keeps_native_backend(self):
        import tempfile,struct,zlib
        import numpy as np
        scene=self.scene()
        cfg=self.settings(wireframe=True,width=64,height=64,supersample=1,line_only=True,line_width=4.)
        with tempfile.TemporaryDirectory() as td:
            def draw(name,**extra):return renderer.render(scene,str(Path(td)/name),dict(cfg,**extra))
            baseline=draw('baseline')
            unit=draw('unit',brush_size_scale=1.)
            half=draw('half',brush_size_scale=.5)
            control=draw('control',line_width=2.)
            zero=draw('zero',brush_size_scale=0.)
            self.assertEqual(Path(baseline['paths']['beauty']).read_bytes(),Path(unit['paths']['beauty']).read_bytes())
            self.assertEqual(Path(half['paths']['beauty']).read_bytes(),Path(control['paths']['beauty']).read_bytes())
            self.assertEqual(baseline['stats']['segment_backend'],half['stats']['segment_backend'])
            data=Path(zero['paths']['beauty']).read_bytes();offset=8;parts=[]
            while offset<len(data):
                size=struct.unpack('>I',data[offset:offset+4])[0]
                if data[offset+4:offset+8]==b'IDAT':parts.append(data[offset+8:offset+8+size])
                offset+=size+12
            rgba=np.frombuffer(zlib.decompress(b''.join(parts)),np.uint8).reshape(64,257)[:,1:].reshape(64,64,4)
            self.assertEqual(rgba[:,:,3].max(),0)
            values=renderer.line_style_passes(scene,dict(width=1280,relative_line_size=True,line_width=4.,brush_size_scale=.25))
            self.assertEqual(values[0]['styles'][0]['line_width'],2.)

    def test_opacity_caps_complete_brush_and_preserves_native_backend(self):
        import tempfile,struct,zlib
        import numpy as np
        scene=self.scene()
        cfg=self.settings(wireframe=True,width=64,height=64,supersample=1,line_only=True,line_width=4.)
        def rgba(path):
            data=Path(path).read_bytes();offset=8;parts=[]
            while offset<len(data):
                size=struct.unpack('>I',data[offset:offset+4])[0]
                if data[offset+4:offset+8]==b'IDAT':parts.append(data[offset+8:offset+8+size])
                offset+=size+12
            return np.frombuffer(zlib.decompress(b''.join(parts)),np.uint8).reshape(64,257)[:,1:].reshape(64,64,4)
        with tempfile.TemporaryDirectory() as td:
            normal=renderer.render(scene,str(Path(td)/'normal'),cfg)
            faded=renderer.render(scene,str(Path(td)/'faded'),dict(cfg,line_opacity=.25))
            invisible=renderer.render(scene,str(Path(td)/'invisible'),dict(cfg,line_opacity=0.))
            self.assertEqual(normal['stats']['segment_backend'],faded['stats']['segment_backend'])
            self.assertEqual(rgba(faded['paths']['beauty'])[:,:,3].max(),64)
            self.assertTrue(np.all(rgba(invisible['paths']['beauty'])[:,:,3]==0))
            self.assertTrue(np.all(rgba(invisible['paths']['beauty'])[:,:,:3]==255))
            self.assertIn('<g opacity="0.25">',Path(faded['paths']['lines']).read_text())
            self.assertNotIn('eps',faded['paths'])
            self.assertIn('eps',normal['paths'])
            self.assertTrue(any('EPS output skipped' in w for w in faded['warnings']))

    def test_opacity_rejects_unimplemented_mixed_or_hidden_brushes(self):
        import tempfile
        scene=self.scene()
        with tempfile.TemporaryDirectory() as td:
            for opacity in (-.1,1.1,float('nan')):
                with self.assertRaisesRegex(ValueError,'opacity'):
                    renderer.render(scene,str(Path(td)/'invalid'),dict(line_opacity=opacity))
            with self.assertRaisesRegex(ValueError,'visible-only'):
                renderer.render(scene,str(Path(td)/'hidden'),dict(line_opacity=.5,hidden_lines=True))
            scene['meshes'][0]['line_passes'].append(dict(line='b',priority=1,face_line_sets=['blue',None]))
            with self.assertRaisesRegex(ValueError,'visible-only'):
                renderer.render(scene,str(Path(td)/'mixed'),dict(line_opacity=.5))

    def test_opacity_applies_to_png_elements_and_explicitly_skips_eps_elements(self):
        import tempfile,struct,zlib
        import numpy as np
        from reatoon.render_elements import DEFAULTS
        scene=self.scene()
        scene['render_elements']=[dict(DEFAULTS,name='png',kind='line'),dict(DEFAULTS,name='eps',kind='eps')]
        with tempfile.TemporaryDirectory() as td:
            result=renderer.render(scene,str(Path(td)/'elements'),dict(width=64,height=64,line_only=True,line_opacity=.5))
            byname={e['name']:e for e in result['render_elements']}
            self.assertEqual(byname['png']['status'],'written')
            data=Path(byname['png']['path']).read_bytes();offset=8;parts=[]
            while offset<len(data):
                size=struct.unpack('>I',data[offset:offset+4])[0]
                if data[offset+4:offset+8]==b'IDAT':parts.append(data[offset+8:offset+8+size])
                offset+=size+12
            rgba=np.frombuffer(zlib.decompress(b''.join(parts)),np.uint8).reshape(64,257)[:,1:].reshape(64,64,4)
            self.assertEqual(rgba[:,:,3].max(),128)
            self.assertEqual(byname['eps']['status'],'unsupported')
            self.assertNotIn('path',byname['eps'])

    def test_collinear_connections_preserve_topology_styles_and_branches(self):
        from reatoon.stroke_graph import connect_collinear
        style=dict(connect_collinear_dashes=True,dash_length=5.)
        def edge(a,b,ids,**extra):
            return dict(a=a,b=b,_vertex_ids=ids,settings=style,features=['open'],line='a',mesh_index=0,mesh='test',**extra)
        a=edge([0,0,0],[1,0,0],(0,1));b=edge([1,0,0],[2,0,0],(1,2))
        joined=connect_collinear([a,b])
        self.assertEqual(len(joined),1);self.assertEqual(joined[0]['b'],[2,0,0])
        self.assertEqual(a['b'],[1,0,0])
        coincident=edge([1,0,0],[2,0,0],(3,4))
        self.assertEqual(len(connect_collinear([a,coincident])),2)
        corner=edge([1,0,0],[1,1,0],(1,2))
        self.assertEqual(len(connect_collinear([a,corner])),2)
        branch=edge([1,0,0],[1,1,0],(1,3))
        self.assertEqual(len(connect_collinear([a,b,branch])),3)
        for field,value in [('mesh_index',1),('line','b'),('features',['crease']),('settings',dict(style))]:
            changed=dict(b,**{field:value})
            self.assertEqual(len(connect_collinear([a,changed])),2)
        disabled=dict(a,settings=dict(style,connect_collinear_dashes=False))
        self.assertEqual(len(connect_collinear([disabled,b])),2)

    def test_collinear_connections_render_subdivided_boundary_like_unsplit(self):
        import tempfile
        coarse=self.scene();fine=self.scene()
        fine['meshes'][0]['line_passes'][0]['face_line_sets']=['red','red']
        coarse['meshes'][0].update(vertices=[[-1,-1,0],[1,-1,0],[-1,1,0],[1,1,0]],faces=[[0,1,3,2]],
            line_passes=[dict(line='a',priority=0,face_line_sets=['red'])])
        cfg=self.settings(open_edges=True,width=96,height=96,supersample=2,line_only=True,
                          dash_length=5.,dash_gap=3.,connect_collinear_dashes=True,line_width=2.)
        with tempfile.TemporaryDirectory() as td:
            a=renderer.render(coarse,str(Path(td)/'coarse'),cfg)
            b=renderer.render(fine,str(Path(td)/'fine'),cfg)
            self.assertEqual(Path(a['paths']['beauty']).read_bytes(),Path(b['paths']['beauty']).read_bytes())
            self.assertEqual(b['stats']['collinear_connections'],2)
            packed=renderer.world_line_segments(fine,cfg,packed=True)['segments']
            plain=renderer.world_line_segments(fine,cfg,packed=False)['segments']
            self.assertEqual(list(packed),plain)

    def test_relative_size_scales_once_by_width_and_preserves_source(self):
        scene=self.scene()
        scene['meshes'][0]['line_passes'].append(dict(line='later',priority=1,face_line_sets=['blue',None]))
        scene['line_sets']['red'].update(relative_line_size=True,line_width=4.,dash_length=15.,dash_gap=10.)
        scene['line_sets']['blue'].update(relative_line_size=False,line_width=4.,dash_length=15.,dash_gap=10.)
        for h in (400,600):
            result=renderer.line_style_passes(scene,dict(width=800,height=h,supersample=4))
            self.assertEqual([p['styles'][0]['line_width'] for p in result],[5.,4.])
            self.assertEqual([p['styles'][0]['dash_length'] for p in result],[18.75,15.])
            self.assertEqual([p['styles'][0]['dash_gap'] for p in result],[12.5,10.])
        self.assertEqual(scene['line_sets']['red']['line_width'],4.)
        scene['line_sets']['red']['dash_gap']=-1.
        self.assertEqual(renderer.line_style_passes(scene,dict(width=1280))[0]['styles'][0]['dash_gap'],-1.)

    def test_independent_dash_gap_and_legacy_default(self):
        import tempfile, struct, zlib
        import numpy as np
        scene=self.scene()
        settings=dict(width=96,height=96,supersample=1,line_only=True,
                      compiled_segments=False,compiled_strokes=False,wireframe=True,
                      intersections=False,line_width=1.)
        def alpha(path):
            data=Path(path).read_bytes();offset=8;parts=[]
            while offset<len(data):
                size=struct.unpack('>I',data[offset:offset+4])[0]
                if data[offset+4:offset+8]==b'IDAT':parts.append(data[offset+8:offset+8+size])
                offset+=size+12
            return np.frombuffer(zlib.decompress(b''.join(parts)),np.uint8).reshape(96,385)[:,1:].reshape(96,96,4)[:,:,3]
        with tempfile.TemporaryDirectory() as td:
            def draw(name,**values):
                return alpha(renderer.render(scene,str(Path(td)/name),dict(settings,**values))['paths']['beauty'])
            legacy=draw('legacy',dash_length=5.)
            np.testing.assert_array_equal(legacy,draw('explicit_legacy',dash_length=5.,dash_gap=-1.))
            np.testing.assert_array_equal(legacy,draw('equal_gap',dash_length=5.,dash_gap=5.))
            short=draw('short_gap',dash_length=5.,dash_gap=2.)
            long=draw('long_gap',dash_length=5.,dash_gap=15.)
            self.assertGreater(int(short.sum()),int(long.sum()))
            np.testing.assert_array_equal(draw('solid',dash_length=0.),draw('zero_gap',dash_length=5.,dash_gap=0.))

    def scene(self):
        return dict(camera=dict(position=[0, 0, 4], target=[0, 0, 0]), meshes=[dict(
            name="plane", vertices=[[-1, -1, 0], [0, -1, 0], [1, -1, 0],
                                    [-1, 1, 0], [0, 1, 0], [1, 1, 0]],
            faces=[[0, 1, 4, 3], [1, 2, 5, 4]],
            line_passes=[dict(line="a", priority=0, face_line_sets=["red", None])])],
            line_sets={"red": dict(_order=0, line_color=[1, 0, 0]),
                       "blue": dict(_order=1, line_color=[0, 0, 1])})

    def settings(self, **extra):
        result = {key: False for key in ("outline", "crease", "wireframe", "open_edges", "hard_edges",
                                         "material_boundaries", "selected_edges", "intersections", "self_intersections")}
        result.update(extra)
        return result

    def test_partial_target_does_not_create_false_open_boundary(self):
        segments = renderer.world_line_segments(self.scene(), self.settings(open_edges=True))["segments"]
        self.assertEqual(len(segments), 3)  # the shared interior edge stays closed

    def test_independent_lines_order_and_disabled_graph(self):
        scene = self.scene()
        scene["meshes"][0]["line_passes"].append(dict(line="later", priority=10, face_line_sets=["blue", None]))
        result = renderer.world_line_segments(scene, self.settings(wireframe=True))["segments"]
        self.assertEqual(len(result), 8)
        self.assertEqual([r["line"] for r in result], ["a"] * 4 + ["later"] * 4)
        scene["meshes"][0]["line_passes"] = []
        self.assertEqual(renderer.world_line_segments(scene, self.settings(wireframe=True))["segments"], [])

    def test_distinct_selected_edges_on_one_face_keep_their_styles(self):
        scene = self.scene()
        item = scene["meshes"][0]["line_passes"][0]
        item["face_line_sets"] = [None, None]
        item["selected_edges"] = {"red": [[0, 1]], "blue": [[3, 4]]}
        result = renderer.world_line_segments(scene, self.settings(selected_edges=True))["segments"]
        self.assertEqual(len(result), 2)
        self.assertEqual([r["settings"]["line_color"] for r in result], [[1, 0, 0], [0, 0, 1]])

    def test_intersection_targets_use_actual_triangle_faces(self):
        scene = self.scene()
        scene["meshes"][0]["triangle_faces"] = [0, 0, 1, 1]
        scene["meshes"].append(dict(scene["meshes"][0], name="other", line_passes=[]))
        records = [dict(a=[0, 0, 0], b=[0, 1, 0], mesh_indices=[0, 1], triangle_pairs=[[2, 0]]),
                   dict(a=[1, 0, 0], b=[1, 1, 0], mesh_indices=[0, 1], triangle_pairs=[[0, 0]])]
        result = renderer.world_line_segments(scene, self.settings(intersections=True), intersections=records)["segments"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["a"], [1, 0, 0])

    def test_cpu_batches_preserve_multiline_targets_features_and_intersections(self):
        scene=self.scene()
        scene['meshes'][0]['triangle_faces']=[0,0,1,1]
        scene['meshes'][0]['line_passes'].append(dict(line='later',priority=2,face_line_sets=['blue','red']))
        scene['meshes'].append(dict(scene['meshes'][0],name='other'))
        records=[dict(a=[0,0,0],b=[0,1,0],mesh_indices=[0,1],triangle_pairs=[[2,0]]),
                 dict(a=[1,0,0],b=[1,1,0],mesh_indices=[0,1],triangle_pairs=[[0,0]])]
        settings=self.settings(wireframe=True,intersections=True)
        reference=renderer.world_line_segments(scene,settings,intersections=records)['segments']
        packed=renderer.world_line_segments(scene,settings,intersections=records,packed=True)['segments']
        self.assertEqual(list(packed),reference)
        self.assertEqual(len(packed),len(reference))
        self.assertEqual(packed.intersection_count,sum('intersection' in x['features'] for x in reference))
        import numpy as np
        from reatoon.cpu_segments import render_segments
        camera=renderer._camera(scene['camera'],80,60)
        depth=np.full((60,80),np.inf);planes=np.zeros((60,80,3))
        images=[];results=[]
        for lines in (reference,packed):
            visible=np.zeros((60,80,4),np.float32);hidden=visible.copy()
            results.append(render_segments(lines,camera,depth,planes,visible,hidden,1))
            images.append(visible)
        np.testing.assert_array_equal(images[0],images[1])
        self.assertEqual(results[0],results[1])

    def test_cpu_batch_fallback_keeps_unsupported_styles(self):
        from reatoon.cpu_segments import render_segments
        import numpy as np
        scene=self.scene();scene['line_sets']['red']['hidden_lines']=True
        packed=renderer.world_line_segments(scene,self.settings(wireframe=True),packed=True)['segments']
        camera=renderer._camera(scene['camera'],16,16)
        layer=np.zeros((16,16,4),np.float32)
        self.assertIsNone(render_segments(packed,camera,np.full((16,16),np.inf),np.zeros((16,16,3)),layer,layer.copy(),1))
        self.assertFalse(layer.any())
        self.assertTrue(all(s['settings']['hidden_lines'] for s in packed))

    def test_triangle_silhouette_keeps_style_and_only_adds_outline_diagonal(self):
        scene=self.scene()
        scene['camera']=dict(position=[-10,0,0],target=[0,0,0],projection='orthographic')
        scene['meshes']=[dict(name='folded',vertices=[[-1,-1,0],[1,-1,0],[1,1,1],[-1,1,-1]],
            faces=[[0,1,2,3]],triangles=[[0,1,2],[0,2,3]],triangle_faces=[0,0],
            line_passes=[dict(line='a',priority=0,face_line_sets=['red'])])]
        settings=self.settings(outline=True,triangle_outlines=True)
        expected=renderer.world_line_segments(scene,settings)['segments']
        packed=renderer.world_line_segments(scene,settings,packed=True)['segments']
        self.assertEqual(len(expected),1)
        self.assertEqual(expected[0]['features'],['outline'])
        self.assertEqual(expected[0]['settings']['line_color'],[1,0,0])
        self.assertEqual(list(packed),expected)
        wire=renderer.world_line_segments(scene,self.settings(wireframe=True,triangle_outlines=True))['segments']
        self.assertEqual(len(wire),4)
        self.assertTrue(all(s['features']==['wireframe'] for s in wire))


if __name__ == "__main__":
    unittest.main()
