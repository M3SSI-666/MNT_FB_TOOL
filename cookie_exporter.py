"""
cookie_exporter.py — MNT_FB version
Đọc c_user + xs từ SQLite (db.py) thay vì Google Sheets.
"""

import os
import sys
import json
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import logger

COOKIES_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies")
PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name.replace(" ", "_"))


def load_cookie(acc_name: str, c_user: str = "") -> dict | None:
    """
    Đọc cookie JSON từ cookies/{acc_name}.json.
    Nếu có c_user → ưu tiên build từ db bằng c_user (tránh nhầm acc trùng tên).
    """
    # c_user đảm bảo duy nhất → dùng trực tiếp nếu có
    if c_user:
        return _build_cookie_from_cuser(c_user)

    safe = _safe_filename(acc_name)
    path = os.path.join(COOKIES_DIR, f"{safe}.json")

    # Thử file JSON trước
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Thử tìm file với tên unicode
    if os.path.exists(COOKIES_DIR):
        for fname in os.listdir(COOKIES_DIR):
            base = os.path.splitext(fname)[0]
            if base.replace("_", " ").lower() == acc_name.lower():
                try:
                    with open(os.path.join(COOKIES_DIR, fname), encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

    # Fallback: build từ db nếu không có file
    return _build_cookie_from_db(acc_name)


def _build_cookie_from_db(acc_name: str) -> dict | None:
    """Build cookie dict từ SQLite khi không có file JSON."""
    try:
        from db import get_account_by_name
        acc = get_account_by_name(acc_name)
        if not acc:
            return None
        data = {
            "c_user":     acc.get("c_user", ""),
            "xs":         acc.get("xs", ""),
            "acc_name":   acc_name,
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return data if data["c_user"] else None
    except Exception as e:
        logger.error(f"❌ _build_cookie_from_db '{acc_name}': {e}")
        return None


def _build_cookie_from_cuser(c_user: str) -> dict | None:
    """Build cookie dict từ SQLite bằng c_user (dùng khi tên acc trùng nhau)."""
    try:
        from db import get_account_by_cuser
        acc = get_account_by_cuser(c_user)
        if not acc:
            return None
        data = {
            "c_user":      acc.get("c_user", ""),
            "xs":          acc.get("xs", ""),
            "acc_name":    acc.get("ten_acc", ""),
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return data if data["c_user"] else None
    except Exception as e:
        logger.error(f"❌ _build_cookie_from_cuser '{c_user}': {e}")
        return None


def export_all_accounts(target_acc: str = None) -> int:
    """
    Đọc từ SQLite → xuất cookie JSON cho từng acc Active.
    Dùng khi cần refresh cookie (cột Refresh = Yes).
    """
    os.makedirs(COOKIES_DIR, exist_ok=True)

    try:
        from db import get_accounts, resolve_page_uid
        accs = get_accounts(trang_thai="Active")
        if target_acc:
            accs = [a for a in accs if a["ten_acc"] == target_acc]

        exported = 0
        for acc in accs:
            c_user = acc.get("c_user", "").strip()
            xs     = acc.get("xs", "").strip()
            if not c_user or not xs:
                continue

            ten = acc["ten_acc"]
            safe = _safe_filename(ten)

            # Lấy Page info — UID gán cho acc quyết định, tên chỉ là dự phòng.
            page_name = acc.get("ten_page", "")
            page_uid  = resolve_page_uid(acc, page_name)

            cookie_data = {
                "c_user":      c_user,
                "xs":          xs,
                "i_user":      page_uid,
                "actor_id":    page_uid,
                "page_name":   page_name,
                "acc_name":    ten,
                "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Thêm extra cookies từ profile nếu có
            extras = _read_extra_cookies_from_profile(ten)
            cookie_data.update(extras)

            path = os.path.join(COOKIES_DIR, f"{safe}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cookie_data, f, ensure_ascii=False, indent=2)

            logger.info(f"  ✅ Exported: {ten} → {safe}.json")
            exported += 1

        logger.info(f"✅ Exported {exported} cookies")
        return exported

    except Exception as e:
        logger.error(f"❌ export_all_accounts: {e}")
        return 0


def _read_extra_cookies_from_profile(acc_name: str) -> dict:
    """Đọc datr/sb/fr/wd từ Playwright profile nếu có."""
    def _find_profile():
        if not os.path.exists(PROFILES_DIR):
            return None
        safe = _safe_filename(acc_name)
        for d in os.listdir(PROFILES_DIR):
            if d.replace(" ","_").lower() == safe.lower():
                return os.path.join(PROFILES_DIR, d)
        return None

    profile_dir = _find_profile()
    if not profile_dir:
        return {}

    try:
        import asyncio
        from playwright.async_api import async_playwright

        async def _read():
            async with async_playwright() as p:
                ctx = await p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir, headless=True,
                    args=["--disable-blink-features=AutomationControlled","--no-sandbox"],
                )
                cookies = await ctx.cookies("https://www.facebook.com")
                await ctx.close()
            return {c["name"]: c["value"] for c in cookies
                    if c["name"] in ("datr","sb","fr","wd")}

        return asyncio.run(_read())
    except Exception:
        return {}


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else None
    export_all_accounts(target_acc=target)
