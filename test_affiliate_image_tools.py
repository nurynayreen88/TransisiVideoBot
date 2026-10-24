import unittest
from io import BytesIO
from PIL import Image
from affiliate_image_tools import render, SIZES

def sample(color):
    im = Image.new('RGB', (320, 240), color)
    out = BytesIO()
    im.save(out, format='PNG')
    return out.getvalue()

class AffiliateImageToolsTests(unittest.TestCase):
    def test_all_tools_and_ratios(self):
        a, b = sample('red'), sample('blue')
        for tool in ('cover', 'sticker', 'resize', 'compare'):
            for ratio, size in SIZES.items():
                with self.subTest(tool=tool, ratio=ratio):
                    result = render(tool, [a,b] if tool == 'compare' else [a], 'RM19.90' if tool in ('cover','sticker') else '', ratio)
                    with Image.open(result) as im:
                        self.assertEqual(im.size, size)
                        self.assertEqual(im.format, 'JPEG')
    def test_reject_invalid_inputs(self):
        with self.assertRaises(ValueError):
            render('resize', [b'not an image'])
        with self.assertRaises(ValueError):
            render('compare', [sample('red')])
        with self.assertRaises(ValueError):
            render('resize', [sample('red')], ratio='invalid')
        with self.assertRaises(ValueError):
            render('sticker', [sample('red')], value='')

if __name__ == '__main__':
    unittest.main()
