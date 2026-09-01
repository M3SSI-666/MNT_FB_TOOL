"""
Báo trạng thái tài khoản qua Telegram.

Chạy nhiều máy thì mỗi máy có một cơ sở dữ liệu riêng, không máy nào nhìn thấy
máy nào. File này là đường duy nhất để các máy nói ra ngoài: mỗi máy tự gửi vào
CÙNG một khung chat Telegram, mỗi tin có tên máy ở đầu. Khung chat đó thành chỗ
xem tổng — không cần máy chủ nào cả.

LUẬT BẤT DI BẤT DỊCH
════════════════════
Không hàm nào trong file này được ném lỗi ra ngoài, và không hàm nào được làm
chậm phiên đăng bài. Mất mạng, sai token, Telegram sập — phần mềm vẫn đăng như
thường, chỉ là không có tin nhắn.

Đây không phải câu nói cho đẹp. Bản v2.0.0 từng biến một máy chủ ngoài thành
thứ bắt buộc, khiến mọi máy cập nhật xong là không chạy được nữa, và phải gỡ đi
ở v2.2.0. Việc báo cáo là phần THÊM; nó hỏng thì chỉ mình nó hỏng.

Ba việc file này làm
════════════════════
1. `bao_doi_trang_thai` — acc đổi trạng thái thì bắn tin ngay.
2. `tom_tat`            — dựng bản tổng kết, dùng cho tin hằng ngày và lệnh hỏi.
3. `vong_nen`           — luồng nền: gửi tổng kết đúng giờ, và nghe lệnh
                          `/tinhtrang` từ Telegram để mọi máy cùng trả lời.
"""

from __future__ import annotations

import atexit
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"

# Chờ mạng tối đa ngần này rồi bỏ. Ngắn có chủ ý: tin nhắn trễ vài giây không
# sao, nhưng một phiên đăng bài bị treo vì chờ Telegram thì mới là hỏng việc.
CHO_GIAY = 8

# Lưới an toàn cho trường hợp hai tiến trình cùng đọc được trạng thái cũ rồi
# cùng ghi. Việc chống lặp thật sự do `_huong_doi` lo — chỉ báo khi trạng thái
# THỰC SỰ đổi — nên cửa sổ này để ngắn: dài quá thì acc hỏng rồi hồi phục rồi
# hỏng lại trong vòng một tiếng sẽ bị nuốt mất tin thứ hai.
LAP_LAI_PHUT = 5

# Cách nhau ít nhất ngần này giây giữa hai tin. Telegram chỉ cho khoảng 20
# tin/phút vào cùng một nhóm, mà báo cáo thường đến theo cụm: mất mạng một cái
# là cả loạt acc cùng hết cookie trong vài giây.
GIAN_CACH_GIAY = 3.5

_hang: "queue.Queue[tuple[str, str]]" = queue.Queue(maxsize=200)
_luong_gui: threading.Thread | None = None
_khoa = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════
# Cấu hình — để trong bảng settings, sửa được từ giao diện
# ═══════════════════════════════════════════════════════════════════════════

def cau_hinh() -> dict:
    """Đọc cấu hình. Lỗi cơ sở dữ liệu thì trả về 'tắt', không ném lỗi."""
    try:
        import db
        return {
            "bat":        db.get_setting("tg_bat", "0") == "1",
            "token":      db.get_setting("tg_token", "").strip(),
            "chat_id":    db.get_setting("tg_chat_id", "").strip(),
            "ten_may":    db.get_setting("tg_ten_may", "").strip() or _ten_may_mac_dinh(),
            "gio_tomtat": db.get_setting("tg_gio_tom_tat", "08:00").strip(),
        }
    except Exception:
        return {"bat": False, "token": "", "chat_id": "", "ten_may": "", "gio_tomtat": ""}


def _ten_may_mac_dinh() -> str:
    """Chưa đặt tên thì lấy tên máy Windows, để tin nhắn vẫn phân biệt được."""
    import os
    return os.environ.get("COMPUTERNAME", "").strip() or "Máy không tên"


