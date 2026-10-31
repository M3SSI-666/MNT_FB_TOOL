"""
================================================================================
via_poster.py  —  Mode "Via" cá nhân
================================================================================
Đăng bài bằng tài khoản cá nhân, cross-post sang nhiều nhóm qua từ khóa.

LUỒNG:
  1. Login acc cá nhân (goto facebook.com, kiểm tra cookie)
  2. Xem story 15-20s
  3. Scroll newsfeed 20-30s (không like — trang cá nhân)
  4. Chui vào nhóm đầu → mở composer → paste nội dung → upload ảnh
  5. Thêm nhóm → gõ từ khóa → tick đủ nhóm → Xong → Đăng
  6. THU LINK bài vừa đăng (phản hồi mạng + trang thông báo) → lưu danh sách
     comment; lướt feed KHÔNG like làm cửa sổ chờ + dò spam → đóng Chrome

DÙNG TỪ CODE KHÁC:
  from via_poster import post_via_crosspost
  ok = post_via_crosspost(
      acc_name       = "Ngô Quang Hùng",
      first_group_uid= "311375961636397",
      search_kw      = "Times City",
      message        = "Nội dung bài đăng...",
      image_url      = "https://drive.google.com/drive/folders/...",
  )
================================================================================
"""

import os
import asyncio
import random
import unicodedata

from cookie_exporter import load_cookie
from config import HEADLESS
from utils import logger, jitter_ms, CookieDeadError, LoiBuoc, ChanNhomError
from fb_common import (kiem_vi_pham, chua_dang_nhap, find_profile_dir, dong_dialog_canh_bao, cho_composer_dong,
                       bat_dau_canh_dialog, dismiss_anon_dialog, dong_hop_cookie, danh_dau_da_dang, browser_launch_kwargs,
                       human_delay, jwait, clipboard_paste, browse_and_like, CHO_SAU_DANG_GIAY,
                       chon_va_tick_nhom_cheo, cho_upload_xong, cho_sau_dang_giay)

# ── User-Agent Chrome 124 ─────────────────────────────────────────────────────
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Vỏ mỏng gọi sang fb_common — TRƯỚC ĐÂY LÀ BẢN SAO NGUYÊN VĂN.
# Ba file cùng giữ một hàm giống hệt nhau từng dòng, nên mỗi lần sửa phải nhớ
# sửa cả ba; thực tế bản trong join_groups_runner đã trôi khác và chạy trên
# thư mục profile trắng suốt không biết bao lâu.
_find_profile_dir = find_profile_dir


# Vỏ mỏng gọi sang fb_common — TRƯỚC ĐÂY LÀ NĂM BẢN SAO NGUYÊN VĂN.
# Hai file poster mỗi file giữ một bộ giống hệt nhau, nên mỗi lần vá phải nhớ vá
# cả hai. Thực tế đã trôi: bản xem story ở đây chờ bằng
# `page.wait_for_timeout(1500)` còn bản kia dùng `_jwait(page, 1500)` — lệch đúng
# một dòng, đủ để hai nick hành xử khác nhau mà không ai biết.
_human_delay     = human_delay
_jwait           = jwait
_clipboard_paste = clipboard_paste
_browse_and_like = browse_and_like


# Dùng bản chung ở fb_common. Trước đây mỗi poster giữ một bản chép giống
# hệt, nên khi sửa lỗi "dò 5 selector tuần tự tốn 15s" phải sửa ba nơi — đúng
# kiểu sai sót đã từng xảy ra với bản vá dialog cảnh báo.
_dismiss_anon_dialog = dismiss_anon_dialog


# ─────────────────────────────────────────────────────────────────────────────
# Core async: toàn bộ flow
# ─────────────────────────────────────────────────────────────────────────────

