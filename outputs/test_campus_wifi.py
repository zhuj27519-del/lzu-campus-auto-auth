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
    def setUp(self):
        patcher=patch.object(app,"campus_wifi_connected",return_value=False)
        self.connected=patcher.start()
        self.addCleanup(patcher.stop)

    def test_online_does_not_switch_or_login(self):
        with patch.object(app,'internet_ok',return_value=True), patch.object(app,'ensure_campus_wifi') as connect, patch.object(app,'login_once') as login:
            self.assertTrue(app.recover_connection(lambda:False))
            connect.assert_not_called(); login.assert_not_called()
    def test_wifi_before_portal(self):
        order=[]
        with patch.object(app,'internet_ok',return_value=False), patch.object(app,'ensure_campus_wifi',side_effect=lambda _, **kwargs: order.append('wifi') or True), patch.object(app,'login_once',side_effect=lambda _:order.append('login') or True):
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

    def test_connected_campus_authenticates_without_reconnect(self):
        self.connected.return_value=True
        with patch.object(app,'internet_ok',return_value=False), patch.object(app,'login_once',return_value=True) as login, patch.object(app,'ensure_campus_wifi') as connect:
            self.assertTrue(app.recover_connection(lambda:False))
            login.assert_called_once(); connect.assert_not_called()

    def test_failed_login_falls_back_without_second_submission(self):
        self.connected.return_value=True
        with patch.object(app,'internet_ok',return_value=False), patch.object(app,'login_once',return_value=False) as login, patch.object(app,'ensure_campus_wifi',return_value=True) as connect:
            self.assertFalse(app.recover_connection(lambda:False))
            login.assert_called_once(); connect.assert_called_once()

class WifiRaceTests(unittest.TestCase):
    def test_online_after_scan_does_not_reconnect(self):
        with patch.object(wifi,'Wlan') as factory, patch.object(wifi,'pause',return_value=True):
            client=factory.return_value
            client.interfaces.return_value=[object()]
            client.current.return_value=b'iLZU'
            client.networks.return_value=[wifi.Candidate(b'LZU','LZU',90)]
            self.assertTrue(wifi.ensure_campus_wifi(lambda:False,online=lambda:True))
            client.connect.assert_not_called()
            client.close.assert_called_once()

    def test_user_changes_network_during_scan(self):
        with patch.object(wifi,'Wlan') as factory, patch.object(wifi,'pause',return_value=True):
            client=factory.return_value
            client.interfaces.return_value=[object()]
            client.current.side_effect=[b'iLZU',b'home']
            client.networks.return_value=[wifi.Candidate(b'LZU','LZU',90)]
            self.assertTrue(wifi.ensure_campus_wifi(lambda:False,online=lambda:False))
            client.connect.assert_not_called()

class LoginPrivacyTests(unittest.TestCase):
    def test_sensitive_exception_message_not_logged(self):
        with patch.object(app,'_login_once',side_effect=RuntimeError('sensitive-sentinel')):
            with self.assertLogs('campus',level='WARNING') as logs:
                self.assertFalse(app._login_in_process(lambda:False))
            self.assertNotIn('sensitive-sentinel',' '.join(logs.output))

if __name__=='__main__': unittest.main()
