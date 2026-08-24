"""
comment_bai.py — PHIÊN ĐI COMMENT

Vì sao có tính năng này
───────────────────────
Nhiều acc bị Facebook dỡ bài ngay khi đăng, nhưng **vẫn comment được**. Trong
nhóm, một bài có comment mới sẽ nổi lên đầu (nhóm sắp xếp theo hoạt động gần
nhất). Vậy thay vì cố đăng bài mới để rồi bị dỡ, ta comment vào các bài cũ còn
sống để đẩy chúng lên.

Cách hoạt động
──────────────
Mỗi loại (homestay / thuê / bán) có một danh sách URL bài viết + một thư viện
câu comment. Đến phiên, acc mở từng bài, gõ một câu bốc ngẫu nhiên, gửi, nghỉ,
sang bài kế tiếp.

Slot chạy phiên comment lấy từ chính lịch đăng bài — giống nuôi nick: cứ mỗi
`comment_interval` phút thì một slot đăng của acc đó biến thành phiên comment.
Lịch không dày thêm, và một slot chỉ làm một việc.

Rủi ro phải nhớ khi sửa file này
────────────────────────────────
1. **Comment trùng nội dung là đường nhanh nhất mất quyền comment.** Thư viện
   câu và `pick_messages` (không lặp câu liền nhau) là bắt buộc, không phải
   trang trí. Nếu acc mất luôn quyền comment thì hết đường.
2. **Đẩy một bài quá dày → admin nhóm đá acc ra**, tệ hơn bị dỡ bài: mất bài
   thì đăng lại được, mất nhóm thì hết. Cooldown theo từng URL
   (đã bỏ theo yêu cầu — mỗi phiên vào comment mọi link được bốc).
3. Phát hiện bị chặn thì **dừng cả phiên**, không cố comment tiếp — cố thêm chỉ
   khiến acc bị soi nặng hơn (cùng nguyên tắc với nuôi nick khi bị chặn nhắn tin).
"""

import os
import sys
import random
import asyncio

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.async_api import async_playwright

from config import HEADLESS
from utils import logger, CookieDeadError
from cookie_exporter import load_cookie
from fb_common import (kiem_vi_pham, chua_dang_nhap, browser_launch_kwargs, find_profile_dir, human_delay,
                       dong_dialog_canh_bao, bat_dau_canh_dialog,
                       view_stories, browse_and_like)
from nuoi_nick import pick_messages, is_messaging_restricted
import db


# Giá trị mặc định — sửa được qua bảng settings / modal Cài đặt comment.
DEFAULTS = {
    "comment_so_bai":    9,     # số bài mỗi phiên (≤ số nhóm trong danh sách)
    # Nghỉ giữa 2 bài (giây). Để một KHOẢNG chứ không một số cố định: comment
    # đều tăm tắp đúng một nhịp là dấu hiệu máy, chính thứ utils.jitter_ms sinh
    # ra để tránh.
    "comment_nghi_min": 10,
    "comment_nghi_max": 15,
}

# Khởi động và kết phiên BÁM ĐÚNG luồng đăng bài Page — cùng một hành vi thì
# cùng một khoảng thời gian, không có lý do gì để chỉnh riêng. Xem các bước
# [2/7], [3/7], [7/7] trong page_via_poster.py; sửa ở đó thì sửa cả ở đây.
STORY_GIAY = (15, 20)     # [2/7] xem story
FEED_GIAY  = (20, 30)     # [3/7] lướt newsfeed, KHÔNG like
KET_GIAY   = (15, 30)     # [7/7] lướt cuối phiên
KET_LIKE   = 1            # [7/7] like tối đa 1 bài — chỗ DUY NHẤT có like


# Trần cứng cho một phiên comment. Đo thật: phiên 9 bài mất ~6 phút, nên 15
# phút là dư gấp đôi.
#
# BẮT BUỘC phải có. Playwright không đặt timeout mặc định cho `page.evaluate`,
# nên khi trang Facebook rơi vào trạng thái xấu thì `browse_and_like` treo vô
# hạn. Đã gặp thật: phiên comment kẹt 13 phút ở bước lướt newsfeed, giữ luôn
# một worker của scheduler, dòng lịch đứng mãi ở "Đang comment", và tới giờ
# scheduler còn mở thêm phiên nuôi cho CÙNG acc đó → hai Chrome cùng một profile.
GIOI_HAN_PHIEN_GIAY = 900


