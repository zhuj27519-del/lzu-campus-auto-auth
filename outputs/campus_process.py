"""Bound a private process tree's lifetime using a Windows Job Object."""
import subprocess
import time
import win32api
import win32con
import win32event
import win32job
import win32process

def run_bounded(argv, timeout, stopped=lambda: False, cwd=None):
    if stopped():
        return None
    job = win32job.CreateJobObject(None, '')
    process = thread = None
    assigned = False
    try:
        limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        limits['BasicLimitInformation']['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
        process, thread, _, _ = win32process.CreateProcess(
            None, subprocess.list2cmdline([str(a) for a in argv]), None, None, False,
            win32con.CREATE_NO_WINDOW | win32con.CREATE_SUSPENDED,
            None, str(cwd) if cwd else None, win32process.STARTUPINFO())
        # Assign before any Python, driver or browser child can start.
        win32job.AssignProcessToJobObject(job, process)
        assigned = True
        win32process.ResumeThread(thread)
        deadline = time.monotonic() + timeout
        while win32event.WaitForSingleObject(process, 100) == win32event.WAIT_TIMEOUT:
            if stopped() or time.monotonic() >= deadline:
                return None
        return win32process.GetExitCodeProcess(process)
    finally:
        job.Close()
        if process:
            if not assigned and win32event.WaitForSingleObject(process, 0) == win32event.WAIT_TIMEOUT:
                win32api.TerminateProcess(process, 1)
            win32event.WaitForSingleObject(process, 5000)
            process.Close()
        if thread:
            thread.Close()
