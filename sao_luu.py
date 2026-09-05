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

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

GIU_LAI = 10


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
    with sqlite3.connect(str(nguon)) as con:
        so_acc = con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        con.execute("VACUUM INTO ?", (str(ra),))

    # Mở lại bản vừa tạo bằng một kết nối mới, đếm lại. Không tin vào việc
    # "lệnh chạy xong mà không báo lỗi" nữa.
    with sqlite3.connect(f"file:{ra}?mode=ro", uri=True) as ktr:
        lai = ktr.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    if lai != so_acc:
        ra.unlink(missing_ok=True)
        raise RuntimeError(f"Bản sao lưu thiếu dữ liệu: {lai}/{so_acc} tài khoản")

    _don(dich)
    return ra


def _don(thu_muc: Path):
    """Giữ `GIU_LAI` bản mới nhất, xoá bớt cho khỏi phình ổ đĩa."""
    ds = sorted(thu_muc.glob("app_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for cu in ds[GIU_LAI:]:
        try:
            cu.unlink()
        except OSError:
            pass


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
    sys.exit(main())
