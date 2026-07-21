"""
================================================================================
page_via_poster.py  —  Mode "PageVia"
================================================================================
Kết hợp tốt nhất của Via + Page:
  - Acc cá nhân đăng nhập → switch sang Page actor (không bị nhận diện robot)
  - Toàn bộ thao tác qua Playwright UI (không HTTP API)
  - Tìm nhóm bằng từ khóa + tick cross-post → đăng 1 lần đến nhiều nhóm

LUỒNG:
  1. Login acc cá nhân (goto facebook.com, kiểm tra cookie)
  2. Xem story 15-20s
  3. Scroll newsfeed 20-30s (không like — đang ở trang cá nhân)
  4. Chui vào Page → click "Chuyển" → chiếm quyền Page actor
  5. Chui vào nhóm đầu → mở composer → paste nội dung → upload ảnh
  6. Thêm nhóm → gõ từ khóa → tick đủ nhóm → Xong → Đăng
  7. Scroll 15-30s + like tối đa 1 bài (đang là Page) → đóng Chrome

DÙNG STANDALONE:
  python page_via_poster.py          # Chạy với TEST_* params ở __main__

DÙNG TỪ CODE KHÁC:
  from page_via_poster import post_page_via
  ok = post_page_via(
      acc_name       = "Ngô Quang Hùng",
      page_uid       = "61583907272784",
      first_group_uid= "311375961636397",
      search_kw      = "Times City",
      message        = "Nội dung bài đăng...",
      image_url      = "https://drive.google.com/drive/folders/...",
  )
================================================================================
"""

import os
import sys
import time
import asyncio
import random

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cookie_exporter import load_cookie
from storage import prepare_images_for_post as smart_download, cleanup_temp
from config import HEADLESS
from utils import logger, jitter_ms, CookieDeadError