def san_sang() -> bool:
    c = cau_hinh()
    return bool(c["bat"] and c["token"] and c["chat_id"])


# ═══════════════════════════════════════════════════════════════════════════
# Gọi Telegram
# ═══════════════════════════════════════════════════════════════════════════

def _goi_api(method: str, tham_so: dict, token: str = "") -> dict | None:
    """
    Gọi một lệnh của Telegram. Trả None nếu hỏng bất kể vì sao — người gọi
    không cần biết hỏng vì mạng, vì token, hay vì Telegram trả lỗi.
    """
    token = token or cau_hinh()["token"]
    if not token:
        return None
    try:
        du_lieu = urllib.parse.urlencode(tham_so).encode("utf-8")
        req = urllib.request.Request(
            API.format(token=token, method=method),
            data=du_lieu,
            # Đặt User-Agent tử tế: có dịch vụ chặn thẳng UA mặc định của Python.
            headers={"User-Agent": "MNT-FB-AutoPost/1.0"},
        )
        with urllib.request.urlopen(req, timeout=CHO_GIAY) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"Telegram {method} hỏng: {e}")
        return None


def _luong_chay():
    """Luồng nền: rút tin khỏi hàng đợi rồi gửi. Chết là chết một mình."""
    lan_truoc = 0.0
    while True:
        try:
            token, text = _hang.get()
        except Exception:
            return
        try:
            if text is None:                     # tín hiệu dừng
                _hang.task_done()
                return

            # Giãn cách giữa hai tin. Telegram chỉ cho khoảng 20 tin/phút vào
            # cùng một nhóm; ba máy cùng báo một lúc — ví dụ cả loạt acc hết
            # cookie cùng lúc — là vượt ngay, và Telegram sẽ NUỐT tin chứ không
            # báo gì. Chờ ở đây vô hại: luồng này chạy nền, không ai đợi nó.
            cho = GIAN_CACH_GIAY - (time.time() - lan_truoc)
            if cho > 0:
                time.sleep(cho)

            c  = cau_hinh()
            kq = _goi_api("sendMessage",
                          {"chat_id": c["chat_id"], "text": text,
                           "disable_web_page_preview": "true"},
                          token=token or c["token"])
            lan_truoc = time.time()

            # Vẫn quá nhanh thì Telegram nói rõ phải chờ bao lâu — nghe lời nó
            # và gửi lại đúng một lần.
            if kq and not kq.get("ok"):
                cho_them = (kq.get("parameters") or {}).get("retry_after")
                if cho_them:
                    time.sleep(min(int(cho_them) + 1, 60))
                    _goi_api("sendMessage",
                             {"chat_id": c["chat_id"], "text": text,
                              "disable_web_page_preview": "true"},
                             token=token or c["token"])
                    lan_truoc = time.time()
        except Exception as e:
            logger.debug(f"Gửi Telegram hỏng: {e}")
        finally:
            try:
                _hang.task_done()
            except Exception:
                pass


def gui(text: str) -> None:
    """
    Xếp một tin vào hàng chờ gửi rồi trả về NGAY. Không chờ mạng.

    Hàng đầy thì bỏ tin mới — thà mất một thông báo còn hơn chặn phiên đăng bài
    đang chạy. Hàng chỉ đầy khi mạng đã hỏng từ lâu, lúc đó tin thứ 200 cũng
    không còn ý nghĩa gì.
    """
    global _luong_gui
    try:
        if not san_sang():
            return
        with _khoa:
            if _luong_gui is None or not _luong_gui.is_alive():
                _luong_gui = threading.Thread(target=_luong_chay, daemon=True,
                                              name="telegram-gui")
                _luong_gui.start()
        _hang.put_nowait((cau_hinh()["token"], text))
    except queue.Full:
        logger.debug("Hàng đợi Telegram đầy — bỏ tin")
    except Exception as e:
        logger.debug(f"Xếp tin Telegram hỏng: {e}")


