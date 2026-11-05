import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from front_app import run_grading

with tempfile.TemporaryDirectory() as directory:
    extra = Path(directory, 'extra.json')
    extra.write_text(json.dumps({'tests': [{'input': '4 5\n', 'expected': '999\n'}]}))
    files = ['examples/tests/basic.json', str(extra)]
    text, report, outputs, html = run_grading('problems/agentic_ai/add.c', 'agentic_ai.json', files)
    assert report, text
    correctness = next(m for m in report['metrics'] if m['analyzer']=='io_tests')
    assert correctness['evidence']['tests_passed']==2
    assert correctness['evidence']['tests_total']==3
    assert len(correctness['evidence']['uploaded_suites'])==2
    assert len(report['uploaded_tests'])==3
    assert 'gg-pie' in html and 'extra.json' in html and '66.7%' not in html
    assert '0.0%' in html and '100.0%' in html
    assert len(outputs)==3 and all(Path(p).is_file() for p in outputs)
    assert html in Path(next(p for p in outputs if p.endswith('.html'))).read_text()
    first_outputs=outputs
    text, partial, outputs, html = run_grading('samples/add_infinite_loop.c','agentic_ai.json',files)
    assert partial and partial['partial'], text
    assert 'results are unavailable' in html and 'Unmeasured / skipped' in html
    assert outputs!=first_outputs and all(Path(p).is_file() for p in first_outputs)
    extra.write_text('{"tests": []}')
    text, report, outputs, html = run_grading('problems/agentic_ai/add.c','agentic_ai.json',[str(extra)])
    assert 'Test upload error:' in text and report is None and not html
    print('Mixed-file grading, per-file pass counts, partial grades, exports and invalid uploads verified.')