class CommentRestricted(Exception):
    """Acc đang bị Facebook chặn comment — dừng phiên, không thử tiếp."""


# Bài bị xoá / đổi phạm vi hiển thị. Phân biệt hẳn với lỗi selector: link chết
# thì phải xoá khỏi danh sách, còn selector hỏng thì phải sửa code — hai việc
# hoàn toàn khác nhau, gộp chung vào "không tìm thấy ô bình luận" là đi mò nhầm.
BAI_KHONG_XEM_DUOC = (
    "bạn hiện không xem được nội dung này",
    "nội dung này hiện không có sẵn",
    "this content isn't available",
    "content isn't available right now",
    "đã xóa nội dung",
)


class BaiDaChet(Exception):
    """Bài không còn xem được — đánh dấu để người dùng lọc ra và bỏ khỏi danh sách."""


def bai_da_chet(page_text: str) -> bool:
    t = (page_text or "").lower()
    return any(m in t for m in BAI_KHONG_XEM_DUOC)


def cai_dat() -> dict:
    """Đọc settings, thiếu thì lấy mặc định."""
    st = {}
    for k, dv in DEFAULTS.items():
        v = db.get_setting(k, "")
        try:
            st[k] = type(dv)(v) if str(v).strip() != "" else dv
        except (TypeError, ValueError):
            st[k] = dv
    for loai in ("homestay", "thue", "ban"):
        st[f"pool_{loai}"] = db.get_setting(f"comment_pool_{loai}", "")
    return st


def ly_do_bo_qua(ds: list) -> str:
    """Vì sao phiên không bốc được bài nào. Chỉ còn một khả năng: danh sách trống."""
    return "danh sách trống" if not ds else ""


def tach_cau(raw: str) -> list:
    """Thư viện câu: mỗi dòng một câu, bỏ dòng trống và trùng lặp."""
    ra, da_co = [], set()
    for ln in (raw or "").splitlines():
        c = ln.strip()
        if c and c not in da_co:
            ra.append(c)
            da_co.add(c)
    return ra


# ═══════════════════════════════════════════════════════════════
# Playwright
# ═══════════════════════════════════════════════════════════════

async def _open_context(p, acc_name: str, c_user: str, headless: bool = None):
    """Mở trình duyệt bằng profile + cookie của acc. Giống nuôi nick."""
    profile_dir = find_profile_dir(acc_name, c_user)
    logger.info(f"  🗂️  Profile: {profile_dir}")
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        **browser_launch_kwargs(HEADLESS if headless is None else headless),
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    bat_dau_canh_dialog(page)          # dialog cảnh báo bật lại bất cứ lúc nào

    cookie_data = load_cookie(acc_name, c_user)
    if not cookie_data:
        await ctx.close()
        raise CookieDeadError(f"{acc_name}: không có cookie")

    ci = []
    for name, http_only in (("c_user", True), ("xs", True),
                            ("datr", False), ("sb", False),
                            ("fr", False), ("wd", False)):
        v = cookie_data.get(name, "")
        if v:
            ci.append({"name": name, "value": v, "domain": ".facebook.com",
                       "path": "/", "httpOnly": http_only, "secure": True,
                       "sameSite": "None"})
    await ctx.add_cookies(ci)

    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded",
                    timeout=30000)
    await human_delay(2000, 3000)
    if await chua_dang_nhap(page):
        await ctx.close()
        raise CookieDeadError(acc_name)

    await dong_dialog_canh_bao(page)
    return ctx, page


# Ô bình luận của Facebook là contenteditable, không phải <input>. aria-label
# đổi theo ngôn ngữ và theo chỗ đặt (dưới bài, trong dialog), nên thử nhiều mẫu
# rồi mới hạ xuống cách đoán chung.
_SELECTORS_O_COMMENT = (
    "div[role='textbox'][aria-label*='Viết bình luận']",
    "div[role='textbox'][aria-label*='Bình luận']",
    "div[role='textbox'][aria-label*='Write a comment']",
    "div[role='textbox'][aria-label*='Comment']",
    "form div[role='textbox'][contenteditable='true']",
)


