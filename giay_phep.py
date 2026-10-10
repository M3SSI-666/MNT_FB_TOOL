"""
giay_phep.py — Đăng nhập bằng Gmail và giữ cho MỖI TÀI KHOẢN CHỈ CHẠY MỘT MÁY.

Luồng đăng nhập
───────────────
App KHÔNG tự nói chuyện với Google. Nó mở trình duyệt tới máy chủ của mình,
máy chủ làm toàn bộ phần OAuth rồi trả giấy phép về:

    App  ──mở trình duyệt──>  {MAY_CHU}/dang-nhap?may_id=…&cb=http://127.0.0.1:PORT
                                        │
                                        ├──> Google (khách chọn Gmail)
                                        │
                              máy chủ kiểm: email có quyền? còn hạn?
                              tạo phiên mới, ĐÁ phiên cũ của email đó
                                        │
         <──chuyển hướng về 127.0.0.1───┘  kèm giấy phép

Vì sao vòng qua máy chủ chứ không để app tự gọi Google: làm thế thì
`client_secret` phải nằm trong bản cài phát cho khách, mà bản cài là mã Python
đọc được. Đi đường này thì trong máy khách không có bí mật nào của Google.

Một tài khoản — một máy
───────────────────────
Máy chủ giữ ĐÚNG MỘT phiên cho mỗi email. Đăng nhập máy mới là phiên cũ bị xoá
ngay. Máy cũ phát hiện ra ở nhịp kiểm tiếp theo rồi tự khoá.

Mất liên lạc thì sao
────────────────────
Máy bị đá chỉ biết mình bị đá khi HỎI ĐƯỢC máy chủ. Mất mạng thì không nghe
được lệnh đá — nên phải có hạn chịu đựng:

    · máy chủ trả lời "không còn hiệu lực"  → KHOÁ NGAY, xoá giấy phép
    · không gọi được máy chủ                 → còn chạy, nhưng quá
                                               AN_HAN_PHUT phút là tự khoá

Con số này vừa là mức chịu mạng chập chờn, vừa là thời gian tối đa một máy bị
đá còn chạy được — hai thứ đó là một, không tách ra được. 15 phút là mức Duong
chọn: mạng rớt vài phút không sao, mà ai chặn mạng để dùng chùa cũng chỉ được
15 phút.
"""

import hashlib
import json
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from utils import logger

# Đổi được khi chạy thử với máy chủ dựng tạm trên máy mình.
MAY_CHU = os.environ.get("MNT_MAY_CHU", "https://mntsignal.com").rstrip("/")

AN_HAN_PHUT = 15        # không gọi được máy chủ quá ngần này phút thì khoá
NHIP_GIAY   = 60        # bao lâu hỏi máy chủ một lần
CHO_GIAY    = 12        # hạn chờ mỗi lần gọi mạng
CHO_DANG_NHAP_GIAY = 300   # khách có 5 phút để đăng nhập xong trong trình duyệt

# Nằm trong data/ nên cập nhật phần mềm không xoá mất, khách không phải đăng
# nhập lại sau mỗi lần bấm Cập nhật.
TEP = Path(__file__).resolve().parent / "data" / "giay_phep.json"


# ═══════════════════════════════════════════════════════════════
# Mã máy
# ═══════════════════════════════════════════════════════════════

def may_id() -> str:
    """Mã nhận dạng máy, cố định qua các lần khởi động lại.

    Ưu tiên MachineGuid của Windows — Windows sinh ra lúc cài và giữ nguyên
    suốt đời bản cài. Không đọc được thì lùi về địa chỉ MAC + tên máy; kém ổn
    định hơn (đổi card mạng là đổi mã) nhưng vẫn hơn là không có gì.

    Băm lại chứ không gửi thẳng: mã máy thô là thông tin nhận dạng được, không
    có lý do gì để nó nằm trên máy chủ ở dạng đọc được.
    """
    tho = ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            tho = winreg.QueryValueEx(k, "MachineGuid")[0]
    except Exception as e:
        logger.debug(f"Không đọc được MachineGuid: {e}")
    if not tho:
        tho = f"{uuid.getnode()}|{socket.gethostname()}"
    return hashlib.sha256(f"mnt|{tho}".encode()).hexdigest()[:32]


