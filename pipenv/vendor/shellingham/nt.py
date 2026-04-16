import contextlib
import ctypes
import os

from ctypes.wintypes import (
    BOOL,
    CHAR,
    DWORD,
    HANDLE,
    LONG,
    LPWSTR,
    MAX_PATH,
    PDWORD,
    ULONG,
)

from pipenv.vendor.shellingham._core import SHELL_NAMES


INVALID_HANDLE_VALUE = HANDLE(-1).value
ERROR_NO_MORE_FILES = 18
ERROR_INSUFFICIENT_BUFFER = 122
TH32CS_SNAPPROCESS = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


kernel32 = ctypes.windll.kernel32


def _check_handle(error_val=0):
    def check(ret, func, args):
        if ret == error_val:
            raise ctypes.WinError()
        return ret

    return check


def _check_expected(expected):
    def check(ret, func, args):
        if ret:
            return True
        code = ctypes.GetLastError()
        if code == expected:
            return False
        raise ctypes.WinError(code)

    return check


class ProcessEntry32(ctypes.Structure):
    _fields_ = (
        ("dwSize", DWORD),
        ("cntUsage", DWORD),
        ("th32ProcessID", DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ULONG)),
        ("th32ModuleID", DWORD),
        ("cntThreads", DWORD),
        ("th32ParentProcessID", DWORD),
        ("pcPriClassBase", LONG),
        ("dwFlags", DWORD),
        ("szExeFile", CHAR * MAX_PATH),
    )


kernel32.CloseHandle.argtypes = [HANDLE]
kernel32.CloseHandle.restype = BOOL

kernel32.CreateToolhelp32Snapshot.argtypes = [DWORD, DWORD]
kernel32.CreateToolhelp32Snapshot.restype = HANDLE
kernel32.CreateToolhelp32Snapshot.errcheck = _check_handle(  # type: ignore
    INVALID_HANDLE_VALUE,
)

kernel32.Process32First.argtypes = [HANDLE, ctypes.POINTER(ProcessEntry32)]
kernel32.Process32First.restype = BOOL
kernel32.Process32First.errcheck = _check_expected(  # type: ignore
    ERROR_NO_MORE_FILES,
)

kernel32.Process32Next.argtypes = [HANDLE, ctypes.POINTER(ProcessEntry32)]
kernel32.Process32Next.restype = BOOL
kernel32.Process32Next.errcheck = _check_expected(  # type: ignore
    ERROR_NO_MORE_FILES,
)

kernel32.GetCurrentProcessId.argtypes = []
kernel32.GetCurrentProcessId.restype = DWORD

kernel32.OpenProcess.argtypes = [DWORD, BOOL, DWORD]
kernel32.OpenProcess.restype = HANDLE
kernel32.OpenProcess.errcheck = _check_handle(  # type: ignore
    INVALID_HANDLE_VALUE,
)

kernel32.QueryFullProcessImageNameW.argtypes = [HANDLE, DWORD, LPWSTR, PDWORD]
kernel32.QueryFullProcessImageNameW.restype = BOOL
kernel32.QueryFullProcessImageNameW.errcheck = _check_expected(  # type: ignore
    ERROR_INSUFFICIENT_BUFFER,
)


@contextlib.contextmanager
def _handle(f, *args, **kwargs):
    pass


def _iter_processes():
    pass


def _get_full_path(proch):
    pass


def get_shell(pid=None, max_depth=10):
    pass
