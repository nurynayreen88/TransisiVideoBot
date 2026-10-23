import unittest
from prompt_engine import _category_specific_scenes

class SubtypeTests(unittest.TestCase):
    def test_handbag(self):
        scenes = _category_specific_scenes('bag', 'BONIA', 'bag_handbag')
        self.assertNotIn('WALLET', scenes[0][0])
    def test_selected_handbag_is_handbag(self):
        scenes = _category_specific_scenes('bag', 'BONIA wallet collection', 'bag_handbag')
        self.assertIn('HANDBAG', scenes[0][0])

    def test_tote_not_forced_to_handbag(self):
        scenes = _category_specific_scenes('bag', 'Tote bag', 'bag_tote')
        self.assertNotIn('HANDBAG', scenes[0][0])

    def test_kitchen_keyword_does_not_override_other_home_subtype(self):
        scenes = _category_specific_scenes('home', 'Pan set organizer', 'home_storage')
        self.assertNotIn('COMPLETE SET', scenes[0][0])

    def test_wallet(self):
        scenes = _category_specific_scenes('bag', 'BONIA', 'bag_wallet')
        self.assertIn('WALLET', scenes[0][0])
    def test_explicit_subtype_wins(self):
        scenes = _category_specific_scenes('bag', 'BONIA wallet collection', 'bag_handbag')
        self.assertNotIn('WALLET', scenes[0][0])

if __name__ == '__main__':
    unittest.main()
