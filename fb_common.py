"""
================================================================================
fb_common.py — Helper Playwright dùng chung cho các poster
================================================================================
via_poster.py (Mode Via) và page_via_poster.py (Mode Hybrid / tường Page) chia
nhau cùng một bộ thao tác nền: tìm profile Chrome, chờ có jitter, đóng popup
"Anonymous post", dán nội dung qua clipboard, xem story, scroll feed.

Trước đây 7 hàm này được copy nguyên vào cả hai file. Khi Facebook đổi giao
diện thì phải sửa cùng một selector ở hai chỗ — và thực tế chúng đã bắt đầu
trôi khác nhau. Gom về đây để chỉ còn một nơi phải sửa.

User-Agent cũng để ở đây vì cả hai poster đều cần khai báo giống nhau.
================================================================================
"""

import os
import asyncio
import random

from utils import logger, jitter_ms

# ── User-Agent Chrome 124 ─────────────────────────────────────────────────────
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def browser_launch_kwargs(headless: bool) -> dict:
    """
    Tham số khởi chạy Chromium cho phiên nuôi nick — GIỮ GIỐNG HỆT cấu hình
    của poster (via_poster / page_via_poster) để hành vi đồng nhất một chỗ.

    Chỉ thêm đúng MỘT cờ so với bản gốc: --disable-gpu. Nó ép Chromium vẽ bằng
    phần mềm (SwiftShader) → sửa lỗi renderer sập khi headless trên Windows.
    TUYỆT ĐỐI KHÔNG kèm --disable-software-rasterizer: cờ đó tắt luôn phần vẽ
    dự phòng, khiến không còn gì để render → sập nặng hơn (lỗi cũ đã gây ra).
    """
    return dict(
        headless=headless,
        slow_mo=120,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--start-maximized",
            "--disable-notifications",
            "--disable-gpu",
        ],
        user_agent=UA,
        viewport={"width": 1920, "height": 1080},
        no_viewport=True,
    )


def find_profile_dir(acc_name: str, c_user: str = "") -> str:
    """
    Trả về thư mục Chrome profile cho acc.
    Luôn dùng format {name}_{c_user} để đảm bảo mỗi acc một profile riêng,
    kể cả khi nhiều acc có cùng tên.
    """
    root       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
    exact_name = acc_name.replace(" ", "_")
    folder     = f"{exact_name}_{c_user}" if c_user else exact_name
    path       = os.path.join(root, folder)
    os.makedirs(path, exist_ok=True)
    return path


# Thư mục cache của Chrome — xoá được mà KHÔNG mất đăng nhập.
# Phiên đăng nhập nằm ở Default/Network/Cookies, trạng thái ứng dụng nằm ở
# Local Storage / IndexedDB — không thư mục nào trong danh sách này đụng tới.
# (Đã kiểm chứng thực tế: xoá 5,1GB cache, mọi phiên sau đó vẫn login bình thường.)
CACHE_DIRS = (
    "Cache", "Code Cache", "GPUCache", "ShaderCache", "GrShaderCache",
    "GraphiteDawnCache", "DawnWebGPUCache", "DawnGraphiteCache",
    "Service Worker/CacheStorage", "Service Worker/ScriptCache",
)


def _dung_luong_mb(p: str) -> float:
    tong = 0
    for goc, _thu_muc, files in os.walk(p):
        for f in files:
            try:
                tong += os.path.getsize(os.path.join(goc, f))
            except OSError:
                pass
    return tong / 1024 / 1024


def don_cache_profile(profile_dir: str, nguong_mb: float = 200) -> float:
    """
    Xoá cache trình duyệt của MỘT profile. Trả về số MB đã giải phóng.

    CHỈ gọi khi profile đó KHÔNG có Chrome nào đang mở (ngay sau ctx.close()),
    vì xoá lúc trình duyệt đang chạy có thể làm hỏng profile.

    `nguong_mb`: dưới mức này thì bỏ qua, khỏi tốn I/O mỗi phiên. Cache mọc
    vài trăm MB mỗi ngày nên để 200MB là dọn thưa mà vẫn không phình.
    """
    import shutil
    if not profile_dir or not os.path.isdir(profile_dir):
        return 0.0

    ung_vien = []
    for goc in (profile_dir, os.path.join(profile_dir, "Default")):
        for ten in CACHE_DIRS:
            d = os.path.join(goc, *ten.split("/"))
            if os.path.isdir(d):
                ung_vien.append(d)
    if not ung_vien:
        return 0.0

    tong = sum(_dung_luong_mb(d) for d in ung_vien)
    if tong < nguong_mb:
        return 0.0

    da_xoa = 0.0
    for d in ung_vien:
        mb = _dung_luong_mb(d)
        try:
            shutil.rmtree(d, ignore_errors=True)
            da_xoa += mb
        except OSError:
            pass          # file bị khoá → bỏ qua, lần sau dọn tiếp

    if da_xoa >= 1:
        logger.info(f"  🧹 Dọn cache '{os.path.basename(profile_dir)}': "
                    f"giải phóng {da_xoa:.0f} MB")
    return da_xoa