@atexit.register
def _xa_hang():
    """
    Tiến trình sắp thoát thì cố gửi nốt, tối đa 10 giây.

    Cần thật: phiên tham gia nhóm chạy trong tiến trình con sống rất ngắn. Không
    có đoạn này thì tin 'Cookie hết hạn' xếp vào hàng xong là tiến trình chết,
    tin bay theo.
    """
    try:
        if _luong_gui is None or not _luong_gui.is_alive():
            return
        han = time.time() + 10
        while not _hang.empty() and time.time() < han:
            time.sleep(0.2)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Báo khi acc đổi trạng thái
# ═══════════════════════════════════════════════════════════════════════════

BIEU_TUONG = {
    "Active":         "✅",
    "Spam":           "🚫",
    "Cookie hết hạn": "🍪",
    "Dừng":           "⏸",
}

# Chỉ báo khi acc VƯỢT QUA ranh giới giữa hai nhóm này.
#
# 'Dừng' cố tình không nằm ở nhóm nào: đó là bạn tự tay cho nick nghỉ, không
# phải sự cố, nên không có gì để báo.
HOAT_DONG       = ("Active",)
NGUNG_HOAT_DONG = ("Spam", "Cookie hết hạn")


def _huong_doi(cu: str, moi: str) -> str:
    """
    Cặp (trạng thái cũ, trạng thái mới) này có đáng báo không?

    Trả 'hong' khi đang chạy mà ngưng, 'hoi_phuc' khi ngưng mà chạy lại, và
    chuỗi rỗng khi không phải chuyển trạng thái thật sự.

    Vì sao phải so cũ với mới chứ không cứ ghi là báo: acc dính spam bị dò lại
    MỖI TIẾNG, và mỗi lần dò hỏng lại ghi 'Spam' đè lên 'Spam'. Cứ ghi là báo
    thì một acc kẹt cả tuần sẽ nhắn 168 lần, toàn tin giống hệt nhau — và người
    ta sẽ tắt bot đi, rồi bỏ lỡ cái cảnh báo thật sự tiếp theo.
    """
    cu, moi = (cu or "").strip(), (moi or "").strip()
    if not cu or cu == moi:
        return ""
    if cu in HOAT_DONG and moi in NGUNG_HOAT_DONG:
        return "hong"
    if cu in NGUNG_HOAT_DONG and moi in HOAT_DONG:
        return "hoi_phuc"
    return ""


