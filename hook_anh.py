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
import json

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Baloo2.ttf")
MAU_CHU   = (24, 40, 78)        # xanh tím than
WGHT      = 800                 # Baloo 2 là variable font — ép nét đậm
LINE_SP   = 1.18                # giãn dòng
# Khung chữ mặc định (tỉ lệ 0..1 theo kích thước ảnh) — vùng bong bóng bên phải.
KHUNG_MAC_DINH = {"x": 0.36, "y": 0.15, "w": 0.58, "h": 0.43}


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
    """Tách tiêu đề theo xuống dòng NGƯỜI DÙNG gõ; bỏ dòng trống đầu/cuối."""
    lines = (tieu_de or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines or [""]


def ghep_tieu_de(bg_path, tieu_de, khung, out_path):
    """Ghép tiêu đề (giữ xuống dòng) lên ảnh nền bg_path → lưu PNG ra out_path.
    Tự co chữ TO NHẤT mà vẫn vừa khung, căn giữa cân mép trên/dưới."""
    from PIL import Image, ImageDraw
    im = Image.open(bg_path).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    bx, by, bw, bh = _doc_khung(khung, W, H)
    lines = _cac_dong(tieu_de)
    max_px = int(H * 0.16)              # trần cỡ chữ: content ít vẫn to mà không quá khổ

    # Phóng chữ to nhất mà mọi dòng vừa bề ngang và tổng cao vừa khung.
    size, best = 14, _load_font(14)
    while size < max_px:
        f = _load_font(size)
        a, de = f.getmetrics(); lh = (a + de) * LINE_SP
        widest = max(d.textlength(t, font=f) for t in lines)
        if widest > bw or lh * len(lines) > bh:
            break
        best, size = f, size + 2

    f = best
    a, de = f.getmetrics(); lh = (a + de) * LINE_SP
    y = by + (bh - lh * len(lines)) / 2          # căn giữa dọc
    for t in lines:
        x = bx + (bw - d.textlength(t, font=f)) / 2   # căn giữa ngang
        d.text((x, y), t, font=f, fill=MAU_CHU)
        y += lh
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
