from pathlib import Path
import struct
import tempfile
import unittest

from core.exifRead import read_exif

ROOT = Path(__file__).resolve().parents[1]


class ExifTests(unittest.TestCase):
    def test_reads_local_tiff_datetime_without_network(self):
        date = b'2026:10:23 12:34:56\x00'
        # Little endian TIFF with one ASCII DateTime entry and no image payload.
        header = b'II' + struct.pack('<HI', 42, 8)
        entry = struct.pack('<HHII', 0x0132, 2, len(date), 26)
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            image = Path(directory) / 'test.tiff'
            image.write_bytes(header + struct.pack('<H', 1) + entry + struct.pack('<I', 0) + date)
            before = image.read_bytes()
            tags = read_exif(image)
            self.assertEqual(tags['Image DateTime'], '2026:10:23 12:34:56')
            self.assertEqual(image.read_bytes(), before)

    def test_rejects_non_image_extension_and_missing_file(self):
        with self.assertRaises(ValueError):
            read_exif(ROOT / 'README.md')
        with self.assertRaises(ValueError):
            read_exif(ROOT / '.work' / 'missing.tiff')


if __name__ == '__main__':
    unittest.main()
