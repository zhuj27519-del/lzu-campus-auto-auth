"""Native WLAN API: no localized netsh parsing and no access to Wi-Fi keys."""
import ctypes as c
from ctypes import wintypes as w
from dataclasses import dataclass
import logging
import time

log = logging.getLogger('campus')
CAMPUS = {b'iLZU', b'LZU'}

class GUID(c.Structure):
    _fields_ = [('data1', w.DWORD), ('data2', w.WORD), ('data3', w.WORD), ('data4', c.c_ubyte * 8)]

class Interface(c.Structure):
    _fields_ = [('guid', GUID), ('description', w.WCHAR * 256), ('state', w.DWORD)]

class SSID(c.Structure):
    _fields_ = [('length', w.DWORD), ('data', c.c_ubyte * 32)]
    def value(self):
        return bytes(self.data[:min(self.length, 32)])

class Network(c.Structure):
    _fields_ = [('profile', w.WCHAR * 256), ('ssid', SSID), ('bss_type', w.DWORD),
                ('bss_count', w.DWORD), ('connectable', w.BOOL), ('reason', w.DWORD),
                ('phy_count', w.DWORD), ('phys', w.DWORD * 8), ('more_phys', w.BOOL),
                ('signal', w.DWORD), ('security', w.BOOL), ('auth', w.DWORD),
                ('cipher', w.DWORD), ('flags', w.DWORD), ('reserved', w.DWORD)]

class Connection(c.Structure):
    _fields_ = [('mode', w.DWORD), ('profile', w.LPCWSTR), ('ssid', c.c_void_p),
                ('bssids', c.c_void_p), ('bss_type', w.DWORD), ('flags', w.DWORD)]

class Association(c.Structure):
    _fields_ = [('ssid', SSID), ('bss_type', w.DWORD), ('bssid', c.c_ubyte * 6),
                ('phy', w.DWORD), ('phy_index', w.DWORD), ('signal', w.DWORD),
                ('rx', w.DWORD), ('tx', w.DWORD)]

class Attributes(c.Structure):
    _fields_ = [('state', w.DWORD), ('mode', w.DWORD), ('profile', w.WCHAR * 256),
                ('association', Association), ('security', w.DWORD * 4)]

@dataclass(frozen=True)
class Candidate:
    ssid: bytes
    profile: str
    signal: int
    connectable: bool = True

def choose(candidates, current):
    if current is not None and current not in CAMPUS:
        return None
    eligible = [n for n in candidates if n.ssid in CAMPUS and n.profile and n.connectable]
    return max(eligible, key=lambda n: (n.signal, n.ssid == current), default=None)

