"""Windows campus authentication monitor. Never log browser exceptions or credentials."""
from __future__ import annotations
import concurrent.futures
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
import winreg
import win32api
import win32con
import win32cred
import win32event
import win32security
from playwright.sync_api import sync_playwright
from campus_wifi import ensure_campus_wifi

ROOT = Path(__file__).resolve().parent
TARGET = 'CampusAutoAuth/10.10.0.166/eLearning/v1'
PORTAL = 'http://10.10.0.166/'
RUN_NAME = 'CampusAutoAuth-eLearning'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
INTERVAL = 15
PROBES = (
    ('https://www.msftconnecttest.com/connecttest.txt', 200, b'Microsoft Connect Test'),
    ('https://connectivitycheck.platform.hicloud.com/generate_204', 204, b''),
    ('https://cp.cloudflare.com/generate_204', 204, b''),
)
log = logging.getLogger('campus')

def object_name(suffix):
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
    finally:
        token.Close()
    return 'Global\\CampusAutoAuth-' + sid + '-' + suffix

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def probe(spec):
    url, status, body = spec
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'CampusAutoAuth/1.0'})
        with opener.open(request, timeout=4) as response:
            return response.status == status and response.read(512).strip() == body
    except Exception:
        return False

def internet_ok():
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(PROBES)) as pool:
        return any(list(pool.map(probe, PROBES)))

def read_credentials():
    try:
        entry = win32cred.CredRead(TARGET, win32cred.CRED_TYPE_GENERIC)
    except win32cred.error as exc:
        if exc.winerror == 1168:
            return None
        raise
    blob = entry['CredentialBlob']
    password = blob.decode('utf-16-le') if isinstance(blob, bytes) else blob
    return entry['UserName'], password

