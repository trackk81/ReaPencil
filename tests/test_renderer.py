import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reatoon.renderer import render, _camera, _clip_polygon, _clip_segment, _raster_triangle, cel_color, shade_amount, classify_edges, _stroke, _over, _screen_clip, _project, _surface_depth_at


def quad(z, name="quad", size=1):
    return dict(name=name, vertices=[[-size, -size, z], [size, -size, z], [size, size, z], [-size, size, z]],
                faces=[[0, 1, 2, 3]], triangles=[[0, 1, 2], [0, 2, 3]], triangle_faces=[0, 0],
                material_ids=[0], materials=[dict(color=[.8, .3, .2])])


class RendererTests(unittest.TestCase):
    def test_line_only_has_transparent_unshaded_interior_and_matches_cpu_reference(self):
        def rgba(path):
            data=Path(path).read_bytes();self.assertEqual(data[25],6)
            offset=8;parts=[]
            while offset<len(data):
                size=struct.unpack('>I',data[offset:offset+4])[0]
                if data[offset+4:offset+8]==b'IDAT':parts.append(data[offset+8:offset+8+size])
                offset+=size+12
            return np.frombuffer(zlib.decompress(b''.join(parts)),np.uint8).reshape(64,257)[:,1:].reshape(64,64,4)
        scene=dict(meshes=[quad(0)],camera=dict(position=[0,0,5],target=[0,0,0]))
        settings=dict(width=64,height=64,supersample=1,line_only=True,line_color=[0,0,0])
        with tempfile.TemporaryDirectory() as td:
            native=render(scene,str(Path(td)/'native'),settings)
            reference=render(scene,str(Path(td)/'reference'),dict(settings,compiled_depth=False))
            a,b=rgba(native['paths']['beauty']),rgba(reference['paths']['beauty'])
            np.testing.assert_array_equal(a,b)
            self.assertEqual(a[32,32,3],0)
            self.assertGreater(np.count_nonzero(a[:,:,3]),0)
            self.assertTrue(np.all(a[32,32,:3]==255))
            self.assertLessEqual(np.abs(a[:,:,:3].astype(int)+a[:,:,3,None].astype(int)-255).max(),1)

    def test_cel_bands_and_offset(self):
        material = dict(color=[.5, .4, .3], shadow_color=[.1, .1, .1], highlight_color=[1, 1, 1],
                        threshold=.4, highlight_threshold=.8)
        light = dict(direction=[0, 0, 1], ambient=0)
        np.testing.assert_allclose(cel_color([0, 0, -1], material, light), [.1] * 3)
        np.testing.assert_allclose(cel_color([0, 0, .6], material, light), [.5, .4, .3])
        np.testing.assert_allclose(cel_color([0, 0, 1], material, light), [1] * 3)
        material["gradation_offset"] = .5
        np.testing.assert_allclose(cel_color([0, 0, -1], material, light), [.5, .4, .3])

    def test_four_zone_ramp_preserves_each_band(self):
        colors = [[.05, .1, .2], [.15, .3, .4], [.3, .6, .7], [.6, .9, 1]]
        material = dict(ramp=[dict(position=p, color=c, interpolation=0)
                              for p, c in zip([0, .25, .5, .75], colors)])
        values = [-.5, 0., .2499, .25, .4999, .5, .7499, .75, 1., 2.]
        expected = [colors[i] for i in [0, 0, 0, 1, 1, 2, 2, 3, 3, 3]]
        np.testing.assert_allclose(shade_amount(values, material), expected)

    def test_ramp_linear_smooth_spline_and_duplicate_stop(self):
        ramp = [dict(position=0., color=[0, 0, 0], interpolation="linear"),
                dict(position=1., color=[1, 1, 1], interpolation="none")]
        np.testing.assert_allclose(shade_amount(.25, dict(ramp=ramp)), [.25] * 3)
        ramp[0]["interpolation"] = "smooth"
        np.testing.assert_allclose(shade_amount(.25, dict(ramp=ramp)), [.15625] * 3)
        ramp[0]["interpolation"] = "spline"
        np.testing.assert_allclose(shade_amount(.25, dict(ramp=ramp)), [.25] * 3)
        ramp.append(dict(position=1., color=[.7, .7, .7]))
        np.testing.assert_allclose(shade_amount(1., dict(ramp=ramp)), [.7] * 3)
        ramp.append(dict(position=.5, color=[1, 0, 0], enabled=False))
        np.testing.assert_allclose(shade_amount(1., dict(ramp=ramp)), [.7] * 3)

    def test_ramp_uses_same_shading_for_flat_and_smooth(self):
        material = dict(ramp=[dict(position=0, color=[.1, .1, .1]),
                              dict(position=.25, color=[.2, .2, .2]),
                              dict(position=.5, color=[.4, .4, .4]),
                              dict(position=.75, color=[.8, .8, .8])])
        light = dict(direction=[0, 0, 1], intensity=.6, ambient=0)
        expected = cel_color([0, 0, 1], material, light)
        cam = _camera(dict(position=[0, 0, 0], target=[0, 0, 1], fov_y=90), 100, 100)
        depth = np.full((100, 100), np.inf)
        image = np.zeros((100, 100, 3))
        pts = np.array([[-1., -1., 2.], [1., -1., 2.], [0., 1., 2.]])
        _raster_triangle(pts, expected, depth, image, cam, [[0, 0, 1]] * 3, material, light)
        np.testing.assert_allclose(image[50, 50], expected)
        np.testing.assert_allclose(expected, [.4, .4, .4])

    def test_invalid_ramp_interpolation_fails(self):
        with self.assertRaises(ValueError):
            shade_amount(.5, dict(ramp=[dict(position=0, color=[0, 0, 0], interpolation=99)]))

    def test_near_clipping(self):
        clipped = _clip_polygon([[0, 0, .05], [1, 0, 1], [0, 1, 1]], .1, 10)
        self.assertEqual(len(clipped), 4)
        self.assertTrue(all(p[2] >= .1 - 1e-10 for p in clipped))
        self.assertIsNone(_clip_segment(np.array([0., 0., -.5]), np.array([1., 1., -.1]), .1, 10))

    def test_topology_does_not_draw_diagonal(self):
        from reatoon.renderer import DEFAULTS
        cam = _camera(dict(position=[0, 0, 5], target=[0, 0, 0]), 64, 64)
        edges = list(classify_edges(quad(0), cam, DEFAULTS))
        self.assertEqual(len(edges), 4)
        self.assertNotIn((0, 2), [e[0] for e in edges])

    def test_perspective_depth_is_reciprocal(self):
        cam = _camera(dict(position=[0, 0, 0], target=[0, 0, 1], fov_y=90), 100, 100)
        depth = np.full((100, 100), np.inf)
        image = np.zeros((100, 100, 3))
        # These camera points project to (25,75), (75,75), (50,25).
        pts = [np.array([-1., -1., 2.]), np.array([2., -2., 4.]), np.array([0., 1., 2.])]
        _raster_triangle(pts, [.2, .3, .4], depth, image, cam)
        u, v, w = .245, .265, .49  # barycentric at pixel center (50.5,50.5)
        # Independently compute the weights to avoid accepting affine z.
        p = np.array([50.5, 50.5])
        matrix = np.array([[25, 75, 50], [75, 75, 25], [1, 1, 1]], float)
        weights = np.linalg.solve(matrix, [*p, 1])
        expected = 1 / np.dot(weights, [1 / 2, 1 / 4, 1 / 2])
        self.assertAlmostEqual(depth[50, 50], expected)
        self.assertGreater(abs(depth[50, 50] - np.dot(weights, [2, 4, 2])), .1)

    def test_render_hidden_edges_and_outputs(self):
        scene = dict(camera=dict(position=[0, 0, 5], target=[0, 0, 0], projection="orthographic", ortho_width=5, far=20),
                     meshes=[quad(0, "back", .6), quad(1, "front", 1.2)])
        with tempfile.TemporaryDirectory() as td:
            result = render(scene, str(Path(td) / "image"), dict(width=64, height=64, supersample=1, hidden_lines=True))
            self.assertGreater(result["stats"]["hidden_segments"], 0)
            self.assertGreater(result["stats"]["visible_segments"], 0)
            for key, path in result["paths"].items():
                self.assertTrue(Path(path).exists(), key)
            png = Path(result["paths"]["beauty"]).read_bytes()
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", png[16:24]), (64, 64))
            svg = Path(result["paths"]["lines"]).read_text()
            self.assertIn('data-visibility="hidden"', svg)
            self.assertIn('data-visibility="visible"', svg)
            self.assertEqual(json.loads(Path(result["paths"]["manifest"]).read_text())["stats"]["meshes"], 2)

    def test_near_crossing_render_finite(self):
        m = dict(vertices=[[-1, -1, -.1], [1, -1, 2], [0, 1, 2]], faces=[[0, 1, 2]])
        scene = dict(camera=dict(position=[0, 0, 0], target=[0, 0, 1], near=.1), meshes=[m])
        with tempfile.TemporaryDirectory() as td:
            result = render(scene, str(Path(td) / "clipped"), dict(width=32, height=32, supersample=2))
            self.assertEqual(result["stats"]["triangles"], 2)
            self.assertNotIn("nan", Path(result["paths"]["lines"]).read_text())

    def test_interpolated_normals_produce_three_bands(self):
        cam = _camera(dict(position=[0, 0, 0], target=[0, 0, 1], fov_y=90), 100, 100)
        depth = np.full((100, 100), np.inf)
        image = np.zeros((100, 100, 3))
        pts = np.array([[-1., -1., 2.], [1., -1., 2.], [0., 1., 2.]])
        normals = [[0, 0, -1], [0, 0, -1], [0, 1, 1]]
        material = dict(color=[.5, .5, .5], shadow_color=[.1, .1, .1], highlight_color=[1, 1, 1],
                        threshold=.2, highlight_threshold=.5)
        _raster_triangle(pts, [0, 0, 0], depth, image, cam, normals, material,
                         dict(direction=[0, 0, 1], ambient=0))
        values = set(np.round(image[np.isfinite(depth), 0], 3))
        self.assertEqual(values, {.1, .5, 1.})

    def test_prepared_nonmanifold_edge_keeps_all_face_features(self):
        from reatoon.renderer import DEFAULTS, prepare_edges
        mesh = dict(vertices=[[0,0,0],[1,0,0],[0,1,0],[0,-1,0],[0,0,1]],
                    faces=[[0,1,2],[0,1,3],[0,1,4]], material_ids=[0,0,1],
                    hard_edges=[[0,1]], selected_edges=[[0,1]])
        camera = _camera(dict(position=[0,0,3],target=[0,0,0]),64,64)
        prepared = prepare_edges(mesh)
        edges = dict(classify_edges(mesh,camera,dict(DEFAULTS,open_edges=False),prepared))
        self.assertEqual(set(edges), {(0,1)})
        self.assertEqual(set(edges[(0,1)]), {'outline','crease','material','hard','selected'})
        self.assertNotIn('_edge_cache', mesh)

    def test_material_boundaries_and_selected_edges(self):
        from reatoon.renderer import DEFAULTS
        mesh = dict(vertices=[[-1, -1, 0], [0, -1, 0], [1, -1, 0], [-1, 1, 0], [0, 1, 0], [1, 1, 0]],
                    faces=[[0, 1, 4, 3], [1, 2, 5, 4]], material_ids=[0, 1], selected_edges=[[0, 1]])
        settings = dict(DEFAULTS, open_edges=False, outline=False, crease=False)
        cam = _camera(dict(position=[0, 0, 5], target=[0, 0, 0]), 64, 64)
        edges = dict(classify_edges(mesh, cam, settings))
        self.assertEqual(edges[(1, 4)], ["material"])
        self.assertEqual(edges[(0, 1)], ["selected"])
        self.assertEqual(len(edges), 2)

    def test_alpha_warning_and_eps_metadata(self):
        m = quad(0)
        m["materials"][0]["opacity"] = .5
        with tempfile.TemporaryDirectory() as td:
            result = render(dict(meshes=[m]), str(Path(td) / "alpha"), dict(width=32, height=32, supersample=1))
            self.assertTrue(any("rendered opaque" in w for w in result["warnings"]))
            self.assertIn("%%BoundingBox: 0 0 32 32", Path(result["paths"]["eps"]).read_text())

    def test_invalid_input_fails_before_output(self):
        with self.assertRaises(ValueError):
            render({}, "unused", dict(width=999999))

    def test_zero_width_has_no_vector_hairlines(self):
        with tempfile.TemporaryDirectory() as td:
            result = render(dict(meshes=[quad(0)]), str(Path(td) / "zero"),
                            dict(width=32, height=32, supersample=1, line_width=0))
            self.assertEqual(result["stats"]["visible_segments"], 0)
            self.assertNotIn("<path", Path(result["paths"]["lines"]).read_text())

    def test_different_color_strokes_use_painter_order(self):
        red = np.zeros((20, 20, 4), dtype=np.float32)
        blue = np.zeros_like(red)
        _stroke(red, np.array([0., 10.]), np.array([20., 10.]), 4, [1, 0, 0])
        _stroke(blue, np.array([10., 0.]), np.array([10., 20.]), 4, [0, 0, 1])
        _over(red, blue)
        np.testing.assert_allclose(red[10, 10], [0, 0, 1, 1])

    def test_thick_stroke_outside_frame_remains_visible(self):
        a, b = np.array([20., 0.]), np.array([20., 20.])
        self.assertIsNotNone(_screen_clip(a, b, 20, 20, margin=3))
        layer = np.zeros((20, 20, 4), dtype=np.float32)
        _stroke(layer, a, b, 4, [1, 0, 0])
        self.assertGreater(layer[10, 19, 3], .99)
        self.assertGreater(layer[10, 18, 3], .99)
        self.assertEqual(layer[10, 17, 3], 0)

    def test_sloped_surface_does_not_occlude_its_own_line(self):
        for projection in ("orthographic", "perspective"):
            cam = _camera(dict(position=[0, 0, 0], target=[0, 0, 1], projection=projection,
                               ortho_width=4, fov_y=70), 100, 100)
            depth = np.full((100, 100), np.inf)
            planes = np.zeros((100, 100, 3))
            image = np.zeros((100, 100, 3))
            vertices = np.array([[-1, -1, 2], [1, -1, 4], [1, 1, 4], [-1, 1, 2]], float)
            for tri in ([0, 1, 2], [0, 2, 3]):
                _raster_triangle(vertices[tri], [1, 1, 1], depth, image, cam, depth_planes=planes)
            a, b = np.array([-1., 0., 2.]), np.array([1., 0., 4.])
            p, q = _project(np.array([a, b]), cam)
            t = np.linspace(.01, .99, 75)
            xy = p + t[:, None] * (q - p)
            z = a[2] + t * (b[2] - a[2]) if cam["ortho"] else 1 / ((1 - t) / a[2] + t / b[2])
            observed = _surface_depth_at(xy, depth, planes, cam)
            self.assertTrue(np.all(z <= observed + .002 * np.maximum(1, z)), projection)
            finite = np.isfinite(observed)
            np.testing.assert_allclose(observed[finite], z[finite], atol=1e-10)
            # A genuinely nearer surface must still occlude the line.
            near_tri = np.array([[-2., -2., 1.], [2., -2., 1.], [0., 2., 1.]])
            _raster_triangle(near_tri, [0, 0, 0], depth, image, cam, depth_planes=planes)
            observed = _surface_depth_at(xy, depth, planes, cam)
            self.assertTrue(np.all(z > observed + .002 * np.maximum(1, z)), projection)


if __name__ == "__main__":
    unittest.main()
