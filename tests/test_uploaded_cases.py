"""Run with python -m unittest discover -s tests inside the project environment."""
import json
import tempfile
import unittest
from pathlib import Path
from test_uploads import load_test_files, TestUploadError


class UploadedCases(unittest.TestCase):
    def test_multiple_files_and_duplicate_names_keep_distinct_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for sub in ('one', 'two'):
                path = Path(folder, sub, 'tests.json')
                path.parent.mkdir()
                path.write_text(json.dumps({'tests': [{'input': '1 2', 'expected': '3'}]}))
                paths.append(str(path))
            tests = load_test_files(paths)
            self.assertEqual(len(tests), 2)
            self.assertNotEqual(tests[0]['id'], tests[1]['id'])
            self.assertNotEqual(tests[0]['suite'], tests[1]['suite'])
            self.assertEqual(len(tests[0]['file_sha256']), 64)

    def test_invalid_empty_and_excessive_cases_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'invalid.json')
            for value in ({'metrics': []}, {'tests': []}, [{'input': 2, 'expected': '2'}],
                          [{'input': 'x'*16385, 'expected': ''}],
                          [{'input': '', 'expected': ''}]*101):
                path.write_text(json.dumps(value))
                with self.assertRaises(TestUploadError):
                    load_test_files([str(path)])
            path.write_text('{')
            with self.assertRaises(TestUploadError):
                load_test_files([str(path)])


if __name__ == '__main__':
    unittest.main()
