import unittest
from unittest.mock import patch
from reatoon import i18n
class LanguageTests(unittest.TestCase):
    def test_both_languages_and_legacy_mixed_labels(self):
        with patch.object(i18n,'language',return_value='en'):
            self.assertEqual(i18n.tr('업데이트 확인…'),'Check for Updates…')
            self.assertEqual(i18n.tr('Alpha Boundary / 알파 경계선'),'Alpha Boundary')
            self.assertEqual(i18n.tr('장면 기본값'),'Scene defaults')
        with patch.object(i18n,'language',return_value='ko'):
            self.assertEqual(i18n.tr('Anti-aliasing'),'안티앨리어싱')
            self.assertEqual(i18n.tr('Open Line Window'),'라인 창 열기')
            self.assertNotIn('Edge detection',i18n.tr('Line types'))
    def test_identifiers_and_nested_labels(self):
        for lang in ('ko','en'):
            with patch.object(i18n,'language',return_value=lang):
                self.assertEqual(i18n.tr('Root_Ctrl.rotateY'),'Root_Ctrl.rotateY')
                self.assertEqual(i18n.tr(17),17)
                self.assertIsInstance(i18n.tr(('Line Types','Brush')),tuple)
    def test_live_roundtrip(self):
        for key in ('Open Line Window','Brush settings','Anti-aliasing','Scene defaults'):
            with patch.object(i18n,'language',return_value='ko'):ko=i18n.tr(key)
            with patch.object(i18n,'language',return_value='en'):self.assertEqual(i18n.tr(ko),key)
