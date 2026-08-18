"""
db.py — SQLite data layer cho MNT_FB
Thay thế hoàn toàn Google Sheets, không cần internet để đọc/ghi data.
"""

import sqlite3
import os
import re
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent / "data" / "app.db"


# 4 tiến trình scheduler × MAX_WORKERS luồng cùng ghi vào một file SQLite.
# Không có busy timeout thì luồng thứ hai vấp "database is locked" ngay lập tức,
# nên cho nó chờ tới 15s để lấy khoá thay vì fail.
BUSY_TIMEOUT_SEC = 15


# ═══════════════════════════════════════════════════════════════
# Loại đăng của tài khoản
# ═══════════════════════════════════════════════════════════════
# Một cột DUY NHẤT quyết định acc làm gì. Không có cờ phụ nào khác — trước đây
# có thêm 2 cột `comment_bai` / `comment_interval` làm đúng việc của "X_", để
# song song thì cùng một acc có hai nguồn sự thật mâu thuẫn nhau.
#
#   Homestay / Thuê / Bán  → chỉ đăng bài
#   X_Home / X_Thuê / X_Bán → vừa đăng vừa comment, theo tỉ lệ (mặc định 75/25)
#   (để trống)             → không vào lịch đăng nào
#
# Từng có thêm C_Home / C_Thuê / C_Bán nghĩa là "chỉ comment, không đăng", dành
# cho acc bị Facebook dỡ bài. Đã bỏ vì trạng thái `Spam` làm đúng việc đó mà
# KHÔNG cần người ngồi đổi cột: acc bị gỡ bài thì máy tự chuyển sang Spam, và
# Gen lịch tự cho nó toàn slot comment. Giữ cả hai đường thì lại thành hai nguồn
# sự thật cho cùng một tình huống — đúng lỗi đã mắc với `comment_bai` trước đây.
LOAI_DANG_OPTIONS = ("", "Homestay", "Thuê", "Bán",
                     "X_Home", "X_Thuê", "X_Bán")

# loại lịch  →  (chỉ đăng, vừa đăng vừa comment)
LOAI_LICH_MAP = {
    "homestay": ("Homestay", "X_Home"),
    "thue":     ("Thuê",     "X_Thuê"),
    "ban":      ("Bán",      "X_Bán"),
}

# Bao nhiêu phần trăm slot của acc "X_" là phiên comment. 25 = 75% đăng, 25%
# comment. Sửa được qua bảng settings (`comment_ti_le`).
TI_LE_COMMENT_MAC_DINH = 25

# Trạng thái acc do máy tự đặt khi phát hiện acc chết (xem suc_khoe_acc.py).
# Đặt vào chính cột trang_thai chứ không thêm cột cờ riêng: mọi chỗ đang lọc
# `trang_thai='Active'` — Gen lịch, get_account_by_name — nhờ đó tự động loại
# acc hỏng mà không phải sửa gì thêm.
TRANG_THAI_HONG = "Hỏng"
# Acc bị Facebook gỡ bài vì spam. KHÁC "Hỏng": acc spam vẫn comment được — đó
# là cả tiền đề của tính năng đi comment — nên nó chỉ bị chặn ĐĂNG BÀI.
TRANG_THAI_SPAM = "Spam"
TRANG_THAI_OPTIONS = ("Active", "Tạm dừng", "Cookie hết hạn",
                      TRANG_THAI_HONG, TRANG_THAI_SPAM)

# Trạng thái slot lịch do MÁY tự tắt vì acc nghỉ/chết/cookie hết hạn. Phải KHÁC
# "X" thủ công: "X" người dùng tự tắt được giữ qua ngày (reset_schedules_to_wait
# keep=("X",)), còn "X😴" tự động thì KHÔNG nằm trong keep nên đầu ngày mới tự về
# "Chờ" — acc nghỉ tạm hôm qua sẽ chạy lại hôm nay.
TT_LICH_X_TU_DONG = "X😴"

# Slot đăng bài bị dừng vì acc dính spam. Tách khỏi "X😴" (nghỉ vì lỗi liên
# tiếp) để nhìn bảng lịch là phân biệt được hai nguyên nhân. Cũng KHÔNG nằm
# trong keep của reset_schedules_to_wait nên sáng hôm sau tự về "Chờ".
TT_LICH_NGHI_SPAM = "Nghỉ Spam"


def acc_chi_comment(acc: dict) -> bool:
    """
    Acc chỉ được đi comment, không đăng bài — vì đang dính spam.

    Thay cho loại đăng "C_*" đã bỏ. Khác biệt quan trọng: đây là TRẠNG THÁI do
    máy tự đặt khi phát hiện Facebook gỡ bài, không phải lựa chọn người dùng
    phải nhớ bật/tắt. Acc khỏi spam thì sửa Trạng thái về Active là đăng lại.
    """
    return (acc.get("trang_thai") or "") == TRANG_THAI_SPAM


def la_loai_hon_hop(loai_dang: str) -> bool:
    """Acc VỪA đăng VỪA comment theo tỉ lệ (X_*)."""
    return (loai_dang or "").strip().upper().startswith("X_")


def khop_loai_lich(loai_dang: str, loai_lich: str) -> bool:
    """
    Acc thuộc lịch nào. So khớp CHÍNH XÁC, không dùng `in`: "X_Thuê" chứa chuỗi
    con "Thuê" và "X_Bán" chứa "Bán", nên so kiểu substring sẽ kéo nhầm acc
    hỗn hợp vào nhóm chỉ đăng bài.
    """
    v = (loai_dang or "").strip()
    return v in LOAI_LICH_MAP.get(loai_lich, ())


def accounts_theo_lich(loai_lich: str, trang_thai: str = None) -> list[dict]:
    """
    Mọi acc thuộc một lịch.

    Mặc định nhận cả 'Active' lẫn 'Spam'. Lọc cứng 'Active' thì acc vừa bị đánh
    spam sẽ biến mất khỏi Gen lịch — không còn slot nào, kể cả slot comment —
    trong khi comment chính là việc duy nhất acc đó còn làm được.
    """
    if trang_thai:
        nguon = get_accounts(trang_thai=trang_thai)
    else:
        nguon = [a for a in get_accounts()
                 if (a.get("trang_thai") or "") in ("Active", TRANG_THAI_SPAM)]
    return [a for a in nguon if khop_loai_lich(a.get("loai_dang"), loai_lich)]


