"""
anh_bien_the.py — Sinh biến thể ảnh để né dedupe ảnh của Facebook.

Vì sao tồn tại
──────────────
Đăng đi đăng lại **cùng một file ảnh** là tín hiệu spam rõ nhất. Facebook so
khớp ảnh bằng perceptual hash (PDQ — họ tự open-source), nghĩa là đổi tên file,
đổi EXIF hay nén lại đều vô ích: hash tính trên *nội dung nhìn thấy*.

Module làm 3 việc, theo yêu cầu:
  1. lệch nhẹ độ sáng
  2. lệch nhẹ độ tương phản
  3. dán HUY HIỆU SỐ ĐIỆN THOẠI vào MỘT góc ngẫu nhiên trong 4 góc — viên thuốc
     nền trắng, vòng tròn xanh có ống nghe, số đỏ đậm, hai bên có tia xanh

Ảnh gốc KHÔNG BAO GIỜ bị sửa. Mỗi lần đăng sinh một bản sao trong thư mục temp,
đăng xong `storage.cleanup_temp()` xoá đi.

⚠️ HIỆU QUẢ NÉ HASH CỦA BỘ NÀY THẤP — ĐỌC TRƯỚC KHI SỬA
────────────────────────────────────────────────────────
Đo trên ảnh thật (chạy CLI bên dưới để tự kiểm chứng):

  • Huy hiệu ở góc:      ~0 bit GIỮA HAI BIẾN THỂ. Đo thật 09/10 trên ảnh H1:
                         biến thể ↔ ảnh gốc 6/64, nhưng biến thể ↔ biến thể chỉ
                         0–2/64 — tức hai lần đăng cùng một ảnh gốc thì Facebook
                         vẫn nhìn là MỘT. pHash hạ ảnh về lưới 32×32 rồi chỉ đọc
                         8×8 hệ số DCT tần số thấp nhất; vài chục pixel ở một
                         góc bị làm nhoè gần hết ở bước đó.
                         Huy hiệu để KHÁCH GỌI ĐƯỢC và để tra ngược bài đã đăng,
                         KHÔNG phải để né hash. Đừng phóng to nó với hy vọng né
                         tốt hơn — đã thử bản 4 số to đậm ở 4 góc, vẫn 0–2 bit.
  • Sáng + tương phản:   ~4 bit. Vẫn nằm sâu dưới ngưỡng khớp chặt (8 bit).
  • Cộng lại:            vẫn dưới ngưỡng — Facebook nhiều khả năng vẫn coi là
                         cùng một ảnh.

Thứ ĐO ĐƯỢC là có tác dụng, đã thử rồi bỏ theo yêu cầu, lấy lại được từ git:
  • Trường sáng tần số thấp (nền sáng lệch theo vùng)  → ~15 bit
  • Lật ngang (`lat_ngang=True`, vẫn còn trong code)   → ~33 bit

Nói cách khác: bộ hiện tại chống được việc so file y hệt (đổi byte, đổi EXIF),
nhưng không chống được perceptual hash. Nếu đo thấy vẫn bị gắn cờ, đây là chỗ
cần xem lại đầu tiên — đừng tăng cỡ chữ mã, nó không giúp gì.

Đo được, không phải đoán
────────────────────────
pHash là thuật toán công khai nên hiệu quả kiểm chứng được, không cần tin suông:

    python anh_bien_the.py data/media/content/homestay

In ra khoảng cách Hamming giữa ảnh gốc và biến thể. Mốc tham khảo: **≥ 32/64 bit
là an toàn**, dưới ~10 bit thì FB gần như chắc chắn coi là cùng một ảnh — lúc đó
tăng cường độ lên.

Giới hạn cần biết
─────────────────
Việc này chỉ đánh bại so khớp mức pixel. Facebook còn có mô hình nhúng ảnh
(SimSearchNet++) so khớp ở mức *nội dung ngữ nghĩa*, cố ý thiết kế để chịu được
crop/xoay/đổi màu. Không ai ngoài FB biết lớp nào áp cho trường hợp nào. Và cờ
spam là đa tín hiệu — caption lặp lại, tần suất đăng, số nhóm trên một nick
thường nặng hơn ảnh. Đây là **một lớp phòng thủ, không phải viên đạn bạc**.
"""

