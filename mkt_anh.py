"""
================================================================================
mkt_anh.py — Biến thể ảnh RIÊNG cho Marketplace: dán huy hiệu LIÊN HỆ
================================================================================
Marketplace đánh RẤT mạnh vào trùng bộ ảnh, nên mỗi ảnh được biến đổi riêng rồi
mới đăng. Mỗi ảnh:

  1. Bốc NGẪU NHIÊN 1 icon trong thư viện ~50 icon liên hệ (assets/icon_lienhe/).
  2. Ghép icon + SỐ ĐIỆN THOẠI (người dùng nhập ở tab Marketplace) thành một huy
     hiệu nền trắng bo tròn, cỡ vừa phải.
  3. Dán vào NGẪU NHIÊN 1 trong 4 góc ảnh.

→ Đăng 5 ảnh thì mỗi ảnh một icon + một góc khác nhau, cùng bộ ảnh ra khác hẳn.

CHỈ Marketplace dùng (gọi từ market_poster). Hỏng ở ảnh nào thì trả lại ảnh gốc
ảnh đó, KHÔNG làm chết cả lượt đăng. Thiếu Pillow → trả nguyên ảnh gốc.

Thư viện icon là các file PNG nền trong ở assets/icon_lienhe/ — người dùng thay
hoặc thêm bằng cách bỏ PNG vào đúng thư mục đó.
================================================================================
"""

import os
import random
from pathlib import Path

from utils import logger

try:
    from PIL import Image, ImageDraw, ImageFont
    CO_PILLOW = True
except ImportError:                                   # pragma: no cover
    CO_PILLOW = False

ANH_TINH = {".jpg", ".jpeg", ".png", ".webp"}         # .gif động → để nguyên

THU_MUC_ICON = Path(__file__).parent / "assets" / "icon_lienhe"
GOC_HOP_LE   = ("tren_trai", "tren_phai", "duoi_trai", "duoi_phai")

NEN_HUY_HIEU = (255, 255, 255, 204)   # viên thuốc trắng, đậm 80% cho chữ dễ đọc
BONG         = (0, 0, 0, 60)          # bóng đổ để nổi trên ảnh sáng
MAU_SO       = (225, 20, 25)          # số điện thoại — ĐỎ, đậm, bắt mắt
CO_CHU       = 0.052                  # cỡ chữ số theo bề rộng ảnh (to vừa phải)

_ICONS = None
_FONT_CACHE = {}


def _ds_icon() -> list:
    """Danh sách file icon trong thư viện (đọc một lần)."""
    global _ICONS
    if _ICONS is None:
        try:
            _ICONS = sorted(str(p) for p in THU_MUC_ICON.glob("*.png"))
        except Exception:
            _ICONS = []
    return _ICONS


def _font(px: int):
    if px not in _FONT_CACHE:
        f = None
        for ten in ("arialbd.ttf", "segoeuib.ttf", "Arialbd.ttf",
                    "DejaVuSans-Bold.ttf", "arial.ttf"):
            try:
                f = ImageFont.truetype(ten, px)
                break
            except Exception:
                continue
        if f is None:
            try:
                f = ImageFont.load_default(size=px)   # Pillow ≥ 10
            except Exception:
                f = ImageFont.load_default()
        _FONT_CACHE[px] = f
    return _FONT_CACHE[px]


def dan_lien_he(im, sdt: str, icon_path, goc: str):
    """Dán huy hiệu (icon + số điện thoại) vào một góc ảnh. Trả ảnh RGBA mới."""
    im = im.convert("RGBA")
    W, H = im.size
    px  = max(26, int(W * CO_CHU))        # cỡ chữ số — co theo bề rộng ảnh
    f   = _font(px)

    lop = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d   = ImageDraw.Draw(lop)
    l, t, r, b = d.textbbox((0, 0), sdt, font=f)
    tw, th = r - l, b - t

    co_icon = bool(icon_path)
    ic_sz = int(px * 1.55)
    pad   = int(px * 0.42)
    gap   = int(px * 0.34)
    bw = pad + (ic_sz + gap if co_icon else 0) + tw + pad
    bh = max(ic_sz if co_icon else 0, th) + int(pad * 1.1)

    le = max(10, int(W * 0.02))
    x = le if "trai" in goc else W - bw - le
    y = le if "tren" in goc else H - bh - le

    # Bóng đổ + viên thuốc trắng bo tròn.
    d.rounded_rectangle([x + 3, y + 4, x + bw + 3, y + bh + 4],
                        radius=bh // 2, fill=BONG)
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=bh // 2,
                        fill=NEN_HUY_HIEU)

    tx = x + pad
    if co_icon:
        try:
            ic = Image.open(icon_path).convert("RGBA").resize((ic_sz, ic_sz))
            lop.alpha_composite(ic, (x + pad, y + (bh - ic_sz) // 2))
            tx = x + pad + ic_sz + gap
        except Exception:
            tx = x + pad

    d.text((tx - l, y + (bh - th) // 2 - t), sdt, font=f, fill=MAU_SO)
    return Image.alpha_composite(im, lop)


def bien_the_lien_he(duong_dan: list, thu_muc_ra: str, sdt: str,
                     seed=None) -> list:
    """Biến thể cả bộ ảnh của một bài Marketplace: mỗi ảnh một icon + một góc
    ngẫu nhiên, dán số điện thoại. Giữ ĐÚNG thứ tự đầu vào (đánh số tên file).

    Ảnh nào hỏng thì giữ nguyên đường dẫn gốc ảnh đó. Thiếu Pillow / thiếu số
    điện thoại → trả nguyên danh sách gốc."""
    sdt = (sdt or "").strip()
    if not duong_dan or not CO_PILLOW or not sdt:
        return duong_dan

    icons = _ds_icon()
    try:
        Path(thu_muc_ra).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"  ⚠️  Không tạo được thư mục biến thể Market: {e}")
        return duong_dan

    rnd = random.Random(seed)
    pad = len(str(len(duong_dan)))
    ra = []
    for i, p in enumerate(duong_dan, 1):
        try:
            if Path(p).suffix.lower() not in ANH_TINH:
                ra.append(p)
                continue
            icon = rnd.choice(icons) if icons else None
            goc  = rnd.choice(GOC_HOP_LE)
            with Image.open(p) as im0:
                im0.load()
                out = dan_lien_he(im0, sdt, icon, goc)
            dich = os.path.join(thu_muc_ra, f"{str(i).zfill(pad)}.jpg")
            out.convert("RGB").save(dich, "JPEG", quality=92, optimize=True)
            ra.append(dich)
            ten_icon = Path(icon).name if icon else "(không icon)"
            logger.info(f"     🏷️  Ảnh {i}: {ten_icon} @ {goc}")
        except Exception as e:
            logger.warning(f"  ⚠️  Biến thể Market ảnh {Path(p).name} lỗi: {e}"
                           f" — dùng ảnh gốc")
            ra.append(p)
    return ra


# Chạy trực tiếp để xem thử: python mkt_anh.py <ảnh> "0333 194 822"
if __name__ == "__main__":                            # pragma: no cover
    import sys
    if len(sys.argv) < 3:
        print('Dùng:  python mkt_anh.py <ảnh> "<số điện thoại>"')
        raise SystemExit(1)
    out = bien_the_lien_he([sys.argv[1]], "bt_thu", sys.argv[2])
    print("Ra:", out)