async def _tim_o_comment(page):
    """Trả về locator ô bình luận, None nếu không thấy."""
    for sel in _SELECTORS_O_COMMENT:
        try:
            box = page.locator(sel).first
            if await box.count() and await box.is_visible():
                return box
        except Exception:
            continue

    # Hạ xuống cách chung: contenteditable đang hiện đầu tiên — NHƯNG phải loại
    # ô soạn bài viết. Trang nhóm vẫn có composer "Bạn đang nghĩ gì", gõ nhầm
    # vào đó rồi Enter là đăng hẳn một bài mới lên nhóm.
    _KHONG_PHAI_COMMENT = ("nghĩ gì", "on your mind", "tạo bài viết",
                           "create post", "tìm kiếm", "search")
    try:
        cand = page.locator("div[role='textbox'][contenteditable='true']")
        for i in range(min(await cand.count(), 6)):
            b = cand.nth(i)
            if not await b.is_visible():
                continue
            nhan = ((await b.get_attribute("aria-label") or "") + " " +
                    (await b.get_attribute("aria-placeholder") or "")).lower()
            if any(x in nhan for x in _KHONG_PHAI_COMMENT):
                continue
            return b
    except Exception:
        pass
    return None


async def _khoi_dong(page, ctx, page_uid: str = "") -> bool:
    """
    Khởi động phiên, y hệt luồng đăng bài Page:
        story cá nhân → newsfeed cá nhân → CHUYỂN sang Page được phân công

    Bước cuối là **chiếm quyền hoạt động của Page** (bấm nút Chuyển + inject
    `i_user`), không phải chỉ ghé xem — sau bước này mọi comment đi ra dưới danh
    nghĩa Page chứ không phải acc cá nhân. Dùng lại `_switch_to_page` của
    page_via_poster, KHÔNG chép lại: selector nút "Chuyển"/"Dùng Trang" đổi theo
    giao diện FB, chép ra hai bản là sau này sửa sót một bản.

    Lướt KHÔNG like ở giai đoạn này — like để dành cho lúc kết phiên.

    Hỏng ở đây không được làm chết phiên: mục đích chỉ là làm mềm hành vi, mất
    một lượt comment vì lỗi khởi động là lỗ hơn.

    Trả về True nếu đã chuyển sang Page.
    """
    logger.info("  🔥 Khởi động phiên...")
    try:
        await page.goto("https://www.facebook.com/",
                        wait_until="domcontentloaded", timeout=30000)
        await human_delay(1500, 2500)
        await dong_dialog_canh_bao(page)
        await view_stories(page, duration_sec=random.randint(*STORY_GIAY))
        await browse_and_like(page, duration_sec=random.randint(*FEED_GIAY),
                              max_likes=0)
    except Exception as e:
        logger.warning(f"    ⚠️  Story/newsfeed không trọn vẹn: {e}")

    if not page_uid:
        logger.info("    ⏭️  Slot không có Page được phân công — comment bằng acc cá nhân")
        return False

    try:
        from page_via_poster import _switch_to_page
        logger.info(f"    🔄 Chuyển sang Page {page_uid}...")
        await _switch_to_page(page, ctx, page_uid)
        await dong_dialog_canh_bao(page)
        return True
    except Exception as e:
        # Chuyển hỏng thì comment sẽ đi ra dưới tên acc cá nhân — khác hẳn ý
        # định, nên báo mức ERROR chứ không nuốt lặng lẽ.
        logger.error(f"    ❌ Không chuyển được sang Page: {e} "
                     f"— comment sẽ mang danh acc CÁ NHÂN")
        return False


