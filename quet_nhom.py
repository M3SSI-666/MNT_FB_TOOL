"""
Quét tên nhóm và số thành viên cho một sheet UID.

Dùng chung cho cả tab "UID Nhóm" (`QUET_MA_NHOM=""`) và "UID Marketplace"
(`QUET_MA_NHOM="MARKET"`) — hai tab chỉ khác nhau đúng giá trị đó.

Dán link vào là xong — không phải gõ tay tên từng nhóm. Worker mở từng trang
nhóm bằng một nick đã đăng nhập, đọc tên và số thành viên rồi ghi về DB.

CHỈ ĐỌC trên Facebook: vào trang nhóm, đọc, đi tiếp. Không bấm Tham gia, không
đăng, không bình luận.

VÌ SAO DÙNG PROFILE RIÊNG, không dùng profile của nick:
Chromium khoá thư mục profile khi đang mở. Nick nào cũng có thể đang chạy một
phiên đăng bài của runner, mà quét thì người dùng bấm lúc nào tuỳ họ — hai bên
giành khoá là hỏng cả hai. Cookie vẫn tiêm vào bình thường nên profile trắng
chạy được ngay, chỉ tốn thêm vài giây lần đầu.

Tiến độ ghi vào bảng settings để giao diện hỏi lại, giống cách lịch tham gia
nhóm báo trạng thái.
"""
import asyncio
import json
import os
import re
import sys

from config import PROFILES_DIR
from cookie_exporter import load_cookie
from db import (_conn, doc_so_thanh_vien, get_account_by_name, set_setting)
from fb_common import browser_launch_kwargs, dong_hop_cookie
from utils import logger

MA_NHOM = os.environ.get("QUET_MA_NHOM", "")
KHOA_TRANG_THAI = f"quet_tt_{MA_NHOM or 'UID'}"

ACC      = os.environ.get("QUET_ACC_NAME", "").strip()
HEADLESS = os.environ.get("HEADLESS", "true").lower() != "false"
# Quét lại cả dòng đã có tên hay chỉ dòng còn trống.
QUET_HET = os.environ.get("QUET_HET", "0") == "1"


def bao(**kw):
    """Ghi tiến độ để giao diện hỏi lại."""
    set_setting(KHOA_TRANG_THAI, json.dumps(kw, ensure_ascii=False))


def can_quet() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, uid, ten_nhom, link_url, thanh_vien FROM uid_groups "
            "WHERE COALESCE(ma_nhom,'')=? ORDER BY order_idx, id", (MA_NHOM,)
        ).fetchall()
    ds = [dict(r) for r in rows]
    if QUET_HET:
        return ds
    # str() chứ không phải `or ""`: cột `thanh_vien` khai là TEXT nhưng dữ liệu
    # cũ có dòng đang giữ SỐ (nhập từ Excel), và SQLite không ép kiểu. Gọi
    # .strip() thẳng lên int là AttributeError — worker sập ngay ở đây, trước
    # khi kịp báo gì, nên người bấm nút chỉ thấy nó đứng im.
    # Số 0 cũng tính là CHƯA BIẾT, không phải "nhóm có 0 thành viên" — nhóm
    # rỗng thì không tồn tại. Dòng mới thêm vào đang mang đúng giá trị 0 này.
    def _rong(v) -> bool:
        s = str(v if v is not None else "").strip()
        return not s or s == "0"

    # Thiếu MÃ SỐ cũng tính là cần quét, dù đã có tên và số thành viên: nhóm
    # lưu bằng tên chữ mà không có dạng số thì bộ lọc "nhóm đã tham gia" trượt,
    # và nhóm đó bị mở lại mỗi lần chạy.
    def _thieu_ma_so(r) -> bool:
        uid = (r["uid"] or "").strip()
        if uid.isdigit():
            return False
        return not re.search(r"/groups/\d{6,}", r["link_url"] or "")

    return [r for r in ds
            if _rong(r["ten_nhom"]) or _rong(r["thanh_vien"]) or _thieu_ma_so(r)]


def ghi(gid: int, ten: str, so: str, link: str = ""):
    with _conn() as con:
        if link:
            con.execute("UPDATE uid_groups SET ten_nhom=?, thanh_vien=?, link_url=? "
                        "WHERE id=?", (ten, so, link, gid))
        else:
            con.execute("UPDATE uid_groups SET ten_nhom=?, thanh_vien=? WHERE id=?",
                        (ten, so, gid))


# Mã SỐ của nhóm, đọc từ những đường dẫn chỉ nhóm đó mới có:
# /groups/<số>/members, /media, /events... KHÔNG quét `/groups/<số>` trần vì
# trang nhóm có đầy link sang nhóm khác trong các bài đăng.
_RE_GID_PHU = re.compile(
    r"/groups/(\d{6,})/(?:members|media|events|about|files|permalink|user)")