import io
import os
import math
import random
from pathlib import Path

from utils import logger

# Pillow là dependency tuỳ chọn: thiếu nó thì tính năng tự tắt, đăng bài vẫn
# chạy bình thường bằng ảnh gốc. Không được để việc thiếu thư viện làm hỏng
# toàn bộ luồng đăng.
try:
    from PIL import Image, ImageEnhance, ImageDraw, ImageFont
    CO_PILLOW = True
except ImportError:                                   # pragma: no cover
    CO_PILLOW = False


ANH_TINH = {".jpg", ".jpeg", ".png", ".webp"}         # .gif động → bỏ qua


# ═══════════════════════════════════════════════════════════════
# Cường độ biến đổi
# ═══════════════════════════════════════════════════════════════
# Mỗi giá trị là khoảng (min, max) để bốc ngẫu nhiên. "vua" là mặc định: đủ đổi
# hash mà mắt thường không thấy khác. "manh" dùng khi đo thấy khoảng cách hash
# vẫn thấp — đổi lại ảnh bị crop/nghiêng rõ hơn.
#
# `sang`/`tuong_phan`: hệ số nhân, 1.0 = giữ nguyên.
# `ma_co`: cỡ chữ số điện thoại, tính theo tỉ lệ bề rộng ảnh.
#
# Không còn `ma_mo`: huy hiệu phải ĐỌC RÕ để khách gọi được, không làm mờ.
CUONG_DO = {
    "nhe": {
        "sang":       (0.98, 1.02),
        "tuong_phan": (0.98, 1.02),
        "ma_co":      0.030,
        "chat":       (88, 94),     # JPEG quality
    },
    "vua": {
        "sang":       (0.96, 1.04),
        "tuong_phan": (0.96, 1.04),
        "ma_co":      0.036,
        "chat":       (84, 92),
    },
    "manh": {
        "sang":       (0.94, 1.06),
        "tuong_phan": (0.94, 1.06),
        "ma_co":      0.042,
        "chat":       (80, 90),
    },
}
CUONG_DO_MAC_DINH = "vua"

# Huy hiệu số điện thoại — màu lấy theo đúng mẫu ảnh Duong đang dùng.
SDT_MAC_DINH = "0333 194 822"
NEN_HUY_HIEU = (255, 255, 255, 240)   # viên thuốc trắng
XANH_DT      = (37, 211, 102, 255)    # vòng tròn ống nghe
DO_SO        = (225, 20, 25, 255)     # chữ số
XANH_TIA     = (46, 204, 113, 255)    # tia hai bên
BONG         = (0, 0, 0, 55)          # bóng đổ nhẹ cho viên thuốc nổi trên nền sáng


# ═══════════════════════════════════════════════════════════════
# Sinh biến thể
# ═══════════════════════════════════════════════════════════════

def _font(px: int):
    """
    Font ĐẬM của hệ thống cho số ở góc. Máy nào cũng phải ra được thứ gì đó.

    Thử font đậm trước; không có thì lùi về font thường và để `stroke_width`
    của Pillow làm dày nét thay. Không làm vậy thì trên máy thiếu font đậm,
    số dán ra mảnh dính — mà "đậm" chính là yêu cầu.
    """
    for ten in ("segoeuib.ttf", "arialbd.ttf", "tahomabd.ttf", "verdanab.ttf",
                "segoeui.ttf", "arial.ttf", "tahoma.ttf", "verdana.ttf"):
        try:
            return ImageFont.truetype(ten, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=px)      # Pillow ≥ 10
    except TypeError:                               # pragma: no cover
        return ImageFont.load_default()


