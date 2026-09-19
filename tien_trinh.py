"""
Xử lý tiến trình Windows — dựng cây con cháu và tắt chúng.

Tách riêng vì HAI nơi cần: `server.py` (nút Dừng, nút Tắt phần mềm) và
`dung_het.py` (gọi từ RESTART.bat / UPDATE.bat, không được nạp cả Flask chỉ để
tắt một tiến trình). Trước đây mỗi nơi giữ một bản chép — đúng thói quen đã
khiến bản vá hộp cookie bị sót một file.

VÌ SAO KHÔNG DÙNG taskkill / WMI — đo trên máy thật ngày 19/09/2026:

    taskkill /F /T /PID <runner>     → treo >20 giây, chạy hai lần, tiến
                                       trình VẪN SỐNG
    taskkill /F /PID <server>        → treo, cửa sổ cmd đứng im
    Get-CimInstance Win32_Process    → QUÁ 120 GIÂY chưa xong
    ------------------------------------------------------------------
    CreateToolhelp32Snapshot         → 0,006 giây, thấy đủ 270 tiến trình
    TerminateProcess                 → chết trong 0,00 giây

Cả ba cách đầu phải đi vòng qua RPC/WMI rồi duyệt tiến trình của cả máy; máy
chạy nhiều phiên có trên hai trăm tiến trình nên chúng nghẽn ở đó. Hai cách
sau chạy thẳng trong tiến trình này.
"""
import os
import sys
import time
import ctypes
from ctypes import wintypes

LA_WINDOWS = sys.platform == "win32"

_TERMINATE        = 0x0001
_QUERY_LIMITED    = 0x1000
_SNAP_PROCESS     = 0x0002
_DANG_CHAY        = 259          # STILL_ACTIVE


class _TienTrinh(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260)]


def ban_do_cha_con() -> dict:
    """{pid cha: [pid con, ...]} — chụp một ảnh danh sách tiến trình."""
    if not LA_WINDOWS:
        return {}
    k32  = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(_SNAP_PROCESS, 0)
    if snap == -1:
        return {}
    ra = {}
    try:
        e = _TienTrinh()
        e.dwSize = ctypes.sizeof(_TienTrinh)
        if k32.Process32First(snap, ctypes.byref(e)):
            while True:
                ra.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
                if not k32.Process32Next(snap, ctypes.byref(e)):
                    break
    finally:
        k32.CloseHandle(snap)
    return ra


def con_song(pid: int) -> bool:
    """
    PID còn sống không.

    KHÔNG dùng os.kill(pid, 0) trên Windows: nó gọi GenerateConsoleCtrlEvent
    (gửi Ctrl+C) và báo lỗi khi tiến trình chạy dưới pythonw — luôn dương tính
    giả. Và phải xem MÃ THOÁT chứ không chỉ xem mở được handle hay không:
    tiến trình đã chết mà còn ai đó giữ handle thì vẫn mở được.
    """
    if pid <= 0:
        return False
    if not LA_WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(_QUERY_LIMITED, False, pid)
    if not h:
        return False
    try:
        ma = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(ma))) and ma.value == _DANG_CHAY
    finally:
        k32.CloseHandle(h)


def diet_mot(pid: int) -> bool:
    """Giết đúng MỘT tiến trình bằng TerminateProcess."""
    if not LA_WINDOWS:
        try:
            os.kill(pid, 9)
            return True
        except OSError:
            return not con_song(pid)
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(_TERMINATE, False, pid)
    if not h:
        return not con_song(pid)        # chết sẵn rồi thì coi như xong
    try:
        return bool(k32.TerminateProcess(h, 1))
    finally:
        k32.CloseHandle(h)


def ca_cay(goc, ban: dict = None) -> list:
    """
    `goc` cùng toàn bộ con cháu, CON XẾP TRƯỚC CHA.

    Thứ tự quan trọng: giết cha trước thì Chromium mồ côi ở lại, vẫn ăn RAM và
    vẫn giữ thư mục profile.
    """
    ban = ban_do_cha_con() if ban is None else ban
    ra, xet = [], list(goc)
    while xet:
        p = xet.pop()
        if p in ra:
            continue
        ra.append(p)
        xet.extend(ban.get(p, []))
    ra.reverse()
    return ra


def to_tien(pid: int = None, ban: dict = None) -> set:
    """
    Chính `pid` và mọi TỔ TIÊN của nó — danh sách cấm giết.

    Phải là tổ tiên, tuyệt đối không phải con cháu: runner chính là con của
    server, chặn con cháu thì nút Dừng không diệt được gì nữa.
    """
    pid = os.getpid() if pid is None else pid
    ban = ban_do_cha_con() if ban is None else ban
    cha = {c: p for p, ds in ban.items() for c in ds}
    cam = {pid}
    p = pid
    while p in cha and cha[p] not in cam:
        p = cha[p]
        cam.add(p)
    return cam


def diet_cay(pids, han_giay: float = 15, ghi=None) -> list:
    """
    Giết các PID cùng toàn bộ con cháu. Trả danh sách PID gốc đã CHẾT THẬT.

    Lọc trùng trước khi bắn — PID hay xuất hiện ở nhiều đường dò cùng lúc.
    Diệt xong hỏi lại hệ điều hành chứ không tin là đã xong: từng có lúc log
    ghi "đã diệt" mà cả bốn tiến trình vẫn sống nguyên.
    """
    goc = [int(p) for p in dict.fromkeys(pids) if p]
    if not goc:
        return []

    ban = ban_do_cha_con()
    cam = to_tien(ban=ban)
    for pid in ca_cay(goc, ban):
        if pid in cam or pid <= 4:          # 0 và 4 là tiến trình hệ thống
            continue
        try:
            diet_mot(pid)
        except Exception:
            pass

    han, xong = time.time() + han_giay, []
    for pid in goc:
        while con_song(pid) and time.time() < han:
            time.sleep(0.15)
        if con_song(pid):
            if ghi:
                ghi(f"  ⚠️  KHÔNG diệt được PID {pid} — vẫn đang chạy")
        else:
            xong.append(pid)
    return xong