def _ma_so_nhom(url: str, html_links: list[str]) -> str:
    """Mã số của nhóm đang xem, hoặc '' nếu không chắc.

    VÌ SAO CẦN: 7/25 nhóm của Duong lưu bằng tên chữ (`timecity`,
    `canhotimescity`...). Bộ lọc "nhóm đã tham gia" so theo định danh, mà nó chỉ
    so được những dạng mình đang lưu — chỉ có dạng chữ thì Facebook liệt kê
    bằng số là trượt, và nhóm đó bị mở lại mỗi lần chạy.

    Lưu thêm dạng số vào `link_url` là `_dinh_danh_nhom` có đủ CẢ HAI dạng.
    """
    m = re.search(r"/groups/(\d{6,})", url or "")
    if m:
        return m.group(1)
    dem = {}
    for h in html_links:
        m = _RE_GID_PHU.search(h or "")
        if m:
            dem[m.group(1)] = dem.get(m.group(1), 0) + 1
    if not dem:
        return ""
    return max(dem, key=dem.get)


# Tên nhóm hay kèm đuôi " | Facebook" hoặc " - Facebook" trong <title>.
_RE_DUOI = re.compile(r"\s*[|\-–]\s*Facebook\s*$", re.I)
# "(8) Tên nhóm" — số thông báo chưa đọc mà Facebook nhét vào đầu <title>.
_RE_DAU = re.compile(r"^\(\d+\)\s*")


def _don_ten(s: str) -> str:
    return _RE_DAU.sub("", _RE_DUOI.sub("", (s or "").strip())).strip()


# Lấy tên nhóm từ ĐÂU — cả ba cách hiển nhiên đều sai, đo thật ngày 30/09:
#
#   meta og:title   KHÔNG TỒN TẠI trên trang nhóm bản đã đăng nhập.
#   document.title  ĐỌC LẠI CỦA TRANG TRƯỚC. Mở riêng hai nhóm, chờ 9 giây,
#                   cả hai vẫn báo cùng một title dù số thành viên khác nhau.
#                   Nó còn kèm số thông báo chưa đọc ở đầu: "(8) Tên nhóm".
#   h1 đầu trang    là mục điều hướng "Thông báo", không phải tên nhóm.
#
# Chỉ `[role="main"] h1` là đọc từ đúng nội dung của trang đang xem.
JS_TEN = r"""() => {
    const t = e => (e.innerText || e.textContent || '').trim().replace(/\s+/g,' ');
    const rac = /^(thông báo|notifications|facebook|trang chủ|home)$/i;
    for (const h of document.querySelectorAll('[role="main"] h1')) {
        const s = t(h).replace(/^\(\d+\)\s*/, '')
                      .replace(/\s*[|\-–]\s*Facebook\s*$/i, '').trim();
        if (s && !rac.test(s)) return s;
    }
    return '';
}"""

# Số thành viên nằm rải rác ở phần đầu trang; lấy CỤM CHỮ chứa nó rồi để Python
# tách số bằng `doc_so_thanh_vien` — cùng hàm dùng cho màn hình chọn nhóm, nên
# "43,5K" kiểu Việt Nam đọc ra đúng 43.500 ở cả hai nơi.
JS_DOC = r"""() => {
    const t = e => (e.innerText || e.textContent || '').trim().replace(/\s+/g,' ');
    const rac = /^(thông báo|notifications|facebook|trang chủ|home)$/i;
    let ten = '';
    for (const h of document.querySelectorAll('[role="main"] h1')) {
        const s = t(h).replace(/^\(\d+\)\s*/, '')
                      .replace(/\s*[|\-–]\s*Facebook\s*$/i, '').trim();
        if (s && !rac.test(s)) { ten = s; break; }
    }
    let tv = '';
    for (const e of document.querySelectorAll('span,div,a')) {
        const s = t(e);
        if (s.length < 60 && /(thành viên|members)/i.test(s) && /\d/.test(s)) { tv = s; break; }
    }
    // Mọi đường dẫn /groups/... trên trang, để Python lọc ra mã số của CHÍNH
    // nhóm này (xem `_ma_so_nhom`).
    const link = [];
    for (const a of document.querySelectorAll('a[href*="/groups/"]')) {
        const h = a.getAttribute('href') || '';
        if (h) link.push(h);
    }
    return {ten, tv, link: link.slice(0, 400)};
}"""


