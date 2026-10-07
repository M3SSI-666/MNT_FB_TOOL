"""
Nhịp đập: mỗi cơ chế tự báo "tôi vừa chạy", để phần mềm biết khi nào một bộ
phận của nó đã chết.

VÌ SAO CẦN — lỗi nguy hiểm nhất của phần mềm này không phải lỗi làm nó dừng,
mà lỗi làm một CƠ CHẾ AN TOÀN chết lặng trong khi mọi thứ khác vẫn chạy. Bảng
vẫn xanh, log vẫn đẹp, bài vẫn lên — chỉ có điều không ai còn canh chừng.

Bốn ca đã xảy ra, tìm ra trong tuần 03–07/10:

    một biến không tồn tại trong hàm kết phiên comment, nằm trong `except
    Exception` nên NameError biến thành dòng log hiền lành "Kết phiên không
    trọn vẹn" → bước dò cảnh báo gỡ bài của phiên comment KHÔNG HỀ CHẠY
    suốt 13 ngày, 178 trên 184 phiên

    bỏ 85 giây chờ để rút ngắn phiên → cửa sổ dò spam tụt từ ~110s còn ~20s,
    không có gì báo

    hàm tìm profile đẻ thư mục mới mỗi khi đổi tên/c_user → 13 acc thành 52
    thư mục, mỗi thư mục là một lần nick mất phiên đăng nhập

    bản cài không liệt kê được phiên bản → máy vệ tinh không bao giờ cập nhật
    được

Cả bốn đều KHÔNG ném lỗi ra ngoài. Không có cách nào bắt chúng bằng việc đọc
log, vì log không có gì bất thường — thứ bất thường là một dòng log ĐÁNG RA
phải có mà không có.

CÁCH LÀM. Không đi bắt từng loại lỗi, mà bắt sự IM LẶNG: mỗi cơ chế ghi một
nhịp khi chạy xong, rồi cuối ngày đối chiếu các CẶP ĐÔI phải đi cùng nhau.

    "hôm nay đăng 412 phiên mà dò cảnh báo gỡ bài 0 lần"

Câu đó bắt được cả bốn ca trên trong vòng một ngày, mà không cần đoán trước
chúng sẽ hỏng kiểu gì.

Ghi nhịp phải RẺ và KHÔNG BAO GIỜ làm hỏng việc chính: một lệnh UPDATE, bọc
try/except nuốt hết. Mất một nhịp chỉ làm báo cáo sai một dòng; ném lỗi ra thì
làm hỏng cả phiên đăng.
"""
from datetime import datetime

from utils import logger

# Tên nhịp → (nhãn cho người đọc, số GIỜ im lặng thì coi là đáng ngờ).
#
# Ngưỡng rộng tay: báo nhầm vài lần là người ta thôi đọc báo cáo, mà báo cáo
# không ai đọc thì vô dụng hơn cả không có.
CO_CHE = {
    "dang_hybrid":     ("Đăng bài (Hybrid)",        6),
    "dang_tuong_page": ("Đăng tường Page",         24),
    "comment":         ("Đi comment",              12),
    "nuoi_nick":       ("Nuôi nick",               24),
    "do_spam_dang":    ("Dò cảnh báo — phiên đăng",  6),
    "do_spam_comment": ("Dò cảnh báo — phiên comment", 12),
    "thu_link":        ("Thu link bài đã đăng",      6),
    "don_cache":       ("Dọn cache profile",        48),
    "don_profile":     ("Dọn thư mục profile",      48),
}

# CẶP ĐÔI PHẢI ĐI CÙNG NHAU. `chinh` chạy mà `kem` im thì chắc chắn có chuyện.
#
# Đây là phần giá trị nhất của cả module. Nó không cần biết hỏng vì lý do gì —
# chỉ cần biết hai thứ đáng ra luôn đi cùng nhau mà nay một cái biến mất.
CAP_DOI = [
    ("dang_hybrid", "do_spam_dang",
     "Đăng bài chạy nhưng KHÔNG dò cảnh báo gỡ bài lần nào"),
    ("comment", "do_spam_comment",
     "Đi comment chạy nhưng KHÔNG dò cảnh báo gỡ bài lần nào"),
    ("dang_hybrid", "thu_link",
     "Đăng bài chạy nhưng KHÔNG thu link lần nào"),
]


