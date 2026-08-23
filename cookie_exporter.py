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

# Lấy từ config để dời được sang %LOCALAPPDATA% khi cài bằng setup.exe.
from config import COOKIES_DIR as _CK, PROFILES_DIR as _PF
COOKIES_DIR  = str(_CK)
PROFILES_DIR = str(_PF)


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

    Trước khi ghi file, thử đọc cookie SỐNG từ profile Chrome của acc: nếu
    profile còn đăng nhập thì xs ở đó mới hơn xs trong DB (Facebook xoay xs
    theo phiên), và ta ghi ngược giá trị mới vào DB. Nhờ vậy cột Refresh tự
    gia hạn cookie thay vì chỉ chép lại đúng thứ người dùng đã nhập tay.
    """
    os.makedirs(COOKIES_DIR, exist_ok=True)

    try:
        from db import get_accounts, get_page_by_name
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

            # Cookie sống từ profile — có thì ưu tiên, không có thì dùng DB.
            live = _read_cookies_from_profile(ten, c_user)
            xs   = _sync_xs_to_db(acc, live) or xs

            # Lấy Page info
            page_uid  = ""
            page_name = acc.get("ten_page", "")
            if page_name:
                page = get_page_by_name(page_name)
                if page:
                    page_uid = page.get("page_uid", "")

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
            cookie_data.update({k: v for k, v in live.items()
                                if k in EXTRA_COOKIES})

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


def refresh_pending_accounts() -> dict:
    """
    Làm mới cookie cho mọi acc đang để cột Refresh = Yes, rồi đánh dấu Done.

    Dùng chung cho vòng lặp scheduler (quét mỗi 10 phút) và nút "Refresh ngay"
    trên giao diện, để hai đường không bao giờ lệch hành vi.
    """
    from db import get_accounts, update_account_field

    ket_qua = {"da_lam": [], "loi": []}
    cho = [a for a in get_accounts()
           if str(a.get("refresh", "")).strip().lower() == "yes"]

    for a in cho:
        ten = a["ten_acc"]
        logger.info(f"🔄 Refresh cookie: '{ten}'...")
        try:
            export_all_accounts(target_acc=ten)
            update_account_field(a["id"], "refresh", "Done")
            logger.info(f"✅ '{ten}': cookie refreshed")
            ket_qua["da_lam"].append(ten)
        except Exception as e:
            logger.error(f"❌ '{ten}': lỗi refresh: {e}")
            ket_qua["loi"].append(f"{ten}: {e}")

    return ket_qua


# Cookie phụ giúp Facebook nhận ra "vẫn là máy cũ" — thiếu chúng thì phiên
# dựng từ c_user+xs trông như đăng nhập từ thiết bị lạ, dễ bị hỏi xác minh.
EXTRA_COOKIES = ("datr", "sb", "fr", "wd")
WANTED_COOKIES = ("xs", "c_user") + EXTRA_COOKIES


def _sync_xs_to_db(acc: dict, live: dict) -> str:
    """
    Ghi xs đọc được từ profile ngược vào DB. Trả về xs mới, hoặc "" nếu không
    có gì để cập nhật.

    Chỉ ghi khi c_user của profile TRÙNG c_user trong DB: profile có thể đã
    được đăng nhập sang nick khác, ghi bừa sẽ gán nhầm cookie của nick này cho
    nick kia — hỏng nặng hơn nhiều so với việc bỏ qua một lần refresh.
    """
    moi = (live.get("xs") or "").strip()
    if not moi:
        return ""

    ten    = acc["ten_acc"]
    db_cu  = (acc.get("c_user") or "").strip()
    pf_cu  = (live.get("c_user") or "").strip()
    if pf_cu and pf_cu != db_cu:
        logger.warning(f"  ⚠️  '{ten}': profile đang là c_user {pf_cu} "
                       f"(DB ghi {db_cu}) — không ghi đè xs")
        return ""

    if moi == (acc.get("xs") or "").strip():
        return ""                       # không đổi, khỏi đụng DB

    try:
        from db import update_account_field
        update_account_field(acc["id"], "xs", moi)
        logger.info(f"  🔑 '{ten}': lấy được xs mới từ profile → đã lưu vào DB")
        return moi
    except Exception as e:
        logger.error(f"  ❌ '{ten}': không lưu được xs mới: {e}")
        return ""


def _find_profile_dir(acc_name: str, c_user: str = "") -> str | None:
    """
    Tìm thư mục profile Chrome của acc — CHỈ ĐỌC, không tạo mới.

    Poster đặt tên thư mục theo dạng "{Tên}_{c_user}" (fb_common.
    find_profile_dir). Bản cũ ở file này chỉ so tên trần nên không bao giờ
    khớp với profile thật, khiến toàn bộ phần đọc cookie từ profile chết lặng.
    Vẫn nhận dạng "{Tên}" trần cho các profile đời đầu còn sót lại.
    """
    if not os.path.isdir(PROFILES_DIR):
        return None

    ten  = acc_name.replace(" ", "_")
    uu_tien = [f"{ten}_{c_user}", ten] if c_user else [ten]

    for folder in uu_tien:
        path = os.path.join(PROFILES_DIR, folder)
        if os.path.isdir(path):
            return path

    # Dự phòng: tên thư mục có thể lệch hoa/thường so với tên acc trong DB
    muon = {f.lower() for f in uu_tien}
    for d in os.listdir(PROFILES_DIR):
        if d.lower() in muon:
            return os.path.join(PROFILES_DIR, d)
    return None


def _read_cookies_from_profile(acc_name: str, c_user: str = "") -> dict:
    """
    Đọc cookie Facebook trực tiếp từ profile Chrome của acc.

    Trả về {} khi không có profile, profile đang được dùng, hoặc đọc lỗi — gọi
    hàm này không bao giờ làm gián đoạn luồng xuất cookie.
    """
    profile_dir = _find_profile_dir(acc_name, c_user)
    if not profile_dir:
        return {}

    # Chromium KHÔNG khoá thư mục profile. Mở song song với một phiên đang chạy
    # sẽ làm hỏng dữ liệu đăng nhập của phiên đó → bỏ qua, lần sau lấy tiếp.
    try:
        from fb_common import _profile_dang_mo
        if os.path.normcase(os.path.abspath(profile_dir)) in _profile_dang_mo():
            logger.info(f"  ⏭️  '{acc_name}': profile đang mở — bỏ qua đọc cookie")
            return {}
    except Exception:
        pass

    try:
        import asyncio
        from playwright.async_api import async_playwright

        async def _read():
            async with async_playwright() as p:
                # --disable-gpu: ép vẽ bằng phần mềm, tránh renderer sập khi
                # headless trên Windows (xem chú thích ở fb_common).
                ctx = await p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir, headless=True,
                    args=["--disable-blink-features=AutomationControlled",
                          "--no-sandbox", "--disable-gpu"],
                )
                try:
                    cookies = await ctx.cookies("https://www.facebook.com")
                finally:
                    await ctx.close()
            return {c["name"]: c["value"] for c in cookies
                    if c["name"] in WANTED_COOKIES and c.get("value")}

        # Chặn trên thời gian: refresh chạy trong vòng lặp scheduler, một
        # profile hỏng treo vô hạn sẽ làm đứng luôn việc đăng bài.
        return asyncio.run(asyncio.wait_for(_read(), timeout=60))
    except Exception as e:
        logger.warning(f"  ⚠️  '{acc_name}': không đọc được cookie từ profile: {e}")
        return {}


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else None
    export_all_accounts(target_acc=target)
