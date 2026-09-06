"""
Lịch của MÁY: sáng tự chạy, khuya tự nghỉ.

Ý TƯỞNG
═══════
Máy trạm chạy cả ngày thì tốn điện và hao máy; mà sáng nào cũng phải nhớ bấm
Run bốn cái thì trước sau gì cũng có hôm quên. File này lo hai mốc giờ:

  07:00 — bật những runner bạn đã tick
  01:00 — dừng hết runner, rồi cho máy ngủ đông

MỘT ĐIỀU KHÔNG PHẦN MỀM NÀO LÀM ĐƯỢC
════════════════════════════════════
Máy đã TẮT HẲN thì không có phần mềm nào bật nó lên được — điện đã ngắt, Windows
không còn chạy. Chỉ có hai đường:

  1. Vào BIOS bật `RTC Alarm` (mỗi máy một kiểu menu, phải làm tay), hoặc
  2. Đừng tắt hẳn — cho máy NGỦ ĐÔNG. Tốn điện gần như bằng tắt, nhưng Windows
     hẹn giờ đánh thức được. `CAI_LICH_MAY.bat` đăng ký tác vụ đánh thức đó.

Ngủ đông còn lợi nữa: máy thức dậy là phần mềm đã sẵn ở đó, không phải khởi
động lại từ đầu, không phải chờ Chrome nạp.

CÁCH ĐIỀU KHIỂN RUNNER
══════════════════════
Gọi qua chính API mà giao diện đang dùng (`127.0.0.1:8080/api/run/...`) chứ
không import từ `server`. Tránh vòng import, và quan trọng hơn: đi đúng con
đường đã được dùng và kiểm hằng ngày, thay vì mở một lối tắt riêng dễ lệch.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime

from utils import logger

RUNNER = ("homestay", "thue", "ban", "page", "nuoi")

HANH_DONG = {
    # Ngủ đông: lưu tất cả xuống ổ cứng rồi ngắt điện. Windows đánh thức được.
    "ngu_dong":  (["shutdown", "/h"], "ngủ đông"),
    # Ngủ thường: thức nhanh nhất, nhưng vẫn ăn điện nhẹ.
    "ngu":       (["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], "ngủ"),
    # Tắt hẳn: CẦN BIOS bật RTC Alarm thì sáng máy mới tự lên lại được.
    "tat_may":   (["shutdown", "/s", "/t", "5"], "tắt máy"),
    # Chỉ dừng runner, máy để nguyên.
    "chi_tat_app": (None, "chỉ dừng runner"),
}


def cau_hinh() -> dict:
    """Đọc cấu hình. Lỗi thì trả 'tắt', không ném ra ngoài."""
    try:
        import db
        chon = [x for x in db.get_setting("lm_runner", "").split(",") if x in RUNNER]
        return {
            "bat":       db.get_setting("lm_bat", "0") == "1",
            "gio_bat":   db.get_setting("lm_gio_bat", "07:00").strip(),
            "gio_tat":   db.get_setting("lm_gio_tat", "01:00").strip(),
            "runner":    chon,
            "hanh_dong": db.get_setting("lm_hanh_dong", "ngu_dong").strip(),
            "ngay_bat":  db.get_setting("lm_ngay_bat", ""),
            "ngay_tat":  db.get_setting("lm_ngay_tat", ""),
        }
    except Exception:
        return {"bat": False, "gio_bat": "", "gio_tat": "", "runner": [],
                "hanh_dong": "ngu_dong", "ngay_bat": "", "ngay_tat": ""}


def _goi(duong_dan: str, du_lieu: dict = None) -> dict:
    """Gọi API nội bộ của chính phần mềm này."""
    from config import PORT
    try:
        body = json.dumps(du_lieu or {}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}{duong_dan}", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"⚠️  Lịch máy: gọi {duong_dan} hỏng: {e}")
        return {}


def _dang_chay() -> dict:
    from config import PORT
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/api/run/status", timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}


def _phut_trong_ngay(moc: str) -> int | None:
    try:
        h, p = (moc or "").split(":")
        return int(h) * 60 + int(p)
    except Exception:
        return None


def _qua_gio(moc: str, bay_gio: datetime = None) -> bool:
    """
    Đã qua mốc `HH:MM` của hôm nay chưa?

    Dùng cho việc BẬT runner. Bật muộn thì vô hại, thậm chí là điều mong muốn:
    mở phần mềm lúc 9h sáng thì vẫn nên bật runner lên chạy.
    """
    m = _phut_trong_ngay(moc)
    if m is None:
        return False
    g = bay_gio or datetime.now()
    return g.hour * 60 + g.minute >= m


def _trong_cua_so(moc: str, bay_gio: datetime = None, rong: int = 30) -> bool:
    """
    Có đang ở trong khoảng `rong` phút NGAY SAU mốc `HH:MM` không?

    Dùng cho việc CHO MÁY NGHỈ, và đây là chỗ suýt hỏng nặng. Nếu dùng "đã qua
    giờ chưa" như lúc bật, thì đêm qua máy tắt, 9h sáng bạn mở phần mềm lên —
    mốc 01:00 vẫn tính là "đã qua mà hôm nay chưa chạy", và máy NGỦ ĐÔNG NGAY
    LÚC 9H SÁNG.

    Lỡ cửa sổ thì bỏ hẳn hôm đó, không làm bù. Việc tắt máy không được phép nổ
    muộn — nó cắt ngang mọi thứ đang chạy.
    """
    m = _phut_trong_ngay(moc)
    if m is None:
        return False
    g   = bay_gio or datetime.now()
    now = g.hour * 60 + g.minute
    # Cộng vòng qua nửa đêm: mốc 23:50 thì cửa sổ chạy tới 00:20 hôm sau.
    return 0 <= (now - m) % (24 * 60) < rong


# ═══════════════════════════════════════════════════════════════════════════
# Giờ đánh thức của Windows — nơi duy nhất phần mềm không tự lo được
# ═══════════════════════════════════════════════════════════════════════════
# Giờ sáng nằm ở HAI nơi: phần mềm biết "7h thì bật runner", còn việc đánh thức
# máy là một tác vụ của Windows. Đổi giờ trong phần mềm mà quên chạy lại
# `CAI_LICH_MAY.bat` thì máy vẫn thức — nhưng theo giờ CŨ.
#
# Hỏng kiểu tệ nhất: nhìn thì như chạy được, chỉ là muộn mấy tiếng, và không có
# một dòng lỗi nào. Nên phần mềm tự đi đọc giờ trong tác vụ Windows rồi đối
# chiếu. Đọc thì không cần quyền quản trị; chỉ ghi mới cần.

TEN_TAC_VU = "MNT_DanhThucMay"


def gio_danh_thuc() -> str | None:
    """
    Giờ `HH:MM` mà Windows đang hẹn đánh thức máy. `None` nếu chưa cài tác vụ.

    Đọc từ XML chứ không đọc bản in `/FO LIST`: bản in ra theo ngôn ngữ và định
    dạng giờ của máy ("7:00:00 AM" hay "07:00:00"), nên phân tích nó sẽ hỏng
    trên máy đặt ngôn ngữ khác. Trong XML luôn là `2026-09-07T07:00:00`.
    """
    if sys.platform != "win32":
        return None
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", TEN_TAC_VU, "/XML"],
                           capture_output=True, timeout=20,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode != 0:
            return None
        xml = r.stdout.decode("utf-16", errors="ignore")
        if "<StartBoundary>" not in xml:
            xml = r.stdout.decode("utf-8", errors="ignore")
        moc = xml.split("<StartBoundary>", 1)[1].split("</StartBoundary>", 1)[0]
        return moc.split("T", 1)[1][:5]          # "2026-09-07T07:00:00" -> "07:00"
    except Exception:
        return None


def tinh_trang_danh_thuc() -> dict:
    """
    Giờ trong phần mềm có khớp giờ Windows đang hẹn không?

    Chỉ xét khi lịch đang bật VÀ kiểu nghỉ cần đánh thức. Chọn "chỉ dừng runner"
    thì máy có ngủ đâu mà cần thức.
    """
    c   = cau_hinh()
    can = c["bat"] and c["hanh_dong"] in ("ngu_dong", "ngu")
    win = gio_danh_thuc()
    return {
        "can_danh_thuc": can,
        "gio_phan_mem":  c["gio_bat"],
        "gio_windows":   win,
        "da_cai":        win is not None,
        "khop":          (win == c["gio_bat"]) if win else False,
        "tat_han":       c["bat"] and c["hanh_dong"] == "tat_may",
    }


def cai_danh_thuc() -> tuple[bool, str]:
    """
    Chạy `CAI_LICH_MAY.bat` với quyền quản trị để cập nhật giờ đánh thức.

    Windows sẽ hiện cửa sổ hỏi xác nhận — không có cách nào đăng ký tác vụ đánh
    thức mà không qua bước đó. Trả về ngay sau khi bật, không chờ người dùng
    bấm, vì họ có thể để đó cả phút.
    """
    from config import BASE_DIR
    from pathlib import Path
    f = Path(BASE_DIR) / "CAI_LICH_MAY.bat"
    if not f.exists():
        return False, "Không thấy CAI_LICH_MAY.bat"
    if sys.platform != "win32":
        return False, "Chỉ chạy được trên Windows"
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command",
             f"Start-Process cmd.exe -ArgumentList '/c',\"`\"{f}`\" < nul\" -Verb RunAs"],
            creationflags=subprocess.CREATE_NO_WINDOW)
        return True, "Đang mở — bấm Yes ở cửa sổ Windows vừa hiện lên"
    except Exception as e:
        return False, str(e)[:90]


def bat_runner() -> int:
    """Bật những runner đã tick. Bỏ qua cái đang chạy. Trả số cái vừa bật."""
    c  = cau_hinh()
    tt = _dang_chay()
    n  = 0
    for loai in c["runner"]:
        if tt.get(loai, {}).get("running"):
            continue
        # headless=True: máy chạy không người trông, hiện cửa sổ Chrome chỉ tổ
        # che màn hình và tốn tài nguyên.
        if _goi(f"/api/run/{loai}/start", {"headless": True}).get("ok"):
            n += 1
            logger.info(f"🌅 Lịch máy: đã bật runner {loai}")
    return n


def tat_runner() -> int:
    """Dừng MỌI runner, kể cả cái không nằm trong danh sách tick."""
    tt = _dang_chay()
    n  = 0
    for loai in RUNNER:
        if not tt.get(loai, {}).get("running"):
            continue
        if _goi(f"/api/run/{loai}/stop").get("ok"):
            n += 1
            logger.info(f"🌙 Lịch máy: đã dừng runner {loai}")
    return n


def _cho_may_nghi(hanh_dong: str):
    """Cho máy nghỉ theo cách đã chọn. Không bao giờ ném lỗi ra ngoài."""
    lenh, ten = HANH_DONG.get(hanh_dong, HANH_DONG["ngu_dong"])
    if lenh is None:
        logger.info("🌙 Lịch máy: chỉ dừng runner, máy để nguyên")
        return
    try:
        logger.info(f"🌙 Lịch máy: cho máy {ten}...")
        subprocess.Popen(lenh, creationflags=(subprocess.CREATE_NO_WINDOW
                                              if sys.platform == "win32" else 0))
    except Exception as e:
        logger.error(f"❌ Lịch máy: không {ten} được: {e}")


def kiem_tra(bay_gio: datetime = None) -> str:
    """
    Gọi định kỳ từ luồng nền. Trả về việc vừa làm, hoặc chuỗi rỗng.

    Mốc "hôm nay đã chạy" ghi XUỐNG cơ sở dữ liệu chứ không giữ trong biến: máy
    ngủ đông rồi thức dậy là tiến trình vẫn nguyên, nhưng tắt mở phần mềm thì
    biến mất — và lúc đó lịch sẽ chạy lại lần nữa trong cùng một ngày.
    """
    try:
        import db
        c = cau_hinh()
        if not c["bat"]:
            return ""
        gio = bay_gio or datetime.now()
        hom = gio.strftime("%Y-%m-%d")

        # Giờ nghỉ xét TRƯỚC giờ chạy, để một cấu hình kiểu 07:00 nghỉ / 08:00
        # chạy không bật runner lên rồi tắt ngay sau đó.
        #
        # Và nó dùng CỬA SỔ chứ không dùng "đã qua giờ chưa" — xem `_trong_cua_so`.
        if _trong_cua_so(c["gio_tat"], gio) and c["ngay_tat"] != hom:
            db.set_setting("lm_ngay_tat", hom)
            n = tat_runner()
            _cho_may_nghi(c["hanh_dong"])
            return f"nghỉ ({n} runner đã dừng)"

        if _qua_gio(c["gio_bat"], gio) and c["ngay_bat"] != hom:
            db.set_setting("lm_ngay_bat", hom)
            n = bat_runner()
            return f"chạy ({n} runner đã bật)"
        return ""
    except Exception as e:
        logger.debug(f"Lịch máy hỏng: {e}")
        return ""
