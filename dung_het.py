"""
Dừng sạch server + mọi runner. Dùng cho RESTART.bat và UPDATE.bat.

VÌ SAO KHÔNG DÙNG .BAT NỮA — đo trên máy thật ngày 19/09:

  taskkill /F /PID <server>      → treo, cửa sổ cmd đứng im ở dòng
                                   "Kill Flask server PID 13680"
  taskkill /F /T /PID <runner>   → treo >20 giây, chạy hai lần, tiến trình
                                   vẫn sống
  Get-CimInstance Win32_Process  → 30 giây chưa xong khi máy đang tải nặng,
  (lọc theo CommandLine)           và trả CommandLine rỗng cho tiến trình do
                                   Task Scheduler khởi chạy → không thấy gì

Cả ba cách đều phải đi hỏi vòng qua RPC/WMI rồi duyệt tiến trình của CẢ MÁY.
Máy này lúc chạy nhiều phiên có hơn hai trăm tiến trình nên chúng nghẽn ở đó.

Cách ở đây: chụp một ảnh danh sách tiến trình (CreateToolhelp32Snapshot) rồi gọi
thẳng TerminateProcess. Cùng phép đo đó: chết trong 0,00 giây.

Nguồn tìm runner cũng khác: đọc FILE KHOÁ `.runner_<loai>.lock`. Hệ điều hành chỉ
nhả khoá khi tiến trình giữ nó chết, nên đây là câu trả lời duy nhất không nói
dối — không phụ thuộc file pid còn hay mất, cũng không phụ thuộc quyền đọc dòng
lệnh.

Dùng:
    python dung_het.py            # dừng hết
    python dung_het.py 13680      # dừng hết, kèm mấy PID chỉ đích danh
"""
import os
import sys
import time
import ctypes
from ctypes import wintypes

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LA_WINDOWS = sys.platform == "win32"


class _TIEN_TRINH(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260)]


def ban_do_cha_con() -> dict:
    """{pid cha: [pid con]} — chụp một ảnh, chạy trong tiến trình này."""
    if not LA_WINDOWS:
        return {}
    k32  = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snap == -1:
        return {}
    ra = {}
    try:
        e = _TIEN_TRINH()
        e.dwSize = ctypes.sizeof(_TIEN_TRINH)
        if k32.Process32First(snap, ctypes.byref(e)):
            while True:
                ra.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
                if not k32.Process32Next(snap, ctypes.byref(e)):
                    break
    finally:
        k32.CloseHandle(snap)
    return ra


def con_song(pid: int) -> bool:
    if not LA_WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)      # QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        ma = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(ma))) and ma.value == 259
    finally:
        k32.CloseHandle(h)


def diet(pid: int) -> bool:
    if not LA_WINDOWS:
        try:
            os.kill(pid, 9)
            return True
        except OSError:
            return not con_song(pid)
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x0001, False, pid)      # PROCESS_TERMINATE
    if not h:
        return not con_song(pid)
    try:
        return bool(k32.TerminateProcess(h, 1))
    finally:
        k32.CloseHandle(h)


def ca_cay(goc, ban=None) -> list:
    """`goc` cùng toàn bộ con cháu, CON XẾP TRƯỚC CHA."""
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


def pid_giu_khoa() -> list:
    """PID của runner đang giữ khoá. Không import được thì bỏ qua, đừng chết."""
    try:
        import khoa_runner as kr
    except Exception:
        return []
    ra = []
    for loai in ("homestay", "thue", "ban", "page", "nuoi"):
        try:
            if kr.dang_giu(loai):
                p = kr.pid_dang_giu(loai)
                if p:
                    ra.append(p)
        except Exception:
            pass
    return ra


def pid_tu_file() -> list:
    ra = []
    for loai in ("homestay", "thue", "ban", "page", "nuoi"):
        f = f".runner_{loai}.pid"
        if os.path.exists(f):
            try:
                ra.append(int(open(f).read().strip()))
            except (OSError, ValueError):
                pass
            try:
                os.unlink(f)
            except OSError:
                pass
    return ra


def main():
    them = [int(a) for a in sys.argv[1:] if a.isdigit()]
    goc  = list(dict.fromkeys(them + pid_giu_khoa() + pid_tu_file()))
    if not goc:
        print("  Khong co tien trinh nao de dung.")
        return

    ban = ban_do_cha_con()
    # Tự vệ: không giết chính mình và TỔ TIÊN của mình (cmd đang chạy file này).
    cha = {c: p for p, ds in ban.items() for c in ds}
    cam = {os.getpid()}
    p = os.getpid()
    while p in cha and cha[p] not in cam:
        p = cha[p]
        cam.add(p)

    t0 = time.time()
    for pid in ca_cay(goc, ban):
        if pid in cam or pid <= 4:
            continue
        try:
            diet(pid)
        except Exception:
            pass

    han = time.time() + 10
    xong, sot = [], []
    for pid in goc:
        while con_song(pid) and time.time() < han:
            time.sleep(0.1)
        (sot if con_song(pid) else xong).append(pid)

    print(f"  Da dung {len(xong)}/{len(goc)} tien trinh trong {time.time()-t0:.2f}s"
          + (f" | CHUA dung duoc: {sot}" if sot else ""))


if __name__ == "__main__":
    main()
