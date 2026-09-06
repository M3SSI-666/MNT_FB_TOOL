"""
TẦNG 1 — cứu acc "Cookie hết hạn" bằng chính profile Chrome của nó.

Ý CHÍNH
═══════
`xs` trong cơ sở dữ liệu và cookie trong profile Chrome là HAI KHO RIÊNG. Cái
trong DB là ảnh chụp lúc người dùng nhập tay; cái trong profile do Chrome giữ
và được Facebook làm mới liên tục mỗi lần acc hoạt động.

Nên "hết cookie" hầu như luôn có nghĩa là **bản chụp trong DB đã cũ**, chứ không
phải phiên đã chết. Đo trên máy thật: 12/12 acc đọc được đều có `xs` ở profile
khác hẳn `xs` trong DB — không một cái nào còn trùng.

Từ đó ra cách cứu không tốn gì: mở đúng profile đó lên, hỏi Facebook xem còn
đăng nhập không. Còn thì lấy `xs` mới ghi vào DB và trả acc về Active.

VÌ SAO CÁCH NÀY AN TOÀN
═══════════════════════
Không dùng một chữ mật khẩu nào. Không có màn đăng nhập nào. Với Facebook thì
đây chỉ là acc đó mở trình duyệt lên xem trang chủ — đúng thứ nó vẫn làm hằng
ngày. Khác hẳn việc đăng nhập lại tự động, vốn là hành vi kích hoạt checkpoint
số một.

BA LUẬT
═══════
1. Không bao giờ ném lỗi ra ngoài — hỏng thì acc cứ ở nguyên "Cookie hết hạn".
2. Không đụng vào acc mà profile đang mở: Chrome khoá file, và acc đó đang chạy.
3. Thử lại có giãn cách. Acc không cứu được mà cứ mở trình duyệt mỗi 10 phút thì
   vừa phí máy vừa đáng ngờ.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from utils import logger

# Cùng một acc, cách nhau ít nhất ngần này phút mới thử cứu lại. Acc cứu không
# được thường là phiên chết thật — thử dày cũng không đổi kết quả.
NGHI_PHUT = 90

# Mỗi lượt quét cứu tối đa ngần này acc. Mỗi lần cứu là một lần mở Chrome; cả
# loạt acc cùng hết cookie mà mở 15 trình duyệt một lúc là treo máy.
MOI_LUOT = 3

# Chặn trên thời gian cho MỘT acc. Profile hỏng có thể treo vô hạn, mà hàm này
# chạy trong vòng lặp của scheduler — treo ở đây là đứng luôn việc đăng bài.
CHO_GIAY = 75


def _bang_da_thu(con):
    con.execute("""CREATE TABLE IF NOT EXISTS kp_da_thu (
                       ten_acc TEXT PRIMARY KEY,
                       luc     TEXT NOT NULL
                   )""")


def _con_nghi(ten_acc: str) -> bool:
    """
    Acc này còn trong thời gian nghỉ giữa hai lần thử không? CHỈ ĐỌC.

    Tách hẳn khỏi việc ghi dấu, và đây không phải chuyện kiểu cách. Lúc đầu tôi
    gộp hai việc vào một hàm rồi gọi nó trong bộ lọc:

        cho = [a for a in ds if not _da_thu_gan_day(a)][:MOI_LUOT]

    Bộ lọc chạy qua MỌI acc hết hạn, nên MỌI acc đều bị ghi dấu "vừa thử" —
    trong khi `[:MOI_LUOT]` chỉ lấy 3 acc đầu để thử thật. Có 10 acc hỏng thì 7
    acc bị khoá 90 phút mà chưa hề được đụng tới. Càng nhiều trạm, mỗi trạm 15
    nick, thì cái này càng cắn đau.
    """
    try:
        import db
        with db._conn() as con:
            _bang_da_thu(con)
            r = con.execute("SELECT luc FROM kp_da_thu WHERE ten_acc=?",
                            (ten_acc,)).fetchone()
        if not r:
            return False
        return datetime.now() - datetime.fromisoformat(r["luc"]) < timedelta(minutes=NGHI_PHUT)
    except Exception:
        return False        # không kiểm được thì cứ thử, thà thừa còn hơn kẹt


def _danh_dau_da_thu(ten_acc: str):
    """Ghi dấu đã thử. Gọi NGAY TRƯỚC khi thử thật, không gọi lúc lọc."""
    try:
        import db
        with db._conn() as con:
            _bang_da_thu(con)
            con.execute("INSERT INTO kp_da_thu(ten_acc,luc) VALUES(?,?) "
                        "ON CONFLICT(ten_acc) DO UPDATE SET luc=excluded.luc",
                        (ten_acc, datetime.now().isoformat(timespec="seconds")))
    except Exception:
        pass


async def _hoi_facebook(profile_dir: str) -> dict:
    """
    Mở profile lên và hỏi Facebook xem còn đăng nhập không.

    Trả `{}` khi đã đăng xuất. Còn đăng nhập thì trả cookie đọc được — lấy SAU
    khi trang tải xong, vì chính lần tải đó khiến Facebook cấp `xs` mới.
    """
    from playwright.async_api import async_playwright
    from fb_common import chua_dang_nhap
    from cookie_exporter import WANTED_COOKIES

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir, headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-gpu"],
        )
        try:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto("https://www.facebook.com/", timeout=45000,
                            wait_until="domcontentloaded")
            if await chua_dang_nhap(page):
                return {}
            ck = await ctx.cookies("https://www.facebook.com")
            return {c["name"]: c["value"] for c in ck
                    if c["name"] in WANTED_COOKIES and c.get("value")}
        finally:
            await ctx.close()


def cuu_mot_acc(acc: dict) -> tuple[bool, str]:
    """
    Thử cứu một acc. Trả `(được hay không, lý do)`.

    Chỉ đổi trạng thái về Active khi Facebook đã xác nhận phiên còn sống. Đổi
    dựa vào "đọc được cookie" thôi thì chưa đủ: file cookie vẫn còn nguyên sau
    khi phiên bị thu hồi, nên acc sẽ về Active rồi hỏng lại ngay phiên sau —
    và mỗi vòng như vậy lại bắn một cặp tin Telegram.
    """
    ten = acc.get("ten_acc", "")
    cu  = (acc.get("c_user") or "").strip()
    try:
        from cookie_exporter import _find_profile_dir, _sync_xs_to_db
        from fb_common import _profile_dang_mo

        pf = _find_profile_dir(ten, cu)
        if not pf:
            return False, "không có profile Chrome"

        import os
        if os.path.basename(pf) in _profile_dang_mo():
            return False, "profile đang mở"

        live = asyncio.run(asyncio.wait_for(_hoi_facebook(pf), timeout=CHO_GIAY))
        if not live:
            return False, "profile cũng đã đăng xuất"

        pf_cu = (live.get("c_user") or "").strip()
        if pf_cu and cu and pf_cu != cu:
            return False, f"profile đang là nick khác ({pf_cu})"

        moi = _sync_xs_to_db(acc, live)
        # `_sync_xs_to_db` trả rỗng khi xs không đổi. Phiên vẫn sống, nên vẫn
        # cứu — chỉ là không có gì mới để ghi.
        if not moi and not (live.get("xs") or "").strip():
            return False, "không đọc được xs"

        # Đổi trạng thái QUA update_account_field để nó tự so cũ với mới rồi
        # bắn tin '🟢 HOẠT ĐỘNG TRỞ LẠI'. Ghi thẳng SQL thì mất thông báo đó.
        from db import update_account_field
        update_account_field(acc["id"], "trang_thai", "Active")
        return True, "lấy lại được phiên từ profile"
    except asyncio.TimeoutError:
        return False, f"quá {CHO_GIAY}s không xong"
    except Exception as e:
        return False, str(e)[:90]


def quet() -> int:
    """
    Quét mọi acc đang 'Cookie hết hạn' và thử cứu. Trả số acc cứu được.

    Gọi định kỳ từ scheduler. Không bao giờ ném lỗi.
    """
    try:
        from db import get_accounts
        cho = [a for a in get_accounts(trang_thai="Cookie hết hạn")
               if not _con_nghi(a["ten_acc"])][:MOI_LUOT]
        if not cho:
            return 0

        duoc = 0
        for a in cho:
            # Ghi dấu ngay trước khi thử, không ghi lúc lọc: acc bị `[:MOI_LUOT]`
            # cắt ra ngoài phải được thử ở lượt sau chứ không bị khoá oan.
            _danh_dau_da_thu(a["ten_acc"])
            ok, vi_sao = cuu_mot_acc(a)
            if ok:
                duoc += 1
                logger.info(f"🔓 '{a['ten_acc']}': {vi_sao} → về Active")
            else:
                logger.info(f"   '{a['ten_acc']}': chưa cứu được — {vi_sao}")
        return duoc
    except Exception as e:
        logger.error(f"❌ Quét cứu phiên hỏng: {e}")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if quet() >= 0 else 1)
