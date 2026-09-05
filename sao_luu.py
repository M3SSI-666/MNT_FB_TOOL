"""
Sao lưu cơ sở dữ liệu trước khi cập nhật.

VÌ SAO PHẢI CÓ FILE NÀY THAY VÌ MỘT LỆNH `copy`
════════════════════════════════════════════════
`UPDATE.bat` trước đây làm `copy data\\app.db ...`. Cách đó hỏng vì hai lẽ, và
hỏng ÂM THẦM — nó vẫn in "[OK] Da sao luu" rồi đi tiếp.

1. Cơ sở dữ liệu chạy ở chế độ WAL. Những gì vừa ghi nằm trong `app.db-wal`,
   chưa gộp vào `app.db`. Chép mỗi `app.db` là chép thiếu — đo trên máy thật:
   dữ liệu 716 KB mà bản sao ra 4 KB, và SQLite mở lên báo "file is not a
   database". Bốn bản sao lưu đang có đều không mở được.

2. Đường dẫn bị đoán, không phải hỏi. `UPDATE.bat` tìm `data\\app.db` cạnh mã
   nguồn. Nhưng bản CÀI ĐẶT để dữ liệu ở `%LOCALAPPDATA%\\MNT FB AutoPost`, nên
   trên máy vệ tinh nó không thấy gì, in "(chua co du lieu - bo qua sao luu)"
   rồi cập nhật luôn. Tức là các máy cài đặt chưa từng được sao lưu lần nào.

`VACUUM INTO` giải quyết cả hai: SQLite tự gộp WAL và ghi ra một file hoàn
chỉnh, nhất quán, kể cả khi phần mềm đang chạy và đang ghi. Còn đường dẫn thì
hỏi thẳng `config`, đúng cái mà phần mềm đang dùng.
"""

from __future__ import annotations

import base64
import contextlib
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

GIU_LAI = 14

# Nhãn ở đầu file đã mã hoá, để nhìn 6 byte đầu là biết đây là bản sao lưu của
# phần mềm này chứ không phải file rác. Đổi cách mã hoá thì tăng số lên.
DAU_FILE = b"MNTBK1\n"
DAI_MUOI = 16

# Số vòng băm khi đổi mật khẩu thành khoá. Cao thì người dò mật khẩu phải trả
# giá cao theo; 200 nghìn vòng tốn khoảng 0,1 giây trên máy thường — người dùng
# không thấy chậm, còn người dò thì mỗi lần đoán mất ngần ấy.
VONG_BAM = 200_000


def thu_muc_dich() -> Path:
    """Nơi để các bản sao lưu — cạnh dữ liệu, không phải cạnh mã nguồn."""
    from config import DB_PATH
    return Path(DB_PATH).parent.parent / "backup"


def tao(dich: Path = None) -> Path:
    """
    Tạo một bản sao lưu hoàn chỉnh và KIỂM LẠI xem nó có mở được không.

    Kiểm lại là phần bắt buộc, không phải cho chắc ăn: cả bốn bản sao lưu cũ đều
    trông như thành công mà thật ra là file hỏng. Bản sao chỉ có giá trị nếu mở
    được và còn đủ số tài khoản.
    """
    from config import DB_PATH
    nguon = Path(DB_PATH)
    if not nguon.exists():
        raise FileNotFoundError(f"Không thấy cơ sở dữ liệu: {nguon}")

    dich = Path(dich) if dich else thu_muc_dich()
    dich.mkdir(parents=True, exist_ok=True)
    ra = dich / f"app_{datetime.now():%Y%m%d_%H%M%S}.db"

    # VACUUM INTO gộp cả WAL và ghi ra file nhất quán, an toàn kể cả khi phần
    # mềm đang chạy. Đây là điểm khác cốt lõi so với `copy`.
    with contextlib.closing(sqlite3.connect(str(nguon))) as con:
        so_acc = con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        con.execute("VACUUM INTO ?", (str(ra),))

    # Mở lại bản vừa tạo bằng một kết nối mới, đếm lại. Không tin vào việc
    # "lệnh chạy xong mà không báo lỗi" nữa.
    with contextlib.closing(
            sqlite3.connect(f"file:{ra}?mode=ro", uri=True)) as ktr:
        lai = ktr.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    if lai != so_acc:
        ra.unlink(missing_ok=True)
        raise RuntimeError(f"Bản sao lưu thiếu dữ liệu: {lai}/{so_acc} tài khoản")

    _don(dich)
    return ra


# ═══════════════════════════════════════════════════════════════════════════
# Mã hoá — bắt buộc trước khi file rời khỏi máy
# ═══════════════════════════════════════════════════════════════════════════
# File sao lưu chứa mật khẩu Facebook, cookie `xs`, mã 2FA và email khôi phục
# của MỌI tài khoản. Ai cầm được nó là đăng nhập được vào tất cả. Nó không phải
# "file dữ liệu" — nó là xâu chìa khoá, và không được rời khỏi máy khi còn trần.

