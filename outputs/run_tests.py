"""Run offline browser and process tests with bounded Windows cleanup."""
import os
from pathlib import Path
import sys
import unittest
from campus_process import run_bounded

if __name__ == '__main__':
    if '--worker' in sys.argv:
        os.environ['CAMPUS_BROWSER_TEST']='1'
        os.environ['CAMPUS_PROCESS_TEST']='1'
        suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_*.py')
        with Path(__file__).with_name('test-details.txt').open('w',encoding='utf-8') as stream:
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        Path(__file__).with_name('test-result.txt').write_text(
            f'tests={result.testsRun} failures={len(result.failures)} errors={len(result.errors)} skipped={len(result.skipped)}\n',encoding='utf-8')
        os._exit(0 if result.wasSuccessful() else 1)
    code=run_bounded([sys.executable,Path(__file__).resolve(),'--worker'],60,cwd=Path(__file__).parent)
    report=Path(__file__).with_name('test-result.txt')
    print(report.read_text(encoding='utf-8') if report.exists() else 'No completed test report')
    print('PASS' if code==0 else 'FAIL_OR_TIMEOUT')
    sys.exit(0 if code==0 else 1)