def _conn():
    """Tạo connection với row_factory để trả về dict."""
    con = sqlite3.connect(str(DB_PATH), timeout=BUSY_TIMEOUT_SEC)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")   # concurrent reads
    con.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_SEC * 1000}")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    """Khởi tạo toàn bộ schema nếu chưa có."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.executescript("""
        -- ── Tài khoản Facebook ──────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS accounts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_idx       INTEGER DEFAULT 0,
            ten_acc         TEXT NOT NULL,
            loai_dang       TEXT DEFAULT '',        -- Bán / Thuê / Homestay
            thoi_gian_nghi  INTEGER DEFAULT 30,     -- phút
            link_profile    TEXT DEFAULT '',
            email_sdt       TEXT DEFAULT '',
            password        TEXT DEFAULT '',
            ten_page        TEXT DEFAULT '',
            c_user          TEXT DEFAULT '',
            xs              TEXT DEFAULT '',
            refresh         TEXT DEFAULT '',        -- Yes / Done / ''
            trang_thai      TEXT DEFAULT 'Active',  -- Active / Tạm dừng
            email_khoiphuc  TEXT DEFAULT '',
            pass_khoiphuc   TEXT DEFAULT '',
            twofa           TEXT DEFAULT '',
            ghi_chu         TEXT DEFAULT '',
            nuoi_nick       INTEGER DEFAULT 0,      -- 1 = bật nuôi nick cho acc này
            nuoi_interval   INTEGER DEFAULT 150,    -- chu kỳ nuôi (phút), mặc định 2h30
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ── Pages ────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS pages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ten_page        TEXT NOT NULL,
            acc_quan_ly     TEXT DEFAULT '',        -- ghi chú acc quản lý page (không ảnh hưởng logic đăng)
            page_uid        TEXT DEFAULT '',
            link_page       TEXT DEFAULT '',
            loai_page       TEXT DEFAULT '',        -- Homestay / Thuê / Bán
            bai_dang_toi_da INTEGER DEFAULT 0,      -- 0 = không xếp lịch đăng page
            ghi_chu         TEXT DEFAULT '',
            order_idx       INTEGER DEFAULT 0        -- thứ tự hiển thị (kéo-thả)
        );

        -- ── Content ──────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS content (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            loai            TEXT NOT NULL,          -- homestay / thue / ban
            ma_content      TEXT NOT NULL,
            noi_dung        TEXT DEFAULT '',
            link_anh        TEXT DEFAULT '',        -- comma-separated URLs, đăng theo đúng thứ tự này
            su_dung         TEXT DEFAULT 'Có',      -- Có / Không
            ghi_chu         TEXT DEFAULT '',
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            order_idx       INTEGER DEFAULT 0        -- thứ tự hiển thị (kéo-thả)
        );

        -- ── UID / Nhóm ───────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS uid_groups (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ma_nhom         TEXT NOT NULL,          -- TIME1, TIME2, ... hoặc '' = UID Nhóm sheet
            uid             TEXT NOT NULL,
            ten_nhom        TEXT DEFAULT '',
            link_url        TEXT DEFAULT '',
            thanh_vien      TEXT DEFAULT '',
            ghi_chu         TEXT DEFAULT '',
            order_idx       INTEGER DEFAULT 0        -- thứ tự hiển thị (kéo-thả)
        );

        -- ── Lịch tham gia nhóm ───────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS join_schedules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ten_acc     TEXT NOT NULL,
            ten_page    TEXT DEFAULT '',
            page_uid    TEXT DEFAULT '',
            gio_chay    TEXT DEFAULT '',
            trang_thai  TEXT DEFAULT 'Chờ',
            tong_nhom   INTEGER DEFAULT 0,
            da_join     INTEGER DEFAULT 0,
            moi_join    INTEGER DEFAULT 0,
            loi         INTEGER DEFAULT 0,
            ket_qua     TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ── Lịch đăng chéo ───────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS schedules (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            loai            TEXT NOT NULL,          -- homestay / thue / ban / page
            stt             INTEGER DEFAULT 0,
            ma_content      TEXT DEFAULT '',
            ten_acc         TEXT DEFAULT '',
            ten_page        TEXT DEFAULT '',
            gio_dang        TEXT DEFAULT '',
            ma_nhom         TEXT DEFAULT '',
            tu_khoa         TEXT DEFAULT '',
            mode            TEXT DEFAULT 'Hybrid',
            trang_thai      TEXT DEFAULT 'Chờ',     -- Chờ / ✅ HH:MM / ❌... / X
            hoat_dong       TEXT DEFAULT 'dang_bai', -- dang_bai | nuoi_nick | comment (slot bị chuyển thành phiên khác)
            updated_at      TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_schedules_loai_status
            ON schedules(loai, trang_thai);

        -- ── Bài viết để đi comment ───────────────────────────────────────
        -- Acc bị dỡ bài vẫn comment được; comment vào bài cũ làm bài nổi lên
        -- đầu nhóm mà không cần đăng bài mới.
        CREATE TABLE IF NOT EXISTS comment_posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            loai        TEXT NOT NULL,          -- homestay / thue / ban
            url         TEXT NOT NULL,
            ghi_chu     TEXT DEFAULT '',
            lan_cuoi    TEXT DEFAULT '',        -- 'YYYY-mm-dd HH:MM' lần comment gần nhất
            so_lan      INTEGER DEFAULT 0,
            trang_thai  TEXT DEFAULT '',        -- '' chưa chạy | ✅ ... | ❌ ...
            order_idx   INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_comment_posts_loai ON comment_posts(loai);

        -- ── Cài đặt hệ thống ─────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS settings (
            key     TEXT PRIMARY KEY,
            value   TEXT DEFAULT ''
        );
        """)

        # ── Migration: thêm cột order_idx cho pages (DB cũ chưa có) ──
        cols = [r["name"] for r in con.execute("PRAGMA table_info(pages)").fetchall()]
        if "order_idx" not in cols:
            con.execute("ALTER TABLE pages ADD COLUMN order_idx INTEGER DEFAULT 0")
            # Gán thứ tự ban đầu theo id để giữ nguyên thứ tự đang thấy
            for idx, row in enumerate(con.execute("SELECT id FROM pages ORDER BY id").fetchall()):
                con.execute("UPDATE pages SET order_idx=? WHERE id=?", (idx, row["id"]))

        # ── Migration: cột cho tính năng nuôi nick (DB cũ chưa có) ──
        def _add_col(table, col, ddl):
            existing = [r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

        _add_col("accounts",  "nuoi_nick",     "nuoi_nick INTEGER DEFAULT 0")
        _add_col("accounts",  "nuoi_interval", "nuoi_interval INTEGER DEFAULT 150")
        _add_col("schedules", "hoat_dong",     "hoat_dong TEXT DEFAULT 'dang_bai'")

        # ── Migration: bỏ 2 cột cờ comment ──────────────────────────────
        # `comment_bai` + `comment_interval` từng là cách thứ hai để acc vừa
        # đăng vừa comment. Nay việc đó do loại đăng "X_*" đảm nhiệm, để lại
        # thì cùng một acc có hai nguồn sự thật mâu thuẫn nhau.
        _acc_cols = [r["name"] for r in con.execute("PRAGMA table_info(accounts)")]
        for _cot in ("comment_bai", "comment_interval"):
            if _cot in _acc_cols:
                con.execute(f"ALTER TABLE accounts DROP COLUMN {_cot}")

        # Nhóm chứa bài — tách sẵn từ URL để bốc bài theo luật "tối đa 1 link
        # mỗi nhóm mỗi phiên". Tách lúc bốc thì phải parse lại toàn bộ danh sách
        # mỗi lần, mà danh sách tới 300 dòng × 3 loại.
        _add_col("comment_posts", "nhom", "nhom TEXT DEFAULT ''")
        # Page nào đã đăng bài này — để acc "X_" chỉ comment vào bài chính chủ.
        _add_col("comment_posts", "page", "page TEXT DEFAULT ''")
        for r in con.execute("SELECT id, url FROM comment_posts "
                             "WHERE COALESCE(nhom,'') = ''").fetchall():
            con.execute("UPDATE comment_posts SET nhom=? WHERE id=?",
                        (tach_nhom_tu_url(r["url"]), r["id"]))
        # Bỏ cột nhom_url: bước "ghé nhóm chứa bài" đã được thay bằng "ghé Page
        # được phân công" (lấy từ cột ten_page của slot), không cần nhớ nhóm nữa.
        if "nhom_url" in [r["name"] for r in
                          con.execute("PRAGMA table_info(comment_posts)").fetchall()]:
            con.execute("ALTER TABLE comment_posts DROP COLUMN nhom_url")

        # ── Migration: order_idx cho content / uid_groups (kéo-thả đổi thứ tự) ──
        # Không cần backfill như pages ở trên: ADD COLUMN với DEFAULT là hằng số
        # khác NULL thì SQLite ghi luôn 0 cho mọi dòng cũ, nên khoá sắp xếp đầu
        # là hằng số và thứ tự thu về đúng tiêu chí cũ (id).
        _add_col("content",    "order_idx", "order_idx INTEGER DEFAULT 0")
        _add_col("uid_groups", "order_idx", "order_idx INTEGER DEFAULT 0")
        # Cột ghi chú "Acc quản lý" cho pages — chỉ để note, không dùng khi đăng bài.
        _add_col("pages",      "acc_quan_ly", "acc_quan_ly TEXT DEFAULT ''")

        # ── Sức khoẻ acc (xem suc_khoe_acc.py) ──────────────────────────
        # `lich_su_phien` là chuỗi "o"/"x" của tối đa 20 phiên đăng gần nhất —
        # gói cả chuỗi lỗi liên tiếp lẫn tỉ lệ hỏng vào một ô, khỏi phải giữ hai
        # bộ đếm rời rồi lo chúng lệch nhau.
        _add_col("accounts", "lich_su_phien", "lich_su_phien TEXT DEFAULT ''")
        # Mốc hết nghỉ (ISO). Rỗng = không nghỉ.
        _add_col("accounts", "nghi_den",      "nghi_den TEXT DEFAULT ''")
        # Cảnh báo chưa được xem — giao diện đọc rồi xoá. Scheduler chạy ở tiến
        # trình riêng nên không đẩy thẳng toast lên web được, phải qua DB.
        _add_col("accounts", "canh_bao_moi",  "canh_bao_moi TEXT DEFAULT ''")
        # ── Migration: bỏ loại đăng "C_*" (chỉ comment) ─────────────────
        # Việc đó nay do trạng thái `Spam` đảm nhiệm, tự động. Phải ĐỔI dữ liệu
        # chứ không chỉ bỏ khỏi LOAI_DANG_OPTIONS: acc còn mang "C_Home" sẽ
        # không khớp LOAI_LICH_MAP nữa nên rơi khỏi Gen lịch mà không báo gì —
        # đúng kiểu hỏng im lặng khó lần ra nhất.
        for _cu, _moi in (("C_Home", "X_Home"), ("C_Thuê", "X_Thuê"),
                          ("C_Bán", "X_Bán")):
            con.execute("UPDATE accounts SET loai_dang=? WHERE loai_dang=?",
                        (_moi, _cu))

        # Số vụ Facebook gỡ bài đo được lần gần nhất. -1 = CHƯA từng đo.
        # Mặc định phải là -1 chứ không phải 0: để 0 thì ngay phiên đầu sau khi
        # bật tính năng, mọi acc có sẵn vi phạm cũ đều bị đánh spam cùng lúc.
        _add_col("accounts", "so_vi_pham",    "so_vi_pham INTEGER DEFAULT -1")

        # ── Migration: bỏ khái niệm "ảnh hook" ──────────────────────────
        # Trước đây content có 2 ô ảnh: link_anh_hook (1 ảnh, luôn đăng đầu) và
        # link_anh (phần còn lại). Giờ gộp làm một danh sách duy nhất.
        #
        # PHẢI dồn ảnh hook vào ĐẦU link_anh trước khi xoá cột, nếu không 32
        # ảnh hook đang có sẽ mất khỏi content và bị "Dọn ảnh thừa" xoá khỏi đĩa.
        if "link_anh_hook" in [r["name"] for r in
                               con.execute("PRAGMA table_info(content)").fetchall()]:
            for r in con.execute(
                    "SELECT id, link_anh_hook, link_anh FROM content "
                    "WHERE COALESCE(link_anh_hook,'') <> ''").fetchall():
                hook = r["link_anh_hook"].strip()
                con_lai = [u.strip() for u in (r["link_anh"] or "").split(",")
                           if u.strip() and u.strip() != hook]
                con.execute("UPDATE content SET link_anh=? WHERE id=?",
                            (", ".join([hook] + con_lai), r["id"]))
            con.execute("ALTER TABLE content DROP COLUMN link_anh_hook")
            print("  ↪ Đã gộp ảnh hook vào danh sách ảnh, bỏ cột link_anh_hook")
    print(f"✅ DB initialized: {DB_PATH}")


# ═══════════════════════════════════════════════════════════════
# Accounts
# ═══════════════════════════════════════════════════════════════

def get_accounts(loai: str = None, trang_thai: str = None) -> list[dict]:
    with _conn() as con:
        sql  = "SELECT * FROM accounts WHERE 1=1"
        args = []
        if loai:
            sql += " AND loai_dang = ?"; args.append(loai)
        if trang_thai:
            sql += " AND trang_thai = ?"; args.append(trang_thai)
        sql += " ORDER BY order_idx, id"
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def reorder_accounts(ordered_ids: list[int]):
    """Cập nhật thứ tự hiển thị của accounts."""
    with _conn() as con:
        for idx, acc_id in enumerate(ordered_ids):
            con.execute("UPDATE accounts SET order_idx=? WHERE id=?", (idx, acc_id))


def insert_account_at(ref_id: int, position: str = "below") -> int:
    """
    Thêm acc trống trước (above) hoặc sau (below) acc có id=ref_id.
    Trả về id của acc mới.
    """
    with _conn() as con:
        ref = con.execute("SELECT order_idx FROM accounts WHERE id=?", (ref_id,)).fetchone()
        ref_idx = ref["order_idx"] if ref else 999
        if position == "above":
            new_idx = ref_idx
            con.execute("UPDATE accounts SET order_idx=order_idx+1 WHERE order_idx >= ?", (ref_idx,))
        else:
            new_idx = ref_idx + 1
            con.execute("UPDATE accounts SET order_idx=order_idx+1 WHERE order_idx > ?", (ref_idx,))
        cur = con.execute(
            "INSERT INTO accounts (order_idx, trang_thai, thoi_gian_nghi) VALUES (?, 'Active', 30)",
            (new_idx,)
        )
        return cur.lastrowid


def get_account_by_id(acc_id: int) -> dict | None:
    with _conn() as con:
        r = con.execute("SELECT * FROM accounts WHERE id = ?", (acc_id,)).fetchone()
        return dict(r) if r else None


def get_account_by_name(ten_acc: str, ten_page: str = "") -> dict | None:
    """
    Tra acc theo tên. Nhận cả trạng thái 'Spam' chứ không chỉ 'Active'.

    Acc dính spam vẫn phải chạy được phiên comment và phiên nuôi; hàm này là
    nơi các phiên đó lấy cookie. Lọc cứng 'Active' thì acc vừa bị đánh spam sẽ
    không tra ra được và cả hai loại phiên chết theo — trong khi việc chặn đăng
    bài đã do `acc_duoc_chay` lo rồi.
    """
    dung = (TRANG_THAI_SPAM, "Active")
    with _conn() as con:
        if ten_page:
            r = con.execute(
                "SELECT * FROM accounts WHERE ten_acc = ? AND ten_page = ? "
                "AND trang_thai IN (?,?) ORDER BY trang_thai='Active' DESC LIMIT 1",
                (ten_acc, ten_page, *dung)
            ).fetchone()
            if r:
                return dict(r)
        r = con.execute(
            "SELECT * FROM accounts WHERE ten_acc = ? AND trang_thai IN (?,?) "
            "ORDER BY trang_thai='Active' DESC LIMIT 1",
            (ten_acc, *dung)
        ).fetchone()
        return dict(r) if r else None


def get_account_by_cuser(c_user: str) -> dict | None:
    with _conn() as con:
        r = con.execute(
            "SELECT * FROM accounts WHERE c_user = ? LIMIT 1",
            (c_user,)
        ).fetchone()
        return dict(r) if r else None


def upsert_account(data: dict) -> int:
    cols   = [k for k in data if k != "id"]
    placeholders = ", ".join(["?"] * len(cols))
    values = [data[c] for c in cols]
    with _conn() as con:
        if "id" in data and data["id"]:
            sets = ", ".join(f"{c}=?" for c in cols)
            con.execute(f"UPDATE accounts SET {sets} WHERE id=?", values + [data["id"]])
            return data["id"]
        else:
            cur = con.execute(
                f"INSERT INTO accounts ({', '.join(cols)}) VALUES ({placeholders})",
                values
            )
            return cur.lastrowid


def delete_account(acc_id: int):
    with _conn() as con:
        con.execute("DELETE FROM accounts WHERE id=?", (acc_id,))


def update_account_field(acc_id: int, field: str, value: str):
    safe = {
        "ten_acc","loai_dang","thoi_gian_nghi","link_profile","email_sdt",
        "password","ten_page","c_user","xs","refresh","trang_thai",
        "email_khoiphuc","pass_khoiphuc","twofa","ghi_chu",
        "nuoi_nick","nuoi_interval"
    }
    if field not in safe:
        raise ValueError(f"Field không hợp lệ: {field}")
    # Loại đăng là tập giá trị đóng. Giá trị lạ ("C_home", "Homestay " thừa
    # khoảng trắng) sẽ khiến Gen lịch âm thầm bỏ sót acc đó — hỏng kiểu im lặng,
    # khó lần ra nhất. Chặn ngay tại cửa ghi.
    if field == "loai_dang":
        value = (value or "").strip()
        if value not in LOAI_DANG_OPTIONS:
            raise ValueError(f"Loại đăng không hợp lệ: '{value}' "
                             f"(chỉ nhận: {', '.join(x or '(trống)' for x in LOAI_DANG_OPTIONS)})")
    with _conn() as con:
        con.execute(f"UPDATE accounts SET {field}=? WHERE id=?", (value, acc_id))
        # Người dùng bật acc về Active = "tôi đã xử lý xong". Phải xoá cả lịch sử
        # phiên, không thì cửa sổ trượt vẫn còn đầy "x" cũ và acc bị tắt lại ngay
        # sau phiên hỏng kế tiếp, trông như nút bật không ăn.
        if field == "trang_thai" and value == "Active":
            con.execute("UPDATE accounts SET lich_su_phien='', nghi_den='', "
                        "canh_bao_moi='' WHERE id=?", (acc_id,))


# ── Sức khoẻ acc ────────────────────────────────────────────────────────
def _moc_nghi(nghi_den: str):
    """Mốc hết nghỉ nếu CÒN đang nghỉ, `None` nếu đã hết hoặc không hợp lệ."""
    if not nghi_den:
        return None
    try:
        moc = datetime.fromisoformat(nghi_den)
    except ValueError:
        return None
    return moc if datetime.now() < moc else None


def acc_duoc_chay(ten_acc: str, hoat_dong: str = "dang_bai") -> tuple[bool, str]:
    """
    Acc có được giao phiên này lúc này không.

    Nghỉ tạm vì LỖI LIÊN TIẾP chỉ chặn ĐĂNG và COMMENT — hai việc vừa bị
    Facebook từ chối. Nuôi nick vẫn chạy, vì xem story / lướt feed chính là thứ
    có cơ gỡ acc ra, cắt nốt là tự bịt đường hồi phục.

    Nghỉ vì DÍNH SPAM chặn ĐĂNG và COMMENT — hai việc vừa khiến Facebook gỡ
    bài. Nuôi nick VẪN chạy: xem story / lướt feed là hành vi người thật, không
    phải thứ bị phạt, và giữ nick sống thay vì im lìm trọn 3 tiếng.

    Tắt hẳn cũng chặn tất: acc đó đang chờ người xử lý, mà `trang_thai` lúc này
    là 'Hỏng' nên `get_account_by_name` cũng không tìm ra nó nữa — cho phiên nuôi
    chạy tiếp chỉ tổ đổ một đống lỗi vô nghĩa vào log.
    """
    with _conn() as con:
        r = con.execute("SELECT trang_thai, nghi_den FROM accounts "
                        "WHERE ten_acc=? LIMIT 1", (ten_acc,)).fetchone()
    if not r:
        return True, ""
    tt = r["trang_thai"] or ""
    if tt == TRANG_THAI_HONG:
        return False, "acc đã bị tắt do hỏng"
    if tt == TRANG_THAI_SPAM:
        den = _moc_nghi(r["nghi_den"])
        # Nuôi nick vẫn chạy suốt thời gian nghỉ: xem story / lướt feed là hành
        # vi người thật, nó không phải thứ khiến Facebook gỡ bài, và giữ nick
        # sống thay vì im lìm cả 3 tiếng.
        if den and hoat_dong != "nuoi_nick":
            return False, f"nghỉ vì dính spam, tới {den:%H:%M}"
        # Hết giờ nghỉ mà chưa được hồi sinh (scheduler chưa kịp quét) — cho
        # chạy luôn chứ đừng bắt đợi thêm một vòng lặp.
        return True, ""
    if hoat_dong == "nuoi_nick":
        return True, ""
    moc = _moc_nghi(r["nghi_den"])
    if moc:
        return False, f"đang nghỉ tới {moc:%H:%M}"
    return True, ""


def ghi_nhan_phien_dang(ten_acc: str, ok: bool) -> tuple[str, str]:
    """
    Ghi kết quả một phiên đăng bài và áp quyết định của `suc_khoe_acc.danh_gia`.

    Trả `(hanh_dong, ly_do)` để nơi gọi ghi log; hanh_dong ∈ {"", "nghi", "tat"}.
    """
    import suc_khoe_acc as sk
    with _conn() as con:
        r = con.execute("SELECT id, lich_su_phien FROM accounts "
                        "WHERE ten_acc=? LIMIT 1", (ten_acc,)).fetchone()
        if not r:
            return "", ""
        moi = sk.them_ket_qua(r["lich_su_phien"] or "", ok)
        con.execute("UPDATE accounts SET lich_su_phien=? WHERE id=?", (moi, r["id"]))

        hanh_dong, ly_do = sk.danh_gia(moi)
        if hanh_dong == "tat":
            con.execute(
                "UPDATE accounts SET trang_thai=?, nghi_den='', canh_bao_moi=? "
                "WHERE id=?",
                (TRANG_THAI_HONG, f"Đã tắt '{ten_acc}' — {ly_do}", r["id"]))
        elif hanh_dong == "nghi":
            moc = datetime.now() + timedelta(hours=sk.NGHI_GIO)
            # Ghi dấu ngắt chứ không xoá lịch sử: acc được lại đủ CHUOI_NGHI lượt
            # thử sau khi nghỉ dậy, mà cửa sổ trượt vẫn giữ các "x" cũ để tầng 2
            # còn tích đủ mà kết luận acc chết.
            con.execute(
                "UPDATE accounts SET nghi_den=?, lich_su_phien=?, canh_bao_moi=? "
                "WHERE id=?",
                (moc.isoformat(timespec="seconds"), sk.danh_dau_nghi(moi),
                 f"'{ten_acc}' nghỉ tới {moc:%H:%M} — {ly_do}", r["id"]))
        if hanh_dong in ("nghi", "tat"):
            # Đánh 'X😴' các slot còn lại hôm nay để nhìn bảng lịch là biết ngay
            # acc này nghỉ — không phải đợi từng slot tới giờ mới đổi thành 😴.
            # Dùng chung `con` đang mở (đừng gọi hàm mở _conn() lần nữa = khoá lồng).
            con.execute(
                "UPDATE schedules SET trang_thai=?, updated_at=datetime('now','localtime') "
                "WHERE ten_acc=? AND trang_thai='Chờ' AND gio_dang > ?",
                (TT_LICH_X_TU_DONG, ten_acc, datetime.now().strftime("%H:%M")))
        return hanh_dong, ly_do


def ghi_nhan_vi_pham(ten_acc: str, so_moi: int, la_spam: bool) -> tuple[bool, int]:
    """
    Ghi số vụ Facebook gỡ bài đo được sau một phiên đăng.

    Chỉ khi số vụ TĂNG so với lần đo trước mới coi là vừa dính — xem
    `suc_khoe_acc.co_vu_moi`. Lần đo đầu tiên chỉ ghi mốc.

    Trả `(vua_dinh, so_cu)`.
    """
    import suc_khoe_acc as sk
    with _conn() as con:
        r = con.execute("SELECT id, so_vi_pham, trang_thai FROM accounts "
                        "WHERE ten_acc=? LIMIT 1", (ten_acc,)).fetchone()
        if not r:
            return False, -1
        so_cu = r["so_vi_pham"] if r["so_vi_pham"] is not None else -1
        con.execute("UPDATE accounts SET so_vi_pham=? WHERE id=?", (so_moi, r["id"]))
        vua_dinh = la_spam and sk.co_vu_moi(so_cu, so_moi)
    return vua_dinh, so_cu


def danh_dau_spam(ten_acc: str, chi_tiet: str = "", gio: str = None) -> tuple[int, object]:
    """
    Cho acc nghỉ ĐĂNG và COMMENT vì Facebook vừa gỡ bài. Nuôi nick vẫn chạy.

    Facebook gỡ bài nghĩa là nó đang soi nick ngay lúc đó, nên dừng hai việc vừa
    bị phạt trong `SK.NGHI_SPAM_GIO` tiếng. Nuôi thì giữ: xem story / lướt feed
    là hành vi người thật, không phải thứ bị gỡ bài. Hết giờ thì
    `hoi_sinh_het_nghi_spam` tự bật lại và trả lịch về 'Chờ'.

    Đánh 'Nghỉ Spam' cho MỌI slot đăng và comment còn lại hôm nay, chỉ chừa slot
    đã qua giờ. Slot nuôi không đụng tới.

    `gio` (HH:MM) chỉ để test đặt mốc cố định — bỏ trống thì lấy giờ hiện tại.

    Trả `(số slot đã dừng, mốc hết nghỉ)`.
    """
    import suc_khoe_acc as sk
    gio = gio or datetime.now().strftime("%H:%M")
    moc = datetime.now() + timedelta(hours=sk.NGHI_SPAM_GIO)
    with _conn() as con:
        r = con.execute("SELECT id FROM accounts WHERE ten_acc=? LIMIT 1",
                        (ten_acc,)).fetchone()
        if not r:
            return 0, None
        con.execute(
            "UPDATE accounts SET trang_thai=?, nghi_den=?, canh_bao_moi=? WHERE id=?",
            (TRANG_THAI_SPAM, moc.isoformat(timespec="seconds"),
             f"'{ten_acc}' bị Facebook gỡ bài (spam) — nghỉ hẳn tới {moc:%H:%M}"
             + (f": {chi_tiet}" if chi_tiet else ""),
             r["id"]))
        n = con.execute(
            "UPDATE schedules SET trang_thai=?, "
            "updated_at=datetime('now','localtime') "
            "WHERE ten_acc=? AND trang_thai='Chờ' AND gio_dang > ? "
            "AND COALESCE(hoat_dong,'dang_bai') IN ('dang_bai','comment')",
            (TT_LICH_NGHI_SPAM, ten_acc, gio)).rowcount
    return n, moc


def hoi_sinh_het_nghi_spam() -> list[dict]:
    """
    Bật lại các acc đã nghỉ đủ giờ vì dính spam, và trả lịch của chúng về 'Chờ'.

    Trả lại slot ĐÃ QUA GIỜ về 'Chờ' là an toàn, không gây dồn bài: scheduler chỉ
    chạy dòng nằm trong cửa sổ `WINDOW_MINUTES` (3 phút) sau giờ hẹn, nên slot lỡ
    trong lúc nghỉ đơn giản không bao giờ tới lượt — nó chỉ nằm đó tới lần reset
    đầu ngày.

    Trả danh sách `[{"ten_acc":…, "so_slot":…}]` để nơi gọi ghi log.
    """
    ra = []
    with _conn() as con:
        rows = con.execute(
            "SELECT id, ten_acc, nghi_den FROM accounts WHERE trang_thai=?",
            (TRANG_THAI_SPAM,)).fetchall()
        for r in rows:
            if _moc_nghi(r["nghi_den"]):
                continue                      # vẫn còn đang nghỉ
            con.execute("UPDATE accounts SET trang_thai='Active', nghi_den='', "
                        "lich_su_phien='', canh_bao_moi=? WHERE id=?",
                        (f"'{r['ten_acc']}' đã nghỉ đủ giờ — chạy lại bình thường",
                         r["id"]))
            n = con.execute(
                "UPDATE schedules SET trang_thai='Chờ', "
                "updated_at=datetime('now','localtime') "
                "WHERE ten_acc=? AND trang_thai=?",
                (r["ten_acc"], TT_LICH_NGHI_SPAM)).rowcount
            ra.append({"ten_acc": r["ten_acc"], "so_slot": n})
    return ra


def lay_canh_bao() -> list[dict]:
    """Cảnh báo chưa xem, kèm mức để giao diện chọn màu."""
    with _conn() as con:
        rows = con.execute(
            "SELECT ten_acc, trang_thai, canh_bao_moi FROM accounts "
            "WHERE COALESCE(canh_bao_moi,'') != ''").fetchall()
    nang = (TRANG_THAI_HONG, TRANG_THAI_SPAM)
    return [{"ten_acc": r["ten_acc"], "noi_dung": r["canh_bao_moi"],
             "muc": "error" if (r["trang_thai"] or "") in nang else "info"}
            for r in rows]


def xoa_canh_bao():
    """Giao diện gọi sau khi đã hiện toast."""
    with _conn() as con:
        con.execute("UPDATE accounts SET canh_bao_moi='' "
                    "WHERE COALESCE(canh_bao_moi,'') != ''")


# Cột số của accounts — ép về int khi nhập từ Excel (Excel hay để dạng float).
_ACC_INT_COLS = {"thoi_gian_nghi", "nuoi_interval", "nuoi_nick"}


def import_accounts(records: list[dict]) -> tuple[int, int]:
    """Nhập hàng loạt tài khoản từ file Excel.

    Chế độ "thêm & bỏ trùng": chỉ thêm acc chưa tồn tại. Trùng khi cùng
    (ten_acc, ten_page). Trả (số đã thêm, số bỏ qua vì trùng).
    Chỉ nhận các cột thuộc bảng accounts; cột lạ bị bỏ qua.
    """
    allowed = {
        "ten_acc", "loai_dang", "thoi_gian_nghi", "link_profile", "email_sdt",
        "password", "ten_page", "c_user", "xs", "refresh", "trang_thai",
        "email_khoiphuc", "pass_khoiphuc", "twofa", "ghi_chu",
        "nuoi_nick", "nuoi_interval",
    }
    added = skipped = 0
    with _conn() as con:
        seen = {
            (r["ten_acc"] or "", r["ten_page"] or "")
            for r in con.execute("SELECT ten_acc, ten_page FROM accounts").fetchall()
        }
        nxt = con.execute(
            "SELECT COALESCE(MAX(order_idx), -1) + 1 FROM accounts"
        ).fetchone()[0]

        for rec in records:
            ten = (rec.get("ten_acc") or "").strip()
            if not ten:
                skipped += 1
                continue
            page = (rec.get("ten_page") or "").strip()
            if (ten, page) in seen:
                skipped += 1
                continue
            seen.add((ten, page))

            data = {}
            for k, v in rec.items():
                if k not in allowed:
                    continue
                v = "" if v is None else str(v).strip()
                if k in _ACC_INT_COLS:
                    try:
                        v = int(float(v)) if v != "" else 0
                    except (ValueError, TypeError):
                        v = 0
                data[k] = v
            data["ten_acc"] = ten
            data["order_idx"] = nxt

            cols = list(data.keys())
            con.execute(
                f"INSERT INTO accounts ({', '.join(cols)}) "
                f"VALUES ({', '.join(['?'] * len(cols))})",
                [data[c] for c in cols],
            )
            nxt += 1
            added += 1
    return added, skipped


# ═══════════════════════════════════════════════════════════════
# Pages
# ═══════════════════════════════════════════════════════════════

def get_pages() -> list[dict]:
    with _conn() as con:
        return [dict(r) for r in con.execute("SELECT * FROM pages ORDER BY order_idx, id").fetchall()]


def reorder_pages(ordered_ids: list[int]):
    """Cập nhật thứ tự hiển thị của pages (kéo-thả)."""
    with _conn() as con:
        for idx, page_id in enumerate(ordered_ids):
            con.execute("UPDATE pages SET order_idx=? WHERE id=?", (idx, page_id))


def get_page_by_name(ten_page: str) -> dict | None:
    with _conn() as con:
        r = con.execute(
            "SELECT * FROM pages WHERE ten_page = ? LIMIT 1", (ten_page,)
        ).fetchone()
        return dict(r) if r else None


def upsert_page(data: dict) -> int:
    cols   = [k for k in data if k != "id"]
    values = [data[c] for c in cols]
    with _conn() as con:
        if "id" in data and data["id"]:
            sets = ", ".join(f"{c}=?" for c in cols)
            con.execute(f"UPDATE pages SET {sets} WHERE id=?", values + [data["id"]])
            return data["id"]
        cur = con.execute(
            f"INSERT INTO pages ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})",
            values
        )
        return cur.lastrowid


def delete_page(page_id: int):
    with _conn() as con:
        con.execute("DELETE FROM pages WHERE id=?", (page_id,))


def import_pages(records: list[dict]) -> tuple[int, int]:
    """Nhập hàng loạt Page từ file Excel.

    Chế độ "thêm & bỏ trùng": chỉ thêm Page chưa tồn tại. Trùng so theo page_uid;
    Page nào (cả cũ lẫn trong file) không có uid thì so theo ten_page.
    Trả (số đã thêm, số bỏ qua vì trùng).
    """
    cols = ("ten_page", "acc_quan_ly", "page_uid", "loai_page",
            "bai_dang_toi_da", "link_page", "ghi_chu")
    added = skipped = 0
    with _conn() as con:
        seen_uid = set()   # page_uid đã có (khác rỗng)
        seen_ten = set()   # ten_page của các Page KHÔNG có uid
        nxt = 0
        for r in con.execute(
            "SELECT ten_page, page_uid, order_idx FROM pages"
        ).fetchall():
            uid = (r["page_uid"] or "").strip()
            if uid:
                seen_uid.add(uid)
            else:
                seen_ten.add((r["ten_page"] or "").strip())
            nxt = max(nxt, (r["order_idx"] or 0) + 1)

        for rec in records:
            ten = (rec.get("ten_page") or "").strip()
            if not ten:
                skipped += 1
                continue
            uid = (rec.get("page_uid") or "").strip()
            # Trùng theo uid nếu có uid, ngược lại theo tên page.
            if uid:
                if uid in seen_uid:
                    skipped += 1
                    continue
                seen_uid.add(uid)
            else:
                if ten in seen_ten:
                    skipped += 1
                    continue
                seen_ten.add(ten)

            # bai_dang_toi_da là cột số — ép về int, rác thì 0.
            try:
                bai = int(float(rec.get("bai_dang_toi_da") or 0))
            except (ValueError, TypeError):
                bai = 0
            values = [
                ten, rec.get("acc_quan_ly", "") or "", uid,
                rec.get("loai_page", "") or "", bai,
                rec.get("link_page", "") or "", rec.get("ghi_chu", "") or "",
            ]
            con.execute(
                f"INSERT INTO pages ({', '.join(cols)}, order_idx) "
                f"VALUES ({', '.join(['?'] * len(cols))}, ?)",
                values + [nxt],
            )
            nxt += 1
            added += 1
    return added, skipped


# ═══════════════════════════════════════════════════════════════
# Content
# ═══════════════════════════════════════════════════════════════

def get_content(loai: str, su_dung: str = None) -> list[dict]:
    with _conn() as con:
        sql  = "SELECT * FROM content WHERE loai=?"
        args = [loai]
        if su_dung:
            sql += " AND su_dung=?"; args.append(su_dung)
        sql += " ORDER BY order_idx, id"
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def reorder_content(ordered_ids: list[int]):
    """Cập nhật thứ tự hiển thị của content (kéo-thả).

    order_idx chỉ có nghĩa TRONG CÙNG một `loai` vì get_content() lọc loai
    trước khi sắp xếp → index trùng nhau giữa các loai là vô hại.
    Tab Content hiển thị MỌI dòng của loai (không lọc su_dung) nên payload
    luôn đầy đủ; nếu sau này thêm filter vào tab thì phải xem lại chỗ này.
    """
    with _conn() as con:
        for idx, cid in enumerate(ordered_ids):
            con.execute("UPDATE content SET order_idx=? WHERE id=?", (idx, cid))


def get_content_by_code(ma_content: str) -> dict | None:
    with _conn() as con:
        r = con.execute(
            "SELECT * FROM content WHERE ma_content=? LIMIT 1", (ma_content,)
        ).fetchone()
        return dict(r) if r else None


def upsert_content(data: dict) -> int:
    cols   = [k for k in data if k != "id"]
    values = [data[c] for c in cols]
    with _conn() as con:
        if "id" in data and data["id"]:
            sets = ", ".join(f"{c}=?" for c in cols)
            con.execute(f"UPDATE content SET {sets} WHERE id=?", values + [data["id"]])
            return data["id"]
        # Dòng mới phải xuống CUỐI danh sách của loai đó. Form lưu content không
        # gửi order_idx, để mặc định 0 thì nó nhảy lên ĐẦU bảng và làm lệch thứ
        # tự luân phiên content khi Gen lịch.
        if "order_idx" not in cols:
            nxt = con.execute(
                "SELECT COALESCE(MAX(order_idx), -1) + 1 FROM content WHERE loai=?",
                (data.get("loai", ""),)
            ).fetchone()[0]
            cols.append("order_idx"); values.append(nxt)
        cur = con.execute(
            f"INSERT INTO content ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})",
            values
        )
        return cur.lastrowid


def delete_content(content_id: int):
    with _conn() as con:
        con.execute("DELETE FROM content WHERE id=?", (content_id,))


def _tach_urls(*chuoi) -> set:
    """'a.jpg, b.jpg' → {'a.jpg', 'b.jpg'} (bỏ khoảng trắng, bỏ rỗng)."""
    ra = set()
    for s in chuoi:
        for u in (s or "").split(","):
            u = u.strip()
            if u:
                ra.add(u)
    return ra


def get_content_image_urls(content_id: int) -> set:
    """Ảnh mà MỘT dòng content đang trỏ tới."""
    with _conn() as con:
        r = con.execute(
            "SELECT link_anh FROM content WHERE id=?", (content_id,)
        ).fetchone()
    return _tach_urls(r["link_anh"]) if r else set()


def get_all_content_image_urls() -> set:
    """Mọi ảnh còn được BẤT KỲ content nào trỏ tới — dùng để biết ảnh nào mồ côi."""
    with _conn() as con:
        rows = con.execute("SELECT link_anh FROM content").fetchall()
    ra = set()
    for r in rows:
        ra |= _tach_urls(r["link_anh"])
    return ra


def import_content(records: list[dict], loai: str) -> tuple[int, int]:
    """Nhập content vào MỘT loại (homestay/thue/ban).

    Chế độ "thêm & bỏ trùng": ma_content nào đã có trong loại đó thì bỏ qua,
    chỉ thêm cái mới. `link_anh` trong records đã là URL /media/... hợp lệ
    (server đã chép ảnh vào đĩa trước khi gọi hàm này). Dòng mới xuống cuối
    danh sách của loại (order_idx tăng dần) như upsert_content lúc thêm tay.
    """
    added = skipped = 0
    with _conn() as con:
        seen = {(r["ma_content"] or "").strip()
                for r in con.execute("SELECT ma_content FROM content WHERE loai=?",
                                     (loai,)).fetchall()}
        nxt = con.execute(
            "SELECT COALESCE(MAX(order_idx), -1) + 1 FROM content WHERE loai=?",
            (loai,)
        ).fetchone()[0]
        for rec in records:
            ma = (rec.get("ma_content") or "").strip()
            if not ma:
                skipped += 1
                continue
            if ma in seen:
                skipped += 1
                continue
            seen.add(ma)
            con.execute(
                "INSERT INTO content (loai, ma_content, noi_dung, link_anh, "
                "su_dung, ghi_chu, order_idx) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (loai, ma, rec.get("noi_dung", "") or "",
                 rec.get("link_anh", "") or "",
                 rec.get("su_dung", "Có") or "Có",
                 rec.get("ghi_chu", "") or "", nxt)
            )
            nxt += 1
            added += 1
    return added, skipped


# ═══════════════════════════════════════════════════════════════
# UID Groups
# ═══════════════════════════════════════════════════════════════

def get_uid_groups_by_code(ma_nhom: str) -> list[dict]:
    with _conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM uid_groups WHERE ma_nhom=? ORDER BY id", (ma_nhom,)
        ).fetchall()]


def get_all_uid_groups() -> list[dict]:
    with _conn() as con:
        # ma_nhom đứng TRƯỚC order_idx để nhóm TIME1-7 vẫn gom đúng như cũ.
        return [dict(r) for r in con.execute(
            "SELECT * FROM uid_groups ORDER BY ma_nhom, order_idx, id"
        ).fetchall()]


def reorder_uid_groups(ordered_ids: list[int]):
    """Cập nhật thứ tự hiển thị của UID nhóm (kéo-thả).

    Tab UID chỉ hiện các dòng ma_nhom='' (loadUidGroups lọc ở client) nên
    payload chỉ gồm id của nhóm trống; các dòng TIME1-7 giữ order_idx=0 và
    thứ tự của chúng không bị ảnh hưởng.
    """
    with _conn() as con:
        for idx, gid in enumerate(ordered_ids):
            con.execute("UPDATE uid_groups SET order_idx=? WHERE id=?", (idx, gid))


def upsert_uid_group(data: dict) -> int:
    cols   = [k for k in data if k != "id"]
    values = [data[c] for c in cols]
    with _conn() as con:
        if "id" in data and data["id"]:
            sets = ", ".join(f"{c}=?" for c in cols)
            con.execute(f"UPDATE uid_groups SET {sets} WHERE id=?", values + [data["id"]])
            return data["id"]
        # Dòng mới xuống CUỐI nhóm của nó — xem chú thích ở upsert_content.
        if "order_idx" not in cols:
            nxt = con.execute(
                "SELECT COALESCE(MAX(order_idx), -1) + 1 FROM uid_groups WHERE ma_nhom=?",
                (data.get("ma_nhom", ""),)
            ).fetchone()[0]
            cols.append("order_idx"); values.append(nxt)
        cur = con.execute(
            f"INSERT INTO uid_groups ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})",
            values
        )
        return cur.lastrowid


def delete_uid_group(gid: int):
    with _conn() as con:
        con.execute("DELETE FROM uid_groups WHERE id=?", (gid,))


def import_uid_groups(records: list[dict]) -> tuple[int, int]:
    """Nhập hàng loạt UID nhóm (sheet 'UID Nhóm', ma_nhom='') từ file Excel.

    Chế độ "thêm & bỏ trùng": chỉ thêm UID chưa tồn tại trong sheet UID Nhóm.
    Trùng so theo cột uid. Trả (số đã thêm, số bỏ qua vì trùng).
    """
    cols = ("uid", "ten_nhom", "link_url", "thanh_vien", "ghi_chu")
    added = skipped = 0
    with _conn() as con:
        existing = {
            r[0] for r in con.execute(
                "SELECT uid FROM uid_groups WHERE ma_nhom=''"
            ).fetchall()
        }
        # Dòng mới xuống cuối sheet — nối tiếp order_idx đang có.
        nxt = con.execute(
            "SELECT COALESCE(MAX(order_idx), -1) + 1 FROM uid_groups WHERE ma_nhom=''"
        ).fetchone()[0]
        for rec in records:
            uid = (rec.get("uid") or "").strip()
            if not uid or uid in existing:
                skipped += 1
                continue
            existing.add(uid)
            values = [rec.get(c, "") or "" for c in cols]
            con.execute(
                f"INSERT INTO uid_groups (ma_nhom, {', '.join(cols)}, order_idx) "
                f"VALUES ('', {', '.join(['?'] * len(cols))}, ?)",
                values + [nxt],
            )
            nxt += 1
            added += 1
    return added, skipped


# ═══════════════════════════════════════════════════════════════
# Schedules
# ═══════════════════════════════════════════════════════════════

def get_schedules(loai: str, trang_thai: str = None) -> list[dict]:
    with _conn() as con:
        sql  = "SELECT * FROM schedules WHERE loai=?"
        args = [loai]
        if trang_thai:
            sql += " AND trang_thai=?"; args.append(trang_thai)
        sql += " ORDER BY stt"   # sort theo thứ tự gen, không sort theo giờ
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def update_schedule_status(schedule_id: int, status: str):
    with _conn() as con:
        con.execute(
            "UPDATE schedules SET trang_thai=?, updated_at=datetime('now','localtime') WHERE id=?",
            (status, schedule_id)
        )


def reset_schedules_to_wait(loai: str, keep: tuple = ("X",)) -> int:
    """
    Đưa MỌI dòng lịch của `loai` về 'Chờ' (reset đầu ngày).
    Bỏ qua các dòng đang có trạng thái trong `keep` (mặc định giữ 'X' — tắt thủ công)
    và các dòng vốn đã 'Chờ'.
    """
    with _conn() as con:
        sql  = ("UPDATE schedules SET trang_thai='Chờ', "
                "updated_at=datetime('now','localtime') "
                "WHERE loai=? AND trang_thai <> 'Chờ'")
        args = [loai]
        if keep:
            sql += " AND trang_thai NOT IN (%s)" % ",".join("?" * len(keep))
            args += list(keep)
        return con.execute(sql, args).rowcount


def danh_dau_x_con_lai_hom_nay(ten_acc: str, loai: str = None) -> int:
    """Đánh 'X😴' cho các slot ĐANG 'Chờ' của acc mà giờ đăng còn ở tương lai
    trong hôm nay (gio_dang > giờ hiện tại). Chỉ đụng slot 'Chờ' — không ghi đè
    ✅/❌/X thủ công đã có. `loai=None` = đánh toàn bộ lịch của acc (acc dùng
    chung 1 cookie, nghỉ là nghỉ hết mọi loại).

    So gio_dang (HH:MM) theo chuỗi: cùng định dạng zero-padded nên so chuỗi =
    so giờ. Slot đã qua giờ mà còn 'Chờ' là slot lỡ — bỏ qua, để reset ngày mai lo.
    """
    gio = datetime.now().strftime("%H:%M")
    sql = ("UPDATE schedules SET trang_thai=?, updated_at=datetime('now','localtime') "
           "WHERE ten_acc=? AND trang_thai='Chờ' AND gio_dang > ?")
    args = [TT_LICH_X_TU_DONG, ten_acc, gio]
    if loai:
        sql += " AND loai=?"; args.append(loai)
    with _conn() as con:
        return con.execute(sql, args).rowcount


def bulk_set_schedule_status(loai: str, old_status_prefix: str, new_status: str) -> int:
    """Batch update trạng thái — không gây 429 vì là SQLite local."""
    with _conn() as con:
        cur = con.execute(
            "UPDATE schedules SET trang_thai=?, updated_at=datetime('now','localtime') "
            "WHERE loai=? AND trang_thai LIKE ?",
            (new_status, loai, old_status_prefix + "%")
        )
        return cur.rowcount


def replace_schedules(loai: str, rows: list[dict]):
    """Xóa lịch cũ và ghi lịch mới — dùng khi gen lịch."""
    with _conn() as con:
        con.execute("DELETE FROM schedules WHERE loai=?", (loai,))
        if rows:
            # Mặc định hoat_dong='dang_bai' nếu row không khai báo (lịch cũ / không nuôi).
            for r in rows:
                r.setdefault("hoat_dong", "dang_bai")
            con.executemany(
                """INSERT INTO schedules
                   (loai, stt, ma_content, ten_acc, ten_page, gio_dang,
                    ma_nhom, tu_khoa, mode, trang_thai, hoat_dong)
                   VALUES (:loai,:stt,:ma_content,:ten_acc,:ten_page,:gio_dang,
                           :ma_nhom,:tu_khoa,:mode,:trang_thai,:hoat_dong)""",
                rows
            )


def update_schedule_field(schedule_id: int, field: str, value: str):
    safe = {"ma_content","ten_acc","ten_page","gio_dang","ma_nhom","tu_khoa","mode","trang_thai"}
    if field not in safe:
        raise ValueError(f"Field không hợp lệ: {field}")
    with _conn() as con:
        con.execute(
            f"UPDATE schedules SET {field}=?, updated_at=datetime('now','localtime') WHERE id=?",
            (value, schedule_id)
        )


def reset_daily_schedules():
    """Reset ✅ → Chờ lúc 00:01 mỗi ngày."""
    with _conn() as con:
        con.execute(
            "UPDATE schedules SET trang_thai='Chờ' WHERE trang_thai LIKE '✅%'"
        )


# ═══════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# Bài viết để đi comment
# ═══════════════════════════════════════════════════════════════

# Mỗi hạng mục giữ bao nhiêu link. Cửa sổ trượt: link mới đẩy link cũ ra và
# link bị đẩy ra bị XOÁ HẲN, không lưu trữ lại.
#
# 300 là con số người dùng chốt sau khi cân nhắc độ sâu: với ~1.000–2.400 link
# sinh ra mỗi ngày, 300 link tương đương 3–7 giờ đăng bài gần nhất.
GIOI_HAN_LINK = 300

_RE_NHOM_URL = re.compile(r"/groups/([0-9A-Za-z._-]+)/")


def tach_nhom_tu_url(url: str) -> str:
    """Định danh nhóm trong URL bài viết. Có thể là số hoặc slug chữ."""
    m = _RE_NHOM_URL.search(url or "")
    return m.group(1) if m else ""


def get_comment_posts(loai: str = None) -> list[dict]:
    with _conn() as con:
        sql, args = "SELECT * FROM comment_posts", []
        if loai:
            sql += " WHERE loai=?"; args.append(loai)
        sql += " ORDER BY order_idx, id"
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def them_comment_posts(loai: str, urls: list[str], gioi_han: int = None,
                       page: str = "") -> int:
    """
    Thêm URL vào cuối danh sách, BỎ QUA url đã có, rồi cắt bớt link cũ nhất cho
    danh sách không vượt `gioi_han`.

    Bỏ trùng là bắt buộc: dán lại cả danh sách là thao tác thường ngày, mà mỗi
    dòng trùng sẽ thành một lượt comment thừa vào đúng một bài.

    `order_idx` tăng dần theo thứ tự thêm vào, và đó chính là "tuổi" của link —
    nhỏ hơn = vào trước = cũ hơn. Cắt bớt thì cắt từ nhỏ nhất.
    """
    gioi_han = GIOI_HAN_LINK if gioi_han is None else gioi_han
    with _conn() as con:
        da_co = {r["url"] for r in
                 con.execute("SELECT url FROM comment_posts WHERE loai=?", (loai,))}
        idx = (con.execute("SELECT COALESCE(MAX(order_idx),-1) m FROM comment_posts "
                           "WHERE loai=?", (loai,)).fetchone()["m"]) + 1
        them = 0
        for u in urls:
            u = (u or "").strip()
            if not u or u in da_co:
                continue
            con.execute("INSERT INTO comment_posts(loai,url,nhom,page,order_idx) "
                        "VALUES(?,?,?,?,?)",
                        (loai, u, tach_nhom_tu_url(u), page, idx))
            da_co.add(u)
            idx  += 1
            them += 1

        # Cửa sổ trượt: link cũ bị đẩy ra thì XOÁ HẲN, không lưu trữ lại.
        if gioi_han and gioi_han > 0:
            con.execute(
                "DELETE FROM comment_posts WHERE loai=? AND id NOT IN ("
                "  SELECT id FROM comment_posts WHERE loai=? "
                "  ORDER BY order_idx DESC LIMIT ?)",
                (loai, loai, gioi_han))
        return them


def update_comment_post_field(post_id: int, field: str, value):
    if field not in {"url", "ghi_chu", "trang_thai"}:
        raise ValueError(f"Không cho sửa cột '{field}'")
    with _conn() as con:
        con.execute(f"UPDATE comment_posts SET {field}=? WHERE id=?", (value, post_id))


def delete_comment_post(post_id: int):
    with _conn() as con:
        con.execute("DELETE FROM comment_posts WHERE id=?", (post_id,))


def xoa_het_comment_posts(loai: str) -> int:
    with _conn() as con:
        return con.execute("DELETE FROM comment_posts WHERE loai=?", (loai,)).rowcount


def boc_bai_de_comment(loai: str, so_bai: int, page: str = "") -> list[dict]:
    """
    Bốc tối đa `so_bai` bài để comment trong một phiên, theo hai luật:

    1. **Tối đa 1 link mỗi NHÓM.** Một đợt đăng chéo tạo 9 bài cùng nội dung ở
       9 nhóm khác nhau, nên cả danh sách 300 link chỉ đến từ ~9 nhóm. Bốc ngẫu
       nhiên 9–10 link thì chắc chắn có nhóm bị comment 2 lần trong cùng một
       phiên — hai comment cách nhau vài phút từ cùng một Page là thứ làm admin
       nhóm để ý nhất. Ràng buộc này cũng tự động cho ra content khác nhau, vì
       mỗi nhóm chỉ góp một bài.
       ⇒ Số bài mỗi phiên KHÔNG BAO GIỜ vượt quá số nhóm đang có trong danh sách.

    2. **Ưu tiên bài cũ nhất còn trong cửa sổ**, nhưng xét `so_lan` trước:
       bài chưa comment lần nào đi trước bài đã comment rồi. Nếu chỉ xét tuổi
       thì mỗi phiên đều bốc trúng đúng một bài cũ nhất của mỗi nhóm, dội đi dội
       lại cho tới khi nó bị đẩy khỏi cửa sổ — đúng kiểu lặp cần tránh.

    `page`: chỉ lấy bài do CHÍNH Page đó đăng ("comment vào bài chính chủ").
    Bỏ trống = lấy mọi bài của hạng mục. Link cũ chưa gắn Page (cột rỗng) bị
    loại khi có lọc — thà bốc ít còn hơn comment nhầm bài của Page khác.
    """
    n = max(0, int(so_bai or 0))
    if n == 0:
        return []

    ds = get_comment_posts(loai)
    if page:
        ds = [r for r in ds if (r.get("page") or "") == page]

    # Trong mỗi nhóm, lấy đúng một ứng viên: ít comment nhất, rồi cũ nhất.
    ung_vien = {}
    for r in ds:
        nhom = (r.get("nhom") or "").strip() or f"__le_{r['id']}"
        khoa = (int(r.get("so_lan") or 0), int(r.get("order_idx") or 0))
        if nhom not in ung_vien or khoa < ung_vien[nhom][0]:
            ung_vien[nhom] = (khoa, r)

    ds = sorted(ung_vien.values(), key=lambda x: x[0])
    return [r for _, r in ds[:n]]


def ghi_nhan_comment(post_id: int, ok: bool, ghi_chu: str = "", chet: bool = False):
    """
    Ghi lại kết quả một lượt comment.

    Chỉ tính `lan_cuoi` / `so_lan` khi THÀNH CÔNG, để hai cột đó phản ánh đúng
    số comment đã lên thật.

    `chet=True`: bài đã bị xoá / đổi phạm vi → **XOÁ NGAY khỏi danh sách**.
    Đo thật cho thấy 20–30% bài bị gỡ; để chúng nằm lại chờ bị đẩy ra thì chừng
    ấy chỗ trong cửa sổ là rác, và mỗi lần bốc trúng là mất một lượt comment.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with _conn() as con:
        if chet:
            con.execute("DELETE FROM comment_posts WHERE id=?", (post_id,))
        elif ok:
            con.execute("UPDATE comment_posts SET lan_cuoi=?, so_lan=so_lan+1, "
                        "trang_thai=? WHERE id=?",
                        (now, f"✅ {now[-5:]}", post_id))
        else:
            con.execute("UPDATE comment_posts SET trang_thai=? WHERE id=?",
                        (f"❌ {now[-5:]} {ghi_chu}"[:60], post_id))


def get_setting(key: str, default: str = "") -> str:
    with _conn() as con:
        r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default


def set_setting(key: str, value: str):
    with _conn() as con:
        con.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )


def get_all_settings() -> dict:
    with _conn() as con:
        return {r["key"]: r["value"] for r in con.execute("SELECT * FROM settings").fetchall()}


# ═══════════════════════════════════════════════════════════════
# Init on import
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    print("Schema created successfully.")
