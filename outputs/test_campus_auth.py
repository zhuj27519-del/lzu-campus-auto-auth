import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import campus_auth as app

class ConnectivityTests(unittest.TestCase):
    def test_single_provider_outage_is_online(self):
        with patch.object(app,'probe',side_effect=[False,True,False]):
            self.assertTrue(app.internet_ok())
    def test_all_fail_is_offline(self):
        with patch.object(app,'probe',return_value=False):
            self.assertFalse(app.internet_ok())
    def test_captive_portal_body_is_rejected(self):
        response=MagicMock()
        response.status=200
        response.read.return_value=b'<html>Login</html>'
        opener=MagicMock()
        opener.open.return_value.__enter__.return_value=response
        with patch.object(app.urllib.request,'build_opener',return_value=opener):
            self.assertFalse(app.probe(app.PROBES[0]))
    def test_redirect_is_not_followed(self):
        self.assertIsNone(app.NoRedirect().redirect_request(None,None,302,'',{},'http://10.10.0.166'))
    def test_probe_exception_is_failure(self):
        with patch.object(app.urllib.request,'build_opener',side_effect=OSError):
            self.assertFalse(app.probe(app.PROBES[0]))

class RetryTests(unittest.TestCase):
    def test_two_failures_required(self):
        p=app.RetryPolicy()
        self.assertFalse(p.observe(False,0))
        self.assertTrue(p.observe(False,15))
    def test_transient_failure_resets(self):
        p=app.RetryPolicy()
        p.observe(False,0)
        p.observe(True,15)
        self.assertFalse(p.observe(False,30))
    def test_cooldown_and_cap(self):
        p=app.RetryPolicy()
        delays=[p.result(False,0) for _ in range(8)]
        self.assertEqual(delays,[60,120,240,480,900,900,900,900])
        p.observe(False,1)
        self.assertFalse(p.observe(False,899))
        self.assertTrue(p.observe(False,900))
    def test_recovery_resets_backoff(self):
        p=app.RetryPolicy()
        p.result(False,0); p.result(False,0)
        p.observe(True,1)
        self.assertEqual(p.result(False,10),60)

if __name__=='__main__': unittest.main()
