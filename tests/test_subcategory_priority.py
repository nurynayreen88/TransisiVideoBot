import unittest
from prompt_engine import _category_specific_scenes

class SubtypeTests(unittest.TestCase):
    def test_handbag(self):
        scenes = _category_specific_scenes('bag', 'BONIA', 'bag_handbag')
        self.assertNotIn('WALLET', scenes[0][0])
    def test_wallet(self):
        scenes = _category_specific_scenes('bag', 'BONIA', 'bag_wallet')
        self.assertIn('WALLET', scenes[0][0])
    def test_explicit_subtype_wins(self):
        scenes = _category_specific_scenes('bag', 'BONIA wallet collection', 'bag_handbag')
        self.assertNotIn('WALLET', scenes[0][0])

if __name__ == '__main__':
    unittest.main()