class Wlan:
    def __init__(self):
        self.dll = c.WinDLL('wlanapi.dll')
        signatures = {
            'WlanOpenHandle': [w.DWORD, c.c_void_p, c.POINTER(w.DWORD), c.POINTER(w.HANDLE)],
            'WlanCloseHandle': [w.HANDLE, c.c_void_p],
            'WlanEnumInterfaces': [w.HANDLE, c.c_void_p, c.POINTER(c.c_void_p)],
            'WlanGetAvailableNetworkList': [w.HANDLE, c.POINTER(GUID), w.DWORD, c.c_void_p, c.POINTER(c.c_void_p)],
            'WlanQueryInterface': [w.HANDLE, c.POINTER(GUID), w.DWORD, c.c_void_p, c.POINTER(w.DWORD), c.POINTER(c.c_void_p), c.POINTER(w.DWORD)],
            'WlanScan': [w.HANDLE, c.POINTER(GUID), c.c_void_p, c.c_void_p, c.c_void_p],
            'WlanConnect': [w.HANDLE, c.POINTER(GUID), c.POINTER(Connection), c.c_void_p],
            'WlanFreeMemory': [c.c_void_p],
        }
        for name, arguments in signatures.items():
            fn = getattr(self.dll, name)
            fn.argtypes = arguments
            fn.restype = None if name == 'WlanFreeMemory' else w.DWORD
        self.handle = w.HANDLE()
        version = w.DWORD()
        self.check(self.dll.WlanOpenHandle(2, None, c.byref(version), c.byref(self.handle)))

    @staticmethod
    def check(code):
        if code:
            raise OSError(code, 'WLAN operation failed')

    def close(self):
        self.dll.WlanCloseHandle(self.handle, None)

    def _list(self, function, args, structure):
        pointer = c.c_void_p()
        self.check(function(*args, c.byref(pointer)))
        try:
            count = w.DWORD.from_address(pointer.value).value
            if count > 4096:
                raise ValueError('invalid WLAN list')
            # WLAN_*_LIST has a DWORD count and a DWORD index before the array.
            return [structure.from_buffer_copy(c.string_at(pointer.value + 8 + i*c.sizeof(structure), c.sizeof(structure))) for i in range(count)]
        finally:
            self.dll.WlanFreeMemory(pointer)

    def interfaces(self):
        return self._list(self.dll.WlanEnumInterfaces, (self.handle, None), Interface)

    def current(self, interface):
        pointer, size, kind = c.c_void_p(), w.DWORD(), w.DWORD()
        code = self.dll.WlanQueryInterface(self.handle, c.byref(interface.guid), 7, None, c.byref(size), c.byref(pointer), c.byref(kind))
        if code == 5023:  # ERROR_INVALID_STATE: disconnected
            return None
        self.check(code)
        try:
            value = c.cast(pointer, c.POINTER(Attributes)).contents
            return value.association.ssid.value() if value.state == 1 else None
        finally:
            self.dll.WlanFreeMemory(pointer)

    def scan(self, interface):
        self.check(self.dll.WlanScan(self.handle, c.byref(interface.guid), None, None, None))

    def networks(self, interface):
        values = self._list(self.dll.WlanGetAvailableNetworkList, (self.handle, c.byref(interface.guid), 0, None), Network)
        return [Candidate(n.ssid.value(), n.profile, n.signal, bool(n.connectable)) for n in values]

    def connect(self, interface, candidate):
        params = Connection(0, candidate.profile, None, None, 1, 0)
        self.check(self.dll.WlanConnect(self.handle, c.byref(interface.guid), c.byref(params), None))

def pause(seconds, stopped):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if stopped():
            return False
        time.sleep(.2)
    return not stopped()

def campus_wifi_connected():
    wlan = None
    try:
        wlan = Wlan()
        return any(wlan.current(interface) in CAMPUS for interface in wlan.interfaces())
    except Exception:
        return False
    finally:
        if wlan:
            wlan.close()

def ensure_campus_wifi(stopped, online=None):
    """Called only after repeated internet failures; connect saved campus profiles."""
    wlan = None
    try:
        wlan = Wlan()
        choices = []
        for interface in wlan.interfaces():
            current = wlan.current(interface)
            if current is not None and current not in CAMPUS:
                continue
            try:
                wlan.scan(interface)
                if not pause(4, stopped):
                    return False
            except OSError:
                log.warning('WIFI_SCAN_UNAVAILABLE: using Windows cached scan')
            candidate = choose(wlan.networks(interface), current)
            if candidate:
                choices.append((candidate, interface, current))
        if not choices:
            log.info('WIFI_NO_CAMPUS_CANDIDATE: continue portal check on existing connection')
            return True
        candidate, interface, current = max(choices, key=lambda x: (x[0].signal, x[0].ssid == x[2]))
        if stopped():
            return False
        # Scanning can take time; do not disrupt a connection restored meanwhile.
        if online is not None and online():
            log.info('WIFI_CONNECT_SKIPPED: internet already restored')
            return True
        if wlan.current(interface) not in (None, *CAMPUS):
            log.info('WIFI_CONNECT_SKIPPED: interface changed to another network')
            return True
        # Also request connection to the current SSID: handles a stale association.
        log.info('WIFI_CONNECT ssid=%s signal=%s%%', candidate.ssid.decode('ascii'), candidate.signal)
        wlan.connect(interface, candidate)
        if not pause(3, stopped):
            return False
        for _ in range(17):
            if stopped():
                return False
            if wlan.current(interface) == candidate.ssid:
                log.info('WIFI_CONNECTED ssid=%s', candidate.ssid.decode('ascii'))
                return pause(3, stopped)  # allow DHCP/default route to settle
            if not pause(1, stopped):
                return False
        log.warning('WIFI_CONNECT_TIMEOUT')
        return False
    except Exception:
        log.warning('WIFI_UNAVAILABLE: continue portal check on existing connection')
        return not stopped()
    finally:
        if wlan:
            wlan.close()