def _da_bao_gan_day(ten_acc: str, chuyen: str) -> bool:
    """
    Đã báo đúng lần chuyển này trong `LAP_LAI_PHUT` phút chưa?

    Khoá phải gồm CẢ HAI đầu của lần chuyển, không chỉ trạng thái mới. Chỉ lấy
    trạng thái mới thì hai lần chuyển khác nhau mà cùng đích sẽ đè lên nhau:
    acc A được thả khỏi Spam lúc 10:00, rồi 10:03 acc A được nạp lại cookie —
    tin thứ hai bị nuốt, đúng cái tin người dùng đang chờ.

    Ghi vào cơ sở dữ liệu chứ không giữ trong bộ nhớ, vì các phiên chạy ở những
    tiến trình khác nhau — bộ nhớ của tiến trình này không thấy tiến trình kia.
    """
    try:
        import db
        khoa = f"{ten_acc}|{chuyen}"
        with db._conn() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS tb_da_gui (
                               khoa TEXT PRIMARY KEY,
                               luc  TEXT NOT NULL
                           )""")
            r = con.execute("SELECT luc FROM tb_da_gui WHERE khoa=?", (khoa,)).fetchone()
            gio = datetime.now()
            if r:
                try:
                    truoc = datetime.fromisoformat(r["luc"])
                    if (gio - truoc).total_seconds() < LAP_LAI_PHUT * 60:
                        return True
                except Exception:
                    pass
            con.execute("INSERT INTO tb_da_gui(khoa,luc) VALUES(?,?) "
                        "ON CONFLICT(khoa) DO UPDATE SET luc=excluded.luc",
                        (khoa, gio.isoformat(timespec="seconds")))
        return False
    except Exception:
        # Không kiểm được thì cứ báo. Thừa một tin tốt hơn thiếu một cảnh báo.
        return False


def bao_doi_trang_thai(ten_acc: str, trang_thai: str, trang_thai_cu: str = "",
                       ly_do: str = "", nghi_den: str = "") -> None:
    """
    Acc vừa chuyển từ `trang_thai_cu` sang `trang_thai`.

    Chỉ báo hai chiều đáng quan tâm — đang chạy mà ngưng, và ngưng mà chạy lại.
    Mọi thứ khác im lặng, kể cả ghi đè cùng một trạng thái.

    KHÔNG biết trạng thái cũ thì KHÔNG báo. Nghe có vẻ mất cảnh báo, nhưng ngược
    lại: chỗ gọi nào cũng đọc được trạng thái cũ ngay trước khi ghi, nên thiếu
    nó nghĩa là chỗ gọi đó viết sai — và im lặng thì còn sửa được, chứ báo bừa
    mỗi lần ghi thì thành 168 tin một tuần cho một acc kẹt.

    `nghi_den` nhận dạng ISO như trong cơ sở dữ liệu; hỏng thì bỏ qua, không để
    một cái mốc giờ xấu làm hỏng cả thông báo.
    """
    try:
        if not san_sang():
            return
        huong = _huong_doi(trang_thai_cu, trang_thai)
        if not huong:
            return

        c = cau_hinh()
        if huong == "hong":
            dau, tieu_de = "🔴", "NGỪNG HOẠT ĐỘNG"
        else:
            dau, tieu_de = "🟢", "HOẠT ĐỘNG TRỞ LẠI"

        dong = [f"{dau} {c['ten_may']} — {tieu_de}",
                f"{ten_acc}: {trang_thai_cu} → {trang_thai}"]

        chi_tiet = []
        if (ly_do or "").strip():
            chi_tiet.append(ly_do.strip())
        if (nghi_den or "").strip():
            try:
                chi_tiet.append(f"nghỉ tới {datetime.fromisoformat(nghi_den):%H:%M}")
            except Exception:
                pass
        if chi_tiet:
            dong.append(" · ".join(chi_tiet))

        # Chặn trùng chỉ còn là lưới an toàn cho trường hợp hai tiến trình cùng
        # đọc được trạng thái cũ rồi cùng ghi. Việc chống lặp thật sự do
        # `_huong_doi` lo. Khoá gồm cả hai đầu của lần chuyển, nên hai lần
        # chuyển khác nhau không bao giờ nuốt nhau.
        if _da_bao_gan_day(ten_acc, f"{trang_thai_cu}→{trang_thai}"):
            return
        gui("\n".join(dong))
    except Exception as e:
        logger.debug(f"bao_doi_trang_thai hỏng: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Bản tổng kết
# ═══════════════════════════════════════════════════════════════════════════

def tom_tat() -> str:
    """
    Dựng bản tổng kết của RIÊNG máy này.

    Liệt kê acc có vấn đề, không liệt kê acc đang chạy tốt: nhìn 40 dòng xanh
    không cho biết thêm điều gì, còn 2 dòng đỏ thì có.
    """
    try:
        import db
        c    = cau_hinh()
        accs = db.get_accounts()
        if not accs:
            return f"📊 {c['ten_may']} — chưa có tài khoản nào."

        tot = [a for a in accs if (a.get("trang_thai") or "") == "Active"]
        xau = [a for a in accs if (a.get("trang_thai") or "") != "Active"]

        dong = [f"📊 {c['ten_may']} · {datetime.now():%d/%m %H:%M}",
                f"{len(tot)}/{len(accs)} Active"]

        if not xau:
            dong.append("")
            dong.append("Tất cả đang chạy bình thường.")
            return "\n".join(dong)

        dong.append("")
        for a in sorted(xau, key=lambda x: (x.get("trang_thai") or "")):
            tt = a.get("trang_thai") or "?"
            d  = f"{BIEU_TUONG.get(tt, '•')} {a['ten_acc']} — {tt}"
            phu = []
            if (a.get("ly_do_nghi") or "").strip():
                phu.append(a["ly_do_nghi"].strip())
            if (a.get("nghi_den") or "").strip():
                try:
                    phu.append(f"tới {datetime.fromisoformat(a['nghi_den']):%H:%M}")
                except Exception:
                    pass
            if phu:
                d += f" ({', '.join(phu)})"
            dong.append(d)
        return "\n".join(dong)
    except Exception as e:
        logger.debug(f"tom_tat hỏng: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# Luồng nền: tổng kết đúng giờ, và nghe lệnh
# ═══════════════════════════════════════════════════════════════════════════

# Đã xử lý những lệnh nào rồi — riêng của tiến trình này.
_da_xu_ly: set[int] = set()


def _nghe_lenh():
    """
    Hỏi Telegram xem có lệnh mới không, rồi trả lời.

    CHỖ NÀY CÓ MỘT MẸO, ĐỌC KỸ TRƯỚC KHI SỬA
    ─────────────────────────────────────────
    Telegram giao mỗi lệnh cho ĐÚNG MỘT bên hỏi, rồi xoá. Ba máy cùng dùng một
    bot mà máy nào cũng xác nhận đã đọc, thì `/tinhtrang` chỉ có một máy nhận
    được — hai máy kia im lặng, đúng cái ta không muốn.

    Nên ở đây dùng offset ÂM: xin mấy lệnh gần nhất và KHÔNG xác nhận đã đọc.
    Telegram giữ nguyên hàng đợi, nên cả ba máy cùng thấy cùng một lệnh và cùng
    trả lời. Mỗi máy tự nhớ mình đã xử lý lệnh nào trong `_da_xu_ly`.

    Vì vậy: ĐỪNG bao giờ đổi thành `offset=<update_id>+1`. Làm thế là xác nhận,
    và các máy khác sẽ mất lệnh.

    Xin 10 lệnh gần nhất chứ không phải 1: giữa hai lần hỏi cách nhau 20 giây,
    trong nhóm đông người có thể trôi qua vài tin. Con số này chỉ đủ dùng khi
    bot GIỮ chế độ riêng tư mặc định — lúc đó trong nhóm nó chỉ nhìn thấy các
    lệnh bắt đầu bằng '/', không thấy người ta nói chuyện với nhau. Nếu ai đó
    tắt chế độ riêng tư ở @BotFather thì mọi câu chat đều lọt vào hàng đợi và
    lệnh có thể bị đẩy ra ngoài 10 tin gần nhất.

    Nghe cả `channel_post`: trong KÊNH, bài đăng không đến dưới dạng `message`
    mà là `channel_post`. Chỉ nghe `message` thì cảnh báo vẫn tới kênh bình
    thường còn `/tinhtrang` im lặng vĩnh viễn — hỏng mà không có lấy một dòng
    lỗi để lần ra. Nghe cả hai thì chọn nhóm hay kênh đều chạy.
    """
    try:
        kq = _goi_api("getUpdates", {"offset": "-10", "timeout": "0",
                                     "allowed_updates": '["message","channel_post"]'})
        if not kq or not kq.get("ok"):
            return

        for up in kq.get("result", []):
            uid = up.get("update_id")
            if uid is None or uid in _da_xu_ly:
                continue
            _da_xu_ly.add(uid)
            # Máy chạy liên tục nhiều tháng, đừng để cái set này phình mãi. Chỉ
            # giữ 100 mã MỚI NHẤT — KHÔNG được xoá sạch: mỗi lần hỏi Telegram
            # trả lại đúng 10 lệnh gần nhất, xoá sạch là lần sau trả lời lại
            # từng ấy lệnh cũ một lần nữa.
            if len(_da_xu_ly) > 300:
                for _cu in sorted(_da_xu_ly)[:-100]:
                    _da_xu_ly.discard(_cu)

            tin  = up.get("message") or up.get("channel_post") or {}
            text = (tin.get("text") or "").strip().lower()
            # Chỉ nghe đúng khung chat đã cấu hình. Bot bị kéo vào nhóm khác thì
            # người lạ ở đó không hỏi được trạng thái acc của mình.
            if str(tin.get("chat", {}).get("id", "")) != cau_hinh()["chat_id"]:
                continue

            # Cắt phần '@tenbot' — Telegram tự thêm khi gõ lệnh trong nhóm.
            lenh = text.split()[0].split("@")[0] if text else ""
            if lenh in ("/tinhtrang", "/trangthai"):
                gui(tom_tat())
            elif lenh in ("/start", "/help"):
                gui(f"🤖 {cau_hinh()['ten_may']} đang nghe.\n\n"
                    f"/tinhtrang — xem trạng thái tài khoản của mọi máy")
    except Exception as e:
        logger.debug(f"_nghe_lenh hỏng: {e}")


def _den_gio(moc: str, lan_cuoi: str, bay_gio: datetime = None) -> bool:
    """
    Đã tới `moc` (HH:MM) của hôm nay mà hôm nay chưa gửi lần nào?

    `bay_gio` chỉ để bài kiểm đặt một mốc giờ cố định. Không có nó thì bài kiểm
    phải so với đồng hồ thật, và sẽ đúng hay sai tuỳ lúc chạy — chạy gần nửa đêm
    là vỡ, mà lỗi kiểu đó làm người ta mất tin vào cả bộ bài kiểm.
    """
    try:
        gio  = bay_gio or datetime.now()
        hom  = gio.strftime("%Y-%m-%d")
        if lan_cuoi == hom:
            return False
        h, p = (moc or "08:00").split(":")
        return (gio.hour, gio.minute) >= (int(h), int(p))
    except Exception:
        return False


def vong_nen(nghi_giay: int = 20):
    """
    Luồng nền, chạy suốt. Gọi một lần lúc phần mềm khởi động.

    Chỉ chạy trong tiến trình giao diện (server.py), KHÔNG chạy trong scheduler:
    có bốn tiến trình scheduler, để chúng cùng chạy thì mỗi ngày nhận bốn bản
    tổng kết giống hệt nhau.

    Ngày đã gửi tổng kết ghi XUỐNG cơ sở dữ liệu, không giữ trong biến. Giữ
    trong biến thì tắt app mở lại là quên, và mỗi lần khởi động lại sau giờ tổng
    kết sẽ gửi thêm một bản nữa — ngày chạy RUN_APP bốn lần là bốn tin giống hệt.
    """
    while True:
        try:
            if san_sang():
                import db
                c = cau_hinh()
                if _den_gio(c["gio_tomtat"], db.get_setting("tg_tomtat_ngay", "")):
                    # Ghi mốc TRƯỚC khi gửi: gửi trước rồi mới ghi thì lỗi mạng
                    # giữa chừng sẽ khiến vòng sau gửi lại, cứ 20 giây một lần.
                    db.set_setting("tg_tomtat_ngay", datetime.now().strftime("%Y-%m-%d"))
                    gui(tom_tat())
                _nghe_lenh()
        except Exception as e:
            logger.debug(f"vong_nen hỏng: {e}")
        time.sleep(max(5, nghi_giay))


def bat_dau_nen():
    """Khởi động luồng nền. Gọi nhiều lần cũng chỉ chạy một luồng."""
    try:
        if getattr(bat_dau_nen, "_da_chay", False):
            return
        bat_dau_nen._da_chay = True
        threading.Thread(target=vong_nen, daemon=True, name="telegram-nen").start()
    except Exception as e:
        logger.debug(f"bat_dau_nen hỏng: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Thử cấu hình — nút "Gửi thử" trên giao diện gọi vào đây
# ═══════════════════════════════════════════════════════════════════════════

def tim_chat(token: str = "") -> tuple[bool, str, list[dict]]:
    """
    Liệt kê những khung chat mà bot vừa nhìn thấy, kèm Chat ID.

    Có hàm này vì lấy Chat ID của NHÓM là bước khó nhất khi cài. `@userinfobot`
    chỉ cho ID cá nhân; ID nhóm là số ÂM và không có chỗ nào trong Telegram hiện
    nó ra. Cách duy nhất là hỏi chính con bot xem nó đang ở những nhóm nào.

    Người dùng: thêm bot vào nhóm → gõ `/start` trong nhóm → bấm nút này.

    Phải gõ một lệnh có dấu `/`, không thể gõ câu thường: bot mặc định bật chế
    độ riêng tư nên trong nhóm nó chỉ nhìn thấy các lệnh.
    """
    tok = (token or cau_hinh()["token"]).strip()
    if not tok:
        return False, "Chưa điền Token của bot.", []

    kq = _goi_api("getUpdates", {"offset": "-20", "timeout": "0"}, token=tok)
    if kq is None:
        return False, "Không gọi được Telegram — kiểm tra mạng, hoặc Token sai.", []
    if not kq.get("ok"):
        return False, f"Telegram từ chối: {kq.get('description', 'không rõ')}", []

    thay: dict[str, dict] = {}
    for up in kq.get("result", []):
        tin = (up.get("message") or up.get("channel_post")
               or up.get("my_chat_member") or {})
        ch  = tin.get("chat") or {}
        if not ch.get("id"):
            continue
        ten = ch.get("title") or " ".join(
            x for x in (ch.get("first_name"), ch.get("last_name")) if x
        ) or ch.get("username") or "(không tên)"
        kieu = str(ch.get("type", ""))
        thay[str(ch["id"])] = {
            "id":   str(ch["id"]),
            "ten":  ten,
            "loai": ("Nhóm"   if kieu.endswith("group") else
                     "Kênh"   if kieu == "channel"      else
                     "Chat riêng"),
        }

    ds = list(thay.values())
    if not ds:
        return False, ("Bot chưa thấy khung chat nào. Thêm bot vào nhóm, gõ "
                       "/start trong nhóm đó, rồi bấm lại nút này."), []
    return True, f"Thấy {len(ds)} khung chat.", ds


def thu(token: str = "", chat_id: str = "") -> tuple[bool, str]:
    """
    Gửi một tin thử và nói rõ hỏng ở đâu. Đây là hàm DUY NHẤT trong file được
    phép chờ mạng đồng bộ — người dùng đang đứng nhìn nút, và không có phiên
    đăng bài nào phụ thuộc vào nó.
    """
    c   = cau_hinh()
    tok = (token or c["token"]).strip()
    cid = (chat_id or c["chat_id"]).strip()
    if not tok:
        return False, "Chưa điền Token của bot."
    if not cid:
        return False, "Chưa điền Chat ID."

    kq = _goi_api("sendMessage",
                  {"chat_id": cid,
                   "text": f"✅ {c['ten_may']} đã nối được với Telegram.\n\n"
                           f"Từ giờ máy này sẽ báo khi có tài khoản gặp vấn đề.\n"
                           f"Gõ /tinhtrang bất cứ lúc nào để hỏi trạng thái."},
                  token=tok)
    if kq is None:
        return False, "Không gọi được Telegram — kiểm tra mạng, hoặc Token sai."
    if not kq.get("ok"):
        mo_ta = str(kq.get("description", "")).lower()
        if "chat not found" in mo_ta:
            return False, ("Chat ID sai. Nếu là NHÓM: ID nhóm là số ÂM "
                           "(-100...), bấm 'Lấy Chat ID' để lấy đúng. Nếu là "
                           "chat riêng: mở Telegram nhắn cho bot một câu trước.")
        if "unauthorized" in mo_ta:
            return False, "Token sai — chép lại từ @BotFather."
        if "kicked" in mo_ta or "not a member" in mo_ta:
            return False, "Bot đã bị xoá khỏi nhóm — thêm lại bot vào nhóm."
        return False, f"Telegram từ chối: {kq.get('description', 'không rõ')}"
    return True, "Đã gửi. Kiểm tra Telegram xem có tin chưa."
