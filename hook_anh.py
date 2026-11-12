# -*- coding: utf-8 -*-
"""
hook_anh.py — Ghép "Tiêu đề hook" (Content Hook) lên ảnh nền hook.

Dùng ở luồng đăng: content bật Hook → bốc 1 ảnh nền hook từ thư viện 'Ảnh hook'
→ ghép tiêu đề CĂN GIỮA ảnh → CHÈN LÀM ẢNH #1 của bài, ảnh content dồn xuống
#2, #3… Mọi lỗi (thiếu Pillow/font, ảnh hỏng) đều nuốt gọn ở `chen_anh_hook_dau`
để KHÔNG làm chết phiên đăng — đăng thiếu hook còn hơn không đăng.

Nền hook nên là ẢNH CHỮ NHẬT ĐƠN GIẢN (đơn sắc hoặc hoạ tiết nhẹ, KHÔNG nhân
vật nổi bật). Chữ: một màu đỏ, font Baloo 2 (kèm trong fonts/), tự co + xuống
dòng cho CÂN ĐỐI GIỮA ảnh, chừa lề 4 phía để Facebook (nhất là Marketplace cắt
ảnh vuông ở giữa) không cắt mất chữ. Ảnh nào ghim vị trí tay thì theo tv_bo.khung.
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
MAU_CHU   = (211, 28, 28)       # đỏ tươi
WGHT      = 800                 # Baloo 2 là variable font — ép nét đậm
LINE_SP   = 1.14                # giãn dòng (dòng có chữ)
BLANK_SP  = 0.45                # dòng TRỐNG chỉ chiếm ~0.45 chiều cao → khỏi phí chỗ, chữ to hơn
# Khung dự phòng khi khung GHIM TAY bị hỏng (tỉ lệ 0..1) — căn giữa, chừa lề.
KHUNG_MAC_DINH = {"x": 0.17, "y": 0.15, "w": 0.66, "h": 0.70}

# Vùng chữ MẶC ĐỊNH (khi không ghim tay) = hình chữ nhật căn GIỮA ảnh, chừa lề 4
# phía. Bề ngang bó trong CẠNH VUÔNG giữa ảnh (= min(W,H)) để chữ sống sót khi
# Facebook/Marketplace cắt ảnh về khung vuông ở giữa.
SAFE_NGANG = 0.86      # bề ngang vùng chữ = 86% cạnh vuông giữa ảnh
SAFE_DOC   = 0.72      # chiều cao vùng chữ = 72% chiều cao ảnh


def _khung_trung_tam(W, H):
    """(bx,by,bw,bh) pixel của vùng chữ căn GIỮA ảnh, đã chừa lề an toàn."""
    canh = min(W, H)
    bw = canh * SAFE_NGANG
    bh = min(H * SAFE_DOC, canh * SAFE_NGANG)
    return int((W - bw) / 2), int((H - bh) / 2), int(bw), int(bh)


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


def _do_bong_bong(im):
    """TỰ ƯỚM vùng bong bóng = blob TRẮNG lớn nhất KHÔNG dính nhiều biên ảnh
    (ruột bong bóng). Trả khung {x,y,w,h} tỉ lệ (đã thụt vào tránh viền lồi lõm
    của mây), hoặc None nếu không chắc. Thuần PIL: thu nhỏ ảnh rồi loang vùng."""
    from collections import deque
    W0, H0 = im.size
    if W0 < 2 or H0 < 2:
        return None
    sc = min(1.0, 320.0 / max(W0, H0))              # thu nhỏ cho nhanh
    w = max(2, int(W0 * sc)); h = max(2, int(H0 * sc))
    data = list(im.convert("RGB").resize((w, h)).getdata())
    white = [1 if (p[0] > 205 and p[1] > 205 and p[2] > 205) else 0 for p in data]
    seen = bytearray(w * h)
    best = None                                      # (area, x0, y0, x1, y1)
    for s in range(w * h):
        if seen[s] or not white[s]:
            continue
        q = deque([s]); seen[s] = 1
        area = 0; x0 = x1 = s % w; y0 = y1 = s // w; border = set()
        while q:
            i = q.popleft(); area += 1
            x = i % w; y = i // w
            if x < x0: x0 = x
            if x > x1: x1 = x
            if y < y0: y0 = y
            if y > y1: y1 = y
            if x == 0: border.add(0)
            if x == w - 1: border.add(1)
            if y == 0: border.add(2)
            if y == h - 1: border.add(3)
            if x + 1 < w and not seen[i+1] and white[i+1]: seen[i+1] = 1; q.append(i+1)
            if x > 0     and not seen[i-1] and white[i-1]: seen[i-1] = 1; q.append(i-1)
            if y + 1 < h and not seen[i+w] and white[i+w]: seen[i+w] = 1; q.append(i+w)
            if y > 0     and not seen[i-w] and white[i-w]: seen[i-w] = 1; q.append(i-w)
        if len(border) >= 3:                         # dính >=3 biên → giống nền, bỏ
            continue
        if best is None or area > best[0]:
            best = (area, x0, y0, x1, y1)
    if not best or best[0] < 0.04 * w * h:           # không có / blob quá nhỏ
        return None
    _, x0, y0, x1, y1 = best
    bw_ = x1 - x0 + 1; bh_ = y1 - y0 + 1
    ix = 0.13 * bw_; iy = 0.13 * bh_                 # thụt vào tránh viền mây lồi lõm
    fx = (x0 + ix) / w; fy = (y0 + iy) / h
    fw = (bw_ - 2 * ix) / w; fh = (bh_ - 2 * iy) / h
    if fw < 0.15 or fh < 0.10:
        return None
    return {"x": round(fx, 3), "y": round(fy, 3), "w": round(fw, 3), "h": round(fh, 3)}


VIEN_TI_LE = 0.07      # bề dày viền chữ = 7% cỡ chữ (viền mảnh, gọn)


def _mau_vien(im, bx, by, bw, bh):
    """Màu VIỀN chữ chọn theo độ sáng vùng nền NGAY SAU chữ: nền tối → viền
    trắng, nền sáng → viền đậm. Nhờ viền tương phản, chữ đỏ đọc rõ trên MỌI nền
    (kể cả xám tối), không bị chìm."""
    from PIL import ImageStat
    x0 = max(0, bx); y0 = max(0, by)
    x1 = min(im.width, bx + bw); y1 = min(im.height, by + bh)
    if x1 <= x0 or y1 <= y0:
        return (255, 255, 255)
    lum = ImageStat.Stat(im.crop((x0, y0, x1, y1)).convert("L")).mean[0]
    return (255, 255, 255) if lum < 150 else (25, 25, 25)


def ghep_tieu_de(bg_path, tieu_de, khung, out_path):
    """Ghép tiêu đề (giữ xuống dòng người dùng) lên ảnh nền → lưu PNG ra out_path.

    Vị trí chữ: có `khung` GHIM TAY thì theo khung; mặc định CĂN GIỮA ảnh, chừa
    lề 4 phía để FB không cắt mất chữ (_khung_trung_tam). Cân cỡ chữ cho DỄ ĐỌC:
    phóng to nhất có thể; dòng quá dài TỰ NGẮT thêm; dòng trống chỉ chiếm ~nửa
    chiều cao. Căn giữa cân mép trên/dưới."""
    from PIL import Image, ImageDraw
    im = Image.open(bg_path).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    if khung and str(khung).strip():                 # có ghim tay → theo khung
        bx, by, bw, bh = _doc_khung(khung, W, H)
    else:                                            # mặc định → căn giữa, chừa lề
        bx, by, bw, bh = _khung_trung_tam(W, H)
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

    vien = _mau_vien(im, bx, by, bw, bh)         # viền tương phản theo nền
    sw = max(2, round(getattr(best, "size", 40) * VIEN_TI_LE))
    y = by + (bh - sum(best_hs)) / 2             # căn giữa dọc
    for r, h in zip(best_rows, best_hs):
        if r.strip():
            x = bx + (bw - d.textlength(r, font=best)) / 2   # căn giữa ngang
            d.text((x, y), r, font=best, fill=MAU_CHU,
                   stroke_width=sw, stroke_fill=vien)
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
