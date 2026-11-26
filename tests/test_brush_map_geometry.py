import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from reatoon import brush_map_geometry as maps
from reatoon.packed_segments import PackedSegments


def fixture():
    mesh = dict(name='testShape', vertices=[[0., 0., 0.], [2., 0., 0.], [0., 2., 0.], [2., 2., 0.]],
                faces=[[0, 1, 2], [1, 3, 2]], triangles=[[0, 1, 2], [1, 3, 2]], triangle_faces=[0, 1])
    counts = [3, 3]
    data = maps.build_uv_lookup(mesh, counts, [0, 1, 2, 1, 3, 2], counts,
                               [0, 1, 2, 3, 4, 5], [[0., 0.], [1., 0.], [0., 1.],
                                                      [2., 0.], [3., 1.], [2., 1.]])
    mesh['_brush_map_uvs'] = {'': data, 'map2': data}
    prepared = dict(vertices=np.asarray(mesh['vertices']), pairs=np.array([[1, 2], [0, 1]]),
                    starts=np.array([0, 2]), counts=np.array([2, 1]), owners=np.array([1, 0, 0]))
    style = dict(line_width=3., line_color=[.1, .2, .3], depth_bias=.002,
                 brush_maps={'color': {'enabled': True, 'amount': 1., 'uv_set': ''}})
    return mesh, prepared, style


