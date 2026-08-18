"""
Sức khoẻ account — phát hiện acc bị Facebook chặn đăng.

Đo trên 3 ngày log thật (766 phiên, 10 acc) cho thấy có ĐÚNG HAI kiểu hỏng, và
chúng đòi hai cách xử lý ngược nhau:

  • Bị chặn tạm — 'The Anh Nguyen' hỏng 29 phiên LIÊN TIẾP ngày 10/08 rồi tự hồi,
    hôm sau chạy 29/34. Tắt acc này là mất acc chạy nhiều nhất (68 phiên thành
    công trong cùng cửa sổ đo).
  • Chết hẳn — 'Thao Ngan' chạy 9/9 ngày 10/08, rồi hỏng 71 phiên liên tiếp và
    không bao giờ hồi.

Chuỗi lỗi liên tiếp KHÔNG phân biệt được hai ca này: 29 và 71 đều là chuỗi dài.
Vì vậy phải dùng hai tín hiệu khác nhau, và đây là lý do module này tồn tại thay
vì một biến đếm lỗi:

  Tầng 1 — chuỗi lỗi liên tiếp → cho nghỉ vài giờ rồi tự thử lại.
           Sai cũng không hại: acc chỉ mất vài slot, tự quay lại.
  Tầng 2 — tỉ lệ hỏng trên cửa sổ trượt → tắt hẳn, cần người xử lý.
           Chỉ acc KHÔNG hồi mới tụt được tỉ lệ cửa sổ xuống mức này.

Chạy lại đúng 766 phiên đó với ngưỡng dưới đây: tắt 1 acc (Thao Ngan — đúng acc
đã chết), cho nghỉ 2 acc rồi cả hai chạy tiếp bình thường, không đụng tới 7 acc
khoẻ. Sửa ngưỡng thì nên chạy lại phép đo đó trước.
"""
import re

# Bao nhiêu lỗi liên tiếp thì cho nghỉ. Acc khoẻ nhất trong cửa sổ đo có chuỗi
# dài nhất là 2, acc 16% lỗi có chuỗi 10 — nên 5 nằm gọn giữa hai vùng.
CHUOI_NGHI = 5
NGHI_GIO   = 3

# Dính spam thì nghỉ bao lâu rồi THĂM DÒ một phiên. Được thì chạy tiếp bình
# thường, không được thì nghỉ thêm chừng đó nữa rồi dò lại.
#
# Vì sao thăm dò thay vì nghỉ cứng: đo trên acc 'Thao Ngan' ngày 18/08 — bị chặn
# đăng lúc 22:32, tới 00:51 đã đăng lại được 9 nhóm. Facebook thả sau chưa tới
# 90 phút, mà mốc nghỉ cứng 3 tiếng bắt nó nằm không thêm ~84 phút vô ích.
#
# Nhưng cũng KHÔNG rút cứng xuống 90 phút: lần chặn trước của chính acc đó kéo
# dài tới ~6 tiếng. Độ dài mỗi lần chặn không đoán được, nên hỏi Facebook mỗi
# tiếng một câu là cách rẻ nhất — sai thì chỉ mất đúng một phiên.
THAM_DO_PHUT = 60

# Cửa sổ trượt để quyết định tắt hẳn. 20 phiên ≈ nửa ngày chạy của một acc.
CUA_SO     = 20
NGUONG_TAT = 0.80

KY_TU_OK   = "o"
KY_TU_LOI  = "x"
# Dấu ngắt, ghi vào lúc cho acc nghỉ. Nó KHÔNG phải một phiên nên không tính vào
# tỉ lệ hỏng, chỉ có tác dụng cắt chuỗi lỗi liên tiếp.
#
# Trước đây chỗ này xoá sạch lịch sử. Làm vậy thì cửa sổ trượt không bao giờ tích
# đủ 20 phiên — cứ tới 5 lỗi là bị xoá — nên tầng 2 vĩnh viễn không nổ được và
# acc chết sẽ nghỉ-rồi-hỏng-rồi-nghỉ mãi mãi mà không ai bị tắt.
KY_TU_NGHI = "-"

_PHIEN = (KY_TU_OK, KY_TU_LOI)


def _so_phien(lich_su: str) -> int:
    return sum(1 for c in lich_su if c in _PHIEN)


def _cat(lich_su: str) -> str:
    """Giữ lại đúng `CUA_SO` phiên gần nhất (dấu ngắt không tính là phiên)."""
    while _so_phien(lich_su) > CUA_SO:
        lich_su = lich_su[1:]
    return lich_su.lstrip(KY_TU_NGHI)


def them_ket_qua(lich_su: str, ok: bool) -> str:
    """Nối kết quả một phiên vào lịch sử."""
    lich_su = "".join(c for c in (lich_su or "")
                      if c in (KY_TU_OK, KY_TU_LOI, KY_TU_NGHI))
    return _cat(lich_su + (KY_TU_OK if ok else KY_TU_LOI))


def danh_dau_nghi(lich_su: str) -> str:
    """Ghi dấu ngắt sau khi cho nghỉ, để acc có lại đủ `CHUOI_NGHI` lượt thử."""
    lich_su = lich_su or ""
    if lich_su.endswith(KY_TU_NGHI):
        return lich_su
    return _cat(lich_su + KY_TU_NGHI)


