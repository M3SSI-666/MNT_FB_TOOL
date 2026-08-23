"""Hỏi máy chủ xem máy này đã được duyệt chưa.

Luồng: khách mở phần mềm lần đầu → điền tên và số điện thoại → gửi lên máy chủ
kèm mã máy → bạn vào trang quản trị bấm Duyệt → phần mềm mở khoá.

Ba quyết định đáng nói:

NHỚ KẾT QUẢ VÀI NGÀY
    Mất mạng mà chặn ngay là phá hỏng công việc của khách vì một sự cố không
    phải lỗi của họ. Kết quả duyệt được nhớ lại; trong thời gian còn hiệu lực,
    mất mạng vẫn mở được phần mềm. Quá hạn mà vẫn không hỏi được máy chủ thì
    mới chặn.

KÝ KẾT QUẢ NHỚ
    Nếu chỉ ghi "đã duyệt" vào một file thì ai cũng tự tạo được file đó. Kết
    quả nhớ lại được ký bằng chữ ký của máy chủ, và phần mềm kiểm chữ ký trước
    khi tin. Không có khoá bí mật thì không giả được.

CẮT QUYỀN CÓ ĐỘ TRỄ
    Bạn bấm Cắt thì máy đó dùng được thêm tối đa bằng thời gian nhớ ở trên rồi
    mới dừng. Đây là cái giá của việc cho chạy khi mất mạng — không tránh được,
    chỉ chọn được con số.
"""

import json
import time
import urllib.error
import urllib.request

from ma_may import ma_may

# Đổi sang địa chỉ máy chủ thật khi dựng xong.
MAY_CHU = "https://mnt-phe-duyet.example.workers.dev"

# Nhớ kết quả trong bao lâu. 7 ngày: đủ để qua một kỳ nghỉ hay một tuần mạng
# chập chờn, mà cắt quyền vẫn có hiệu lực trong vòng một tuần.
HAN_NHO_NGAY = 7

CHO_DUYET = "cho_duyet"     # đã đăng ký, bạn chưa bấm gì
DA_DUYET  = "da_duyet"
BI_CAT    = "bi_cat"
CHUA_DANG_KY = "chua_dang_ky"


def _goi(duong_dan, du_lieu=None, giay=12):
    """Gọi một đường dẫn trên máy chủ. Trả (ok, dữ liệu) — không ném lỗi ra
    ngoài, vì mọi chỗ gọi đều phải xử lý được trường hợp mất mạng."""
    url = MAY_CHU.rstrip("/") + duong_dan
    try:
        if du_lieu is None:
            req = urllib.request.Request(url, method="GET")
        else:
            req = urllib.request.Request(
                url, data=json.dumps(du_lieu).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=giay) as r:
            return True, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return False, json.loads(e.read().decode("utf-8"))
        except Exception:
            return False, {"loi": f"máy chủ trả lỗi {e.code}"}
    except Exception as e:
        return False, {"loi": f"không gọi được máy chủ: {e}"}


def dang_ky(ten, dien_thoai, ghi_chu=""):
    """Gửi đăng ký lên máy chủ. Gọi lại nhiều lần không sao — máy chủ ghi đè
    theo mã máy chứ không tạo bản ghi mới."""
    return _goi("/dang-ky", {
        "ma_may":     ma_may(),
        "ten":        (ten or "").strip()[:80],
        "dien_thoai": (dien_thoai or "").strip()[:30],
        "ghi_chu":    (ghi_chu or "").strip()[:200],
    })


def hoi_may_chu():
    """Hỏi trạng thái hiện tại. Trả (ok, dữ liệu)."""
    return _goi("/kiem-tra?ma_may=" + ma_may())


def _duong_dan_nho():
    # Để cạnh dữ liệu, không để cạnh mã nguồn: bản cài có thư mục mã nguồn bị
    # xoá sạch mỗi lần cập nhật.
    from config import DATA_ROOT
    return DATA_ROOT / "phe_duyet.json"


def doc_nho():
    try:
        return json.loads(_duong_dan_nho().read_text(encoding="utf-8"))
    except Exception:
        return None


def ghi_nho(goi_tin):
    try:
        p = _duong_dan_nho()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(goi_tin, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def con_han(goi_tin, bay_gio=None):
    """Kết quả nhớ lại còn dùng được không.

    Tách riêng để kiểm được bằng assertion mà không cần máy chủ. `bay_gio` là
    để bài kiểm tự đặt thời điểm, khỏi phụ thuộc đồng hồ máy.
    """
    if not isinstance(goi_tin, dict):
        return False
    if goi_tin.get("trang_thai") != DA_DUYET:
        return False
    try:
        luc = float(goi_tin.get("luc", 0))
    except (TypeError, ValueError):
        return False
    if luc <= 0:
        return False
    t = time.time() if bay_gio is None else bay_gio
    # Đồng hồ máy bị vặn LÙI thì `t - luc` âm. Không cho qua: vặn lùi là cách
    # dễ nhất để kéo dài hạn vô tận.
    troi = t - luc
    return 0 <= troi <= HAN_NHO_NGAY * 86400
