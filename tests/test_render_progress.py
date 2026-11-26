import unittest
from reatoon import render_progress


class Commands:
    def __init__(self, owned=True):
        self.calls=[];self.owned=owned
    def about(self, **kwargs):return False
    def optionVar(self, **kwargs):return False

class Window:
    def __init__(self, english):self.calls=[];self.closed=False
    def update(self, percent, status):self.calls.append(dict(progress=percent,status=status))
    def close(self):self.closed=True


class RenderProgressTests(unittest.TestCase):
    def test_progress_is_stage_specific_and_throttled(self):
        cmds=Commands();clock=[0.]
        with render_progress.RenderProgress(cmds,lambda:clock[0],Window) as p:
            cmds.calls=p.window.calls
            p('strokes',25,100,'tree')
            self.assertEqual(cmds.calls[-1]['progress'],25)
            self.assertIn('25 / 100',cmds.calls[-1]['status'])
            count=len(cmds.calls);p('strokes',50,100)
            self.assertEqual(len(cmds.calls),count)
            clock[0]=2.5;p('strokes',50,100)
            self.assertEqual(cmds.calls[-1]['progress'],50)
            self.assertIn('0:02',cmds.calls[-1]['status'])
            p('output')
            self.assertIn('계산 중',cmds.calls[-1]['status'])
        self.assertTrue(p.window.closed)

    def test_exception_closes_only_owned_window_and_allows_next_render(self):
        cmds=Commands()
        with self.assertRaises(ValueError):
            with render_progress.RenderProgress(cmds,window_factory=Window) as p:raise ValueError('bad scene')
        self.assertFalse(render_progress._ACTIVE)
        self.assertTrue(p.window.closed)
        other=Commands();other.about=lambda **kwargs:True
        with render_progress.RenderProgress(other,window_factory=Window) as q:pass
        self.assertIsNone(q.window)

    def test_reentrant_render_cannot_clear_outer_guard(self):
        with render_progress.RenderProgress(Commands(),window_factory=Window):
            with self.assertRaises(RuntimeError):
                with render_progress.RenderProgress(Commands(),window_factory=Window):pass
            self.assertTrue(render_progress._ACTIVE)
        self.assertFalse(render_progress._ACTIVE)
