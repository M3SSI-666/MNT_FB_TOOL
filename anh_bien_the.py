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
  3. dán mã 8 ký tự chữ-số vào một trong 4 góc, mỗi ảnh một mã khác

Ảnh gốc KHÔNG BAO GIỜ bị sửa. Mỗi lần đăng sinh một bản sao trong thư mục temp,
đăng xong `storage.cleanup_temp()` xoá đi.

⚠️ HIỆU QUẢ NÉ HASH CỦA BỘ NÀY THẤP — ĐỌC TRƯỚC KHI SỬA
────────────────────────────────────────────────────────
Đo trên ảnh thật (chạy CLI bên dưới để tự kiểm chứng):

  • Mã ở góc:            ~0 bit. pHash hạ ảnh về lưới 32×32 rồi chỉ đọc 8×8 hệ
                         số DCT tần số thấp nhất; vài chục pixel ở một góc bị
                         làm nhoè gần hết ở bước đó. Mã dùng để TRA NGƯỢC bài
                         đã đăng, không phải để né.
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
# `ma_co`: cỡ chữ mã, tính theo tỉ lệ bề rộng ảnh.
# `ma_mo`: độ mờ của chữ mã (0 = tàng hình, 1 = đặc).
CUONG_DO = {
    "nhe": {
        "sang":       (0.98, 1.02),
        "tuong_phan": (0.98, 1.02),
        "ma_co":      0.030,
        "ma_mo":      0.22,
        "chat":       (88, 94),     # JPEG quality
    },
    "vua": {
        "sang":       (0.96, 1.04),
        "tuong_phan": (0.96, 1.04),
        "ma_co":      0.036,
        "ma_mo":      0.30,
        "chat":       (84, 92),
    },
    "manh": {
        "sang":       (0.94, 1.06),
        "tuong_phan": (0.94, 1.06),
        "ma_co":      0.042,
        "ma_mo":      0.38,
        "chat":       (80, 90),
    },
}
CUONG_DO_MAC_DINH = "vua"

# Bảng ký tự sinh mã. Bỏ O/0 và I/1/L để đọc log không nhầm khi cần dò lại một
# bài đã đăng.
BANG_MA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
DAI_MA  = 8


# ═══════════════════════════════════════════════════════════════
# Sinh biến thể
# ═══════════════════════════════════════════════════════════════

def _font(px: int):
    """Font hệ thống cho chữ mã. Máy nào cũng phải ra được thứ gì đó."""
    for ten in ("segoeui.ttf", "arial.ttf", "tahoma.ttf", "verdana.ttf"):
        try:
            return ImageFont.truetype(ten, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=px)      # Pillow ≥ 10
    except TypeError:                               # pragma: no cover
        return ImageFont.load_default()


def sinh_ma(rnd) -> str:
    """Mã 8 ký tự chữ-số, mỗi ảnh một mã."""
    return "".join(rnd.choice(BANG_MA) for _ in range(DAI_MA))


def _dan_ma(im, ma: str, ts: dict, rnd):
    """
    Dán mã vào một trong 4 góc, chọn ngẫu nhiên.

    Chữ vàng nhạt, mờ, cỡ ~3–4% bề rộng ảnh (ảnh 1900px → chữ ~60–80px) — đọc
    được trên bài đăng. Đây là đánh đổi có ý thức: đổi lại, mã được ghi vào log
    nên tra ngược được bài nào dùng ảnh nào.

    Lưu ý về hiệu quả né hash: đo thực tế cho thấy chữ ở góc gần như KHÔNG dịch
    được pHash. Thuật toán hạ ảnh về lưới 32×32 rồi chỉ đọc 8×8 hệ số DCT tần
    số thấp nhất — vài chục pixel ở một góc bị làm nhoè gần hết trong bước đó.
    Phần né hash ở đây đến từ sáng/tương phản, không phải từ mã.
    """
    px = max(11, int(im.width * ts["ma_co"]))
    f  = _font(px)
    lop = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d   = ImageDraw.Draw(lop)

    l, t, r, b = d.textbbox((0, 0), ma, font=f)
    tw, th = r - l, b - t
    le = max(8, int(im.width * 0.015))               # lề tính từ mép ảnh

    x, y = rnd.choice((
        (le,                       le),                          # trên trái
        (im.width - tw - le,       le),                          # trên phải
        (le,                       im.height - th - le * 2),     # dưới trái
        (im.width - tw - le,       im.height - th - le * 2),     # dưới phải
    ))

    d.text((x - l, y - t), ma, font=f,
           fill=(255, 235, 140, int(255 * ts["ma_mo"])))
    # Trả về đúng mode ban đầu: ảnh PNG có nền trong suốt mà ép về RGB là mất
    # kênh alpha, nền trong biến thành đen.
    return Image.alpha_composite(im.convert("RGBA"), lop).convert(im.mode)


def tao_bien_the(nguon: str, dich: str, seed=None,
                 cuong_do: str = CUONG_DO_MAC_DINH,
                 lat_ngang: bool = False) -> str:
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

            # 3. Mã 8 ký tự ở một góc ngẫu nhiên — mỗi ảnh, mỗi lượt đăng một mã.
            ma = sinh_ma(rnd)
            im = _dan_ma(im, ma, ts, rnd)

            # 4. Ghi ra. Lưu lại là EXIF gốc (máy ảnh, GPS, ngày chụp) bị xoá
            #    sạch — bản thân EXIF trùng nhau cũng là một dấu vân tay.
            if co_alpha:
                ra = str(Path(dich).with_suffix(".png"))
                im.save(ra, "PNG", optimize=True)
            else:
                ra = str(Path(dich).with_suffix(".jpg"))
                im.save(ra, "JPEG", quality=rnd.randint(*ts["chat"]),
                        subsampling=rnd.choice((0, 2)), optimize=True)
            logger.info(f"     🔖 {Path(nguon).name} → mã {ma}")
            return ra

    except Exception as e:
        logger.warning(f"  ⚠️  Không tạo được biến thể {Path(nguon).name}: {e}"
                       f" — dùng ảnh gốc")
        return nguon


def bien_the_ca_bo(duong_dan: list, thu_muc_ra: str, seed_key: str = "",
                   cuong_do: str = CUONG_DO_MAC_DINH,
                   lat_ngang: bool = False) -> list:
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
            seed=f"{goc_seed}|{i}", cuong_do=cuong_do, lat_ngang=lat_ngang))
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