def ten_may() -> str:
    """Tên máy, chỉ để Duong nhìn vào danh sách phiên cho dễ nhận ra ai là ai."""
    try:
        return socket.gethostname()[:40]
    except Exception:
        return "?"


# ═══════════════════════════════════════════════════════════════
# Lưu / đọc giấy phép
# ═══════════════════════════════════════════════════════════════

def doc() -> dict:
    """Giấy phép đang lưu. Chưa đăng nhập hoặc tệp hỏng thì trả {}."""
    try:
        return json.loads(TEP.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"⚠️  Tệp giấy phép hỏng, coi như chưa đăng nhập: {e}")
        return {}


def _ghi(gp: dict) -> None:
    try:
        TEP.parent.mkdir(parents=True, exist_ok=True)
        TEP.write_text(json.dumps(gp, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    except Exception as e:
        # Không ghi được thì lần sau mở app phải đăng nhập lại — phiền, nhưng
        # không được để nó làm chết app.
        logger.warning(f"⚠️  Không lưu được giấy phép: {e}")


def xoa() -> None:
    """Xoá giấy phép khỏi máy này — dùng khi bị đá hoặc khách tự đăng xuất."""
    try:
        TEP.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"⚠️  Không xoá được giấy phép: {e}")


# ═══════════════════════════════════════════════════════════════
# Trạng thái
# ═══════════════════════════════════════════════════════════════

def _phut_tu(moc: str) -> float:
    """Bao nhiêu phút đã trôi qua kể từ mốc ISO. Đọc không ra thì coi như rất lâu."""
    try:
        return (datetime.now() - datetime.fromisoformat(moc)).total_seconds() / 60
    except Exception:
        return 1e9


def bat() -> bool:
    """Tính năng giấy phép đã bật chưa. MẶC ĐỊNH LÀ TẮT.

    Tắt sẵn là cố ý. Phần mềm đang chạy thật trên máy Duong và trên những máy
    đã phát đi từ trước; bật kèm theo một bản cập nhật là tất cả đồng loạt
    hiện màn hình đăng nhập trong khi máy chủ giấy phép còn chưa dựng xong.

    Bật bằng một trong hai cách:
        · đặt `giay_phep_bat = 1` trong bảng cài đặt
        · hoặc biến môi trường MNT_GIAY_PHEP=1 (tiện khi chạy thử)
    """
    if os.environ.get("MNT_GIAY_PHEP") == "1":
        return True
    try:
        from db import get_setting
        return get_setting("giay_phep_bat", "0") == "1"
    except Exception:
        # Đọc cài đặt hỏng thì coi như TẮT. Thà để lọt còn hơn khoá nhầm cả
        # những máy đang chạy việc thật vì một lỗi đọc cơ sở dữ liệu.
        return False


def trang_thai() -> dict:
    """Máy này có được dùng phần mềm không, và vì sao.

    {"dung_duoc": bool, "email": str, "ly_do": str, "han_den": str}
    """
    if not bat():
        return {"dung_duoc": True, "email": "", "han_den": "", "ly_do": ""}

    gp = doc()
    if not gp.get("token"):
        return {"dung_duoc": False, "email": "", "han_den": "",
                "ly_do": "Chưa đăng nhập"}

    # Giấy phép của máy KHÁC bị chép sang đây thì không dùng được. Chép cả tệp
    # data/ sang máy mới là cách chia sẻ dễ nghĩ ra nhất.
    if gp.get("may_id") and gp["may_id"] != may_id():
        return {"dung_duoc": False, "email": gp.get("email", ""), "han_den": "",
                "ly_do": "Giấy phép này của máy khác"}

    han = gp.get("han_den") or ""
    if han and han < datetime.now().strftime("%Y-%m-%d"):
        return {"dung_duoc": False, "email": gp.get("email", ""), "han_den": han,
                "ly_do": f"Hết hạn ngày {han}"}

    im = _phut_tu(gp.get("kiem_cuoi") or "")
    if im > AN_HAN_PHUT:
        return {"dung_duoc": False, "email": gp.get("email", ""), "han_den": han,
                "ly_do": f"Không liên lạc được máy chủ {int(im)} phút"}

    return {"dung_duoc": True, "email": gp.get("email", ""), "han_den": han,
            "ly_do": ""}


def dung_duoc() -> bool:
    return trang_thai()["dung_duoc"]


# ═══════════════════════════════════════════════════════════════
# Nói chuyện với máy chủ
# ═══════════════════════════════════════════════════════════════

def _goi(duong: str, du_lieu: dict) -> dict | None:
    """Gọi một API của máy chủ. Trả None khi KHÔNG LIÊN LẠC ĐƯỢC.

    Phân biệt None với dict là mấu chốt của cả module: None nghĩa là "chưa
    biết" (còn ân hạn), còn dict {"ok": false} nghĩa là máy chủ đã trả lời dứt
    khoát "không được" (khoá ngay). Gộp hai thứ này lại là hoặc mất mạng cũng
    bị khoá, hoặc bị đá rồi vẫn chạy tiếp.
    """
    try:
        req = urllib.request.Request(
            f"{MAY_CHU}{duong}",
            data=json.dumps(du_lieu).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "User-Agent": "MNT-FB-AutoPost/1.0"})
        with urllib.request.urlopen(req, timeout=CHO_GIAY) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Máy chủ CÓ trả lời, chỉ là trả lời từ chối — đây là câu trả lời dứt
        # khoát, không phải mất liên lạc.
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "ly_do": f"Máy chủ từ chối ({e.code})"}
    except Exception as e:
        logger.debug(f"Không gọi được {duong}: {e}")
        return None


