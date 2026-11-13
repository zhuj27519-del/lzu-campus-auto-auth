import unittest
from unittest.mock import patch
import campus_wifi as wifi
import campus_auth as app

class SelectionTests(unittest.TestCase):
    def test_strongest_saved_campus(self):
        values=[wifi.Candidate(b'iLZU','iLZU',40),wifi.Candidate(b'LZU','LZU',80)]
        self.assertEqual(wifi.choose(values,b'iLZU').ssid,b'LZU')
    def test_excludes_unsaved_unconnectable_and_other(self):
        values=[wifi.Candidate(b'iLZU','',100),wifi.Candidate(b'LZU','LZU',90,False),wifi.Candidate(b'other','other',100)]
        self.assertIsNone(wifi.choose(values,None))
    def test_preserves_other_connection(self):
        self.assertIsNone(wifi.choose([wifi.Candidate(b'LZU','LZU',100)],b'home'))
    def test_tie_keeps_current(self):
        values=[wifi.Candidate(b'iLZU','iLZU',80),wifi.Candidate(b'LZU','LZU',80)]
        self.assertEqual(wifi.choose(values,b'LZU').ssid,b'LZU')
    def test_no_visible_network(self):
        self.assertIsNone(wifi.choose([],None))

class RecoveryTests(unittest.TestCase):
    def test_online_does_not_switch_or_login(self):
        with patch.object(app,'internet_ok',return_value=True), patch.object(app,'ensure_campus_wifi') as connect, patch.object(app,'login_once') as login:
            self.assertTrue(app.recover_connection(lambda:False))
            connect.assert_not_called(); login.assert_not_called()
    def test_wifi_before_portal(self):
        order=[]
        with patch.object(app,'internet_ok',return_value=False), patch.object(app,'ensure_campus_wifi',side_effect=lambda _: order.append('wifi') or True), patch.object(app,'login_once',side_effect=lambda _:order.append('login') or True):
            self.assertTrue(app.recover_connection(lambda:False))
        self.assertEqual(order,['wifi','login'])
    def test_wifi_recovers_without_login(self):
        with patch.object(app,'internet_ok',side_effect=[False,True]), patch.object(app,'ensure_campus_wifi',return_value=True), patch.object(app,'login_once') as login:
            self.assertTrue(app.recover_connection(lambda:False))
            login.assert_not_called()
    def test_failed_connection_skips_login(self):
        with patch.object(app,'internet_ok',return_value=False), patch.object(app,'ensure_campus_wifi',return_value=False), patch.object(app,'login_once') as login:
            self.assertFalse(app.recover_connection(lambda:False))
            login.assert_not_called()
    def test_cancel_skips_network(self):
        with patch.object(app,'internet_ok') as check:
            self.assertFalse(app.recover_connection(lambda:True))
            check.assert_not_called()

if __name__=='__main__': unittest.main()