async def _ket_phien(page, acc_name: str = "") -> None:
    """
    Kết phiên y hệt bước [7/7] của luồng đăng bài: lướt newsfeed rồi like 1 bài
    trước khi đóng trình duyệt.

    Comment xong tắt máy ngay cũng là khuôn máy — người thật còn lướt tiếp một
    lúc. Đây là chỗ DUY NHẤT trong phiên comment có like.
    """
    try:
        giay = random.randint(*KET_GIAY)
        logger.info(f"  🏁 Kết phiên: lướt newsfeed {giay}s + like {KET_LIKE} bài...")
        await page.goto("https://www.facebook.com/",
                        wait_until="domcontentloaded", timeout=30000)
        await human_delay(1500, 2500)
        await dong_dialog_canh_bao(page)
        await browse_and_like(page, duration_sec=giay, max_likes=KET_LIKE)
        # Comment bị gỡ cũng là dính spam, y như bài đăng bị gỡ. Dò SAU khi
        # lướt feed vì Facebook cần vài chục giây mới đổ thông báo về.
        await kiem_vi_pham(page, acc_name, "phiên comment")
    except Exception as e:
        logger.warning(f"    ⚠️  Kết phiên không trọn vẹn: {e}")


async def _comment_mot_bai(page, url: str, cau: str) -> None:
    """
    Mở một bài viết và gửi một comment.

    Ném exception nếu không gửi được; CommentRestricted nếu acc bị chặn (phiên
    sẽ dừng); BaiDaChet nếu bài đã bị xoá.
    """
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await human_delay(2500, 4500)

    # Dialog cảnh báo che mất ô bình luận y như che composer khi đăng bài.
    await dong_dialog_canh_bao(page)

    if await chua_dang_nhap(page):
        raise CookieDeadError("bị đá về trang đăng nhập khi mở bài viết")

    # Bị chặn thì dừng NGAY, không gõ gì. Cùng lý do với nuôi nick: cố thao tác
    # trong lúc đang bị hạn chế chỉ làm acc bị soi nặng thêm.
    try:
        body = await page.inner_text("body")
    except Exception:
        body = ""
    if is_messaging_restricted(body):
        raise CommentRestricted("Facebook đang hạn chế hoạt động của acc")
    if bai_da_chet(body):
        raise BaiDaChet("bài đã bị xoá hoặc đổi phạm vi hiển thị")

    box = await _tim_o_comment(page)
    if box is None:
        raise Exception("Không tìm thấy ô bình luận (bài bị xoá / FB đổi giao diện?)")

    await box.click()
    await human_delay(600, 1400)
    # Gõ từng ký tự có độ trễ — dán cả câu một phát là dấu hiệu máy rõ nhất.
    await page.keyboard.type(cau, delay=random.randint(40, 110))
    await human_delay(500, 1200)
    await page.keyboard.press("Enter")
    await human_delay(2500, 4000)

    # XÁC MINH ĐÃ GỬI — gõ xong không lỗi KHÔNG có nghĩa là comment đã lên.
    # Gửi thành công thì Facebook xoá trắng ô nhập; gửi hỏng (mất mạng, bài bị
    # xoá, bị chặn) thì chữ còn nguyên trong ô. Không kiểm thì bảng sẽ ghi ✅
    # cho những lượt chẳng có comment nào.
    try:
        con_lai = (await box.inner_text()).strip()
    except Exception:
        con_lai = ""                    # ô biến mất cũng là dấu hiệu đã gửi
    if con_lai and cau.strip() in con_lai:
        raise Exception("gõ xong nhưng comment không gửi được (chữ còn trong ô)")

    # Gõ xong FB mới chặn cũng có — kiểm lại để dừng đúng lúc thay vì chạy hết list.
    try:
        if is_messaging_restricted(await page.inner_text("body")):
            raise CommentRestricted("bị chặn ngay sau khi gửi comment")
    except CommentRestricted:
        raise
    except Exception:
        pass


def _lay_page_uid(page_name: str) -> str:
    """UID của Page được phân công cho slot (cột Page trong bảng lịch)."""
    if not (page_name or "").strip():
        return ""
    try:
        p = db.get_page_by_name(page_name.strip())
    except Exception:
        return ""
    if not p:
        logger.warning(f"    ⚠️  Không tìm thấy Page '{page_name}' trong bảng Page")
        return ""
    return str(p.get("page_uid") or "").strip()