def _ve_ong_nghe(d, cx: float, cy: float, dm: int) -> None:
    """Ống nghe trắng, vẽ vào giữa (cx, cy).

    Dùng ký tự 📞 của Segoe UI Symbol — font này có sẵn trên mọi bản Windows.
    Thiếu font thì bỏ qua, để vòng tròn xanh trơn: thà đơn giản còn hơn Pillow
    vẽ ra ô vuông rỗng.
    """
    for ch in ("\U0001F4DE", "☎"):               # 📞 rồi mới tới ☎
        try:
            f = ImageFont.truetype("seguisym.ttf", max(8, int(dm * 0.74)))
        except OSError:
            return
        l, t, r, b = d.textbbox((0, 0), ch, font=f)
        d.text((cx - (l + r) / 2, cy - (t + b) / 2), ch, font=f,
               fill=(255, 255, 255, 255))
        return


def _dan_sdt(im, sdt: str, ts: dict, rnd) -> str:
    """
    Dán huy hiệu số điện thoại vào MỘT góc ngẫu nhiên trong bốn góc.

    Huy hiệu dựng theo đúng mẫu Duong đang dùng: viên thuốc nền trắng, vòng
    tròn xanh có ống nghe, số đỏ đậm, hai bên ba tia xanh.

    Nền trắng và bóng đổ là bắt buộc chứ không phải trang trí: ảnh homestay
    phần lớn tường trắng và sàn gỗ sáng, chữ đỏ đặt thẳng lên đó bị chìm.

    Trả về tên góc đã dán, để ghi log tra ngược.
    """
    px = max(16, int(im.width * ts["ma_co"] * 1.15))
    f  = _font(px)

    lop = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d   = ImageDraw.Draw(lop)
    l, t, r, b = d.textbbox((0, 0), sdt, font=f)
    tw, th = r - l, b - t

    dm   = int(th * 1.55)                 # đường kính vòng tròn
    dem  = int(px * 0.40)                 # đệm trong viên thuốc
    khe  = int(px * 0.32)                 # khe giữa vòng tròn và số
    tia  = int(px * 0.70)                 # bề ngang cụm tia mỗi bên
    bw   = dem * 2 + dm + khe + tw
    bh   = max(dm, th) + dem * 2
    tong_w = bw + tia * 2                 # cả tia hai bên

    le   = max(10, int(im.width * 0.018))
    goc  = rnd.choice(("trên trái", "trên phải", "dưới trái", "dưới phải"))
    x = le if "trái" in goc else im.width - tong_w - le
    y = le if "trên" in goc else im.height - bh - le
    bx = x + tia                          # mép trái viên thuốc

    # Bóng đổ nhẹ rồi mới tới viên thuốc.
    d.rounded_rectangle([bx + 3, y + 4, bx + bw + 3, y + bh + 4],
                        radius=bh // 2, fill=BONG)
    d.rounded_rectangle([bx, y, bx + bw, y + bh], radius=bh // 2,
                        fill=NEN_HUY_HIEU)

    # Vòng tròn xanh + ống nghe trắng.
    cx, cy = bx + dem, y + (bh - dm) // 2
    d.ellipse([cx, cy, cx + dm, cy + dm], fill=XANH_DT)
    _ve_ong_nghe(d, cx + dm / 2, cy + dm / 2, dm)

    # Số điện thoại.
    d.text((bx + dem + dm + khe - l, y + (bh - th) // 2 - t),
           sdt, font=f, fill=DO_SO)

    # Ba tia mỗi bên, như mẫu.
    nen = max(2, px // 9)
    for ben in (-1, 1):
        goc_x = bx - int(tia * 0.30) if ben < 0 else bx + bw + int(tia * 0.30)
        for k, (dy, dai) in enumerate(((-0.26, 0.46), (0.0, 0.60), (0.26, 0.46))):
            y0 = y + bh / 2 + bh * dy
            x0 = goc_x - ben * int(tia * dai * 0.5)
            x1 = goc_x + ben * int(tia * dai * 0.5)
            d.line([x0, y0 - bh * dy * 0.35, x1, y0 + bh * dy * 0.35],
                   fill=XANH_TIA, width=nen)

    # Trả về đúng mode ban đầu: ảnh PNG có nền trong suốt mà ép về RGB là mất
    # kênh alpha, nền trong biến thành đen.
    return goc, Image.alpha_composite(im.convert("RGBA"), lop).convert(im.mode)


def tao_bien_the(nguon: str, dich: str, seed=None,
                 cuong_do: str = CUONG_DO_MAC_DINH,
                 lat_ngang: bool = False, sdt: str = "") -> str:
    """
    Đọc `nguon`, ghi một biến thể ra `dich` (không kể đuôi — hàm tự chọn .jpg
    hoặc .png), trả về đường dẫn file đã ghi.

    `seed` cố định thì kết quả tái lập được — cần khi cần dựng lại đúng ảnh đã
    đăng để đối chiếu. Truyền None = mỗi lần một khác.

    Hỏng ở bất kỳ bước nào thì trả về chính `nguon`: thà đăng ảnh gốc còn hơn
    hỏng cả lượt đăng.
    """
    if not CO_PILLOW:
        return nguon
    if Path(nguon).suffix.lower() not in ANH_TINH:
        return nguon                                   # .gif động: giữ nguyên

    ts = CUONG_DO.get(cuong_do, CUONG_DO[CUONG_DO_MAC_DINH])
    rnd = random.Random(seed)

    try:
        with Image.open(nguon) as im:
            im.load()
            co_alpha = im.mode in ("RGBA", "LA", "P") and "transparency" in im.info
            im = im.convert("RGBA" if co_alpha else "RGB")

            # 1. Lật ngang — tuỳ chọn, mặc định tắt. Đây là phép duy nhất ở đây
            #    thực sự dịch mạnh được pHash, đổi lại ảnh soi gương.
            if lat_ngang:
                im = im.transpose(Image.FLIP_LEFT_RIGHT)

            # 2. Sáng và tương phản, lệch nhẹ mỗi lần một khác.
            im = ImageEnhance.Brightness(im).enhance(rnd.uniform(*ts["sang"]))
            im = ImageEnhance.Contrast(im).enhance(rnd.uniform(*ts["tuong_phan"]))

            # 3. Huy hiệu số điện thoại ở một góc ngẫu nhiên.
            goc, im = _dan_sdt(im, sdt or SDT_MAC_DINH, ts, rnd)

            # 4. Ghi ra. Lưu lại là EXIF gốc (máy ảnh, GPS, ngày chụp) bị xoá
            #    sạch — bản thân EXIF trùng nhau cũng là một dấu vân tay.
            if co_alpha:
                ra = str(Path(dich).with_suffix(".png"))
                im.save(ra, "PNG", optimize=True)
            else:
                ra = str(Path(dich).with_suffix(".jpg"))
                im.save(ra, "JPEG", quality=rnd.randint(*ts["chat"]),
                        subsampling=rnd.choice((0, 2)), optimize=True)
            logger.info(f"     🔖 {Path(nguon).name} → "
                        f"{sdt or SDT_MAC_DINH} ở {goc}")
            return ra

    except Exception as e:
        logger.warning(f"  ⚠️  Không tạo được biến thể {Path(nguon).name}: {e}"
                       f" — dùng ảnh gốc")
        return nguon


def bien_the_ca_bo(duong_dan: list, thu_muc_ra: str, seed_key: str = "",
                   cuong_do: str = CUONG_DO_MAC_DINH,
                   lat_ngang: bool = False, sdt: str = "") -> list:
    """
    Biến thể cả một bộ ảnh của một bài đăng, ghi vào `thu_muc_ra`.

    Giữ nguyên thứ tự đầu vào bằng cách đánh số tên file, để ảnh lên Facebook
    đúng thứ tự người dùng đã xếp.

    `seed_key` (thường là tên acc) chỉ vào seed cùng với thời điểm gọi, nên hai
    nick đăng cùng một content ở cùng một giây vẫn ra hai bộ ảnh khác nhau.
    """
    if not duong_dan or not CO_PILLOW:
        return duong_dan

    Path(thu_muc_ra).mkdir(parents=True, exist_ok=True)
    goc_seed = f"{seed_key}|{os.getpid()}|{random.getrandbits(64)}"
    pad = len(str(len(duong_dan)))

    ra = []
    for i, p in enumerate(duong_dan, 1):
        ra.append(tao_bien_the(
            p, os.path.join(thu_muc_ra, str(i).zfill(pad)),
            seed=f"{goc_seed}|{i}", cuong_do=cuong_do, lat_ngang=lat_ngang,
            sdt=sdt))
    return ra


# ═══════════════════════════════════════════════════════════════
# Đo hiệu quả — pHash 64 bit (DCT), cùng họ với PDQ của Facebook
# ═══════════════════════════════════════════════════════════════

_N   = 32                                              # cỡ lưới trước DCT
_COS = [[math.cos((2 * x + 1) * u * math.pi / (2 * _N)) for x in range(_N)]
        for u in range(_N)]


def _dct_1d(v: list) -> list:
    return [sum(v[x] * _COS[u][x] for x in range(_N)) for u in range(_N)]


def phash(duong_dan: str) -> int:
    """
    pHash 64 bit. Không dùng numpy để khỏi thêm dependency — 32×32 nên chi phí
    không đáng kể, và hàm này chỉ chạy khi đo, không nằm trong luồng đăng bài.
    """
    if not CO_PILLOW:
        raise RuntimeError("Cần Pillow để đo pHash: pip install pillow")

    with Image.open(duong_dan) as im:
        px = list(im.convert("L").resize((_N, _N), Image.LANCZOS).getdata())

    m = [px[r * _N:(r + 1) * _N] for r in range(_N)]
    m = [_dct_1d(hang) for hang in m]                          # DCT theo hàng
    m = list(map(list, zip(*m)))
    m = [_dct_1d(cot) for cot in m]
    m = list(map(list, zip(*m)))                               # …rồi theo cột

    # Góc trên trái 8×8 = tần số thấp (bố cục tổng thể). Bỏ ô [0][0] vì nó chỉ
    # là độ sáng trung bình — giữ lại thì chỉnh sáng một chút đã đổi hash, cho
    # cảm giác an toàn giả.
    he_so = [m[u][v] for u in range(8) for v in range(8)][1:]
    sap = sorted(he_so)
    trung_vi = (sap[len(sap) // 2 - 1] + sap[len(sap) // 2]) / 2

    bits = 0
    for i, c in enumerate(he_so):
        if c > trung_vi:
            bits |= 1 << i
    return bits


# Ngưỡng quy đổi từ PDQ (256 bit) về thang pHash 64 bit ở đây. Facebook công bố
# khoảng cách ≤31/256 là "khớp chắc chắn" và ≤63/256 là "khớp lỏng" — tức ~12%
# và ~25% số bit, quy về 64 bit thành 8 và 16.
#
# Đừng lấy 32/64 làm mốc: 32/64 là mức của hai ảnh HOÀN TOÀN không liên quan,
# một biến thể vô hại không bao giờ với tới, và lấy nó làm chuẩn sẽ khiến bạn
# kết luận nhầm là mọi cường độ đều thất bại.
NGUONG_CHAT = 8
NGUONG_LONG = 16


def khoang_cach(a: int, b: int) -> int:
    """Số bit khác nhau giữa hai pHash (0 = giống hệt, 64 = ngược hoàn toàn)."""
    return bin(a ^ b).count("1")


# ═══════════════════════════════════════════════════════════════
# CLI đo hiệu quả
# ═══════════════════════════════════════════════════════════════

def _do(duong_dan: list, cuong_do: str, lat_ngang: bool, so_lan: int = 3):
    import tempfile, shutil, time

    tmp = tempfile.mkdtemp(prefix="do_bienthe_")
    print(f"\nCường độ: {cuong_do}"
          f"{' + lật ngang' if lat_ngang else ''} · {so_lan} lần/ảnh")
    print(f"Khoảng cách Hamming gốc↔biến thể (0–64). "
          f"<{NGUONG_CHAT} là FB khớp chắc chắn, "
          f"<{NGUONG_LONG} còn trong ngưỡng khớp lỏng.\n")
    print(f"{'Ảnh':<34}{'k/c hash':>10}{'giây':>8}   đánh giá")
    print("─" * 74)

    tong, dem, kem = 0, 0, 0
    try:
        for p in duong_dan:
            try:
                h0 = phash(p)
            except Exception as e:
                print(f"{Path(p).name[:33]:<34}  lỗi đọc: {e}")
                continue
            for lan in range(so_lan):
                t0 = time.time()
                bt = tao_bien_the(p, os.path.join(tmp, f"{dem}_{lan}"),
                                  cuong_do=cuong_do, lat_ngang=lat_ngang)
                giay = time.time() - t0
                if bt == p:
                    print(f"{Path(p).name[:33]:<34}    (bỏ qua)")
                    break
                d = khoang_cach(h0, phash(bt))
                tong += d
                dem += 1
                if d < NGUONG_CHAT:
                    dg, kem = "❌ FB coi là cùng ảnh", kem + 1
                elif d < NGUONG_LONG:
                    dg, kem = "⚠️  còn trong ngưỡng khớp lỏng", kem + 1
                elif d < 24:
                    dg = "🟡 vượt ngưỡng, nhưng sát"
                else:
                    dg = "✅ tốt"
                ten = Path(p).name[:33] if lan == 0 else ""
                print(f"{ten:<34}{d:>10}{giay:>8.2f}   {dg}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not dem:
        print("\nKhông đo được ảnh nào.")
        return
    tb = tong / dem
    print("─" * 74)
    print(f"Trung bình {tb:.1f}/64 bit trên {dem} lượt · "
          f"{kem} lượt còn trong ngưỡng khớp")
    ke = {"nhe": "vua", "vua": "manh"}.get(cuong_do)
    if tb < NGUONG_LONG:
        print(f"→ Cường độ '{cuong_do}' CHƯA đủ cho bộ ảnh này."
              + (f" Thử '{ke}'." if ke else " Cân nhắc bật lật ngang."))
    elif tb < 24:
        print(f"→ '{cuong_do}' đã vượt ngưỡng khớp, nhưng không dư nhiều."
              + (f" Tăng lên '{ke}' thì chắc hơn." if ke else ""))
    else:
        print(f"→ '{cuong_do}' đủ dùng cho bộ ảnh này.")
    print("\nLưu ý: con số này chỉ đo việc né so khớp mức pixel. Nó KHÔNG đo "
          "được lớp\nnhận dạng theo nội dung (SimSearchNet++), và không thay "
          "thế việc đổi caption.\nCách chắc chắn nhất vẫn là có nhiều ảnh gốc "
          "khác nhau để xoay vòng.\n")


if __name__ == "__main__":
    import sys

    # Console Windows mặc định cp1252, in tiếng Việt là crash.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not CO_PILLOW:
        print("Chưa có Pillow. Cài bằng:  pip install pillow")
        sys.exit(1)

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    cd = next((a[2:] for a in sys.argv[1:] if a.startswith("--")
               and a[2:] in CUONG_DO), CUONG_DO_MAC_DINH)
    lat = "-l" in sys.argv[1:]

    if not args:
        print(__doc__)
        print("Dùng:  python anh_bien_the.py <ảnh|thư mục> [--nhe|--vua|--manh] [-l]")
        print("  -l  bật lật ngang\n")
        sys.exit(0)

    ds = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            ds += sorted(f for f in p.iterdir()
                         if f.suffix.lower() in ANH_TINH)
        elif p.is_file():
            ds.append(p)
        else:
            print(f"Không thấy: {a}")
    if not ds:
        print("Không tìm thấy ảnh nào.")
        sys.exit(1)

    _do([str(p) for p in ds[:20]], cd, lat)
