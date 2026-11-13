import os
import sys
import time
import unittest
from campus_process import run_bounded

class ProcessTests(unittest.TestCase):
    def test_pre_cancel_does_not_launch(self):
        self.assertIsNone(run_bounded(['nonexistent'],1,lambda:True))

@unittest.skipUnless(os.environ.get('CAMPUS_PROCESS_TEST')=='1','Opt-in process lifecycle tests')
class ProcessIntegrationTests(unittest.TestCase):
    def test_complete_login_worker_with_offline_portal(self):
        code = '''import os
import campus_auth as app
from test_portal_browser import FORM
app.read_credentials=lambda: ('test-account','test-only-password')
original=app.prepare_form
pages=[]
def prepare(page):
    pages.append(page)
    page.route('**/*',lambda route: route.fulfill(status=200,content_type='text/html',body=FORM))
    return original(page)
app.prepare_form=prepare
app.internet_ok=lambda: bool(pages) and pages[0].locator('#result').inner_text()=='accepted'
os._exit(0 if app._login_in_process(lambda:False) else 2)
'''
        self.assertEqual(run_bounded([sys.executable,'-c',code],20,cwd=__import__('pathlib').Path(__file__).parent),0)
    def test_exit_status(self):
        self.assertEqual(run_bounded([sys.executable,'-c','raise SystemExit(7)'],5),7)
    def test_deadline_terminates_hanging_worker(self):
        start=time.monotonic()
        self.assertIsNone(run_bounded([sys.executable,'-c','import time; time.sleep(120)'],.5))
        self.assertLess(time.monotonic()-start,6)
    def test_cancel_terminates_worker(self):
        start=time.monotonic()
        self.assertIsNone(run_bounded([sys.executable,'-c','import time; time.sleep(120)'],30,lambda:time.monotonic()-start>.5))
        self.assertLess(time.monotonic()-start,6)

if __name__=='__main__':unittest.main()
