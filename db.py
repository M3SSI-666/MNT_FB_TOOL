"""
db.py — SQLite data layer cho MNT_FB
Thay thế hoàn toàn Google Sheets, không cần internet để đọc/ghi data.
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "app.db"


# 4 tiến trình scheduler × MAX_WORKERS luồng cùng ghi vào một file SQLite.
# Không có busy timeout thì luồng thứ hai vấp "database is locked" ngay lập tức,
# nên cho nó chờ tới 15s để lấy khoá thay vì fail.
BUSY_TIMEOUT_SEC = 15


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
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ── Pages ────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS pages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ten_page        TEXT NOT NULL,
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
            link_anh_hook   TEXT DEFAULT '',        -- URL ảnh hook
            link_anh        TEXT DEFAULT '',        -- comma-separated URLs
            su_dung         TEXT DEFAULT 'Có',      -- Có / Không
            ghi_chu         TEXT DEFAULT '',
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ── UID / Nhóm ───────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS uid_groups (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ma_nhom         TEXT NOT NULL,          -- TIME1, TIME2, ... hoặc '' = UID Nhóm sheet
            uid             TEXT NOT NULL,
            ten_nhom        TEXT DEFAULT '',
            link_url        TEXT DEFAULT '',
            thanh_vien      TEXT DEFAULT '',
            ghi_chu         TEXT DEFAULT ''
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
            updated_at      TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_schedules_loai_status
            ON schedules(loai, trang_thai);

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
    with _conn() as con:
        if ten_page:
            r = con.execute(
                "SELECT * FROM accounts WHERE ten_acc = ? AND ten_page = ? AND trang_thai = 'Active' LIMIT 1",
                (ten_acc, ten_page)
            ).fetchone()
            if r:
                return dict(r)
        r = con.execute(
            "SELECT * FROM accounts WHERE ten_acc = ? AND trang_thai = 'Active' LIMIT 1",
            (ten_acc,)
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
        "email_khoiphuc","pass_khoiphuc","twofa","ghi_chu"
    }
    if field not in safe:
        raise ValueError(f"Field không hợp lệ: {field}")
    with _conn() as con:
        con.execute(f"UPDATE accounts SET {field}=? WHERE id=?", (value, acc_id))


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


# ═══════════════════════════════════════════════════════════════
# Content
# ═══════════════════════════════════════════════════════════════

def get_content(loai: str, su_dung: str = None) -> list[dict]:
    with _conn() as con:
        sql  = "SELECT * FROM content WHERE loai=?"
        args = [loai]
        if su_dung:
            sql += " AND su_dung=?"; args.append(su_dung)
        sql += " ORDER BY id"
        return [dict(r) for r in con.execute(sql, args).fetchall()]


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
        cur = con.execute(
            f"INSERT INTO content ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})",
            values
        )
        return cur.lastrowid


def delete_content(content_id: int):
    with _conn() as con:
        con.execute("DELETE FROM content WHERE id=?", (content_id,))


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
        return [dict(r) for r in con.execute(
            "SELECT * FROM uid_groups ORDER BY ma_nhom, id"
        ).fetchall()]


def upsert_uid_group(data: dict) -> int:
    cols   = [k for k in data if k != "id"]
    values = [data[c] for c in cols]
    with _conn() as con:
        if "id" in data and data["id"]:
            sets = ", ".join(f"{c}=?" for c in cols)
            con.execute(f"UPDATE uid_groups SET {sets} WHERE id=?", values + [data["id"]])
            return data["id"]
        cur = con.execute(
            f"INSERT INTO uid_groups ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})",
            values
        )
        return cur.lastrowid


def delete_uid_group(gid: int):
    with _conn() as con:
        con.execute("DELETE FROM uid_groups WHERE id=?", (gid,))


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
            con.executemany(
                """INSERT INTO schedules
                   (loai, stt, ma_content, ten_acc, ten_page, gio_dang,
                    ma_nhom, tu_khoa, mode, trang_thai)
                   VALUES (:loai,:stt,:ma_content,:ten_acc,:ten_page,:gio_dang,
                           :ma_nhom,:tu_khoa,:mode,:trang_thai)""",
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