def ghi(ten: str) -> None:
    """Ghi một nhịp. Hỏng thì nuốt — mất nhịp không được phép làm hỏng việc chính."""
    try:
        import db
        hom_nay = datetime.now().strftime("%Y-%m-%d")
        with db._conn() as con:
            con.execute(
                "INSERT INTO nhip_dap (ten, lan_cuoi, ngay, so_lan) VALUES (?,?,?,1) "
                "ON CONFLICT(ten) DO UPDATE SET "
                "  lan_cuoi = excluded.lan_cuoi, "
                # Sang ngày mới thì đếm lại từ 1, không cộng dồn mãi.
                "  so_lan   = CASE WHEN ngay = excluded.ngay THEN so_lan + 1 ELSE 1 END, "
                "  ngay     = excluded.ngay",
                (ten, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), hom_nay))
    except Exception as e:
        logger.debug(f"ghi nhịp {ten} hỏng: {e}")


def doc() -> dict:
    """{ten: {"lan_cuoi": str, "so_lan": int, "gio_im": float|None}}"""
    try:
        import db
        hom_nay = datetime.now().strftime("%Y-%m-%d")
        ra = {}
        with db._conn() as con:
            for r in con.execute("SELECT ten, lan_cuoi, ngay, so_lan FROM nhip_dap"):
                gio_im = None
                try:
                    gio_im = (datetime.now()
                              - datetime.strptime(r["lan_cuoi"], "%Y-%m-%d %H:%M:%S")
                              ).total_seconds() / 3600
                except Exception:
                    pass
                ra[r["ten"]] = {
                    "lan_cuoi": r["lan_cuoi"],
                    # `so_lan` chỉ có nghĩa khi nó của HÔM NAY.
                    "so_lan": r["so_lan"] if r["ngay"] == hom_nay else 0,
                    "gio_im": gio_im,
                }
        return ra
    except Exception as e:
        logger.debug(f"đọc nhịp hỏng: {e}")
        return {}


def soi() -> list:
    """
    Tìm chỗ bất thường. Trả [(mức, câu), ...] với mức ∈ {"do", "vang"}.

    Chỉ xét cơ chế ĐÃ TỪNG CHẠY trên máy này. Máy không bật phiên comment thì
    "comment im lặng" là bình thường, không phải lỗi — báo nó lên chỉ làm người
    đọc quen với cảnh báo giả rồi bỏ qua cả cảnh báo thật.
    """
    nhip = doc()
    ra = []

    # 1. Cặp đôi đứt gãy — tín hiệu mạnh nhất.
    for chinh, kem, cau in CAP_DOI:
        a, b = nhip.get(chinh), nhip.get(kem)
        if a and a["so_lan"] > 0 and (not b or b["so_lan"] == 0):
            ra.append(("do", f"{cau} (chạy {a['so_lan']} lần hôm nay)"))

    # 2. Im lặng quá lâu so với kỳ vọng.
    for ten, (nhan, han_gio) in CO_CHE.items():
        n = nhip.get(ten)
        if not n or n["gio_im"] is None:
            continue
        if n["gio_im"] > han_gio:
            ra.append(("vang",
                       f"{nhan}: im {n['gio_im']:.0f} giờ (thường mỗi {han_gio} giờ)"))
    return ra


def bao_cao() -> str:
    """Khối chèn vào bản tổng kết Telegram cuối ngày. Rỗng nếu chưa có nhịp nào."""
    nhip = doc()
    if not nhip:
        return ""

    van_de = soi()
    dong = ["", "🩺 Tình hình từng chức năng"]

    for ten, (nhan, _) in CO_CHE.items():
        n = nhip.get(ten)
        if not n:
            continue
        if n["so_lan"] > 0:
            dong.append(f"  ✅ {nhan}: {n['so_lan']} lần")
        else:
            # Từng chạy nhưng hôm nay thì không — nói rõ lần cuối là khi nào.
            gio = f"{n['gio_im']:.0f} giờ trước" if n["gio_im"] is not None else "?"
            dong.append(f"  ⬜ {nhan}: hôm nay chưa chạy (lần cuối {gio})")

    if van_de:
        dong.append("")
        for muc, cau in van_de:
            dong.append(f"  {'🔴' if muc == 'do' else '🟡'} {cau}")

    return "\n".join(dong)
