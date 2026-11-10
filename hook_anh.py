# -*- coding: utf-8 -*-
"""
hook_anh.py — Ghép "Tiêu đề hook" lên ảnh nền hook (bong bóng rỗng).

Dùng ở luồng đăng: content bật Hook → bốc 1 ảnh nền hook từ thư viện 'Ảnh hook'
→ ghép tiêu đề vào bong bóng → CHÈN LÀM ẢNH #1 của bài, ảnh content dồn xuống
#2, #3… Mọi lỗi (thiếu Pillow/font, ảnh hỏng) đều nuốt gọn ở `chen_anh_hook_dau`
để KHÔNG làm chết phiên đăng — đăng thiếu hook còn hơn không đăng.

Chữ: MỘT màu xanh tím than, font Baloo 2 (kèm trong fonts/), tự co + xuống dòng
cho vừa "khung chữ". Khung mặc định căn giữa vùng bên phải (khớp ảnh hook mẫu:
nhân vật trái, bong bóng phải ~60%); ảnh nào đã ghim vị trí thì theo tv_bo.khung.
"""
import os
import re
import json

# Emoji / ký hiệu hình mà font Baloo 2 KHÔNG có glyph (ghép vào sẽ ra ô vuông).
# Bỏ hẳn khi ghép chữ lên ảnh hook — emoji vẫn giữ nguyên trong NỘI DUNG bài,
# chỉ lược ở ảnh bìa cho sạch. (Gạch "–", chữ Việt… KHÔNG nằm trong dải này.)
_RE_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"     # hầu hết emoji/pictograph (🏡 🔹 🔥 ⭐…)
    "\U00002600-\U000027BF"     # misc symbols + dingbats (☎ ✔ ✅ ☀…)
    "\U00002B00-\U00002BFF"     # sao/mũi tên (⭐ ⬆…)
    "\U00002300-\U000023FF"     # ⌚ ⏰ ⌛…
    "\U0000FE00-\U0000FE0F"     # variation selector (kèm sau emoji)
    "\U000020E3"                # keycap
    "]+", flags=re.UNICODE)