def _thu_muc_profiles() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")


def loc_profile_tu_cmdline(text: str, goc_profiles: str) -> set:
    """
    Rút các --user-data-dir trong text, CHỈ giữ đường dẫn nằm trong thư mục
    profiles/ của dự án.

    Máy còn nhiều ứng dụng khác cũng chạy Chromium kèm --user-data-dir (Zalo,
    Edge WebView, trình duyệt cá nhân) — tính cả vào thì số liệu sai lệch.
    """
    import re
    goc = os.path.normcase(os.path.abspath(goc_profiles))
    ra = set()
    for m in re.finditer(r'--user-data-dir=(?:"([^"]+)"|(\S+))', text or ""):
        d = (m.group(1) or m.group(2) or "").strip().strip('"')
        if not d:
            continue
        try:
            full = os.path.normcase(os.path.abspath(d))
        except Exception:
            continue
        if full.startswith(goc):
            ra.add(full)
    return ra


def _profile_dang_mo() -> set:
    """
    Tập thư mục profile ĐANG được trình duyệt mở, đọc từ --user-data-dir trên
    dòng lệnh. Chromium không để lại file khoá nào trong profile nên đây là
    cách nhận biết đáng tin duy nhất.
    """
    import sys, subprocess, re
    if sys.platform != "win32":
        return set()
    # PHẢI ép UTF-8 cả hai đầu: mặc định subprocess giải mã theo bảng mã hệ
    # thống (cp1252) làm hỏng dấu tiếng Việt trong đường dẫn — "Huỳnh_Như" ra
    # "Hu?nh_Nh?" nên so khớp trượt, và bộ quét sẽ dọn nhầm profile ĐANG CHẠY.
    ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
          "Get-CimInstance Win32_Process | "
          "Where-Object { $_.CommandLine -like '*--user-data-dir=*' } | "
          "ForEach-Object { $_.CommandLine }")
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, timeout=25,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        r_stdout = (r.stdout or b"").decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"  ⚠️  Không dò được profile đang mở: {e}")
        return set()

    return loc_profile_tu_cmdline(r_stdout, _thu_muc_profiles())


def don_cache_tat_ca(nguong_mb: float = 200) -> float:
    """
    Quét MỌI profile, dọn cache những cái KHÔNG có trình duyệt nào đang mở.

    Cần thêm bước này bên cạnh việc dọn sau mỗi phiên: profile của acc đã ngừng
    dùng (không đăng, không nuôi) thì chẳng phiên nào chạm tới, cache cũ nằm lại
    mãi. Bỏ qua profile đang mở để không làm hỏng phiên đang chạy.
    """
    goc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
    if not os.path.isdir(goc):
        return 0.0

    dang_mo = _profile_dang_mo()
    tong = 0.0
    for ten in sorted(os.listdir(goc)):
        p = os.path.join(goc, ten)
        if not os.path.isdir(p):
            continue
        if os.path.normcase(os.path.abspath(p)) in dang_mo:
            continue                      # đang mở → tuyệt đối không đụng
        tong += don_cache_profile(p, nguong_mb)

    if tong >= 1:
        logger.info(f"🧹 Quét dọn cache: giải phóng {tong:.0f} MB "
                    f"(bỏ qua {len(dang_mo)} profile đang mở)")
    return tong


async def human_delay(min_ms: int = 800, max_ms: int = 2000):
    await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)


async def jwait(page, base_ms: int, pct: float = 0.3):
    """Chờ base_ms nhưng dao động ±pct (mặc định ±30%) — tránh nhịp cố định."""
    await page.wait_for_timeout(jitter_ms(base_ms, pct))


async def dismiss_anon_dialog(page, wait_ms: int = 0) -> bool:
    """
    Đóng popup 'Anonymous post' / 'Bài viết ẩn danh' nếu xuất hiện.
    wait_ms > 0: chủ động chờ tối đa wait_ms ms để dialog xuất hiện.
    """
    from playwright.async_api import TimeoutError as PWTimeout
    selectors = [
        "div[role='dialog']:has-text('Anonymous') div[role='button']:has-text('Got it')",
        "div[role='dialog']:has-text('ẩn danh') div[role='button']:has-text('Hiểu rồi')",
        "div[role='dialog']:has-text('ẩn danh') div[role='button']:has-text('OK')",
        "div[role='button']:has-text('Got it')",
        "div[role='button']:has-text('Hiểu rồi')",
    ]
    if wait_ms > 0:
        for sel in selectors:
            try:
                btn = await page.wait_for_selector(sel, timeout=wait_ms, state="visible")
                if btn:
                    await btn.click()
                    await asyncio.sleep(1.0)
                    logger.info("    ℹ️  Dismiss 'Anonymous post'")
                    return True
            except PWTimeout:
                continue
            except Exception:
                continue
    else:
        for sel in selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(0.8)
                    logger.info("    ℹ️  Dismiss 'Anonymous post'")
                    return True
            except Exception:
                continue
    return False


