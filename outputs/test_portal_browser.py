"""Offline Edge regression tests; no campus requests or real credentials."""
import os
import unittest
from playwright.sync_api import sync_playwright
import campus_auth as app

# Minimal form reproducing observed portal IDs, hidden select, custom menu and
# login handler's select.value read. The menu intentionally has no load handler.
FORM = '''<!doctype html><html><body>
<div class="tab-item" data="account">Account</div>
<div class="domain custom-select"><div class="select-selected">Choose</div>
<div class="select-items" style="display:none"><div data-value="@study">@eLearning</div></div>
<select class="domain" style="display:none"><option value="">@lzu.edu.cn</option><option value="@study">@eLearning</option></select></div>
<input id="username"><input id="password" type="password">
<input id="captcha" style="display:none">
<input id="remember" type="checkbox" checked><label for="remember">Remember</label>
<input id="protocol" type="checkbox"><label for="protocol">Agreement</label>
<button id="login-account">Login</button><div id="result"></div>
<script>document.querySelector('#login-account').onclick=()=>{
const ok=document.querySelector('select.domain').value==='@study'
&& document.querySelector('#username').value==='test-account'
&& document.querySelector('#password').value==='test-only-password'
&& document.querySelector('#protocol').checked
&& !document.querySelector('#remember').checked;
document.querySelector('#result').textContent=ok?'accepted':'rejected';};</script>
</body></html>'''

@unittest.skipUnless(os.environ.get('CAMPUS_BROWSER_TEST') == '1', 'Opt-in offline Edge tests')
class PortalBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw=sync_playwright().start()
        cls.browser=cls.pw.chromium.launch(channel='msedge',headless=True)
    @classmethod
    def tearDownClass(cls):
        # Run under run_tests.py's Job Object; do not use potentially hanging close.
        pass
    def setUp(self):
        self.context=self.browser.new_context(service_workers='block')
        self.context.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html',body=FORM))
        self.page=self.context.new_page()
        self.page.set_default_timeout(1500)
    def tearDown(self): self.context.close()
    def test_uninitialized_decorative_menu_does_not_block_submission(self):
        self.assertTrue(app.prepare_form(self.page))
        app.submit_form(self.page,'test-account','test-only-password')
        self.assertEqual(self.page.locator('#result').inner_text(),'accepted')
    def test_visible_captcha_prevents_preparation(self):
        self.context.unroute('**/*')
        self.context.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html',body=FORM.replace('id="captcha" style="display:none"','id="captcha"')))
        self.assertFalse(app.prepare_form(self.page))

if __name__=='__main__': unittest.main()
