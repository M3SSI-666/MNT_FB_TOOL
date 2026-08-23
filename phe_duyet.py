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

import base64
import json
import time
import urllib.error
import urllib.request

from ma_may import ma_may

# Khoá CÔNG KHAI của máy chủ, dạng base64. Nằm trong phần mềm cũng không sao:
# nó chỉ KIỂM được chữ ký chứ không TẠO được. Khoá riêng nằm ở máy chủ.
#
# Vì sao Ed25519 mà không phải HMAC: HMAC cần cả hai bên giữ CÙNG một khoá bí
# mật. Khoá đó nằm trong phần mềm trên máy khách thì sớm muộn cũng bị moi ra,
# và moi được là tự ký được "đã duyệt" cho chính mình.
#
# Đổi lại bằng khoá thật sau khi dựng máy chủ và sinh cặp khoá.
KHOA_CONG_KHAI = ""

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


def dang_ky(ten, dien_thoai, email="", ghi_chu=""):
    """Gửi đăng ký lên máy chủ. Gọi lại nhiều lần không sao — máy chủ ghi đè
    theo mã máy chứ không tạo bản ghi mới.

    Lấy cả email lẫn số điện thoại vì việc thu hồi làm theo NGƯỜI: một người
    có thể cài trên hai ba máy, cắt theo mã máy thì phải cắt từng cái và sót
    một cái là họ vẫn dùng được.
    """
    return _goi("/dang-ky", {
        "ma_may":     ma_may(),
        "ten":        (ten or "").strip()[:80],
        "dien_thoai": (dien_thoai or "").strip()[:30],
        "email":      (email or "").strip().lower()[:120],
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


def bat_buoc():
    """Có bắt buộc phải được duyệt mới dùng được phần mềm không.

    Chừng nào chưa gắn khoá công khai thì KHÔNG bắt buộc — phần mềm chạy y như
    trước. Cần thiết vì máy chủ dựng sau phần này: nếu để mặc định là bắt buộc
    thì ngay lúc cập nhật code, mọi máy đang chạy đều bị khoá ngoài, kể cả máy
    của chính mình, mà chưa có chỗ nào để xin duyệt.

    Gắn khoá công khai vào là cổng chặn tự bật.
    """
    return bool(KHOA_CONG_KHAI)


def trang_thai_hien_tai(bay_gio=None):
    """Máy này có được phép dùng phần mềm không.

    Trả về dict: {cho_vao, trang_thai, nguon, thong_bao}

    Thứ tự: hỏi máy chủ trước; hỏi được thì tin máy chủ và nhớ lại. Không hỏi
    được — mất mạng, máy chủ chết — thì lùi về kết quả đã nhớ. Nhớ mà hết hạn
    hoặc chữ ký sai thì mới chặn.
    """
    if not bat_buoc():
        return {"cho_vao": True, "trang_thai": DA_DUYET, "nguon": "chua_bat",
                "thong_bao": ""}

    ok, d = hoi_may_chu()
    if ok and isinstance(d, dict) and d.get("ok"):
        goi = {"ma_may": d.get("ma_may"), "trang_thai": d.get("trang_thai"),
               "luc": d.get("luc"), "chu_ky": d.get("chu_ky")}
        # Chỉ nhớ khi chữ ký thật. Nhớ bừa thì lần sau mất mạng là tin vào một
        # gói tin không rõ nguồn gốc.
        if chu_ky_dung(goi):
            ghi_nho(goi)
            return {"cho_vao": goi["trang_thai"] == DA_DUYET,
                    "trang_thai": goi["trang_thai"], "nguon": "may_chu",
                    "thong_bao": ""}
        return {"cho_vao": False, "trang_thai": "chu_ky_sai", "nguon": "may_chu",
                "thong_bao": "Máy chủ trả về dữ liệu không hợp lệ."}

    nho = doc_nho()
    if dung_duoc(nho, bay_gio=bay_gio):
        return {"cho_vao": True, "trang_thai": DA_DUYET, "nguon": "nho_lai",
                "thong_bao": "Không kết nối được máy chủ — đang dùng kết quả đã lưu."}
    return {"cho_vao": False,
            "trang_thai": (nho or {}).get("trang_thai", CHUA_DANG_KY),
            "nguon": "nho_lai",
            "thong_bao": d.get("loi", "") if isinstance(d, dict) else ""}


def chu_ky_dung(goi_tin, khoa_cong_khai=None):
    """Chữ ký của máy chủ trên gói tin này có thật không.

    Không có bước này thì cả cơ chế vô nghĩa: ai cũng tự tạo được một file
    phe_duyet.json ghi "da_duyet" rồi dùng thoải mái.

    Chữ ký phủ đúng ba phần `mã máy | trạng thái | thời điểm`, nên sửa bất kỳ
    phần nào — đổi "bi_cat" thành "da_duyet", hay đẩy thời điểm về tương lai để
    kéo dài hạn — đều làm chữ ký hỏng.
    """
    kck = KHOA_CONG_KHAI if khoa_cong_khai is None else khoa_cong_khai
    if not kck:
        # Chưa gắn khoá (giai đoạn dựng). Trả False chứ KHÔNG trả True: thiếu
        # khoá mà cho qua thì lỡ quên gắn là mở toang cho tất cả.
        return False
    if not isinstance(goi_tin, dict):
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        khoa = Ed25519PublicKey.from_public_bytes(base64.b64decode(kck))
        noi = "{}|{}|{}".format(goi_tin.get("ma_may", ""),
                                goi_tin.get("trang_thai", ""),
                                goi_tin.get("luc", ""))
        khoa.verify(base64.b64decode(goi_tin.get("chu_ky", "")), noi.encode("utf-8"))
        return True
    except Exception:
        # Chữ ký sai, thiếu, hỏng dạng base64, hay thiếu thư viện — đều là
        # không tin được.
        return False


def dung_duoc(goi_tin, bay_gio=None, khoa_cong_khai=None):
    """Gói tin nhớ lại có cho mở phần mềm không.

    Phải qua CẢ HAI cửa: chữ ký thật, và còn trong hạn. Thiếu một là chặn.
    Gói tin cũng phải đúng của MÁY NÀY — không thì chép gói tin của máy đã được
    duyệt sang máy khác là dùng được.
    """
    if not chu_ky_dung(goi_tin, khoa_cong_khai):
        return False
    if goi_tin.get("ma_may") != ma_may():
        return False
    return con_han(goi_tin, bay_gio=bay_gio)


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