def kiem_tra() -> dict:
    """Hỏi máy chủ xem phiên này còn hiệu lực không, rồi cập nhật giấy phép.

    Trả về `trang_thai()` sau khi cập nhật.
    """
    gp = doc()
    if not gp.get("token"):
        return trang_thai()

    tra = _goi("/api/nhip", {"token": gp["token"], "may_id": may_id()})

    if tra is None:
        # Mất liên lạc — giữ nguyên `kiem_cuoi`, để ân hạn tự đếm.
        return trang_thai()

    if not tra.get("ok"):
        ly_do = tra.get("ly_do") or "Phiên không còn hiệu lực"
        logger.warning(f"🔒 Mất quyền dùng phần mềm: {ly_do}")
        xoa()
        return {"dung_duoc": False, "email": gp.get("email", ""),
                "han_den": "", "ly_do": ly_do}

    gp["kiem_cuoi"] = datetime.now().isoformat(timespec="seconds")
    if tra.get("han_den"):
        gp["han_den"] = tra["han_den"]
    _ghi(gp)
    return trang_thai()


def dang_xuat() -> None:
    """Tự đăng xuất: báo máy chủ thả phiên rồi xoá giấy phép ở máy này."""
    gp = doc()
    if gp.get("token"):
        _goi("/api/dang-xuat", {"token": gp["token"]})
    xoa()


# ═══════════════════════════════════════════════════════════════
# Đăng nhập — mở trình duyệt, chờ máy chủ trả giấy phép về
# ═══════════════════════════════════════════════════════════════

class _NhanGiayPhep:
    """Máy chủ HTTP bé xíu chạy ở 127.0.0.1, chỉ sống đúng một lần đăng nhập."""

    def __init__(self):
        self.ket_qua: dict | None = None
        self.state = secrets.token_urlsafe(24)
        self._xong = threading.Event()
        self._srv = None

    def _tao(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        cha = self

        class Tay(BaseHTTPRequestHandler):
            def log_message(self, *a):          # im lặng, đừng bẩn log
                pass

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
                # `state` chặn việc ai đó gửi link vào cổng này để ép app nhận
                # một giấy phép lạ.
                if q.get("state") != cha.state:
                    self._tra("Yêu cầu không hợp lệ.", 400)
                    return
                cha.ket_qua = q
                self._tra("Đăng nhập xong. Quay lại cửa sổ phần mềm nhé.")
                cha._xong.set()

            def _tra(self, chu: str, ma: int = 200):
                than = (
                    "<!doctype html><meta charset='utf-8'>"
                    "<title>MNT AutoPost</title>"
                    "<body style='font:16px system-ui;text-align:center;"
                    "padding:60px;background:#111;color:#eee'>"
                    f"<h2>{chu}</h2>"
                    "<p style='color:#888'>Có thể đóng thẻ này.</p>"
                ).encode("utf-8")
                self.send_response(ma)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(than)))
                self.end_headers()
                self.wfile.write(than)

        # Cổng 0 = để hệ điều hành chọn cổng trống, khỏi đụng cổng đang dùng.
        self._srv = HTTPServer(("127.0.0.1", 0), Tay)
        return self._srv.server_port

    def chay(self) -> tuple[str, threading.Thread]:
        cong = self._tao()
        t = threading.Thread(target=self._srv.serve_forever, daemon=True)
        t.start()
        return f"http://127.0.0.1:{cong}/xong", t

    def cho(self, giay: int) -> dict | None:
        self._xong.wait(giay)
        try:
            self._srv.shutdown()
        except Exception:
            pass
        return self.ket_qua


