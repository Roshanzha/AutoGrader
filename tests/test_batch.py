import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import front_app


class BatchTests(unittest.TestCase):
    def test_errors_do_not_stop_batch_and_duplicate_names_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = []
            for name in ['first', 'second']:
                folder = root/name
                folder.mkdir()
                source = folder/'add.c'
                source.write_text('int main(void){return 0;}')
                sources.append(str(source))
            artifact = root/'add.txt'
            artifact.write_text('Example report')
            report = {'grade': 50.0, 'partial': False}
            with patch.object(front_app, 'BASE_DIR', directory), patch.object(front_app, 'list_rule_files', return_value=['preset.json']), patch.object(front_app.result_analysis, 'render_batch', return_value='batch'), patch.object(front_app, 'run_grading', side_effect=[('ok', report, [str(artifact)], ''), ('bad', None, None, '')]) as grade:
                _, data, files, _ = front_app.run_batch(sources, 'preset.json')
                self.assertEqual(grade.call_count, 2)
                self.assertEqual([e['status'] for e in data['submissions']], ['Complete','Error'])
                with zipfile.ZipFile(files[0]) as archive:
                    self.assertIn('01_add/add.txt', archive.namelist())
                    self.assertIn('batch_scores.csv', archive.namelist())
                grade.side_effect = [('ok', report, [str(artifact)], '')]*2
                _, _, files, _ = front_app.run_batch(sources, 'preset.json')
                with zipfile.ZipFile(files[0]) as archive:
                    self.assertIn('01_add/add.txt', archive.namelist())
                    self.assertIn('02_add/add.txt', archive.namelist())

    def test_empty_and_oversize_batch_rejected_before_grading(self):
        with patch.object(front_app, 'run_grading') as grade:
            self.assertIsNone(front_app.run_batch([], 'agentic_ai.json')[1])
            self.assertIsNone(front_app.run_batch(['add.c']*21, 'agentic_ai.json')[1])
            grade.assert_not_called()
