"""Regressions for mapped CPU stroke coverage, provenance and channel routing."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from reatoon import brush_maps, stroke_presets, renderer
from reatoon.packed_segments import PackedSegments
from reatoon.cpu_brush import _clip_packed_depth


def camera(ortho=True):
    return dict(eye=np.zeros(3), basis=np.eye(3), ortho=ortho, width=256, height=128,
                span=4., focal=128., near=.1, far=100.)


def texture():
    axis = (np.arange(256)+.5)/256
    pixels = np.tile(np.repeat(axis[None, :, None], 3, axis=2), (256, 1, 1)).astype(np.float32)
    return {'r': {'pixels': pixels, 'repeat': False}}


def style(**changes):
    result = dict(renderer.DEFAULTS, line_width=20., line_color=[0., 0., 0.],
                  brush_maps={'color': {'texture_id': 'r', 'enabled': True, 'amount': 1.}})
    result.update(changes)
    return result


def packed(points=None, settings=None):
    result = PackedSegments()
    result.parts = [dict(points=np.asarray([points or [[-1., 0., 2.], [1., 0., 2.]]]),
                        flags=np.array([4], np.uint8), settings=settings or style(),
                        mesh='mapped', mesh_index=0, line=None, count=1,
                        map_uvs={'': np.array([[[0., .5], [1., .5]]])})]
    result.count = 1
    return result


def render(source, view):
    layer = np.zeros((view['height'], view['width'], 4), np.float32)
    depth = np.full(layer.shape[:2], np.inf)
    planes = np.zeros(layer.shape[:2]+(3,))
    stats = brush_maps.render(source, view, depth, planes, layer, 1, texture())
    return layer, stats


class MapNativeTests(unittest.TestCase):
    def test_thick_color_map_uses_current_uv_not_earlier_piece_cap(self):
        image, stats = render(packed(), camera())
        x = np.array([80, 100, 128, 150, 175])
        expected = (x+.5-64)/128
        np.testing.assert_allclose(image[64, x, 0], expected, atol=.005)
        np.testing.assert_allclose(image[64, 64:192, 3], 1., atol=1e-6)
        self.assertLessEqual(stats['peak_map_batch'], brush_maps.BATCH_SIZE)

    def test_perspective_color_map_uses_surface_uv(self):
        view = camera(False)
        image, _ = render(packed([[-1., 0., 2.], [1., 0., 6.]]), view)
        x = np.array([90, 110, 130])
        start, end = 64., 128.+128./6.
        t = (x+.5-start)/(end-start)
        expected = (t/6.)/((1-t)/2.+t/6.)
        np.testing.assert_allclose(image[64, x, 0], expected, atol=.008)
        np.testing.assert_allclose(image[64, x, 3], 1., atol=1e-6)

    def test_outer_caps_remain_round_and_opaque(self):
        image, _ = render(packed(), camera())
        self.assertGreater(image[64, 59, 3], .99)
        self.assertGreater(image[64, 196, 3], .99)
        self.assertEqual(image[64, 52, 3], 0.)
        self.assertEqual(image[64, 204, 3], 0.)
        # The corner outside a circular cap must remain clear.
        self.assertLess(image[55, 55, 3], .01)

    def test_mapped_rough_and_clean_features_remain_packed(self):
        source = packed(settings=style(brush_preset=1))
        clean = dict(source.parts[0], points=np.array([[[-1., .5, 2.], [1., .5, 2.]]]),
                     settings=dict(renderer.DEFAULTS))
        clean.pop('map_uvs')
        source.parts.append(clean)
        source.count += 1
        expanded = stroke_presets.cpu_segments(source, camera(), 1)
        expanded._flush()
        self.assertFalse(any('records' in part for part in expanded.parts))
        self.assertTrue(any('map_uvs' in part for part in expanded.parts))
        self.assertTrue(any(not part['settings'].get('brush_maps') for part in expanded.parts))

    def test_shared_maps_with_hidden_lines_get_independent_channels(self):
        mesh = dict(vertices=[[0., 0., 2.], [1., 0., 2.], [0., 1., 2.]], faces=[[0, 1, 2]])
        passes = renderer.line_style_passes({'meshes': [mesh]}, style(hidden_lines=True, _cpu_brush_channels=True))
        resolved = passes[0]['styles'][0]
        channels = resolved.get('_brush_channels', [])
        self.assertEqual(len(channels), 2)
        self.assertEqual({c['settings']['_visibility_mode'] for c in channels}, {-1, 1})

    def test_profile_crossing_camera_plane_stays_finite(self):
        curve = [[0., 0., 0., 0., .5, 0., 0.], [0., 0., 0., 1., 1., 0., 0.]]
        source = packed([[1., 0., 0.], [0., 0., 2.]], style(width_profile=curve))
        view = camera(False)
        original = brush_maps.coordinates
        checked = []
        def verify(part_source, part_view):
            original(part_source, part_view)
            self.assertTrue(all(np.isfinite(part['profile_u']).all() for part in part_source.parts))
            self.assertTrue(all(np.isfinite(uv).all() for part in part_source.parts for uv in part['map_uvs'].values()))
            checked.append(True)
        with patch.object(brush_maps, 'coordinates', side_effect=verify):
            image, _ = render(source, view)
        self.assertTrue(checked)
        self.assertTrue(np.isfinite(image).all())
        self.assertGreater(float(image[..., 3].sum()), 1.)


if __name__ == '__main__':
    unittest.main()