def bat_dau_dang_nhap() -> dict:
    """Mở trình duyệt cho khách chọn Gmail, chờ giấy phép trả về.

    Chặn cho tới khi xong hoặc hết giờ, nên bên gọi phải chạy ở luồng riêng
    chứ đừng gọi thẳng trong tay xử lý HTTP của giao diện.
    """
    nhan = _NhanGiayPhep()
    cb, _ = nhan.chay()
    lien_ket = f"{MAY_CHU}/dang-nhap?" + urllib.parse.urlencode({
        "may_id": may_id(), "ten_may": ten_may(),
        "cb": cb, "state": nhan.state,
    })

    logger.info(f"🔑 Mở trình duyệt để đăng nhập: {lien_ket}")
    try:
        import webbrowser
        webbrowser.open(lien_ket)
    except Exception as e:
        return {"ok": False, "ly_do": f"Không mở được trình duyệt: {e}",
                "lien_ket": lien_ket}

    q = nhan.cho(CHO_DANG_NHAP_GIAY)
    if not q:
        return {"ok": False, "ly_do": "Hết giờ chờ đăng nhập",
                "lien_ket": lien_ket}
    if not q.get("token"):
        return {"ok": False, "ly_do": q.get("ly_do") or "Máy chủ không cấp giấy phép"}

    _ghi({
        "email":     q.get("email", ""),
        "token":     q["token"],
        "may_id":    may_id(),
        "han_den":   q.get("han_den", ""),
        "kiem_cuoi": datetime.now().isoformat(timespec="seconds"),
    })
    logger.info(f"✅ Đã đăng nhập: {q.get('email')} (hạn {q.get('han_den') or '—'})")
    return {"ok": True, "email": q.get("email", ""), "han_den": q.get("han_den", "")}


# ═══════════════════════════════════════════════════════════════
# Vòng canh chạy nền
# ═══════════════════════════════════════════════════════════════

_vong = None
_khi_mat_quyen = None


def bat_dau_canh(khi_mat_quyen=None) -> None:
    """Chạy nền, cứ NHIP_GIAY giây hỏi máy chủ một lần.

    `khi_mat_quyen(ly_do)` được gọi ĐÚNG MỘT LẦN ngay khi mất quyền — Duong
    chọn dừng ngay lập tức, nên chỗ này sẽ đóng mọi phiên đang chạy.
    """
    global _vong, _khi_mat_quyen
    if not bat():
        logger.info("  🔓 Giấy phép đang TẮT — không canh")
        return
    _khi_mat_quyen = khi_mat_quyen
    if _vong and _vong.is_alive():
        return

    def _chay():
        da_bao = False
        while True:
            try:
                tt = kiem_tra()
                if tt["dung_duoc"]:
                    da_bao = False
                elif not da_bao:
                    da_bao = True
                    if _khi_mat_quyen:
                        try:
                            _khi_mat_quyen(tt["ly_do"])
                        except Exception as e:
                            logger.error(f"❌ Xử lý mất quyền hỏng: {e}")
            except Exception as e:
                # Vòng canh chết là app chạy mãi không ai kiểm — phải sống dai.
                logger.warning(f"⚠️  Vòng canh giấy phép vấp: {e}")
            time.sleep(NHIP_GIAY)

    _vong = threading.Thread(target=_chay, daemon=True, name="canh-giay-phep")
    _vong.start()