class GeometryTests(unittest.TestCase):
    def test_disabled_maps_do_not_require_uv_data(self):
        self.assertFalse(maps.active({}))
        self.assertFalse(maps.active({'brush_maps': {'color': {'enabled': False}}}))
        self.assertFalse(maps.active({'brush_maps': {'width': {'amount': 0.}}}))
        self.assertEqual(maps.edge_uv({}, {}, [0], {}), {})
        maps.export_uv_sets({}, None, None, [{}])

    def test_nested_visible_and_hidden_brushes_are_found(self):
        style = {'feature_brushes': {'outline': {'brush_maps': {'width': {'uv_set': 'detail'}}}},
                 'hidden_style': {'brush_maps': {'color': {'uv_set': ''}}}}
        self.assertTrue(maps.any_active(style))
        self.assertEqual(maps.uv_sets(style), ['', 'detail'])

    def test_edge_uv_seam_uses_lowest_polygon_even_when_owners_unsorted(self):
        mesh, prepared, style = fixture()
        uv = maps.edge_uv(mesh, prepared, [0], style)['']
        np.testing.assert_array_equal(uv, [[[1., 0.], [0., 1.]]])

    def test_intersection_uv_uses_requested_owner_triangle(self):
        mesh, _, style = fixture()
        points = np.array([[[1., 1., 0.], [1.5, .5, 0.]]])
        uv_a = maps.intersection_uv(mesh, points, [0], style)['']
        uv_b = maps.intersection_uv(mesh, points, [1], style)['']
        np.testing.assert_allclose(uv_a, [[[.5, .5], [.75, .25]]])
        np.testing.assert_allclose(uv_b, [[[2., .5], [2., .25]]])

    def test_intersection_world_degenerate_triangle_is_explicit(self):
        mesh, _, style = fixture()
        mesh['vertices'][2] = [4., 0., 0.]
        with self.assertRaisesRegex(ValueError, 'degenerate.*testShape'):
            maps.intersection_uv(mesh, np.zeros((1, 2, 3)), [0], style)

    def test_missing_uv_does_not_fail_an_unmapped_face(self):
        mesh, prepared, style = fixture()
        mesh['_brush_map_uvs'][''] = maps.build_uv_lookup(mesh, [3, 3], [0, 1, 2, 1, 3, 2],
                                                        [3, 0], [0, 1, 2], [[0., 0.], [1., 0.], [0., 1.]])
        maps.edge_uv(mesh, prepared, [1], style)
        with self.assertRaisesRegex(ValueError, 'missing or invalid.*testShape'):
            maps.intersection_uv(mesh, np.zeros((1, 2, 3)), [1], style)

    def test_missing_export_is_explicit(self):
        mesh, prepared, style = fixture()
        del mesh['_brush_map_uvs']
        with self.assertRaisesRegex(ValueError, 'not exported.*testShape'):
            maps.edge_uv(mesh, prepared, [0], style)

    def test_packed_edges_preserve_uv_and_mapped_arrays(self):
        mesh, prepared, style = fixture()
        packed = PackedSegments()
        packed.add_edges(mesh, 0, prepared, [0, 1], np.array([4, 2], np.uint8), style, 'line')
        part = packed.parts[0]
        part['mapped_widths'] = np.array([1., 2.])
        part['mapped_colors'] = np.array([[1., 0., 0.], [0., 0., 1.]])
        _, widths, _, colors, _, _ = packed.arrays()
        np.testing.assert_array_equal(widths, [1., 2.])
        np.testing.assert_array_equal(colors, part['mapped_colors'])
        row = packed[1]
        self.assertEqual(row['_mapped_width'], 2.)
        np.testing.assert_array_equal(row['_map_uvs'][''], [[0., 0.], [1., 0.]])
        self.assertIs(row['settings'], style)

    def test_packed_intersection_column(self):
        mesh, _, style = fixture()
        rows = np.array([[1., 1., 0., 1.5, .5, 0., 0, 1]])
        packed = PackedSegments()
        packed.add_intersections(mesh, 0, rows, style, 'line', triangle_column=7)
        np.testing.assert_allclose(packed.parts[0]['map_uvs'][''], [[[2., .5], [2., .25]]])

    def test_export_named_and_default_uvs_share_one_lookup(self):
        mesh, _, style = fixture()
        style['brush_maps']['width'] = {'uv_set': 'map1'}
        fn = SimpleNamespace(numVertices=4, numPolygons=2, getVertices=lambda: ([3, 3], [0, 1, 2, 1, 3, 2]),
                             getUVSetNames=lambda: ['map1'], currentUVSetName=lambda: 'map1',
                             getAssignedUVs=lambda name: ([3, 3], [0, 1, 2, 3, 4, 5]),
                             getUVs=lambda name: ([0., 1., 0., 2., 3., 2.], [0., 0., 1., 0., 1., 1.]))
        with patch.dict(sys.modules, {'reatoon.alpha_boundary': SimpleNamespace(_texture_fn=lambda *args: (fn, None))}):
            maps.export_uv_sets(mesh, None, {}, style)
        self.assertIs(mesh['_brush_map_uvs'][''], mesh['_brush_map_uvs']['map1'])

    def test_alpha_contour_uv_uses_the_same_barycentric_binding(self):
        from reatoon.cpu_alpha import append_boundaries
        mesh, _, style = fixture()
        style['open_edges'] = True
        bary = np.array([[[.75, .25, 0.], [.25, .25, .5]]])
        region = SimpleNamespace(boundary=lambda *args: bary)
        mesh['_cpu_alpha'] = SimpleNamespace(lookup=np.array([0, -1]), masks=np.array([0]),
                                             uv=np.array([[[0., 0.], [1., 0.], [0., 1.]]]),
                                             wrap=np.array([False]), regions=[region])
        packed = PackedSegments()
        camera = dict(eye=np.array([0., 0., -5.]), basis=np.eye(3), ortho=True,
                      width=64, height=64, span=4., near=.1, far=100.)
        append_boundaries(mesh, 0, [0, 0], [style], 'line', packed, camera)
        self.assertEqual(len(packed), 1)
        np.testing.assert_allclose(packed.parts[0]['map_uvs'][''], [[[.25, 0.], [.25, .5]]])

    def test_alpha_clipped_edge_interpolates_uv_at_clipped_endpoints(self):
        from reatoon.cpu_alpha import clip_edges
        mesh, _, style = fixture()
        region = SimpleNamespace(intervals=lambda *args: [(0.2, 0.8)])
        mesh['_cpu_alpha'] = SimpleNamespace(lookup=np.array([0, -1]), masks=np.array([0]),
                                             uv=np.array([[[0., 0.], [1., 0.], [0., 1.]]]),
                                             wrap=np.array([False]), regions=[region])
        prepared = dict(vertices=np.asarray(mesh['vertices']), pairs=np.array([[0, 1]]),
                        starts=np.array([0]), counts=np.array([1]), owners=np.array([0]))
        packed = PackedSegments()
        unmasked = clip_edges(mesh, prepared, np.array([0]), np.array([2], np.uint8), style, 'line', 0, packed)
        self.assertEqual(len(unmasked), 0)
        np.testing.assert_allclose(packed.parts[0]['map_uvs'][''], [[[.2, 0.], [.8, 0.]]])


if __name__ == '__main__':
    unittest.main()