async def _chay_phien(acc_name: str, c_user: str, loai: str,
                      headless: bool = None, page_name: str = "",
                      tien_trinh=None) -> dict:
    """
    `tien_trinh(da_xong, tong)`: gọi sau mỗi bài để bên ngoài cập nhật trạng
    thái. Một phiên 10 bài kéo dài 12–18 phút; không báo tiến trình thì nhìn
    bảng lịch không phân biệt được đang chạy hay đã treo.
    """
    st   = cai_dat()
    pool = tach_cau(st.get(f"pool_{loai}", ""))
    if not pool:
        logger.warning(f"  ⏭️  Chưa có thư viện câu cho loại '{loai}' — bỏ phiên")
        return {"da_comment": 0, "loi": 0, "bo_qua": "thiếu thư viện câu"}

    # Bài chính chủ đi trước, rồi LẤP ĐẦY bằng bài khác cùng hạng mục cho đủ số
    # bài đã cài đặt. `page` là thứ tự ưu tiên chứ không phải bộ lọc cứng.
    #
    # Trước đây lọc cứng nên acc yếu — chỉ đăng chéo được vào 1 nhóm, cả kho chỉ
    # có 1 link của nó — mỗi phiên comment đúng 1 bài thay vì 10. Nhánh lùi về
    # kho chung chỉ chạy khi có ĐÚNG 0 link chính chủ nên không cứu được ca đó.
    page_uid = _lay_page_uid(page_name)
    bai = db.boc_bai_de_comment(loai, st["comment_so_bai"], page=page_uid)

    if not bai:
        logger.warning(f"  ⏭️  Bỏ phiên — chưa có link nào trong danh sách '{loai}'")
        return {"da_comment": 0, "loi": 0, "bo_qua": "danh sách trống"}

    cau_ds = pick_messages(pool, len(bai))     # không lặp câu ở hai bài liền nhau
    n_minh = sum(1 for b in bai if page_uid and (b.get("page") or "") == page_uid)
    nguon = (f"{n_minh} bài chính chủ + {len(bai) - n_minh} bài cùng hạng mục"
             if page_uid else "chung kho")
    logger.info(f"  💬 Phiên comment: {len(bai)}/{st['comment_so_bai']} bài | "
                f"thư viện {len(pool)} câu | {nguon}")

    ok_n, loi_n = 0, 0
    chet = []                                  # link chết gặp trong phiên này
    chet_theo_acc = {}                         # acc đã đăng các bài chết đó
    async with async_playwright() as p:
        ctx, page = await _open_context(p, acc_name, c_user, headless)
        try:
            la_page = await _khoi_dong(page, ctx, page_uid)
            logger.info(f"  💬 Comment dưới danh nghĩa: "
                        f"{'Page ' + page_name if la_page else 'acc cá nhân ' + acc_name}")
            for i, (b, cau) in enumerate(zip(bai, cau_ds), 1):
                try:
                    await _comment_mot_bai(page, b["url"], cau)
                    db.ghi_nhan_comment(b["id"], True)
                    ok_n += 1
                    logger.info(f"    ✅ [{i}/{len(bai)}] {cau[:38]} "
                                f"→ ...{b['url'][-32:]}")
                except BaiDaChet as e:
                    # Không tính là lỗi hệ thống: bài cũ bị xoá là chuyện bình
                    # thường. Xoá khỏi danh sách, nhưng GHI LẠI acc đã đăng bài
                    # đó — bài bị Facebook gỡ là tín hiệu spam, mà tín hiệu ấy
                    # chỉ dùng được khi biết nó của acc nào.
                    _xoa = db.ghi_nhan_comment(b["id"], False, chet=True)
                    chet.append(b["url"])
                    _cua = (_xoa or {}).get("acc") or "?"
                    logger.warning(f"    💀 [{i}/{len(bai)}] LINK CHẾT: {e} "
                                   f"→ bài do '{_cua}' đăng → {b['url']}")
                    if _cua != "?":
                        chet_theo_acc[_cua] = chet_theo_acc.get(_cua, 0) + 1
                except CommentRestricted as e:
                    db.ghi_nhan_comment(b["id"], False, "bị chặn")
                    logger.error(f"    ⛔ Dừng phiên: {e} "
                                 f"(đã comment {ok_n}/{len(bai)})")
                    raise
                except CookieDeadError:
                    raise
                except Exception as e:
                    db.ghi_nhan_comment(b["id"], False, str(e)[:30])
                    loi_n += 1
                    logger.warning(f"    ⚠️  [{i}/{len(bai)}] hỏng: {e}")

                if tien_trinh:
                    # Hỏng ở đây (DB khoá, v.v.) không được kéo sập phiên —
                    # báo tiến trình chỉ để nhìn cho biết.
                    try:
                        tien_trinh(i, len(bai))
                    except Exception:
                        pass

                if i < len(bai):
                    await asyncio.sleep(random.uniform(st["comment_nghi_min"],
                                                       st["comment_nghi_max"]))
            # Chỉ kết phiên tử tế khi đã comment được ít nhất một bài. Đang bị
            # chặn mà còn nán lại lướt + like là làm acc bị soi thêm.
            if ok_n:
                await _ket_phien(page, acc_name)
        finally:
            try:
                await ctx.close()
            except Exception:
                pass

    logger.info(f"  ✅ Xong phiên comment — {ok_n} thành công, "
                f"{loi_n} lỗi, {len(chet)} link chết")
    if chet:
        # In hẳn ra log để người dùng biết mà dọn, không phải mở app mới thấy.
        logger.warning(f"  💀 {len(chet)} link chết — ĐÃ XOÁ khỏi danh sách:")
        for u in chet:
            logger.warning(f"       {u}")
        # Bài bị gỡ là tín hiệu spam, nhưng chỉ dùng được khi biết nó của ACC
        # nào. Trước đây link chỉ gắn Page, mà 10/10 Page có 2 acc cùng đăng nên
        # tín hiệu này luôn dừng ở "một trong hai".
        if chet_theo_acc:
            tk = " · ".join(f"{a}: {n}" for a, n in
                            sorted(chet_theo_acc.items(), key=lambda x: -x[1]))
            logger.warning(f"  📌 Bài bị gỡ thuộc về — {tk}")
    return {"da_comment": ok_n, "loi": loi_n, "link_chet": len(chet),
            "tong_bai": len(bai), "chet_theo_acc": chet_theo_acc}