async def _run_crosspost(
    acc_name:        str,
    first_group_uid: str,
    search_kw:       str,
    message:         str,
    local_photos:    list,
    c_user:          str = "",
    loai_comment:    str = "",
    page_uid:        str = "",
) -> bool:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    profile_dir = _find_profile_dir(acc_name, c_user)
    logger.info(f"  🗂️  Profile: {profile_dir}")

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            **browser_launch_kwargs(HEADLESS),
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        # Vòng canh nền: Facebook bật lại dialog cảnh báo bất cứ lúc nào, không
        # riêng ở mấy điểm mình đoán trước. Tự huỷ khi đóng Chrome.
        bat_dau_canh_dialog(page)

        # ── Inject cookies ────────────────────────────────────────────────────
        cookie_data = load_cookie(acc_name, c_user)
        if not cookie_data:
            logger.error(f"❌ [{acc_name}] Không có cookie!")
            await ctx.close()
            raise LoiBuoc("Không có cookie trong máy")

        _ci = []
        for name, key in [("c_user", "c_user"), ("xs", "xs")]:
            v = cookie_data.get(key, "")
            if v:
                _ci.append({"name": name, "value": v, "domain": ".facebook.com",
                             "path": "/", "httpOnly": True, "secure": True, "sameSite": "None"})
        for name in ["datr", "sb", "fr", "wd"]:
            v = cookie_data.get(name, "")
            if v:
                _ci.append({"name": name, "value": v, "domain": ".facebook.com",
                             "path": "/", "httpOnly": False, "secure": True, "sameSite": "None"})
        await ctx.add_cookies(_ci)

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 1 — Login vào acc cá nhân
        # ════════════════════════════════════════════════════════════════
        logger.info(f"  [1/5] 🔐 Login acc cá nhân...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await _human_delay(2000, 3000)

        if await chua_dang_nhap(page):
            logger.error(f"  ❌ [{acc_name}] Cookie hết hạn!")
            await ctx.close()
            raise CookieDeadError(acc_name)

        logger.info(f"  ✅ Login OK")
        # Hộp xin phép cookie hay bật ngay sau khi vào facebook.com và chặn
        # MỌI cú bấm phía sau: bấm story trượt, bấm "Chuyển" trượt, bấm ô
        # soạn bài trượt. Dọn một lần ở đây rẻ hơn chữa từng bước.
        if await dong_hop_cookie(page):
            logger.info("  🍪 Đã đóng hộp xin phép cookie")

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 2 — Scroll newsfeed 20-30s (không like — trang cá nhân)
        # ════════════════════════════════════════════════════════════════
        # KHÔNG còn bước xem story: Duong chỉ giữ story ở phiên NUÔI NICK.
        scroll_sec = random.randint(8, 12)
        logger.info(f"  [2/5] 📜 Scroll newsfeed {scroll_sec}s...")
        await _browse_and_like(page, duration_sec=scroll_sec, max_likes=0)

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 3 — Chui vào nhóm đầu, paste nội dung + upload ảnh
        # ════════════════════════════════════════════════════════════════
        group_url = f"https://www.facebook.com/groups/{first_group_uid}/"
        logger.info(f"  [3/5] 📌 Vào nhóm: {group_url}")
        await page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
        await _human_delay(3000, 5000)

        if await chua_dang_nhap(page):
            logger.error(f"  ❌ Bị redirect về login!")
            await ctx.close()
            raise CookieDeadError(acc_name)

        # Gạt dialog cảnh báo vi phạm sang một bên — nó nổi đè lên newfeed và
        # nuốt mất cú click vào ô soạn bài.
        await dong_dialog_canh_bao(page)

        # Mở composer
        logger.info(f"    📝 Mở composer...")
        opened = False
        # Hai lượt: dialog cảnh báo thường bật lên MUỘN vài giây sau khi trang
        # tải xong, nên lần dọn phía trên có thể diễn ra lúc nó chưa kịp hiện.
        # Lượt đầu trượt thì dọn lại rồi thử tiếp — bám theo triệu chứng thay vì
        # cầu may đúng thời điểm.
        for _luot in range(2):
            # Hộp cookie là lớp phủ MODAL: ô soạn bài vẫn nằm trong DOM và vẫn
            # tính là "visible", nhưng mọi cú bấm đều bị nó nuốt. Dọn TRƯỚC khi
            # dò nút, nếu không thì dò đủ 6 kiểu nút rồi mới thua sau ~41 giây.
            await dong_hop_cookie(page)
            for sel in [
                ':text("Bạn viết gì đi")', ':text("Write something")',
                ':text("Bạn đang nghĩ gì?")',
                "div[role='button']:has-text('Tạo bài viết')",
                "[aria-label='Tạo bài viết']", "[aria-label='Create post']",
            ]:
                try:
                    el = await page.wait_for_selector(sel, timeout=5000, state="visible")
                    if el:
                        await el.hover()
                        await _human_delay(400, 700)
                        await el.click()
                        await _human_delay(2000, 3000)
                        opened = True
                        break
                except PWTimeout:
                    continue
            # Không có dialog cảnh báo nào để dọn → trượt vì lý do khác, thử lại vô ích
            # Thử lại khi vừa dọn được MỘT lớp phủ nào đó — hộp cookie hoặc
            # dialog cảnh báo. Bản cũ chỉ hỏi dialog cảnh báo, nên gặp hộp
            # cookie là bỏ cuộc ngay sau lượt đầu.
            if opened or _luot == 1:
                break
            da_don = await dong_hop_cookie(page)
            if not (da_don or await dong_dialog_canh_bao(page)):
                break
        if not opened:
            logger.error(f"  ❌ Không mở được composer!")
            # FB chặn hành động nhóm? Đọc text trang để phân biệt với tải chậm.
            try:
                from nuoi_nick import is_messaging_restricted
                _body = await page.inner_text("body")
            except Exception:
                _body = ""
            await ctx.close()
            if _body and is_messaging_restricted(_body):
                raise ChanNhomError(
                    f"Acc bị hạn chế hành động nhóm (nhóm {first_group_uid})")
            raise LoiBuoc(f"Không mở được ô soạn bài (nhóm {first_group_uid})")

        # Paste nội dung
        logger.info(f"    📋 Paste nội dung ({len(message)}c)...")
        await _human_delay(800, 1200)
        typed = False
        for sel in [
            "div[role='dialog'] div[contenteditable='true'][data-lexical-editor='true']",
            "div[role='dialog'] div[contenteditable='true']",
            "div[contenteditable='true']",
        ]:
            try:
                box = await page.wait_for_selector(sel, timeout=5000, state="visible")
                if box:
                    await box.click()
                    await _human_delay(400, 600)
                    await _clipboard_paste(page, ctx, message)
                    typed = True
                    break
            except PWTimeout:
                continue
        if not typed:
            logger.error(f"  ❌ Không paste được nội dung!")
            await ctx.close()
            raise LoiBuoc("Mở được ô soạn bài nhưng không dán được nội dung")

        # Upload ảnh
        if local_photos:
            logger.info(f"    📤 Upload {len(local_photos)} ảnh...")
            await _human_delay(800, 1200)
            uploaded = False
            for sel in [
                "div[role='dialog'] [aria-label*='Ảnh']",
                "div[role='dialog'] [aria-label*='Photo']",
                "[aria-label*='Ảnh/video']", "[aria-label*='Photo/video']",
                "span:has-text('Ảnh/video')", "span:has-text('Photo/video')",
            ]:
                try:
                    btn = await page.wait_for_selector(sel, timeout=5000, state="visible")
                    if btn:
                        await btn.hover()
                        await _human_delay(300, 500)
                        async with page.expect_file_chooser(timeout=8000) as fc_info:
                            await btn.click()
                        fc = await fc_info.value
                        await fc.set_files(local_photos)
                        _cap = max(6000, len(local_photos) * 3500)
                        logger.info(f"    ⏳ Chờ upload (tối đa {_cap // 1000}s)...")
                        _n = await cho_upload_xong(page, len(local_photos), _cap)
                        logger.info(f"    ✅ {_n}/{len(local_photos)} ảnh đã lên")
                        uploaded = True
                        break
                except (PWTimeout, Exception):
                    continue
            if not uploaded:
                logger.warning(f"    ⚠️  Không upload được ảnh — đăng text-only")
        else:
            logger.info(f"    ⏭️  Không có ảnh")

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 5 — Thêm nhóm → gõ từ khóa → tick → Đăng
        # ════════════════════════════════════════════════════════════════
        logger.info(f"  [4/5] ➕ Thêm nhóm → tìm \"{search_kw}\" → tick → Đăng...")

        # Click "+ Thêm nhóm"
        await _human_delay(1000, 1500)
        add_clicked    = False
        _groups_posted = 0
        for sel in [
            "div[role='dialog'] span:has-text('Thêm nhóm')",
            "div[role='dialog'] div[role='button']:has-text('Thêm nhóm')",
            "span:has-text('+ Thêm nhóm')",
            "[aria-label*='Add groups']",
            "span:has-text('Add groups')",
        ]:
            try:
                btn = await page.wait_for_selector(sel, timeout=5000, state="visible")
                if btn:
                    await btn.hover()
                    await _human_delay(300, 500)
                    await btn.click()
                    await _human_delay(2000, 3000)
                    add_clicked = True
                    break
            except PWTimeout:
                continue
        if not add_clicked:
            logger.warning(f"  ⚠️  Không tìm thấy nút Thêm nhóm — acc chưa đủ khỏe, đăng 1 nhóm và nuôi nick")

        if add_clicked:
            # Chờ tối đa 3s để "Anonymous post" dialog xuất hiện rồi dismiss
            await _dismiss_anon_dialog(page, wait_ms=3000)

            # Chọn nhóm: QUÉT cả list đã tham gia → lọc từ khoá → XOAY VÒNG.
            # (Thay cách cũ: gõ từ khoá rồi tick HẾT nhóm hiện ra — không lọc.)
            # Facebook chặn tối đa 9 nhóm/lần đăng chéo.
            _groups_posted = await chon_va_tick_nhom_cheo(
                page, search_kw, c_user, loai_comment, 9)

            # Click "Xong"
            await _human_delay(800, 1200)
            xong_clicked = False
            for sel in [
                "div[role='button']:has-text('Xong')",
                "button:has-text('Xong')",
                "span:has-text('Xong')",
                "div[role='button']:has-text('Done')",
            ]:
                try:
                    btn = await page.wait_for_selector(sel, timeout=5000, state="visible")
                    if btn:
                        await btn.hover()
                        await _human_delay(300, 500)
                        await btn.click()
                        await _human_delay(2000, 3000)
                        xong_clicked = True
                        break
                except PWTimeout:
                    continue
            if not xong_clicked:
                logger.error(f"  ❌ Không tìm thấy nút Xong!")
                await ctx.close()
                raise LoiBuoc("Không thấy nút Xong sau khi tick nhóm")

        # Bắt link bài vừa đăng từ phản hồi mạng. Gắn TRƯỚC khi bấm Đăng vì phản
        # hồi chứa ID bài về ngay sau cú bấm. Bọc try/except — tính năng phụ,
        # hỏng ở đây không được làm hỏng việc đăng.
        _bat = None
        try:
            from thu_link import BoBatLink
            _bat = BoBatLink(page)
            _bat.bat_dau()
        except Exception as e:
            logger.warning(f"    ⚠️  Không gắn được bộ bắt link: {e}")

        # Click "Đăng"
        await _human_delay(2000, 3000)
        posted = False
        for sel in [
            "div[role='dialog'] div[aria-label='Đăng']",
            "div[role='dialog'] div[aria-label='Post']",
            "div[role='dialog'] div[role='button']:has-text('Đăng')",
            "div[role='dialog'] div[role='button']:has-text('Post')",
        ]:
            try:
                btn = await page.wait_for_selector(sel, timeout=5000, state="visible")
                if btn:
                    await btn.hover()
                    await _human_delay(500, 800)
                    await btn.click()
                    posted = True
                    break
            except PWTimeout:
                continue
        if not posted:
            logger.error(f"  ❌ Không tìm thấy nút Đăng!")
            await ctx.close()
            raise LoiBuoc("Không thấy nút Đăng")

        # Chờ ô soạn bài đóng = Facebook đã nhận bài
        if await cho_composer_dong(page):
            logger.info(f"  ✅ [{acc_name}] ĐĂNG THÀNH CÔNG!")
            # Từ ĐÂY nội dung mới thật sự nằm trên Facebook. Cảnh báo gỡ bài
            # thấy sau mốc này mới có thể là của phiên này — xem ghi chú ở
            # `fb_common.danh_dau_da_dang`.
            danh_dau_da_dang(page)
            import nhip_dap
            nhip_dap.ghi("dang_hybrid")
        else:
            logger.warning(f"  ⚠️  Không chắc kết quả — kiểm tra thủ công trên Facebook")

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 6 — Thu link bài vừa đăng + lướt feed (KHÔNG like) + dò spam
        # ════════════════════════════════════════════════════════════════
        # Thu link GIỐNG Hybrid: (a) link từ phản hồi mạng (nhóm mở composer),
        # (b) link từ TRANG THÔNG BÁO (FB đẩy 1 thông báo/nhóm đăng chéo — nguồn
        # CHÍNH). Thông báo về chậm (~60-76s) nên cần quãng chờ; ở đây là quãng
        # lướt feed cá nhân — KHÔNG like (đúng ý: VIA đang ở trang cá nhân).
        _link_moi = []

        # (a) Phản hồi mạng — nhóm mở composer KHÔNG sinh thông báo đăng chéo nên
        #     đây là nguồn bổ sung bắt buộc, không phải dự phòng.
        try:
            if _bat is not None:
                _kq = _bat.ket_qua()
                _bat.dung()
                _link_moi = list(_kq["links"])
                logger.info(f"  🔗 [a] Phản hồi mạng (nhóm mở composer): {len(_link_moi)} link")
        except Exception as e:
            logger.warning(f"  ⚠️  Thu link từ phản hồi lỗi: {e}")

        # Lướt feed cá nhân — vừa hạ nhiệt, vừa là cửa sổ dò spam, vừa chờ thông
        # báo đăng chéo về cho bước (b). KHÔNG like.
        try:
            await page.goto("https://www.facebook.com/",
                            wait_until="domcontentloaded", timeout=30000)
            await _jwait(page, 1500)
            _luot = random.randint(*cho_sau_dang_giay())
            logger.info(f"  [5/5] 📜 Lướt feed {_luot}s (không like — vừa hạ nhiệt, "
                        f"vừa chờ thông báo, vừa là cửa sổ dò spam)...")
            await _browse_and_like(page, duration_sec=_luot, max_likes=0)
        except Exception as e:
            logger.warning(f"  ⚠️  Lướt feed lỗi: {e}")

        # (b) Trang thông báo — nguồn CHÍNH, chạy SAU quãng lướt feed ở trên.
        if loai_comment:
            try:
                from thu_link import thu_tu_thong_bao, THU_LINK_MOI_NHAT
                _tb = await thu_tu_thong_bao(page, toi_da_phut=1440)
                _lay = [u for u, _ in _tb[:THU_LINK_MOI_NHAT]]
                logger.info(f"  🔗 [b] Trang thông báo: {len(_tb)} link trong 24h "
                            f"→ lấy {len(_lay)} bài mới nhất")
                _link_moi += [u for u in _lay if u not in _link_moi]
            except Exception as e:
                logger.warning(f"  ⚠️  Thu link từ trang thông báo lỗi: {e}")

        logger.info(f"  🔗 TỔNG: {len(_link_moi)} link / {_groups_posted or '?'} nhóm đã tick")
        for _u in _link_moi[:15]:
            logger.info(f"        {_u}")

        # ── Lưu vào danh sách đi comment ───────────────────────────────
        # Bài VIA đứng tên NICK CÁ NHÂN (không có vai Page). Gắn `page` = page_uid
        # của acc (scheduler truyền vào) để bộ lọc `la_chinh_chu` cho phép CHÍNH
        # acc đó (qua Page của nó) vào comment đẩy bài — giống Hybrid. Thiếu
        # loai_comment thì bỏ qua, KHÔNG đoán.
        if _link_moi and loai_comment:
            try:
                import db as _db
                _n = _db.them_comment_posts(loai_comment, _link_moi,
                                            page=page_uid, acc=acc_name)
                logger.info(f"  💾 Lưu vào danh sách comment '{loai_comment}': "
                            f"+{_n} link mới (bỏ {len(_link_moi) - _n} link trùng), "
                            f"tổng {len(_db.get_comment_posts(loai_comment))}/"
                            f"{_db.GIOI_HAN_LINK}")
            except Exception as e:
                logger.warning(f"  ⚠️  Không lưu được link: {e}")

        # Facebook gỡ bài rồi mới đổ thông báo về — quãng lướt feed ở trên vừa
        # hay là cửa sổ chờ, nên dò ngay sau đó.
        await kiem_vi_pham(page, acc_name, "phiên đăng VIA", c_user=c_user)

        logger.info(f"  ✅ Đóng Chrome")
        await ctx.close()
        return _groups_posted if add_clicked else 1


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def post_via_crosspost(
    acc_name:        str,
    search_kw:       str,
    message:         str,
    image_url:       str = "",
    first_group_uid: str = "",
    c_user:          str = "",
    loai_comment:    str = "",
    page_uid:        str = "",
    bien_the_sdt:    str = "",
) -> bool:
    """
    Hàm đồng bộ — gọi từ scheduler (chạy trong thread).

    `bien_the_sdt`: có số thì DÁN SỐ ĐT vào góc mỗi ảnh (dùng chung mkt_anh với
    Marketplace); rỗng = giữ ảnh gốc.

    Args:
        acc_name:        Tên acc VD "Ngô Quang Hùng"
        search_kw:       Từ khóa tìm nhóm VD "Homestay Times City"
        message:         Nội dung bài đăng
        image_url:       Link ảnh Drive (để trống = không ảnh)
        first_group_uid: UID nhóm để mở composer
        c_user:          c_user của acc (dùng khi có nhiều acc trùng tên)
        loai_comment:    mảng để lưu link thu được vào danh sách đi comment
                         (để trống = không thu link)
        page_uid:        Page của acc — gắn vào link để `la_chinh_chu` cho phép
                         acc đó vào comment đẩy bài

    Returns:
        Số nhóm đã đăng nếu thành công, False nếu thất bại
    """
    if not first_group_uid:
        logger.error("❌ Thiếu first_group_uid — không biết mở composer ở nhóm nào")
        raise LoiBuoc("Dòng lịch thiếu UID nhóm đầu")

    local_photos = []
    temp_dir     = None

    if image_url:
        try:
            from storage import prepare_images_for_post as smart_download, cleanup_temp
            logger.info(f"  📥 Download ảnh...")
            local_photos, temp_dir = smart_download(image_url)
            logger.info(f"  → {len(local_photos)} ảnh đã tải")
            # Biến thể ảnh: dán số ĐT vào góc (nếu bật ở cài đặt Gen) — đăng nhóm.
            if bien_the_sdt:
                import mkt_anh
                local_photos, temp_dir = mkt_anh.dan_sdt_neu_can(
                    local_photos, temp_dir, bien_the_sdt)
                logger.info(f"  🏷️  Đã dán số ĐT lên ảnh ({bien_the_sdt})")
        except Exception as e:
            logger.warning(f"  ⚠️  Không download/biến thể được ảnh: {e}")

    try:
        ok = asyncio.run(_run_crosspost(
            acc_name=acc_name,
            first_group_uid=first_group_uid,
            search_kw=search_kw,
            message=message,
            local_photos=local_photos,
            c_user=c_user,
            loai_comment=loai_comment,
            page_uid=page_uid,
        ))
        return ok
    except CookieDeadError:
        raise
    except Exception as e:
        # Ném tiếp — xem ghi chú ở `page_via_poster.post_page_via`.
        logger.error(f"❌ [{acc_name}] Lỗi Via: {e}")
        raise
    finally:
        if temp_dir:
            try:
                from storage import cleanup_temp
                cleanup_temp(temp_dir)
            except Exception:
                pass
