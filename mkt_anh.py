"""
================================================================================
mkt_anh.py — Biến thể ảnh RIÊNG cho Marketplace: dán SỐ ĐIỆN THOẠI vào góc ảnh
================================================================================
Marketplace đánh RẤT mạnh vào trùng bộ ảnh, nên mỗi ảnh được biến đổi riêng rồi
mới đăng. Mỗi ảnh:

  1. Dán SỐ ĐIỆN THOẠI (người dùng nhập ở tab Marketplace) vào một huy hiệu nền
     trắng mờ bo tròn, số màu đỏ.
  2. Dán vào NGẪU NHIÊN 1 trong 4 góc ảnh.

VÙNG AN TOÀN — vì sao không dán sát mép: Facebook Marketplace CẮT VUÔNG ở giữa
khi hiện thumbnail / ảnh bìa. Ảnh dọc (homestay thường 896×1195) mà dán huy hiệu
sát góc trên/dưới thì bị cắt mất → nhìn như "mất số / sai vị trí / ảnh có ảnh
không". Nên huy hiệu luôn nằm trong HÌNH VUÔNG GIỮA ẢNH (cạnh = min(W,H)) — góc
của vùng vuông đó, không phải góc của ảnh — để crop kiểu gì cũng còn.

CHỈ Marketplace dùng (gọi từ market_poster). Hỏng ở ảnh nào thì trả lại ảnh gốc
ảnh đó, KHÔNG làm chết cả lượt đăng. Thiếu Pillow → trả nguyên ảnh gốc.
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
GOC_HOP_LE = ("tren_trai", "tren_phai", "duoi_trai", "duoi_phai")

NEN_HUY_HIEU = (255, 255, 255, 204)   # viên thuốc trắng, đậm 80% cho chữ dễ đọc
BONG         = (0, 0, 0, 60)          # bóng đổ để nổi trên ảnh sáng
MAU_SO       = (225, 20, 25)          # số điện thoại — ĐỎ, đậm, bắt mắt
CO_CHU       = 0.052                  # cỡ chữ số theo bề rộng ảnh (to vừa phải)

_FONT_CACHE = {}


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


def dan_lien_he(im, sdt: str, goc: str):
    """Dán huy hiệu số điện thoại vào một góc VÙNG AN TOÀN của ảnh. Trả ảnh mới.

    Huy hiệu nằm trong hình vuông giữa ảnh (cạnh = min(W,H)) để không bị Facebook
    cắt mất khi hiện thumbnail vuông."""
    im = im.convert("RGBA")
    W, H = im.size
    px  = max(26, int(W * CO_CHU))        # cỡ chữ số — co theo bề rộng ảnh
    f   = _font(px)

    lop = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d   = ImageDraw.Draw(lop)
    l, t, r, b = d.textbbox((0, 0), sdt, font=f)
    tw, th = r - l, b - t

    pad = int(px * 0.5)                    # đệm trong viên thuốc
    bw = pad + tw + pad
    bh = th + int(pad * 1.1)

    # Vùng an toàn = hình vuông giữa ảnh, chừa thêm một lề để crop hơi lố vẫn còn.
    S  = min(W, H)
    cx = (W - S) // 2
    cy = (H - S) // 2
    le = max(12, int(S * 0.025))
    x = cx + le if "trai" in goc else cx + S - bw - le
    y = cy + le if "tren" in goc else cy + S - bh - le

    # Bóng đổ + viên thuốc trắng bo tròn.
    d.rounded_rectangle([x + 3, y + 4, x + bw + 3, y + bh + 4],
                        radius=bh // 2, fill=BONG)
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=bh // 2,
                        fill=NEN_HUY_HIEU)
    d.text((x + pad - l, y + (bh - th) // 2 - t), sdt, font=f, fill=MAU_SO)
    return Image.alpha_composite(im, lop)


def bien_the_lien_he(duong_dan: list, thu_muc_ra: str, sdt: str,
                     seed=None) -> list:
    """Biến thể cả bộ ảnh của một bài Marketplace: mỗi ảnh dán số điện thoại vào
    một góc ngẫu nhiên (trong vùng an toàn). Giữ ĐÚNG thứ tự đầu vào.

    Ảnh nào hỏng thì giữ nguyên đường dẫn gốc ảnh đó. Thiếu Pillow / thiếu số
    điện thoại → trả nguyên danh sách gốc."""
    sdt = (sdt or "").strip()
    if not duong_dan or not CO_PILLOW or not sdt:
        return duong_dan

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
            goc = rnd.choice(GOC_HOP_LE)
            with Image.open(p) as im0:
                im0.load()
                out = dan_lien_he(im0, sdt, goc)
            dich = os.path.join(thu_muc_ra, f"{str(i).zfill(pad)}.jpg")
            out.convert("RGB").save(dich, "JPEG", quality=92, optimize=True)
            ra.append(dich)
            logger.info(f"     🏷️  Ảnh {i}: số điện thoại @ {goc}")
        except Exception as e:
            logger.warning(f"  ⚠️  Biến thể Market ảnh {Path(p).name} lỗi: {e}"
                           f" — dùng ảnh gốc")
            ra.append(p)
    return ra


def dan_sdt_neu_can(local_photos: list, temp_dir, sdt: str):
    """Tiện ích dùng chung cho các poster: nếu có `sdt` + có ảnh thì dán số ĐT
    vào góc (qua bien_the_lien_he), ảnh ra lưu trong temp_dir/bt. Trả (photos,
    temp_dir). Không có sdt/ảnh → trả nguyên, không đụng gì."""
    sdt = (sdt or "").strip()
    if not local_photos or not sdt:
        return local_photos, temp_dir
    import tempfile as _tempfile
    if temp_dir is None:
        temp_dir = _tempfile.mkdtemp(prefix="mnt_bt_")
    out = bien_the_lien_he(local_photos, os.path.join(temp_dir, "bt"), sdt)
    return out, temp_dir


# Chạy trực tiếp để xem thử: python mkt_anh.py <ảnh> "0333 194 822"
if __name__ == "__main__":                            # pragma: no cover
    import sys
    if len(sys.argv) < 3:
        print('Dùng:  python mkt_anh.py <ảnh> "<số điện thoại>"')
        raise SystemExit(1)
    out = bien_the_lien_he([sys.argv[1]], "bt_thu", sys.argv[2])
    print("Ra:", out)