async def _chay_co_han(*a, **kw) -> dict:
    """Bọc phiên trong trần thời gian — xem ghi chú ở GIOI_HAN_PHIEN_GIAY."""
    try:
        return await asyncio.wait_for(_chay_phien(*a, **kw),
                                      timeout=GIOI_HAN_PHIEN_GIAY)
    except asyncio.TimeoutError:
        # wait_for huỷ coroutine bên trong; khối `finally` của nó đóng trình
        # duyệt, nên không để lại Chrome mồ côi giữ khoá profile.
        logger.error(f"  ⏱️  Phiên comment quá {GIOI_HAN_PHIEN_GIAY}s — cắt ngang. "
                     f"Thường là trang Facebook treo ở bước lướt newsfeed.")
        return {"da_comment": 0, "loi": 0, "link_chet": 0, "tong_bai": 0,
                "bo_qua": f"quá {GIOI_HAN_PHIEN_GIAY // 60} phút, bị cắt"}


def chay_phien_comment(acc_name: str, loai: str, c_user: str = "",
                       headless: bool = None, page_name: str = "",
                       tien_trinh=None) -> dict:
    """Hàm đồng bộ — scheduler gọi từ thread. Ném exception để scheduler phân loại lỗi."""
    return asyncio.run(_chay_co_han(acc_name, c_user, loai, headless,
                                    page_name, tien_trinh))


# ─────────────────────────────────────────────────────────────────────────────
# Chạy tay để thử: python comment_bai.py "Tên acc" homestay
# Hiện cửa sổ Chrome để nhìn tận mắt, KHÔNG headless.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if len(sys.argv) < 3:
        print('Dùng:  python comment_bai.py "Tên acc" <homestay|thue|ban>')
        sys.exit(0)

    ten, loai_ = sys.argv[1], sys.argv[2]
    acc = db.get_account_by_name(ten)
    if not acc:
        print(f"Không tìm thấy acc '{ten}'")
        sys.exit(1)
    print(chay_phien_comment(ten, loai_, acc.get("c_user", ""), headless=False))
