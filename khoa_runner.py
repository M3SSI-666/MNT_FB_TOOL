"""
Chốt "một loại lịch — một runner".

VÌ SAO CẦN, đo thật lúc 19:50 ngày 17/09/2026:

Bộ quét runner mồ côi của server dò bằng DÒNG LỆNH:

    Get-CimInstance Win32_Process | Where { $_.CommandLine -like '*scheduler.py*' }

Khi phần mềm do Task Scheduler khởi chạy, tiến trình con nằm ở mức toàn vẹn cao
hơn cửa sổ đang dò, nên WMI trả `CommandLine = null`. Lệnh trên vì thế tìm ra
ĐÚNG 0 tiến trình trong lúc máy đang chạy 18 `pythonw.exe`. Bộ quét mù hoàn
toàn, và không có cách nào vá nó bằng cách sửa câu truy vấn.

Hậu quả đã đo được: mỗi lần mở lại phần mềm, 4 runner cũ vẫn sống mà 4 runner
mới vẫn được bật thêm. Sau 4 lần mở lại, máy có 16 runner thay vì 4. Mỗi runner
tự mở phiên Chrome riêng (~1,1 GB) nên RAM 16 GB cạn sạch → Chromium bị Windows
giết → phiên hỏng hàng loạt → acc bị báo "nghỉ" oan. Chưa kể cùng một dòng lịch
bị hai runner đăng hai lần.

CÁCH CHỐT: runner nào khởi động trước thì giữ khoá file của loại đó; runner
trùng loại mở sau không lấy được khoá và tự thoát ngay. Khoá do HỆ ĐIỀU HÀNH
nhả khi tiến trình chết — kể cả bị taskkill hay mất điện — nên không bao giờ có
chuyện khoá kẹt lại chặn oan runner thật.

Bố cục file khoá `.runner_<loai>.lock`:

    byte 0      ký tự '#', là byte được khoá (không chứa dữ liệu)
    byte 1..    PID của runner đang giữ, dạng text

Tách như vậy để người khác ĐỌC ĐƯỢC pid mà không cần giành khoá — server dùng
nó để diệt runner mồ côi thay cho việc dò dòng lệnh.
"""
import os
import sys
import time

from config import BASE_DIR

# Giữ tham chiếu tới fd suốt đời tiến trình. Thả ra là Python đóng file và hệ
# điều hành nhả khoá — runner trùng sẽ lọt vào ngay.
_DANG_GIU = {}


def duong_dan(loai: str) -> str:
    return str(BASE_DIR / f".runner_{loai}.lock")


def _khoa_byte_dau(fd) -> bool:
    """Khoá độc quyền byte 0, không chờ. Trả False nếu người khác đang giữ."""
    try:
        if sys.platform == "win32":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _mo_khoa(fd):
    try:
        if sys.platform == "win32":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def dang_giu(loai: str) -> bool:
    """
    Có runner nào ĐANG GIỮ khoá loại này không.

    Hỏi thẳng hệ điều hành bằng cách thử giành khoá một nhịp rồi nhả ra ngay —
    KHÔNG đọc PID trong file rồi xem PID đó còn sống hay không.

    Vì sao: Windows dùng lại số PID. File khoá cũ trỏ vào một PID mà hệ thống
    đã cấp cho tiến trình khác thì phần mềm tưởng runner còn chạy và KHÔNG BAO
    GIỜ bật lại. Đã xảy ra thật: `.runner_thue.lock` giữ PID 1244 chết từ
    21:53 ngày 18/09, `/api/run/status` vẫn báo `thue: running=True`, và lịch
    Thuê nằm im gần 4 tiếng mà không một dòng lỗi nào.

    Khoá thì không nói dối: hệ điều hành chỉ nhả khi tiến trình giữ nó chết.
    """
    if loai in _DANG_GIU:
        return True                      # chính tiến trình này đang giữ
    try:
        fd = os.open(duong_dan(loai), os.O_CREAT | os.O_RDWR)
    except OSError:
        return False
    try:
        if _khoa_byte_dau(fd):
            _mo_khoa(fd)                 # giành được ⇒ chẳng ai giữ cả
            return False
        return True
    finally:
        os.close(fd)


def giu_khoa(loai: str) -> bool:
    """
    Giành quyền chạy cho `loai`. Trả True nếu được chạy, False nếu đã có runner
    cùng loại đang sống.

    Gọi một lần lúc runner khởi động. Không cần nhả — tiến trình chết là xong.

    Thử lại vài nhịp trước khi chịu thua: `dang_giu` cũng giành khoá trong tích
    tắc rồi nhả, mà giao diện lại hỏi trạng thái mỗi 10 giây. Đâm đúng vào cái
    tích tắc đó rồi bỏ cuộc thì runner thật không khởi động được — đúng loại
    lỗi mà hàm này sinh ra để chống.
    """
    if loai in _DANG_GIU:
        return True
    try:
        fd = os.open(duong_dan(loai), os.O_CREAT | os.O_RDWR)
    except OSError:
        # Không tạo nổi file khoá thì đừng chặn runner thật — thà chạy trùng
        # còn hơn không có runner nào.
        return True
    if not _khoa_byte_dau(fd):
        for _ in range(3):
            time.sleep(0.3)
            if _khoa_byte_dau(fd):
                break
        else:
            os.close(fd)
            return False
    try:
        so = f"{os.getpid()}\n".encode()
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, b"#" + so)
        os.ftruncate(fd, 1 + len(so))
    except OSError:
        pass          # ghi pid hỏng thì thôi, khoá vẫn có tác dụng
    _DANG_GIU[loai] = fd
    return True


def pid_dang_giu(loai: str) -> int | None:
    """
    PID runner đang giữ khoá loại này, đọc từ file — KHÔNG giành khoá.

    Trả None khi KHÔNG CÓ AI đang giữ khoá — kể cả lúc file còn nguyên và pid
    ghi trong đó trỏ vào một tiến trình đang sống, vì Windows dùng lại số PID
    (xem `dang_giu`). Ai đang giữ mới là câu hỏi đúng; pid chỉ để biết diệt cái
    nào.

    PHẢI nhảy qua byte 0 rồi mới đọc. Windows từ chối mọi lượt đọc chạm vào vùng
    đang bị khoá, nên `f.read()` từ đầu file sẽ ném PermissionError đúng lúc
    khoá đang có chủ — tức là đúng lúc ta cần đọc nhất.
    """
    if not dang_giu(loai):
        return None
    try:
        with open(duong_dan(loai), "rb") as f:
            f.seek(1)
            pid = int(f.read().strip() or 0)
    except (OSError, ValueError):
        return None
    return pid if pid > 0 and con_song(pid) else None


def con_song(pid: int) -> bool:
    """
    PID còn sống không.

    KHÔNG dùng os.kill(pid, 0) trên Windows: nó gọi GenerateConsoleCtrlEvent
    (gửi Ctrl+C) và báo lỗi khi tiến trình chạy dưới pythonw — tức là luôn
    dương tính giả. Và phải xem mã thoát chứ không chỉ xem mở được handle hay
    không: tiến trình đã chết mà còn ai đó giữ handle thì vẫn mở được.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