async def clipboard_paste(page, ctx, text: str):
    """Ghi text vào clipboard rồi Ctrl+V."""
    try:
        await ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        await page.evaluate(
            "async (t) => { await navigator.clipboard.writeText(t); }", text
        )
    except Exception:
        await page.evaluate(
            """(t) => {
                const el = Object.assign(document.createElement('textarea'),
                    {value: t, style: 'position:fixed;opacity:0'});
                document.body.appendChild(el);
                el.focus(); el.select();
                document.execCommand('copy');
                document.body.removeChild(el);
            }""",
            text,
        )
    await page.keyboard.press("Control+v")
    await asyncio.sleep(0.6)


async def view_stories(page, duration_sec: int = None):
    """
    Click vào story đầu tiên trong newsfeed, xem duration_sec giây rồi đóng.
    Bỏ qua nếu không tìm thấy story (không raise lỗi).
    """
    from playwright.async_api import TimeoutError as PWTimeout
    if duration_sec is None:
        duration_sec = random.randint(15, 20)
    logger.info(f"    📖 Xem story ~{duration_sec}s...")
    try:
        story_el = await page.evaluate_handle("""() => {
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href || '';
                if (!href.includes('/stories/')) continue;
                if (href.includes('create') || href.includes('compose') || href.includes('add')) continue;
                const txt = (a.textContent || '').trim().toLowerCase();
                if (txt.includes('tạo tin') || txt.includes('create')) continue;
                if (!a.querySelector('image,img,svg')) continue;
                return a;
            }
            return null;
        }""")
        story_elem = story_el.as_element()
        if story_elem:
            await story_elem.click()
            await page.wait_for_timeout(duration_sec * 1000)
            for csel in ["[aria-label='Đóng']", "[aria-label='Close']"]:
                try:
                    btn = await page.wait_for_selector(csel, timeout=2000, state="visible")
                    if btn:
                        await btn.click()
                        break
                except PWTimeout:
                    continue
            await page.keyboard.press("Escape")
            await jwait(page, 1500)
            logger.info(f"    ✅ Đã xem story")
        else:
            logger.info(f"    ⏭️  Không tìm thấy story — bỏ qua")
    except Exception:
        logger.info(f"    ⏭️  Story: bỏ qua")


async def browse_and_like(page, duration_sec: int, max_likes: int = 1):
    """
    Scroll feed trang hiện tại trong duration_sec giây, like tối đa max_likes bài.
    Dùng JS evaluate để tránh click overlay.
    """
    liked   = 0
    elapsed = 0.0
    if max_likes > 0:
        logger.info(f"    📜 Scroll + like {duration_sec}s (max {max_likes} like)...")
    else:
        logger.info(f"    📜 Scroll {duration_sec}s (không like)...")

    while elapsed < duration_sec:
        px = random.randint(300, 600)
        await page.evaluate(f"window.scrollBy(0, {px})")
        wait = random.uniform(1.5, 3.5)
        await page.wait_for_timeout(int(wait * 1000))
        elapsed += wait

        if liked >= max_likes:
            continue

        # Xác suất 15% mỗi lần scroll mới thử like — thưa, tự nhiên hơn
        if random.random() > 0.15:
            continue

        try:
            like_btn = await page.evaluate_handle("""() => {
                const allDivs = document.querySelectorAll('div[aria-label]');
                const candidates = [];
                for (const el of allDivs) {
                    const label = (el.getAttribute('aria-label') || '').trim();
                    if (label !== 'Thích' && label !== 'Like') continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.top >= 0 && rect.bottom <= window.innerHeight &&
                        rect.width > 0 && rect.height > 0) {
                        candidates.push({el, top: rect.top});
                    }
                }
                if (candidates.length === 0) return null;
                candidates.sort((a, b) => a.top - b.top);
                return candidates[0].el;
            }""")
            like_el = like_btn.as_element()
            if like_el:
                await page.evaluate("el => el.scrollIntoView({block:'center'})", like_el)
                await page.wait_for_timeout(300)
                await page.evaluate("el => el.click()", like_el)
                liked += 1
                logger.info(f"    👍 Like #{liked}")
                await page.wait_for_timeout(random.randint(800, 1500))
        except Exception:
            pass

    logger.info(f"    ✅ Browse xong — liked {liked} bài")
