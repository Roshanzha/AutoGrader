import sys, tempfile, zipfile
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from front_app import run_batch
with tempfile.TemporaryDirectory() as folder:
    broken=Path(folder,'add.c')
    broken.write_text('int main( { this is invalid C; }')
    text, summary, files, html=run_batch(['problems/agentic_ai/add.c',str(broken)],'agentic_ai.json',['examples/tests/basic.json','examples/tests/negative.json'])
    assert summary, text
    assert [e['status'] for e in summary['submissions']]==['Complete','Partial'],summary
    assert summary['submissions'][1]['report']['first_pass']['compiled'] is False
    assert 'Batch results' in html and html.count('class="gg-pie"')==2
    with zipfile.ZipFile(files[0]) as z:
        assert z.testzip() is None
        assert all(f'{i:02d}_add/add.{ext}' in z.namelist() for i in [1,2] for ext in ['html','json','txt'])
    print('Batch grading verified: valid + compile-failing submissions, shared JSON cases, separate reports and ZIP.')