def configure_logging():
    folder = ROOT / 'logs'
    folder.mkdir(exist_ok=True)
    handler = RotatingFileHandler(folder / 'monitor.log', maxBytes=1024*1024, backupCount=5, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    log.setLevel(logging.INFO)
    log.addHandler(handler)

def prepare_form(page):
    # Selectors confirmed from the live SRun portal, 2026-11-12.
    page.goto(PORTAL, wait_until='domcontentloaded', timeout=20000)
    page.locator('.tab-item[data="account"]').wait_for(state='visible', timeout=12000)
    page.locator('.tab-item[data="account"]').click()
    page.locator('#username').wait_for(state='visible')
    page.locator('.domain.custom-select .select-selected').click()
    page.locator('.domain.custom-select .select-items [data-value="@study"]').click()
    if page.locator('select.domain').input_value() != '@study':
        raise RuntimeError('domain_mismatch')
    if page.locator('#captcha').is_visible():
        return False
    if page.locator('#remember').is_checked():
        page.locator('label[for="remember"]').click()
    if page.locator('label[for="protocol"]').is_visible() and not page.locator('#protocol').is_checked():
        page.locator('label[for="protocol"]').click()
    return True

def login_once(stopped):
    credentials = read_credentials()
    if not credentials:
        log.warning('CREDENTIALS_MISSING: run setup')
        return False
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        try:
            context = browser.new_context(service_workers='block')
            # Never forward credentials to another host; no saved profile, trace or screenshots.
            context.route('**/*', lambda route: route.continue_() if urllib.parse.urlparse(route.request.url).hostname == '10.10.0.166' else route.abort())
            page = context.new_page()
            page.set_default_timeout(10000)
            if not prepare_form(page):
                log.warning('CAPTCHA_REQUIRED: manual portal login required')
                return False
            if stopped():
                return False
            page.locator('#username').fill(credentials[0])
            page.locator('#password').fill(credentials[1])
            page.locator('#login-account').click()
            for _ in range(6):
                if stopped():
                    return False
                page.wait_for_timeout(2500)
                if internet_ok():
                    log.info('LOGIN_VERIFIED')
                    return True
            return False
        finally:
            credentials = None
            browser.close()

class RetryPolicy:
    def __init__(self):
        self.misses = 0
        self.failures = 0
        self.next_attempt = 0.0

    def observe(self, online, now):
        self.misses = 0 if online else self.misses + 1
        if online:
            self.failures = 0
        return not online and self.misses >= 2 and now >= self.next_attempt

    def result(self, success, now):
        self.failures = 0 if success else self.failures + 1
        delay = 60 if success else min(900, 60 * 2 ** min(self.failures - 1, 4))
        self.next_attempt = now + delay
        return delay

def recover_connection(stopped):
    if stopped():
        return False
    if internet_ok():
        return True
    if not ensure_campus_wifi(stopped) or stopped():
        return False
    if internet_ok():
        return True
    return login_once(stopped)

def monitor():
    configure_logging()
    mutex = win32event.CreateMutex(None, False, object_name('monitor'))
    if win32api.GetLastError() == 183:
        log.info('ALREADY_RUNNING')
        mutex.Close()
        return
    event = win32event.CreateEvent(None, True, False, object_name('stop'))
    win32event.ResetEvent(event)
    stopped = lambda: win32event.WaitForSingleObject(event, 0) == win32event.WAIT_OBJECT_0
    policy = RetryPolicy()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    pending = None
    previous = None
    log.info('MONITOR_STARTED interval=15s wifi_recovery=enabled')
    try:
        while not stopped():
            tick = time.monotonic()
            online = internet_ok()
            if online != previous:
                log.info('INTERNET_%s', 'ONLINE' if online else 'UNREACHABLE')
                previous = online
            if pending is not None and pending.done():
                try:
                    success = pending.result()
                except Exception:
                    # Playwright error strings can contain fill values. Never emit them.
                    success = False
                    log.warning('LOGIN_ERROR: browser or portal unavailable; details suppressed')
                delay = policy.result(success, time.monotonic())
                log.info('RECOVERY_%s retry_after=%ss', 'VERIFIED' if success else 'FAILED', delay)
                pending = None
            ready = policy.observe(online, time.monotonic())
            if ready and pending is None and not stopped():
                log.info('RECOVERY_ATTEMPT')
                pending = executor.submit(recover_connection, stopped)
            remaining = max(0.1, INTERVAL - (time.monotonic() - tick))
            win32event.WaitForSingleObject(event, int(remaining * 1000))
    except KeyboardInterrupt:
        win32event.SetEvent(event)
    finally:
        win32event.SetEvent(event)
        executor.shutdown(wait=True)
        event.Close()
        mutex.Close()
        log.info('MONITOR_STOPPED')

def running():
    try:
        handle = win32event.OpenMutex(win32con.SYNCHRONIZE, False, object_name('monitor'))
        handle.Close()
        return True
    except win32event.error as exc:
        if exc.winerror == 2:
            return False
        raise

def stop():
    if not running():
        return
    event = win32event.OpenEvent(win32event.EVENT_MODIFY_STATE, False, object_name('stop'))
    win32event.SetEvent(event)
    event.Close()
    for _ in range(90):
        if not running():
            return
        time.sleep(1)
    raise RuntimeError('stop_timeout')

def start():
    if running():
        return
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    subprocess.Popen([str(pythonw), str(Path(__file__).resolve()), 'run'], cwd=ROOT,
                     creationflags=subprocess.CREATE_NO_WINDOW, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env={k:v for k,v in os.environ.items() if k not in ('DEBUG','PWDEBUG')})

def startup(install):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if install:
            command = subprocess.list2cmdline([str(Path(sys.executable).with_name('pythonw.exe')), str(Path(__file__).resolve()), 'run'])
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass

def setup():
    import tkinter as tk
    from tkinter import messagebox
    window = tk.Tk()
    window.title('校园网 eLearning 凭据设置')
    window.resizable(False, False)
    tk.Label(window, text='凭据仅存入本机 Windows Credential Manager。\n账号无需添加 @study；密码不会写入日志。', padx=25, pady=15).grid(row=0,columnspan=2)
    tk.Label(window,text='账号').grid(row=1,column=0)
    username = tk.Entry(window, width=32)
    username.grid(row=1,column=1,padx=15,pady=8)
    tk.Label(window,text='密码').grid(row=2,column=0)
    password = tk.Entry(window, show='●', width=32)
    password.grid(row=2,column=1,padx=15,pady=8)
    def save():
        user, secret = username.get().strip(), password.get()
        if not user or not secret:
            messagebox.showerror('未保存','请输入账号和密码。')
            return
        if user.endswith('@study'):
            user = user[:-6]
        try:
            win32cred.CredWrite({'Type':win32cred.CRED_TYPE_GENERIC,'TargetName':TARGET,
                                'UserName':user,'CredentialBlob':secret,
                                'Persist':win32cred.CRED_PERSIST_LOCAL_MACHINE},0)
        except Exception:
            messagebox.showerror('保存失败','无法写入 Windows 凭据管理器。')
            return
        password.delete(0,tk.END)
        username.delete(0,tk.END)
        secret = None
        start()
        messagebox.showinfo('已保存','凭据已保存，后台监控已启动。')
        window.destroy()
    tk.Button(window,text='保存凭据并启动',command=save).grid(row=3,columnspan=2,pady=18)
    username.focus_set()
    window.mainloop()

def main():
    # Disable Playwright verbose output even when inherited from a developer shell.
    os.environ.pop('DEBUG',None)
    os.environ.pop('PWDEBUG',None)
    command = sys.argv[1] if len(sys.argv)>1 else 'status'
    if command == 'setup': setup()
    elif command == 'run': monitor()
    elif command == 'start': start(); print('Background start requested.')
    elif command == 'stop': stop(); print('Stopped.')
    elif command == 'status': print('Running' if running() else 'Stopped')
    elif command == 'check': print('Online' if internet_ok() else 'All probes failed')
    elif command == 'install-startup': startup(True); print('Startup installed for current Windows user.')
    elif command == 'remove-startup': startup(False); print('Startup removed.')
    elif command == 'uninstall':
        stop()
        startup(False)
        try: win32cred.CredDelete(TARGET, win32cred.CRED_TYPE_GENERIC)
        except win32cred.error as exc:
            if exc.winerror != 1168: raise
        print('Stopped; startup and this tool credential removed. Project files retained.')
    else: raise ValueError('unknown_command')

if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Suppress sensitive exception values in every mode.
        if sys.stderr: print('Operation failed; no sensitive details recorded.', file=sys.stderr)
        sys.exit(1)
