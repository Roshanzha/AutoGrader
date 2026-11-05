"""Validate uploaded test data without accepting executable grading configuration."""
import hashlib
import json
from pathlib import Path


class TestUploadError(ValueError):
    pass


def load_test_files(paths):
    if not paths:
        return []
    if len(paths) > 10:
        raise TestUploadError('Upload at most 10 JSON files.')
    tests = []
    for index, filename in enumerate(paths, 1):
        path = Path(filename)
        if path.suffix.lower() != '.json' or path.stat().st_size > 1024 * 1024:
            raise TestUploadError(f'{path.name}: use a JSON file smaller than 1 MB.')
        try:
            raw = path.read_bytes()
            data = json.loads(raw.decode('utf-8-sig'))
        except (ValueError, UnicodeError) as exc:
            raise TestUploadError(f'{path.name}: invalid UTF-8 JSON.') from exc
        cases = data.get('tests') if isinstance(data, dict) else data
        if not isinstance(cases, list) or not cases:
            raise TestUploadError(f'{path.name}: expected a non-empty tests array.')
        for number, case in enumerate(cases, 1):
            if not isinstance(case, dict) or not all(isinstance(case.get(k), str) for k in ('input', 'expected')):
                raise TestUploadError(f'{path.name}, test {number}: input and expected must be strings.')
            if any(len(case[k].encode('utf-8')) > 16384 for k in ('input', 'expected')):
                raise TestUploadError(f'{path.name}, test {number}: input and expected must each be at most 16 KB.')
            if len(tests) >= 100:
                raise TestUploadError('Upload at most 100 test cases in total.')
            tests.append({'id': f'{index:02d}-{number:03d}', 'file': path.name,
                          'suite': f'{index}. {path.name}', 'input': case['input'],
                          'expected': case['expected'], 'file_sha256': hashlib.sha256(raw).hexdigest()})
    return tests