def chuoi_loi(lich_su: str) -> int:
    """Số phiên hỏng liên tiếp tính từ phiên gần nhất trở về trước."""
    n = 0
    for c in reversed(lich_su or ""):
        if c != KY_TU_LOI:
            break
        n += 1
    return n


def ti_le_hong(lich_su: str) -> float:
    """Tỉ lệ hỏng trên số phiên thật trong cửa sổ. Trả 0.0 khi chưa có phiên nào."""
    lich_su = lich_su or ""
    n = _so_phien(lich_su)
    return lich_su.count(KY_TU_LOI) / n if n else 0.0


# ── Nhận biết acc bị Facebook gỡ bài vì spam ────────────────────────────
# Nguồn tín hiệu là dialog "Sự việc" Facebook tự bật khi vừa gỡ nội dung của
# nick. Thân dialog liệt kê từng vụ dạng "Spam / Đã gỡ bài viết / <ngày>", đáy
# có nút "Xem tất cả (N)" với N là TỔNG số vụ.
#
# Vì sao đếm N chứ không bắt theo ngày: dialog hiện lại y nguyên suốt nhiều
# ngày sau đó (log có cả vụ 7/8, 10/8, 11/8, 12/8, 13/8), nên "thấy dialog =
# vừa dính" là sai — sẽ gắn cờ acc mỗi phiên vì một vụ từ tuần trước. Đếm thì
# chỉ cần N TĂNG mới là có vụ mới, không phụ thuộc vào việc đọc định dạng ngày
# tiếng Việt cho đúng.
_RE_XEM_TAT_CA = re.compile(r"xem tất cả\s*\((\d+)\)", re.I)

# Facebook diễn đạt việc gỡ nội dung theo HAI cách, và phải nhận cả hai. Đọc 9
# chuỗi cảnh báo thật trong log thấy 4 chuỗi ghi "Đã gỡ bài viết" còn 5 chuỗi
# ghi "Ảnh đã bị gỡ" — bản đầu chỉ bắt vế trước nên bỏ sót quá nửa. Phần mềm
# này đăng bài KÈM ẢNH, nên ảnh bị gỡ chính là bài bị gỡ.
_MOC_GO_BAI = ("đã gỡ bài viết", "ảnh đã bị gỡ",
               "removed your post", "your photo was removed")
_MOC_SPAM   = ("spam",)


def doc_vi_pham(text: str) -> dict | None:
    """
    Đọc nội dung dialog cảnh báo, trả về số vụ gỡ bài.

    Trả `None` nếu đây không phải dialog gỡ BÀI VIẾT — dialog cũng bật cho việc
    gỡ tin nhắn hay bình luận, mà hai thứ đó không phải lý do dừng đăng bài.

    Trả `{"so": N, "spam": bool}` với N là tổng số vụ. Ưu tiên số trong "Xem tất
    cả (N)" vì danh sách chỉ hiện sẵn 5 dòng đầu; không có thì đếm số dòng.
    """
    if not text:
        return None
    thap = " ".join(text.split()).lower()
    if not any(m in thap for m in _MOC_GO_BAI):
        return None
    m = _RE_XEM_TAT_CA.search(thap)
    so = int(m.group(1)) if m else sum(thap.count(k) for k in _MOC_GO_BAI)
    return {"so": max(so, 1), "spam": any(k in thap for k in _MOC_SPAM)}


def co_vu_moi(so_cu: int, so_moi: int) -> bool:
    """
    Có vụ gỡ bài MỚI so với lần đo trước không.

    `so_cu < 0` nghĩa là chưa từng đo acc này — lần đầu chỉ ghi mốc, KHÔNG gắn
    cờ. Thiếu bước này thì ngay phiên đầu tiên sau khi bật tính năng, mọi acc có
    sẵn vi phạm cũ đều bị đánh spam cùng lúc.
    """
    if so_cu < 0:
        return False
    return so_moi > so_cu


def danh_gia(lich_su: str) -> tuple[str, str]:
    """
    Quyết định phải làm gì với acc, dựa trên lịch sử phiên ĐĂNG BÀI.

    Trả `(hanh_dong, ly_do)` với hanh_dong ∈ {"", "nghi", "tat"}.
    "tat" được xét trước vì nó là kết luận nặng hơn và bao trùm.
    """
    lich_su = lich_su or ""

    # Chỉ kết luận "chết" khi cửa sổ đã đầy. Thiếu bước này thì acc mới chạy 5
    # phiên hỏng cả 5 sẽ ra tỉ lệ 100% và bị tắt ngay, trong khi 5 phiên chưa đủ
    # để phân biệt acc chết với acc gặp một đợt chặn tạm.
    if _so_phien(lich_su) >= CUA_SO and ti_le_hong(lich_su) >= NGUONG_TAT:
        hong = lich_su.count(KY_TU_LOI)
        return "tat", f"hỏng {hong}/{_so_phien(lich_su)} phiên gần nhất"

    n = chuoi_loi(lich_su)
    if n >= CHUOI_NGHI:
        return "nghi", f"{n} lỗi liên tiếp"

    return "", ""
