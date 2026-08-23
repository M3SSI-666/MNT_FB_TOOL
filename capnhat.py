"""Chọn phiên bản để cập nhật.

Tách khỏi server.py vì phần dễ sai nhất ở đây là **so sánh số phiên bản** và
**bóc ghi chú từ CHANGELOG** — hai việc thuần tính toán, kiểm được bằng
assertion. Phần gọi git nằm lại server.py.

Vì sao phải lấy CHANGELOG từ tag mới nhất chứ không đọc file trên đĩa: file
trên đĩa là của bản khách **đang cài**, nên nó không hề biết các bản mới hơn.
Tag mới nhất chứa đủ mục của mọi bản, kể cả cũ, nên một file là đủ.
"""

import re

# "## v1.1.0 — 23/08/2026" → nhóm 1 là số, nhóm 2 là phần còn lại của tiêu đề.
# Bắt buộc có khoảng trắng sau số để "## v1.1.0" không nuốt nhầm "## v1.1.01".
_TIEU_DE = re.compile(r"(?m)^## v(\d+\.\d+\.\d+)[ \t]+(.*)$")


def kieu_so(v):
    """'1.10.2' → (1, 10, 2). Dùng để so sánh, không dùng thứ tự chữ cái:
    xếp chữ cái thì '1.9.0' đứng SAU '1.10.0', tức là sai."""
    return tuple(int(x) for x in v.split("."))


def doc_ghi_chu(text):
    """CHANGELOG.md → {'1.1.0': {'ngay': ..., 'ghi_chu': ...}}"""
    moc = list(_TIEU_DE.finditer(text or ""))
    ra = {}
    for i, m in enumerate(moc):
        het = moc[i + 1].start() if i + 1 < len(moc) else len(text)
        than = text[m.end():het].strip()
        # Tiêu đề dạng "— 23/08/2026"; lấy phần ngày nếu có, bỏ gạch ngang.
        duoi = m.group(2).strip().lstrip("—-").strip()
        ra[m.group(1)] = {"ngay": duoi, "ghi_chu": than}
    return ra


def danh_sach_ban(tags, changelog, dang_dung):
    """Ghép danh sách bản để hiện trong giao diện.

    tags       — tên tag lấy từ git, ví dụ ['v1.1.0', 'v1.0.5']
    changelog  — nội dung CHANGELOG.md lấy từ tag mới nhất
    dang_dung  — số phiên bản đang chạy, ví dụ '1.1.0'

    Trả về danh sách đã xếp từ mới xuống cũ. Mỗi mục có `huong`:
      'moi'      bản mới hơn bản đang chạy  → cập nhật lên
      'dang_chay'
      'cu'       bản cũ hơn                 → lùi về, cảnh báo mất tính năng
    """
    ghi_chu = doc_ghi_chu(changelog)

    so = []
    for t in tags or []:
        s = t[1:] if t.startswith("v") else t
        # Bỏ qua tag không đúng dạng MAJOR.MINOR.PATCH thay vì để nó làm hỏng
        # cả danh sách: kho code có thể mang tag khác cho mục đích khác.
        if re.fullmatch(r"\d+\.\d+\.\d+", s):
            so.append(s)
    so = sorted(set(so), key=kieu_so, reverse=True)

    hien_tai = kieu_so(dang_dung) if re.fullmatch(r"\d+\.\d+\.\d+", dang_dung or "") else None

    ra = []
    for s in so:
        if hien_tai is None:
            huong = "cu"
        elif kieu_so(s) > hien_tai:
            huong = "moi"
        elif kieu_so(s) == hien_tai:
            huong = "dang_chay"
        else:
            huong = "cu"
        g = ghi_chu.get(s, {})
        ra.append({
            "phien_ban": s,
            "tag":       "v" + s,
            "ngay":      g.get("ngay", ""),
            "ghi_chu":   g.get("ghi_chu", ""),
            "huong":     huong,
        })
    return ra


def ban_moi_nhat(danh_sach):
    """Bản mới nhất, hoặc None nếu đang chạy bản mới nhất rồi."""
    for m in danh_sach:
        if m["huong"] == "moi":
            return m           # danh sách đã xếp từ mới xuống cũ
    return None
