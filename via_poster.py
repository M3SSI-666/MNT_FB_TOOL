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
  6. Scroll 15-30s → đóng Chrome (không like — trang cá nhân)

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
from utils import logger, jitter_ms, CookieDeadError, LoiBuoc
from fb_common import (kiem_vi_pham, chua_dang_nhap, find_profile_dir, dong_dialog_canh_bao, cho_composer_dong,
                       bat_dau_canh_dialog, dismiss_anon_dialog, dong_hop_cookie, browser_launch_kwargs,
                       human_delay, jwait, clipboard_paste,
                       view_stories, browse_and_like)

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
# cả hai. Thực tế đã trôi: bản `_view_stories` ở đây chờ bằng
# `page.wait_for_timeout(1500)` còn bản kia dùng `_jwait(page, 1500)` — lệch đúng
# một dòng, đủ để hai nick hành xử khác nhau mà không ai biết.
_human_delay     = human_delay
_jwait           = jwait
_clipboard_paste = clipboard_paste
_view_stories    = view_stories
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
        logger.info(f"  [1/6] 🔐 Login acc cá nhân...")
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
        # BƯỚC 2 — Xem story 15-20s
        # ════════════════════════════════════════════════════════════════
        logger.info(f"  [2/6] 📖 Xem story...")
        await _view_stories(page, duration_sec=random.randint(15, 20))

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 3 — Scroll newsfeed 20-30s (không like — trang cá nhân)
        # ════════════════════════════════════════════════════════════════
        scroll_sec = random.randint(20, 30)
        logger.info(f"  [3/6] 📜 Scroll newsfeed {scroll_sec}s...")
        await _browse_and_like(page, duration_sec=scroll_sec, max_likes=0)

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 4 — Chui vào nhóm đầu, paste nội dung + upload ảnh
        # ════════════════════════════════════════════════════════════════
        group_url = f"https://www.facebook.com/groups/{first_group_uid}/"
        logger.info(f"  [4/6] 📌 Vào nhóm: {group_url}")
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
            await ctx.close()
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
                        wait_ms = max(6000, len(local_photos) * 3500)
                        logger.info(f"    ⏳ Chờ upload {wait_ms // 1000}s...")
                        await _human_delay(wait_ms, wait_ms + 2000)
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
        logger.info(f"  [5/6] ➕ Thêm nhóm → tìm \"{search_kw}\" → tick → Đăng...")

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

            # Gõ từ khóa
            await _human_delay(1000, 1500)
            search_input = None
            for sel in [
                "input[placeholder*='Tìm kiếm nhóm']",
                "input[placeholder*='Search groups']",
                "div[role='dialog'] input:not([role='combobox'])",
                "div[role='dialog'] input[type='text']",
                "div[role='dialog'] input",
            ]:
                try:
                    el = await page.wait_for_selector(sel, timeout=4000, state="visible")
                    if el:
                        tag = await el.evaluate("e => e.tagName")
                        if tag.lower() == "input":
                            search_input = el
                            break
                except PWTimeout:
                    continue
            if not search_input:
                logger.error(f"  ❌ Không tìm thấy ô tìm kiếm nhóm!")
                await ctx.close()
                raise LoiBuoc("Không thấy ô tìm nhóm ở bước đăng chéo")

            await search_input.click()
            await _human_delay(400, 600)
            await search_input.fill(search_kw)
            await _human_delay(2500, 3500)


            # Tick từng nhóm — dùng search_input.evaluate() để traverse từ đúng element
            total_checked = 0
            for scroll_round in range(8):
                rows = await search_input.evaluate("""(si) => {
                    // Đi lên từ đúng search input (trong panel Thêm nhóm)
                    // tìm container chứa danh sách nhóm
                    let container = si.parentElement;
                    for (let i = 0; i < 15 && container && container !== document.body; i++) {
                        const cbs = container.querySelectorAll(
                            '[role="checkbox"], input[type="checkbox"]'
                        );
                        if (cbs.length > 0) break;
                        container = container.parentElement;
                    }
                    if (!container || container === document.body) return [];

                    // Tìm tất cả item chưa chọn
                    let candidates = Array.from(
                        container.querySelectorAll('[role="checkbox"][aria-checked="false"]')
                    );
                    if (candidates.length === 0)
                        candidates = Array.from(
                            container.querySelectorAll('input[type="checkbox"]:not(:checked)')
                        );

                    // Với mỗi checkbox, tìm row cha có kích thước thực để click
                    const result = [];
                    const seen = new Set();
                    for (const cb of candidates) {
                        let row = cb.parentElement;
                        for (let i = 0; i < 10 && row && row !== container; i++) {
                            const r = row.getBoundingClientRect();
                            if (r.width > 100 && r.height > 30 &&
                                r.top >= 0 && r.bottom <= window.innerHeight) {
                                if (!seen.has(row)) {
                                    seen.add(row);
                                    result.push({
                                        x: r.left + r.width / 2,
                                        y: r.top + r.height / 2
                                    });
                                }
                                break;
                            }
                            row = row.parentElement;
                        }
                    }
                    return result;
                }""")

                if rows:
                    for pos in rows:
                        await page.mouse.click(pos["x"], pos["y"])
                        await asyncio.sleep(0.35)
                    total_checked += len(rows)
                    logger.info(f"    ✓ Round {scroll_round+1}: tick {len(rows)} nhóm (tổng: {total_checked})")
                else:
                    logger.info(f"    ⚠️  Round {scroll_round+1}: không tìm được row nào — dừng")
                    break

                await page.mouse.wheel(0, 400)
                await asyncio.sleep(0.5)

                remaining = await search_input.evaluate("""(si) => {
                    let container = si.parentElement;
                    for (let i = 0; i < 15 && container && container !== document.body; i++) {
                        if (container.querySelectorAll('[role="checkbox"], input[type="checkbox"]').length > 0) break;
                        container = container.parentElement;
                    }
                    if (!container || container === document.body) return 0;
                    return container.querySelectorAll('[role="checkbox"][aria-checked="false"]').length
                        + container.querySelectorAll('input[type="checkbox"]:not(:checked)').length;
                }""")
                if remaining == 0:
                    break

            logger.info(f"    → Đã tick {total_checked} nhóm")
            _groups_posted = total_checked

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
        else:
            logger.warning(f"  ⚠️  Không chắc kết quả — kiểm tra thủ công trên Facebook")

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 6 — Scroll 15-30s rồi đóng Chrome (không like — trang cá nhân)
        # ════════════════════════════════════════════════════════════════
        cooldown_sec = random.randint(15, 30)
        logger.info(f"  [6/6] 📜 Cooldown {cooldown_sec}s...")
        await _browse_and_like(page, duration_sec=cooldown_sec, max_likes=0)

        # Facebook gỡ bài rồi mới đổ thông báo về — cooldown ở trên vừa hay là
        # quãng chờ cần thiết, nên dò ngay sau đó.
        await kiem_vi_pham(page, acc_name, "phiên đăng VIA")

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
) -> bool:
    """
    Hàm đồng bộ — gọi từ scheduler (chạy trong thread).

    Args:
        acc_name:        Tên acc VD "Ngô Quang Hùng"
        search_kw:       Từ khóa tìm nhóm VD "Homestay Times City"
        message:         Nội dung bài đăng
        image_url:       Link ảnh Drive (để trống = không ảnh)
        first_group_uid: UID nhóm để mở composer
        c_user:          c_user của acc (dùng khi có nhiều acc trùng tên)

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
            local_photos, temp_dir = smart_download(image_url, seed_key=acc_name)
            logger.info(f"  → {len(local_photos)} ảnh đã tải")
        except Exception as e:
            logger.warning(f"  ⚠️  Không download được ảnh: {e}")

    try:
        ok = asyncio.run(_run_crosspost(
            acc_name=acc_name,
            first_group_uid=first_group_uid,
            search_kw=search_kw,
            message=message,
            local_photos=local_photos,
            c_user=c_user,
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