def _lam_sach_dong(t: str) -> str:
    """Bỏ emoji + gộp khoảng trắng thừa (do emoji để lại) trên MỘT dòng."""
    t = _RE_EMOJI.sub("", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Baloo2.ttf")
MAU_CHU   = (24, 40, 78)        # xanh tím than
WGHT      = 800                 # Baloo 2 là variable font — ép nét đậm
LINE_SP   = 1.14                # giãn dòng (dòng có chữ)
BLANK_SP  = 0.45                # dòng TRỐNG chỉ chiếm ~0.45 chiều cao → khỏi phí chỗ, chữ to hơn
# Khung chữ mặc định (tỉ lệ 0..1 theo kích thước ảnh) — vùng bong bóng bên phải.
KHUNG_MAC_DINH = {"x": 0.35, "y": 0.13, "w": 0.60, "h": 0.47}


def _doc_khung(khung, W, H):
    """Đổi khung (dict hoặc chuỗi JSON {x,y,w,h} tỉ lệ) → (bx,by,bw,bh) pixel.
    Khung rỗng / hỏng → dùng KHUNG_MAC_DINH."""
    k = dict(KHUNG_MAC_DINH)
    if khung:
        try:
            j = khung if isinstance(khung, dict) else json.loads(khung)
            for t in ("x", "y", "w", "h"):
                if t in j:
                    k[t] = float(j[t])
        except Exception:
            pass
    return int(W * k["x"]), int(H * k["y"]), int(W * k["w"]), int(H * k["h"])


def _load_font(size):
    from PIL import ImageFont
    f = ImageFont.truetype(FONT_PATH, size)
    try:
        f.set_variation_by_axes([WGHT])     # Baloo2 có một trục 'wght'
    except Exception:
        pass
    return f


def _cac_dong(tieu_de):
    """Tách tiêu đề theo xuống dòng NGƯỜI DÙNG gõ; bỏ emoji từng dòng; bỏ dòng
    trống đầu/cuối (dòng chỉ có emoji → rỗng → thành khoảng cách hoặc bị bỏ)."""
    raw = (tieu_de or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [_lam_sach_dong(l) for l in raw]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines or [""]


def _wrap_dong(d, f, t, bw):
    """Ngắt MỘT dòng người dùng cho vừa bề ngang bw — chỉ ngắt thêm khi dòng QUÁ
    dài (giữ nguyên chỗ xuống dòng người dùng gõ). Dòng trống trả [''] để làm
    khoảng cách."""
    if not t.strip():
        return [""]
    out, cur = [], ""
    for w in t.split(" "):
        thu = (cur + " " + w).strip()
        if not cur or d.textlength(thu, font=f) <= bw:
            cur = thu
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out


def ghep_tieu_de(bg_path, tieu_de, khung, out_path):
    """Ghép tiêu đề (giữ xuống dòng người dùng) lên ảnh nền → lưu PNG ra out_path.

    Cân cỡ chữ cho DỄ ĐỌC: phóng to nhất có thể; dòng quá dài TỰ NGẮT thêm cho
    khỏi phải thu nhỏ cả cụm vì một dòng dài; dòng trống chỉ chiếm ~nửa chiều cao
    (khỏi phí chỗ). Căn giữa cân mép trên/dưới."""
    from PIL import Image, ImageDraw
    im = Image.open(bg_path).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    bx, by, bw, bh = _doc_khung(khung, W, H)
    lines = _cac_dong(tieu_de)
    max_px = int(H * 0.20)              # trần cỡ chữ: content ít vẫn to mà không quá khổ

    def _bo_cuc(f):
        """(các dòng đã ngắt, chiều cao từng dòng, bề rộng lớn nhất) cho 1 cỡ chữ."""
        a, de = f.getmetrics(); base = a + de
        rows, hs = [], []
        for t in lines:
            for r in _wrap_dong(d, f, t, bw):
                rows.append(r)
                hs.append(base * LINE_SP if r.strip() else base * LINE_SP * BLANK_SP)
        widest = max([d.textlength(r, font=f) for r in rows if r.strip()] or [0])
        return rows, hs, widest

    # Phóng chữ TO NHẤT mà sau khi ngắt dòng vẫn vừa bề ngang và tổng cao vừa khung.
    size, best, best_rows, best_hs = 14, _load_font(14), None, None
    while size < max_px:
        f = _load_font(size)
        rows, hs, widest = _bo_cuc(f)
        if widest > bw or sum(hs) > bh:
            break
        best, best_rows, best_hs, size = f, rows, hs, size + 2

    if best_rows is None:              # cỡ nhỏ nhất vẫn tràn → cứ vẽ ở 14px
        best_rows, best_hs, _ = _bo_cuc(best)

    y = by + (bh - sum(best_hs)) / 2             # căn giữa dọc
    for r, h in zip(best_rows, best_hs):
        if r.strip():
            x = bx + (bw - d.textlength(r, font=best)) / 2   # căn giữa ngang
            d.text((x, y), r, font=best, fill=MAU_CHU)
        y += h
    im.save(out_path)
    return out_path


def chen_anh_hook_dau(local_photos, temp_dir, tieu_de, bg_path, khung=""):
    """Ghép tiêu đề lên bg_path → CHÈN làm ảnh #1 của local_photos.

    Trả (danh_sách_mới, temp_dir). Lỗi gì cũng trả NGUYÊN local_photos (không
    làm chết phiên đăng). KHÔNG đụng ảnh gốc: ghi file hook vào temp_dir (tạo
    mới nếu chưa có — nơi gọi dọn bằng cleanup_temp)."""
    import tempfile
    tieu_de = (tieu_de or "").strip()
    if not tieu_de or not bg_path or not os.path.exists(bg_path):
        return list(local_photos), temp_dir
    try:
        if not temp_dir:
            temp_dir = tempfile.mkdtemp(prefix="mnt_hook_")
        out = os.path.join(temp_dir, "hook_00.png")
        ghep_tieu_de(bg_path, tieu_de, khung, out)
        return [out] + list(local_photos), temp_dir
    except Exception:
        return list(local_photos), temp_dir
