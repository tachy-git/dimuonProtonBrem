"""Data preservation and preparation checks; no CMSSW or Condor submission needed."""
import contextlib
import csv
import importlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import settings
import submit_condor_jobs
import submit_custom_miniaod_jobs
from split_background_npy import split_sources


class BackgroundWorkflowTest(unittest.TestCase):
    def setUp(self):
        importlib.reload(settings)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(importlib.reload, settings)
        self.root = Path(self.temp.name)

    def save(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, data)
        return path

    def test_split_preserves_data_reuses_and_rejects_conflicts(self):
        data = np.arange(2001 * 13, dtype=np.float32).reshape(2001, 13)
        source = self.save('source/eta_221_ECal/sample.npy', data)
        self.save('source/eta_221_ECal/empty.npy', np.empty((0, 13)))
        output = self.root / 'chunks'
        with contextlib.redirect_stdout(io.StringIO()):
            summary = split_sources(self.root / 'source', output)
        chunks = [output / 'eta_221_ECal/sample' / f'Events_{i}.npy' for i in range(3)]
        self.assertEqual(summary, dict(files=2, empty=1, rows=2001, chunks=3))
        self.assertEqual([np.load(p).shape[0] for p in chunks], [1000, 1000, 1])
        np.testing.assert_array_equal(np.concatenate([np.load(p) for p in chunks]), data)
        self.assertEqual(np.load(chunks[0]).dtype, data.dtype)
        with (output / "npy_chunks_manifest.csv").open() as handle:
            manifest = list(csv.DictReader(handle))
        self.assertEqual([r['row_start'] for r in manifest if r['output']], ['0', '1000', '2000'])
        mtimes = [p.stat().st_mtime_ns for p in chunks]
        with contextlib.redirect_stdout(io.StringIO()):
            split_sources(self.root / 'source', output)
        self.assertEqual(mtimes, [p.stat().st_mtime_ns for p in chunks])
        changed = np.load(chunks[1]); changed[0, 0] += 1; np.save(chunks[1], changed)
        with self.assertRaisesRegex(ValueError, 'conflicting existing chunk'):
            split_sources(self.root / 'source', output)
        np.testing.assert_array_equal(np.load(source), data)

    def test_manifest_retains_unselected_categories_and_replaces_selected_rows(self):
        self.save('source/eta_continuum_HCal/old.npy', np.ones((2, 13)))
        self.save('source/phi_333_HCal/new.npy', np.ones((1001, 13)))
        source, output = self.root / 'source', self.root / 'chunks'
        with contextlib.redirect_stdout(io.StringIO()):
            split_sources(source, output, category_patterns=['eta_continuum_HCal'])
        manifest = output / 'npy_chunks_manifest.csv'
        with manifest.open() as handle:
            old = list(csv.DictReader(handle))
        for _ in range(2):
            with contextlib.redirect_stdout(io.StringIO()):
                split_sources(source, output, category_patterns=['phi_333_HCal'])
            with manifest.open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([r for r in rows if 'eta_continuum_HCal' in r['source']], old)
            self.assertEqual(len(rows), 3)
            self.assertEqual(sum(int(r['row_stop']) - int(r['row_start']) for r in rows), 1003)
        original = manifest.read_bytes()
        chunk = output / 'phi_333_HCal/new/Events_0.npy'
        np.save(chunk, np.zeros((1000, 13)))
        with self.assertRaisesRegex(ValueError, 'conflicting existing chunk'):
            split_sources(source, output, category_patterns=['phi_333_HCal'])
        self.assertEqual(manifest.read_bytes(), original)

    def test_category_cap_skips_empty_sources_and_limits_rows(self):
        self.save('source/eta_221_ECal/a_empty.npy', np.empty((0, 13)))
        self.save('source/eta_221_ECal/b_first.npy', np.ones((2500, 13)))
        self.save('source/eta_221_ECal/c_later.npy', np.ones((4000, 13)))
        self.save('source/rho_113_ECal/a_first.npy', np.ones((2000, 13)))
        with contextlib.redirect_stdout(io.StringIO()):
            summary = split_sources(self.root / 'source', self.root / 'chunks', max_chunks_per_category=1)
        self.assertEqual(summary['rows'], 2000)
        self.assertEqual(summary['chunks'], 2)
        self.assertEqual(len(list((self.root / 'chunks').rglob('*.npy'))), 2)

    def test_per_source_cap_and_category_filter(self):
        for name in ('a', 'b'):
            self.save(f'source/eta_continuum_HCal/{name}.npy', np.ones((2500, 13)))
        self.save('source/eta_continuum_ECal/other.npy', np.ones((3000, 13)))
        with contextlib.redirect_stdout(io.StringIO()):
            summary = split_sources(self.root / 'source', self.root / 'chunks',
                                    max_chunks_per_source=2, category_patterns=['eta_continuum_HCal'])
        self.assertEqual(summary['rows'], 4000)
        self.assertEqual(summary['chunks'], 4)
        self.assertFalse((self.root / 'chunks/eta_continuum_ECal').exists())

    def test_nested_chunks_are_reused_and_never_read_as_originals(self):
        data = np.arange(2001 * 13, dtype=np.float64).reshape(2001, 13)
        source = self.save('source/eta_continuum_HCal/sample.npy', data)
        output = self.root / 'source/chunks'
        with contextlib.redirect_stdout(io.StringIO()):
            split_sources(self.root / 'source', output)
        paths = sorted((output / 'eta_continuum_HCal/sample').glob('*.npy'))
        mtimes = [p.stat().st_mtime_ns for p in paths]
        # Even a loose NPY in the reserved chunks directory is not an original.
        self.save('source/chunks/stray.npy', np.ones((5, 13)))
        with contextlib.redirect_stdout(io.StringIO()):
            summary = split_sources(self.root / 'source', output)
        self.assertEqual(summary, dict(files=1, empty=0, rows=2001, chunks=3))
        self.assertEqual(mtimes, [p.stat().st_mtime_ns for p in paths])
        np.testing.assert_array_equal(np.load(source), data)
        np.testing.assert_array_equal(np.concatenate([np.load(p) for p in paths]), data)

    def test_output_cannot_overlap_original_categories_or_source_ancestors(self):
        source = self.root / 'source'
        self.save('source/eta_continuum_HCal/sample.npy', np.ones((1, 13)))
        for output in (source, source.parent, source / 'eta_continuum_HCal'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                split_sources(source, output)

    def test_empty_and_column_validation(self):
        empty = self.save('empty.npy', np.empty((0, 13)))
        self.assertEqual(submit_condor_jobs.inspect_npy(empty, 'background', True)[0], 0)
        with self.assertRaises(ValueError):
            submit_condor_jobs.inspect_npy(empty, 'background')
        background = self.save('bkg.npy', np.ones((2, 13)))
        self.assertEqual(submit_condor_jobs.inspect_npy(background, 'background')[1], 13)
        with self.assertRaises(ValueError):
            submit_condor_jobs.inspect_npy(background, 'signal')
        with background.open('ab') as handle:
            handle.write(b'bad')
        with self.assertRaisesRegex(ValueError, 'file size'):
            submit_condor_jobs.inspect_npy(background, 'background')

    def test_background_preparation_and_custom_roundtrip(self):
        a = self.save('chunks/eta_221_ECal/source_a/Events_0.npy', np.ones((2, 13)))
        self.save('chunks/eta_221_ECal/source_a/Events_1.npy', np.ones((3, 13)))
        b = self.save('chunks/rho_113_ECal/source_b/Events_0.npy', np.ones((4, 13)))
        settings.BACKGROUND["category_patterns"] = ["*"]
        settings.BACKGROUND["npy_directory"] = str(self.root / 'chunks')
        settings.BACKGROUND["output_directory"] = str(self.root / 'production')
        settings.BACKGROUND['custom_raw_directory'] = str(self.root / 'production/gen_sim_raw')
        settings.BACKGROUND['custom_output_directory'] = str(self.root / 'production')
        settings.COMMON["cmssw14_src"] = settings.COMMON["cmssw15_src"] = settings.COMMON["cmssw16_src"] = str(self.root)
        with patch.object(sys, 'argv', ['submit_condor_jobs.py', '--background']), patch('subprocess.run') as submit, contextlib.redirect_stdout(io.StringIO()):
            submit_condor_jobs.main()
            submit.assert_not_called()
        args = self.root / 'production/sub/dimuon_proton_brem_jobs.args'
        rows = [line.split() for line in args.read_text().splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(len(row) == 14 and row[-1] == 'background' and float(row[1]) == 1800 for row in rows))
        self.assertEqual(rows[0][0], str(a))
        self.assertEqual(rows[-1][0], str(b))
        self.assertEqual(int(rows[0][4]), settings.BACKGROUND['base_seed'])
        self.assertEqual(settings.COMMON['base_seed'], 42)
        for row in rows:
            setting = row[2].rsplit('__chunk', 1)[0] + '_lxy1800'
            raw = self.root / 'production/gen_sim_raw' / setting / Path(row[0]).with_suffix('.root').name
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_bytes(b'fixture')
        with patch.object(sys, 'argv', ['submit_custom_miniaod_jobs.py', '--background']), patch('subprocess.run') as submit, contextlib.redirect_stdout(io.StringIO()):
            submit_custom_miniaod_jobs.main()
            submit.assert_not_called()
        custom = self.root / 'production/sub/dimuon_proton_brem_custom_miniaod_jobs.args'
        self.assertEqual([r.split()[0] for r in custom.read_text().splitlines()], [r[0] for r in rows])
        self.assertEqual(int(custom.read_text().splitlines()[0].split()[4]), settings.BACKGROUND['base_seed'])
        with patch.object(sys, 'argv', ['submit_condor_jobs.py', '--background', '--max-jobs-per-category', '1']), patch('subprocess.run'), contextlib.redirect_stdout(io.StringIO()):
            submit_condor_jobs.main()
        self.assertEqual(len(args.read_text().splitlines()), 2)

    def test_relative_paths_and_runner_locations(self):
        self.configure_signal()
        workflow_root = Path(submit_condor_jobs.__file__).resolve().parent.parent
        self.save('signal/barrel_m_2.0_GeV/Events_0.npy', np.ones((2, 17)))
        for key in ('npy_directory', 'output_directory'):
            settings.SIGNAL[key] = os.path.relpath(settings.SIGNAL[key], workflow_root)
        settings.SIGNAL['max_chunks_by_lxy'] = {1800.0: None}
        with patch.object(sys, 'argv', ['submit_condor_jobs.py']), patch('subprocess.run') as submit, contextlib.redirect_stdout(io.StringIO()):
            submit_condor_jobs.main()
            submit.assert_not_called()
        raw = self.root / 'output/gen_sim_raw/barrel_m_2.0_GeV_lxy1800/Events_0.root'
        raw.parent.mkdir(parents=True)
        raw.write_bytes(b'fixture')
        settings.SIGNAL['custom_raw_directory'] = os.path.relpath(raw.parent.parent, workflow_root)
        settings.SIGNAL['custom_output_directory'] = settings.SIGNAL['output_directory']
        with patch.object(sys, 'argv', ['submit_custom_miniaod_jobs.py']), patch('subprocess.run') as submit, contextlib.redirect_stdout(io.StringIO()):
            submit_custom_miniaod_jobs.main()
            submit.assert_not_called()
        for prefix, runner in (('dimuon_proton_brem', 'run_condor_job.sh'),
                               ('dimuon_proton_brem_custom_miniaod', 'run_custom_miniaod_job.sh')):
            submission = (self.root / 'output/sub' / (prefix + '_jobs.sub')).read_text()
            self.assertIn(f'executable = {workflow_root / "script" / runner}', submission)
            args = (self.root / 'output/sub' / (prefix + '_jobs.args')).read_text().split()
            self.assertEqual(args[0], str(self.root / 'signal/barrel_m_2.0_GeV/Events_0.npy'))
            self.assertEqual(args[5], str(self.root / 'output'))

    def test_signal_job_preparation_retains_original_paths(self):
        source = self.save('signal/barrel_m_2.0_GeV/Events_0.npy', np.ones((2, 17)))
        settings.SIGNAL.update({
            'npy_directory': str(self.root / 'signal'),
            'output_directory': str(self.root / 'signal_output'),
            'submit_jobs': False,
            'category_patterns': ['barrel_m_2.0*_GeV'],
            'max_chunks_by_lxy': {3300.0: None, 3800.0: None},
        })
        settings.COMMON["cmssw14_src"] = settings.COMMON["cmssw15_src"] = settings.COMMON["cmssw16_src"] = str(self.root)
        with patch.object(sys, 'argv', ['submit_condor_jobs.py']), patch('subprocess.run') as submit, contextlib.redirect_stdout(io.StringIO()):
            submit_condor_jobs.main()
            submit.assert_not_called()
        args = self.root / 'signal_output/sub/dimuon_proton_brem_jobs.args'
        rows = [line.split() for line in args.read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r[-1] == 'signal' and r[0] == str(source) for r in rows))
        self.assertEqual({float(r[1]) for r in rows}, {3300., 3800.})
        self.assertTrue(all(r[2].startswith('barrel_m_2.0_GeV__chunk0000_') for r in rows))

    def test_default_signal_and_exclusive_flags(self):
        import argparse
        parser = argparse.ArgumentParser()
        submit_condor_jobs.add_sample_arguments(parser)
        self.assertFalse(parser.parse_args([]).background)
        self.assertTrue(parser.parse_args(['--signal']).signal)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(['--signal', '--background'])
        self.assertIsNot(settings.SIGNAL, settings.BACKGROUND)
        self.assertNotIn('sample_type', settings.COMMON)
        path = self.save('signal/barrel_m_2.0_GeV/Events_0.npy', np.ones((1, 17)))
        self.assertEqual(submit_condor_jobs.input_identity(path), ('barrel_m_2.0_GeV', 0))
        self.assertEqual(submit_condor_jobs.inspect_npy(path)[1], 17)

    def configure_signal(self):
        settings.SIGNAL.update(
            npy_directory=str(self.root / 'signal'),
            output_directory=str(self.root / 'output'),
            category_patterns=['*'],
            max_chunks_by_lxy={1800.0: 1, 3300.0: None},
            submit_jobs=False,
        )
        for key in ('cmssw14_src', 'cmssw15_src', 'cmssw16_src'):
            settings.COMMON[key] = str(self.root)

    def test_caps_events_order_and_seed_allocation(self):
        self.configure_signal()
        settings.COMMON['max_events'] = 3
        for chunk, rows in ((10, 5), (2, 2), (0, 4)):
            self.save(f'signal/barrel_m_2.0_GeV/Events_{chunk}.npy', np.ones((rows, 17)))
        with patch.object(sys, 'argv', ['submit_condor_jobs.py', '--max-jobs-per-category', '2']), patch('subprocess.run'), contextlib.redirect_stdout(io.StringIO()):
            submit_condor_jobs.main()
        rows = [line.split() for line in (self.root / 'output/sub/dimuon_proton_brem_jobs.args').read_text().splitlines()]
        self.assertEqual([Path(row[0]).name for row in rows], ['Events_0.npy', 'Events_0.npy', 'Events_2.npy'])
        self.assertEqual([float(row[1]) for row in rows], [1800, 3300, 3300])
        self.assertEqual([int(row[3]) for row in rows], [3, 3, 2])
        self.assertEqual([int(row[4]) for row in rows], [42, 5042, 10042])

    def test_invalid_input_beyond_cap_is_still_validated(self):
        self.configure_signal()
        self.save('signal/barrel_m_2.0_GeV/Events_0.npy', np.ones((1, 17)))
        self.save('signal/barrel_m_2.0_GeV/Events_1.npy', np.ones((1, 13)))
        with patch.object(sys, 'argv', ['submit_condor_jobs.py', '--max-jobs-per-category', '1']), patch('subprocess.run') as submit:
            with self.assertRaisesRegex(ValueError, 'invalid input'):
                submit_condor_jobs.main()
            submit.assert_not_called()
        self.assertFalse((self.root / 'output').exists())

    def test_seed_boundary_and_submission_flag(self):
        self.configure_signal()
        settings.SIGNAL['max_chunks_by_lxy'] = {1800.0: None}
        self.save('signal/barrel_m_2.0_GeV/Events_0.npy', np.ones((1, 17)))
        settings.COMMON['base_seed'] = submit_condor_jobs.MAX_RNG_SEED - 4000
        with patch.object(sys, 'argv', ['submit_condor_jobs.py']), patch('subprocess.run') as submit:
            with self.assertRaisesRegex(ValueError, 'seed allocation exceeds'):
                submit_condor_jobs.main()
            submit.assert_not_called()
        self.assertFalse((self.root / 'output').exists())
        settings.COMMON['base_seed'] -= 1
        settings.SIGNAL['submit_jobs'] = True
        with patch.object(sys, 'argv', ['submit_condor_jobs.py']), patch('subprocess.run') as submit, contextlib.redirect_stdout(io.StringIO()):
            submit_condor_jobs.main()
            submit.assert_called_once_with(
                ['condor_submit', str(self.root / 'output/sub/dimuon_proton_brem_jobs.sub')], check=True,
            )


if __name__ == '__main__':
    unittest.main()