# Helper dùng chung với poster còn lại — xem fb_common.py.
# Giữ tên có gạch dưới để không phải sửa toàn bộ chỗ gọi trong file này.
from fb_common import (
    UA as _UA,
    find_profile_dir     as _find_profile_dir,
    human_delay          as _human_delay,
    jwait                as _jwait,
    dismiss_anon_dialog  as _dismiss_anon_dialog,
    clipboard_paste      as _clipboard_paste,
    view_stories         as _view_stories,
    browse_and_like      as _browse_and_like,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _scroll_feed(page, duration_sec: int = 30):
    """Scroll newsfeed tự nhiên — mô phỏng người đang đọc bài."""
    logger.info(f"    📜 Scroll {duration_sec}s...")
    end_at = time.time() + duration_sec
    while time.time() < end_at:
        await page.mouse.wheel(0, random.randint(300, 800))
        await asyncio.sleep(random.uniform(1.5, 4.0))


# ─────────────────────────────────────────────────────────────────────────────
# Bước 3: Switch sang Page actor
# ─────────────────────────────────────────────────────────────────────────────

async def _switch_to_page(page, ctx, page_uid: str) -> bool:
    """
    Chuyển browser context từ acc cá nhân sang Page actor.
    Tối ưu tốc độ: không chờ networkidle, timeout ngắn, không dismiss popup nhiều lần.
    """
    from playwright.async_api import TimeoutError as PWTimeout

    # a) Vào trang Page — chỉ chờ domcontentloaded
    t0 = time.time()
    logger.info(f"    [Switch] Goto Page profile.php?id={page_uid}")
    await page.goto(
        f"https://www.facebook.com/profile.php?id={page_uid}",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    await _jwait(page, 3000)   # ~2–4s rồi nhấn
    logger.info(f"    [Switch] Page load {time.time()-t0:.1f}s")

    # b) Dismiss popup "Dùng Trang" nếu có (thử nhanh, không chờ lâu)
    for sel in [
        'div[role="dialog"] div[role="button"]:has-text("Dùng Trang")',
        'div[role="button"]:has-text("Dùng Trang")',
        'div[role="button"]:has-text("Use Page")',
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=1000, state="visible")
            if btn:
                await btn.click()
                await _jwait(page, 1000)
                logger.info("    [Switch] Dismissed popup 'Dùng Trang'")
                break
        except (PWTimeout, Exception):
            continue

    # c) Click "Chuyển ngay" nếu xuất hiện
    try:
        btn = await page.wait_for_selector(
            'div[role="button"]:has-text("Chuyển ngay")',
            timeout=2000,
            state="visible",
        )
        if btn:
            await btn.click()
            await _jwait(page, 1500)
            logger.info("    [Switch] Clicked 'Chuyển ngay'")
    except (PWTimeout, Exception):
        pass

    # d) Click "Chuyển" trong popup xác nhận
    switched = False
    for sel in [
        'div[role="dialog"] div[role="button"]:has-text("Chuyển")',
        'div[role="dialog"] div[role="button"]:has-text("Switch")',
        'div[role="button"]:has-text("Chuyển")',
        'div[role="button"]:has-text("Switch")',
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if btn:
                label = (await btn.inner_text()).strip()
                await btn.click()
                await _jwait(page, 1500)
                logger.info(f"    [Switch] Clicked '{label}' ✅")
                switched = True
                break
        except (PWTimeout, Exception):
            continue

    if not switched:
        logger.info("    [Switch] Không tìm thấy nút Chuyển — giả định đã ở Page context")

    # e) Inject i_user + chờ 3s trước khi vào nhóm
    await ctx.add_cookies([{
        "name":     "i_user",
        "value":    page_uid,
        "domain":   ".facebook.com",
        "path":     "/",
        "httpOnly": False,
        "secure":   True,
        "sameSite": "None",
    }])
    await _jwait(page, 3000)
    logger.info(f"    [Switch] ✅ i_user={page_uid} injected | url={page.url[:70]}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Core async: toàn bộ flow
# ─────────────────────────────────────────────────────────────────────────────

async def _run_page_via(
    acc_name:        str,
    page_uid:        str,
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
            headless=HEADLESS,
            slow_mo=120,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--start-maximized",
                "--disable-notifications",
            ],
            user_agent=_UA,
            viewport={"width": 1920, "height": 1080},
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # ── Inject cookies cá nhân ────────────────────────────────────────────
        cookie_data = load_cookie(acc_name, c_user)
        if not cookie_data:
            logger.error(f"❌ [{acc_name}] Không có cookie!")
            await ctx.close()
            return False

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
        logger.info(f"  [1/7] 🔐 Login acc cá nhân...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await _human_delay(2000, 3000)

        if "login" in page.url or "checkpoint" in page.url:
            logger.error(f"  ❌ [{acc_name}] Cookie hết hạn!")
            await ctx.close()
            raise CookieDeadError(acc_name)

        logger.info(f"  ✅ Login OK")

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 2 — Xem story 15-20s
        # ════════════════════════════════════════════════════════════════
        logger.info(f"  [2/7] 📖 Xem story...")
        await _view_stories(page, duration_sec=random.randint(15, 20))

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 3 — Scroll newsfeed 20-30s (không like — đang ở trang cá nhân)
        # ════════════════════════════════════════════════════════════════
        scroll_sec = random.randint(20, 30)
        logger.info(f"  [3/7] 📜 Scroll newsfeed {scroll_sec}s...")
        await _browse_and_like(page, duration_sec=scroll_sec, max_likes=0)

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 4 — Chui vào Page, chiếm quyền Page
        # ════════════════════════════════════════════════════════════════
        logger.info(f"  [4/7] 🔄 Switch → Page {page_uid}...")
        await _switch_to_page(page, ctx, page_uid)

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 5 — Chui vào nhóm đầu, paste nội dung + upload ảnh
        # ════════════════════════════════════════════════════════════════
        group_url = f"https://www.facebook.com/groups/{first_group_uid}/"
        logger.info(f"  [5/7] 📌 Vào nhóm: {group_url}")
        await page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
        await _human_delay(3000, 5000)

        if "login" in page.url or "checkpoint" in page.url:
            logger.error(f"  ❌ Bị redirect về login sau switch!")
            await ctx.close()
            raise CookieDeadError(acc_name)

        # Mở composer
        logger.info(f"    📝 Mở composer...")
        opened = False
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
        if not opened:
            logger.error(f"  ❌ Không mở được composer!")
            await ctx.close()
            return False

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
            return False

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
        # BƯỚC 6 — Thêm nhóm → gõ từ khóa → tick → Đăng
        # ════════════════════════════════════════════════════════════════
        logger.info(f"  [6/7] ➕ Thêm nhóm → tìm \"{search_kw}\" → tick → Đăng...")

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
            # Bỏ qua bước thêm nhóm, nhảy thẳng xuống bước Đăng

        if add_clicked:
            # Chờ tối đa 3s để "Anonymous post" dialog xuất hiện rồi dismiss
            await _dismiss_anon_dialog(page, wait_ms=3000)

            # Gõ từ khóa
            await _human_delay(1000, 1500)
            search_input = None
            for sel in [
                "input[placeholder*='Tìm kiếm nhóm']",
                "input[placeholder*='Search groups']",
                "input[placeholder*='Tìm kiếm']",
                "input[placeholder*='Search']",
                "div[role='dialog'] input",
                "input[type='text']",
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
                return False

            await search_input.click()
            await _human_delay(400, 600)
            await search_input.fill(search_kw)
            await _human_delay(2500, 3500)


            # Tick từng nhóm: tìm checkbox trực tiếp rồi click row chứa nó
            total_checked = 0
            for scroll_round in range(8):
                rows = await page.evaluate("""() => {
                    const cbs = [
                        ...document.querySelectorAll('[role="checkbox"][aria-checked="false"]'),
                        ...Array.from(document.querySelectorAll('input[type="checkbox"]:not(:checked)'))
                              .filter(i => !document.querySelector('[role="checkbox"][aria-checked="false"]')),
                    ];

                    const result = [];
                    const seen = new Set();
                    for (const cb of cbs) {
                        const row = cb.closest('li') || cb.parentElement;
                        if (!row || seen.has(row)) continue;
                        seen.add(row);

                        const r = row.getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) continue;
                        if (r.top < 0 || r.bottom > window.innerHeight) continue;

                        result.push({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
                    }
                    return result;
                }""")

                if rows:
                    for pos in rows:
                        await page.mouse.click(pos["x"], pos["y"])
                        await asyncio.sleep(0.35)
                    total_checked += len(rows)
                    logger.info(f"    ✓ Round {scroll_round+1}: tick {len(rows)} nhóm (tổng: {total_checked})")

                await page.mouse.wheel(0, 400)
                await asyncio.sleep(0.5)

                remaining = await page.evaluate("""() =>
                    document.querySelectorAll('[role="checkbox"][aria-checked="false"]').length
                    || document.querySelectorAll('input[type="checkbox"]:not(:checked)').length
                """)
                if remaining == 0 and total_checked > 0:
                    break

            # Đếm số nhóm thực tế đã được tick (không dùng total_checked vì có thể đếm lặp qua nhiều scroll round)
            actual_checked = await page.evaluate("""() =>
                document.querySelectorAll('[role="checkbox"][aria-checked="true"]').length
                + document.querySelectorAll('input[type="checkbox"]:checked').length
            """)
            _groups_posted = min(actual_checked if actual_checked > 0 else total_checked, 10)
            logger.info(f"    → Đã tick {_groups_posted} nhóm")

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
                return False

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
            return False

        # Chờ dialog đóng
        try:
            await page.wait_for_selector("div[role='dialog']", state="detached", timeout=30000)
            logger.info(f"  ✅ [{acc_name}] ĐĂNG THÀNH CÔNG!")
        except PWTimeout:
            await asyncio.sleep(9)
            if not await page.query_selector("div[role='dialog']"):
                logger.info(f"  ✅ [{acc_name}] ĐĂNG THÀNH CÔNG!")
            else:
                logger.warning(f"  ⚠️  Không chắc kết quả — kiểm tra thủ công trên Facebook")

        # ════════════════════════════════════════════════════════════════
        # BƯỚC 7 — Scroll 15-30s + like tối đa 1 bài (đang là Page) rồi đóng Chrome
        # ════════════════════════════════════════════════════════════════
        cooldown_sec = random.randint(15, 30)
        logger.info(f"  [7/7] 📜 Cooldown {cooldown_sec}s + like...")
        await _browse_and_like(page, duration_sec=cooldown_sec, max_likes=1)

        logger.info(f"  ✅ Đóng Chrome")
        await ctx.close()
        # Trả về số nhóm đã đăng (0 nếu không có nút Thêm nhóm = đăng 1 nhóm)
        return _groups_posted if add_clicked else 1


# ─────────────────────────────────────────────────────────────────────────────
# Core async: đăng lên TƯỜNG PAGE (không cross-post nhóm)
# ─────────────────────────────────────────────────────────────────────────────

async def _run_page_wall(
    acc_name:     str,
    page_uid:     str,
    message:      str,
    local_photos: list,
    c_user:       str = "",
) -> bool:
    """
    Acc cá nhân → switch sang Page actor → đăng thẳng lên tường Page.
    Toàn bộ thao tác qua Playwright UI (thay cho HTTP API cũ).
    """
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    profile_dir = _find_profile_dir(acc_name, c_user)
    logger.info(f"  🗂️  Profile: {profile_dir}")

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=HEADLESS,
            slow_mo=120,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--start-maximized",
                "--disable-notifications",
            ],
            user_agent=_UA,
            viewport={"width": 1920, "height": 1080},
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # ── Inject cookies cá nhân ────────────────────────────────────────────
        cookie_data = load_cookie(acc_name, c_user)
        if not cookie_data:
            logger.error(f"❌ [{acc_name}] Không có cookie!")
            await ctx.close()
            return False

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

        # ── BƯỚC 1 — Login acc cá nhân ────────────────────────────────────────
        logger.info(f"  [1/5] 🔐 Login acc cá nhân...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await _human_delay(2000, 3000)
        if "login" in page.url or "checkpoint" in page.url:
            logger.error(f"  ❌ [{acc_name}] Cookie hết hạn!")
            await ctx.close()
            raise CookieDeadError(acc_name)
        logger.info(f"  ✅ Login OK")

        # ── BƯỚC 2 — Warm-up nhẹ (story + scroll, không like — trang cá nhân) ─
        logger.info(f"  [2/5] 📖 Xem story + scroll newsfeed...")
        await _view_stories(page, duration_sec=random.randint(10, 15))
        await _browse_and_like(page, duration_sec=random.randint(15, 25), max_likes=0)

        # ── BƯỚC 3 — Switch sang Page actor ───────────────────────────────────
        logger.info(f"  [3/5] 🔄 Switch → Page {page_uid}...")
        await _switch_to_page(page, ctx, page_uid)

        # Về lại trang Page để chắc chắn composer là của tường Page
        await page.goto(
            f"https://www.facebook.com/profile.php?id={page_uid}",
            wait_until="domcontentloaded", timeout=30000,
        )
        await _human_delay(3000, 5000)
        if "login" in page.url or "checkpoint" in page.url:
            logger.error(f"  ❌ Bị redirect về login sau switch!")
            await ctx.close()
            raise CookieDeadError(acc_name)

        # ── BƯỚC 4 — Mở composer tường Page → paste → upload ──────────────────
        logger.info(f"  [4/5] 📝 Mở composer tường Page...")
        opened = False
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
        if not opened:
            logger.error(f"  ❌ Không mở được composer!")
            await ctx.close()
            return False

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
            return False

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

        # ── BƯỚC 5 — Click "Tiếp" → "Đăng" → xử lý popup WhatsApp ─────────────
        logger.info(f"  [5/5] 🚀 Tiếp → Đăng...")

        # 5a. Click "Tiếp" (composer tường Page có thêm bước này trước khi Đăng)
        await _human_delay(1500, 2500)
        for sel in [
            "div[role='dialog'] div[aria-label='Tiếp']",
            "div[role='dialog'] div[role='button']:has-text('Tiếp')",
            "div[role='dialog'] div[aria-label='Next']",
            "div[role='dialog'] div[role='button']:has-text('Next')",
        ]:
            try:
                btn = await page.wait_for_selector(sel, timeout=4000, state="visible")
                if btn:
                    await btn.hover()
                    await _human_delay(400, 700)
                    await btn.click()
                    await _human_delay(2000, 3000)
                    logger.info(f"    ➡️  Đã click 'Tiếp'")
                    break
            except PWTimeout:
                continue

        # 5b. Click "Đăng" trong dialog "Cài đặt bài viết"
        await _human_delay(1000, 1800)
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
                    logger.info(f"    ✅ Đã click 'Đăng'")
                    break
            except PWTimeout:
                continue
        if not posted:
            logger.error(f"  ❌ Không tìm thấy nút Đăng!")
            await ctx.close()
            return False

        # 5c. Popup "Tạo điều kiện để dễ liên hệ..." (WhatsApp) → click "Lúc khác"
        await _human_delay(1500, 2500)
        for sel in [
            "div[role='dialog'] div[role='button']:has-text('Lúc khác')",
            "div[role='dialog'] div[role='button']:has-text('Để sau')",
            "div[role='dialog'] div[role='button']:has-text('Not now')",
            "div[role='dialog'] div[role='button']:has-text('Maybe later')",
        ]:
            try:
                btn = await page.wait_for_selector(sel, timeout=4000, state="visible")
                if btn:
                    await btn.click()
                    await _human_delay(1500, 2500)
                    logger.info(f"    ⏭️  Đã bỏ qua popup WhatsApp ('Lúc khác')")
                    break
            except PWTimeout:
                continue

        # Chờ dialog đóng = đăng xong
        try:
            await page.wait_for_selector("div[role='dialog']", state="detached", timeout=30000)
            logger.info(f"  ✅ [{acc_name}] ĐĂNG TƯỜNG PAGE THÀNH CÔNG!")
        except PWTimeout:
            await asyncio.sleep(9)
            if not await page.query_selector("div[role='dialog']"):
                logger.info(f"  ✅ [{acc_name}] ĐĂNG TƯỜNG PAGE THÀNH CÔNG!")
            else:
                logger.warning(f"  ⚠️  Không chắc kết quả — kiểm tra thủ công trên Facebook")
                await ctx.close()
                return False

        # Cooldown nhẹ rồi đóng — đang là Page, like tối đa 1 bài
        await _browse_and_like(page, duration_sec=random.randint(10, 20), max_likes=1)
        logger.info(f"  ✅ Đóng Chrome")
        await ctx.close()
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def post_page_wall(
    acc_name:  str,
    page_uid:  str,
    message:   str,
    image_url: str = "",
    c_user:    str = "",
) -> bool:
    """
    Hàm sync — đăng lên TƯỜNG PAGE bằng Playwright (thay HTTP API).

    Args:
        acc_name:  Tên acc cá nhân
        page_uid:  UID Page sẽ switch sang để đăng
        message:   Nội dung bài đăng
        image_url: Link folder ảnh (bỏ trống = text-only)
        c_user:    c_user của acc (khi nhiều acc trùng tên)

    Returns:
        True nếu đăng thành công, False nếu lỗi.
    """
    local_photos = []
    temp_dir     = None

    if image_url:
        try:
            logger.info(f"  📥 Download ảnh...")
            local_photos, temp_dir = smart_download(image_url)
            logger.info(f"  → {len(local_photos)} ảnh đã tải")
        except Exception as e:
            logger.warning(f"  ⚠️  Không download được ảnh: {e}")

    try:
        return asyncio.run(_run_page_wall(
            acc_name=acc_name,
            page_uid=page_uid,
            message=message,
            local_photos=local_photos,
            c_user=c_user,
        ))
    except CookieDeadError:
        raise
    except Exception as e:
        logger.error(f"❌ [{acc_name}] Lỗi đăng tường Page: {e}")
        return False
    finally:
        if temp_dir:
            try:
                cleanup_temp(temp_dir)
            except Exception:
                pass


def post_page_via(
    acc_name:        str,
    page_uid:        str,
    first_group_uid: str,
    search_kw:       str,
    message:         str,
    image_url:       str = "",
    c_user:          str = "",
) -> bool:
    """
    Hàm sync — gọi từ scheduler hoặc script độc lập.

    Args:
        acc_name:        Tên acc cá nhân VD "Ngô Quang Hùng"
        page_uid:        UID Page sẽ switch sang VD "61583907272784"
        first_group_uid: UID nhóm để mở composer VD "311375961636397"
        search_kw:       Từ khóa tìm nhóm trong dialog cross-post
        message:         Nội dung bài đăng
        image_url:       Link Google Drive folder ảnh (bỏ trống = text-only)
        c_user:          c_user của acc (dùng khi có nhiều acc trùng tên)

    Returns:
        True nếu thành công, False nếu có lỗi
    """
    local_photos = []
    temp_dir     = None

    if image_url:
        try:
            logger.info(f"  📥 Download ảnh...")
            local_photos, temp_dir = smart_download(image_url)
            logger.info(f"  → {len(local_photos)} ảnh đã tải")
        except Exception as e:
            logger.warning(f"  ⚠️  Không download được ảnh: {e}")

    if not first_group_uid:
        logger.error("❌ Thiếu first_group_uid — không biết mở composer ở nhóm nào")
        return False

    try:
        ok = asyncio.run(_run_page_via(
            acc_name=acc_name,
            page_uid=page_uid,
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
        logger.error(f"❌ [{acc_name}] Lỗi PageVia: {e}")
        return False
    finally:
        if temp_dir:
            try:
                cleanup_temp(temp_dir)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Test chạy trực tiếp: python page_via_poster.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import random as _random
    from sheets import get_page_by_name, get_uid_groups_by_code, _get_sheet

    # ── Tham số test ─────────────────────────────────────────────────────────
    ACC_NAME   = "Nguyễn Quỳnh Như"      # Tên acc đúng như trong sheet Accounts
    PAGE_NAME  = "Tùng Núi"             # Tên Page đúng như trong sheet Pages
    MA_NHOM    = "TIME1"                # Mã nhóm để lấy first_group_uid
    SEARCH_KW  = "Cư dân Times City"     # Từ khóa tìm nhóm trong dialog cross-post

    print()
    print("=" * 60)
    print("  PAGE VIA POSTER — TEST")
    print(f"  Acc:      {ACC_NAME}")
    print(f"  Page:     {PAGE_NAME}")
    print(f"  Mã nhóm:  {MA_NHOM}")
    print(f"  Từ khóa:  {SEARCH_KW}")
    print(f"  HEADLESS: {HEADLESS}")
    print("=" * 60)

    # ── 1. Lấy Page UID ──────────────────────────────────────────────────────
    page_info = get_page_by_name(PAGE_NAME)
    if not page_info:
        print(f"\n❌ Không tìm thấy Page '{PAGE_NAME}' trong sheet Pages!")
        sys.exit(1)
    page_uid = str(page_info.get("Page UID", "")).strip()
    if not page_uid:
        print(f"\n❌ Page '{PAGE_NAME}' không có UID trong sheet!")
        sys.exit(1)
    print(f"\n  Page UID: {page_uid}")

    # ── 2. Lấy first_group_uid từ mã nhóm ────────────────────────────────────
    groups = get_uid_groups_by_code(MA_NHOM)
    if not groups:
        print(f"\n❌ Không tìm thấy nhóm nào với mã '{MA_NHOM}'!")
        sys.exit(1)
    first_group_uid = groups[0]["UID"]
    print(f"  Nhóm UID: {first_group_uid} ({len(groups)} nhóm trong mã {MA_NHOM})")

    # ── 3. Lấy content thuê ngẫu nhiên ───────────────────────────────────────
    try:
        content_sheet = _get_sheet("Content thuê")
        content_rows  = content_sheet.get_all_records()
        pool = [
            r for r in content_rows
            if str(r.get("Sử dụng", "")).strip() == "Có"
            and str(r.get("Nội dung", "")).strip()
        ]
        if not pool:
            print("\n❌ Sheet 'Content thuê' không có dòng nào 'Sử dụng = Có'!")
            sys.exit(1)
        chosen    = _random.choice(pool)
        message   = str(chosen.get("Nội dung", "")).strip()
        image_url = str(chosen.get("Link ảnh", "")).strip()
        ma_ct     = str(chosen.get("Mã content", "")).strip()
        print(f"  Content:  {ma_ct} — {message[:60]}...")
        print(f"  Link ảnh: {image_url[:60] if image_url else '(không có)'}")
    except Exception as e:
        print(f"\n❌ Lỗi đọc sheet 'Content thuê': {e}")
        sys.exit(1)

    print()

    # ── 4. Chạy ──────────────────────────────────────────────────────────────
    result = post_page_via(
        acc_name=ACC_NAME,
        page_uid=page_uid,
        first_group_uid=first_group_uid,
        search_kw=SEARCH_KW,
        message=message,
        image_url=image_url,
    )

    print()
    print("✅ Thành công!" if result else "❌ Thất bại!")