def _khoa_tu_mat_khau(mat_khau: str, muoi: bytes) -> bytes:
    """
    Đổi mật khẩu người dùng gõ thành khoá mã hoá.

    Không dùng thẳng mật khẩu làm khoá: người ta đặt mật khẩu ngắn và dễ đoán.
    PBKDF2 kéo dài mỗi lần thử ra, nên dò cạn từ điển trở nên đắt.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=muoi, iterations=VONG_BAM)
    return base64.urlsafe_b64encode(kdf.derive(mat_khau.encode("utf-8")))


def ma_hoa(nguon: Path, mat_khau: str, dich: Path = None) -> Path:
    """
    Mã hoá một bản sao lưu. Trả về đường dẫn file `.enc`.

    Mỗi file có `muối` riêng, sinh ngẫu nhiên và ghi ngay trong file. Nhờ vậy
    hai bản sao lưu của cùng một dữ liệu vẫn ra hai file khác nhau hoàn toàn —
    người ngoài nhìn vào không đoán được hôm nay dữ liệu có đổi hay không.
    """
    from cryptography.fernet import Fernet
    if not (mat_khau or "").strip():
        raise ValueError("Chưa đặt mật khẩu mã hoá")

    nguon = Path(nguon)
    dich  = Path(dich) if dich else nguon.with_suffix(nguon.suffix + ".enc")
    muoi  = os.urandom(DAI_MUOI)
    goi   = Fernet(_khoa_tu_mat_khau(mat_khau, muoi)).encrypt(nguon.read_bytes())
    dich.write_bytes(DAU_FILE + muoi + goi)
    return dich


def giai_ma(nguon: Path, mat_khau: str, dich: Path = None) -> Path:
    """
    Giải mã, rồi MỞ RA ĐẾM số tài khoản trước khi coi là thành công.

    Fernet tự phát hiện file bị sửa hay mật khẩu sai và ném lỗi, nhưng thế vẫn
    chưa đủ: đọc được không có nghĩa là bên trong còn nguyên một cơ sở dữ liệu
    dùng được. Bốn bản sao lưu hỏng trước đây cũng "chép xong không báo lỗi".
    """
    from cryptography.fernet import Fernet, InvalidToken
    nguon = Path(nguon)
    thoc  = nguon.read_bytes()
    if not thoc.startswith(DAU_FILE):
        raise ValueError("Không phải file sao lưu của phần mềm này")

    muoi = thoc[len(DAU_FILE):len(DAU_FILE) + DAI_MUOI]
    goi  = thoc[len(DAU_FILE) + DAI_MUOI:]
    try:
        thoat = Fernet(_khoa_tu_mat_khau(mat_khau, muoi)).decrypt(goi)
    except InvalidToken:
        raise ValueError("Sai mật khẩu, hoặc file đã bị sửa/hỏng") from None

    dich = Path(dich) if dich else nguon.with_suffix("")
    dich.write_bytes(thoat)
    try:
        with contextlib.closing(
                sqlite3.connect(f"file:{dich}?mode=ro", uri=True)) as c:
            c.execute("SELECT COUNT(*) FROM accounts").fetchone()
    except Exception as e:
        dich.unlink(missing_ok=True)
        raise ValueError(f"Giải mã xong nhưng bên trong không dùng được: {e}") from None
    return dich


def dem_acc(f: Path) -> int:
    """Số tài khoản trong một file cơ sở dữ liệu — dùng để đối chiếu."""
    with contextlib.closing(
            sqlite3.connect(f"file:{Path(f)}?mode=ro", uri=True)) as c:
        return c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]


def _don(thu_muc: Path):
    """Giữ `GIU_LAI` bản mới nhất, xoá bớt cho khỏi phình ổ đĩa."""
    ds = sorted(thu_muc.glob("app_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for cu in ds[GIU_LAI:]:
        try:
            cu.unlink()
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Sao lưu hằng ngày, tự động đẩy đi nơi khác
# ═══════════════════════════════════════════════════════════════════════════

def cau_hinh() -> dict:
    """
    Cấu hình sao lưu tự động. Lỗi thì trả 'tắt', không ném ra ngoài.

    Nơi gửi lấy thẳng từ tab *Báo về Telegram* — cùng khung chat với cảnh báo,
    không có ô riêng. Chủ dự án chọn vậy để khỏi phải điền hai chỗ, và để thêm
    một trạm mới chỉ là điền đúng một bộ thông số.

    Đánh đổi cần biết: ai ở trong khung chat đó cũng nhận được file sao lưu.
    File đã mã hoá nên không mở ra được nếu không có mật khẩu, nhưng họ vẫn giữ
    được file — nên mật khẩu mã hoá phải khác mọi mật khẩu họ có thể đoán ra.
    """
    try:
        import db
        return {
            "bat":      db.get_setting("sl_bat", "0") == "1",
            "mat_khau": db.get_setting("sl_mat_khau", ""),
            "chat_id":  db.get_setting("tg_chat_id", "").strip(),
            "ngay":     db.get_setting("sl_ngay", ""),
            "ket_qua":  db.get_setting("sl_ket_qua", ""),
        }
    except Exception:
        return {"bat": False, "mat_khau": "", "chat_id": "", "ngay": "", "ket_qua": ""}


def chay_hang_ngay(ep: bool = False) -> tuple[bool, str]:
    """
    Hôm nay chưa sao lưu thì làm: tạo bản → mã hoá → đẩy lên Telegram.

    Gọi từ luồng nền lúc phần mềm khởi động. Máy trạm không bật 24/7 nên không
    hẹn giờ cố định — cứ mở phần mềm mà hôm nay chưa sao lưu thì làm luôn.

    LỚP 1 LUÔN CHẠY, LỚP 2 THÌ TUỲ. Bản trên máy được tạo trước và không phụ
    thuộc mạng; đẩy lên Telegram hỏng thì chỉ mất phần đẩy, và hôm sau thử lại —
    KHÔNG ghi nhận là "đã xong" nếu chưa đẩy được, để nó còn tự sửa.
    """
    import db
    hom_nay = datetime.now().strftime("%Y-%m-%d")
    c = cau_hinh()
    if not c["bat"]:
        return False, "Chưa bật sao lưu tự động"
    if not ep and c["ngay"] == hom_nay:
        return True, "Hôm nay đã sao lưu rồi"
    if not (c["mat_khau"] or "").strip():
        return False, "Chưa đặt mật khẩu mã hoá"
    if not c["chat_id"]:
        return False, "Chưa cấu hình Telegram ở tab Báo về Telegram"

    ban = enc = None
    try:
        # ── Lớp 1: bản trên máy ────────────────────────────────────────────
        ban = tao()
        so  = dem_acc(ban)

        # ── Lớp 2: mã hoá rồi đẩy đi ───────────────────────────────────────
        import thong_bao
        ten_may = thong_bao.cau_hinh()["ten_may"]
        an_toan = "".join(ch if ch.isalnum() else "_" for ch in ten_may).strip("_")
        enc = ban.parent / f"MNT_{an_toan}_{datetime.now():%Y%m%d}.db.enc"
        ma_hoa(ban, c["mat_khau"], enc)

        ok, loi = thong_bao.gui_file(
            enc,
            chu_thich=f"🗄 {ten_may} · {datetime.now():%d/%m/%Y}\n"
                      f"{so} tài khoản · đã mã hoá",
            chat_id=c["chat_id"])
        if not ok:
            db.set_setting("sl_ket_qua", f"Đẩy đi hỏng: {loi}")
            return False, f"Đã tạo bản trên máy, nhưng không đẩy đi được: {loi}"

        db.set_setting("sl_ngay", hom_nay)
        db.set_setting("sl_ket_qua", f"{datetime.now():%H:%M} · {so} tài khoản")
        return True, f"Đã sao lưu và gửi đi ({so} tài khoản)"
    except Exception as e:
        try:
            db.set_setting("sl_ket_qua", f"Hỏng: {e}")
        except Exception:
            pass
        return False, str(e)
    finally:
        # File .enc chỉ là bản trung gian để gửi. Bản gốc chưa mã hoá thì GIỮ
        # trên máy — đó là lớp 1, và nó phải dùng được ngay mà không cần mật khẩu.
        if enc is not None:
            try:
                Path(enc).unlink(missing_ok=True)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════════════════
# Khôi phục — đường về, phải luôn dùng được
# ═══════════════════════════════════════════════════════════════════════════

def khoi_phuc(nguon, mat_khau: str = "") -> tuple[int, Path]:
    """
    Đưa một bản sao lưu trở lại thành dữ liệu đang dùng.

    Nhận cả file `.enc` (đã mã hoá) lẫn `.db` (bản trên máy). Trả về số tài
    khoản khôi phục được và nơi đã cất bản đang dùng trước đó.

    Thứ tự có chủ ý: giải mã và ĐẾM XONG rồi mới đụng vào dữ liệu thật. Làm
    ngược lại thì một file sao lưu hỏng sẽ xoá mất bản đang chạy — mất luôn cả
    cái còn dùng được.

    PHẢI TẮT PHẦN MỀM TRƯỚC KHI GỌI. Đang chạy mà thay file dưới chân nó thì
    hai bên ghi đè lẫn nhau, hỏng cả hai.
    """
    from config import DB_PATH
    nguon = Path(nguon)
    if not nguon.exists():
        raise FileNotFoundError(f"Không thấy file: {nguon}")

    tam = nguon.parent / f"_giai_ma_tam_{os.getpid()}.db"
    try:
        if nguon.suffix == ".enc" or nguon.read_bytes()[:len(DAU_FILE)] == DAU_FILE:
            giai_ma(nguon, mat_khau, tam)
        else:
            # Bản chưa mã hoá — vẫn kiểm xem mở được không rồi mới nhận.
            dem_acc(nguon)
            tam.write_bytes(nguon.read_bytes())
        so = dem_acc(tam)

        dich = Path(DB_PATH)
        dich.parent.mkdir(parents=True, exist_ok=True)

        # Cất bản đang dùng sang một bên. Khôi phục nhầm file là chuyện xảy ra
        # thật, và lúc đó người ta cần đường lùi.
        cu = dich.parent / f"truoc_khi_khoi_phuc_{datetime.now():%Y%m%d_%H%M%S}.db"
        if dich.exists():
            cu.write_bytes(dich.read_bytes())

        tam.replace(dich)
        # Xoá WAL cũ: chúng thuộc về cơ sở dữ liệu vừa bị thay, để lại là SQLite
        # gộp nhầm phần đuôi của dữ liệu cũ vào dữ liệu vừa khôi phục.
        for duoi in ("-wal", "-shm"):
            Path(str(dich) + duoi).unlink(missing_ok=True)
        return so, cu
    finally:
        tam.unlink(missing_ok=True)


def _hoi_khoi_phuc() -> int:
    """Chế độ hỏi đáp cho `KHOI_PHUC_DU_LIEU.bat`."""
    from config import DB_PATH
    print("=" * 62)
    print(" KHOI PHUC DU LIEU TU BAN SAO LUU")
    print("=" * 62)
    print()
    print(" CANH BAO: viec nay THAY the toan bo du lieu dang dung.")
    print(" Hay chac chan da TAT phan mem truoc khi lam.")
    print()

    d = thu_muc_dich()
    ds = sorted(list(d.glob("app_*.db")) + list(d.glob("*.enc")),
                key=lambda p: p.stat().st_mtime, reverse=True)[:15]
    if ds:
        print(f" Cac ban sao luu tim thay trong {d}:")
        for i, f in enumerate(ds, 1):
            print(f"   {i:>2}. {f.name:<40} {f.stat().st_size/1024:>7.0f} KB"
                  f"  {datetime.fromtimestamp(f.stat().st_mtime):%d/%m/%Y %H:%M}")
        print()
        print(" Go SO thu tu, hoac dan duong dan day du cua mot file khac.")
    else:
        print(f" Khong thay ban sao luu nao trong {d}.")
        print(" Dan duong dan day du cua file sao luu (vi du file .enc tai tu Telegram).")
    print()

    tra_loi = input(" File: ").strip().strip('"')
    if not tra_loi:
        print(" Da huy.")
        return 1
    if tra_loi.isdigit() and ds and 1 <= int(tra_loi) <= len(ds):
        chon = ds[int(tra_loi) - 1]
    else:
        chon = Path(tra_loi)

    mk = ""
    if chon.suffix == ".enc":
        mk = input(" Mat khau ma hoa: ").strip()

    print()
    print(f" Se thay du lieu tai: {DB_PATH}")
    if input(" Go 'dong y' de tiep tuc: ").strip().lower() not in ("dong y", "dongy", "y"):
        print(" Da huy.")
        return 1

    try:
        so, cu = khoi_phuc(chon, mk)
        print()
        print(f" [OK] Da khoi phuc {so} tai khoan.")
        print(f"      Ban dang dung truoc do da cat tai: {cu}")
        print()
        print(" Mo lai phan mem de kiem tra.")
        return 0
    except Exception as e:
        print()
        print(f" [LOI] {e}")
        print("       Du lieu dang dung KHONG bi dung toi.")
        return 1


def main() -> int:
    """`UPDATE.bat` gọi vào đây. Mã thoát khác 0 nghĩa là ĐỪNG cập nhật tiếp."""
    try:
        from config import DB_PATH
        if not Path(DB_PATH).exists():
            # Máy mới tinh, chưa chạy phần mềm lần nào thì không có gì để mất.
            # Đây là trường hợp DUY NHẤT được đi tiếp mà không có bản sao lưu.
            print("     (chua co du lieu - bo qua sao luu)")
            return 0
        ra = tao()
        kb = ra.stat().st_size / 1024
        print(f"[OK] Da sao luu: {ra}  ({kb:.0f} KB)")
        return 0
    except Exception as e:
        print(f"[LOI] Khong sao luu duoc: {e}")
        return 1


if __name__ == "__main__":
    if "--khoi-phuc" in sys.argv:
        sys.exit(_hoi_khoi_phuc())
    sys.exit(main())