async def doc_mot_nhom(page, link: str) -> tuple[str, str, str, str]:
    """Trả về (tên, số thành viên, mã số nhóm, lý do hỏng). Hỏng thì tên rỗng.

    HAI NHÓM TRÙNG TÊN LÀ CHUYỆN BÌNH THƯỜNG, không phải lỗi đọc: đo ngày
    30/09, nhóm 382936754082358 và 1362597001398822 cùng tên "✅Chợ Cư Dân
    Times City & Park Hill" nhưng một bên 16,6K một bên 13,5K thành viên.
    Nên ĐỪNG thêm phép "trùng tên thì đọc lại" — nó sẽ ghi đè tên đúng.

    Hệ quả cho việc đối chiếu về sau: TÊN NHÓM KHÔNG DUY NHẤT, muốn chắc chắn
    thì phải khớp bằng UID.
    """
    try:
        await page.goto(link, wait_until="domcontentloaded", timeout=40000)
    except Exception as e:
        return "", "", "", f"không mở được ({type(e).__name__})"
    await asyncio.sleep(4)
    await dong_hop_cookie(page)

    if "/login" in page.url or "checkpoint" in page.url:
        return "", "", "", "cookie hỏng / bị chặn"

    kq = await page.evaluate(JS_DOC)

    ten   = _don_ten(kq.get("ten") or "")
    so    = doc_so_thanh_vien(kq.get("tv") or "")
    ma_so = _ma_so_nhom(page.url, kq.get("link") or [])
    if not ten:
        return "", "", ma_so, "không đọc được tên"
    return ten, (str(so) if so else ""), ma_so, ""


async def main():
    if not ACC:
        logger.error("❌ Thiếu QUET_ACC_NAME")
        bao(xong=True, loi="Chưa chọn tài khoản")
        return
    if not get_account_by_name(ACC):
        bao(xong=True, loi=f"Không có tài khoản {ACC!r}")
        return
    ck = load_cookie(ACC, (get_account_by_name(ACC) or {}).get("c_user", ""))
    if not ck:
        bao(xong=True, loi=f"{ACC} chưa có cookie")
        return

    ds = can_quet()
    if not ds:
        bao(xong=True, tong=0, da=0, ok=0, loi="")
        logger.info("Không có nhóm nào cần quét")
        return

    ten_sheet = "Marketplace" if MA_NHOM else "UID Nhóm"
    logger.info(f"🔎 Quét {len(ds)} nhóm {ten_sheet} bằng nick {ACC}")
    bao(xong=False, tong=len(ds), da=0, ok=0, dang="")

    from playwright.async_api import async_playwright
    profile = str(PROFILES_DIR / f"_quet_{MA_NHOM or 'uid'}_{ACC.replace(' ', '_')}")

    ok = 0
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=profile, **browser_launch_kwargs(HEADLESS))
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        ci = []
        for n in ("c_user", "xs"):
            if ck.get(n):
                ci.append({"name": n, "value": ck[n], "domain": ".facebook.com",
                           "path": "/", "httpOnly": True, "secure": True, "sameSite": "None"})
        for n in ("datr", "sb", "fr", "wd"):
            if ck.get(n):
                ci.append({"name": n, "value": ck[n], "domain": ".facebook.com",
                           "path": "/", "httpOnly": False, "secure": True, "sameSite": "None"})
        await ctx.add_cookies(ci)

        try:
            for i, r in enumerate(ds, 1):
                link = (r["link_url"] or "").strip() \
                       or f"https://www.facebook.com/groups/{r['uid']}/"
                bao(xong=False, tong=len(ds), da=i - 1, ok=ok,
                    dang=(r["ten_nhom"] or r["uid"] or "")[:40])
                ten, so, ma_so, loi = await doc_mot_nhom(page, link)
                if ten:
                    # Lưu địa chỉ dạng SỐ khi uid đang là tên chữ: bộ lọc "nhóm
                    # đã tham gia" nhờ đó có đủ cả hai dạng để đối chiếu.
                    link_moi = (f"https://www.facebook.com/groups/{ma_so}/"
                                if ma_so and ma_so != (r["uid"] or "").strip() else "")
                    ghi(r["id"], ten, so, link_moi)
                    ok += 1
                    logger.info(f"  [{i}/{len(ds)}] ✅ {ten[:50]} · {so or '?'} thành viên"
                                + (f" · mã số {ma_so}" if link_moi else ""))
                else:
                    logger.warning(f"  [{i}/{len(ds)}] ⚠️  {r['uid']}: {loi}")
                await asyncio.sleep(2.5)
        finally:
            await ctx.close()

    bao(xong=True, tong=len(ds), da=len(ds), ok=ok, loi="")
    logger.info(f"🔎 Xong: đọc được {ok}/{len(ds)} nhóm")


if __name__ == "__main__":
    # Sập thì PHẢI báo ra màn hình. Không có lưới này thì mọi lỗi đều hiện ra
    # y như nhau: nút bấm xong rồi đứng im, không ai biết vì sao — đúng chuyện
    # đã xảy ra ngày 30/09 khi worker chết ở bước đọc danh sách.
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception("❌ Quét tên nhóm hỏng")
        bao(xong=True, loi=f"{type(e).__name__}: {e}"[:160])
        raise
