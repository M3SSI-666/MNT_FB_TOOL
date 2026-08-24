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
from config import PROFILES_DIR

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
    root       = str(PROFILES_DIR)
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
    return str(PROFILES_DIR)


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
    goc = str(PROFILES_DIR)
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


async def chua_dang_nhap(page) -> bool:
    """
    True nếu trang đang ở trạng thái CHƯA đăng nhập (cookie chết / bị checkpoint).

    Dò Ô MẬT KHẨU trên DOM, không so chuỗi trong URL. Bản cũ dùng
    `"login" in page.url` và phép đó VÔ DỤNG ở đúng hai chỗ nó được gọi nhiều
    nhất — đã đo bằng trình duyệt sạch, không tiêm cookie:

        facebook.com/                 URL không đổi  → ❌ không bắt được
        facebook.com/groups/<slug>/   URL không đổi  → ❌ không bắt được
        facebook.com/notifications    → login.php    → ✅ bắt được

    Hai trang đầu XEM ĐƯỢC khi chưa đăng nhập nên Facebook giữ nguyên URL, chỉ
    đổi nội dung. Cả hai đều hiện ô mật khẩu, nên dò DOM bắt được cả ba.

    Hậu quả thật của lỗ này: cookie chết đi qua mọi chốt kiểm, phiên chạy tiếp
    tới bước mở composer rồi báo "Không mở được composer" — bị tính là lỗi đăng
    bài. Acc 'Anh Nguyen The' vì thế bị đánh "Hỏng 16/20 phiên" trong khi nó chỉ
    cần thay `xs`; đổi cookie xong đăng lại 9 nhóm ngay lần đầu.

    Nặng nhất là `nuoi_nick`: nó chỉ có ĐÚNG MỘT chốt kiểm và chốt đó nằm sau
    trang gốc, nên nick chết cookie chạy trọn phiên nuôi trên trang landing —
    lướt không, like không — rồi báo `✅ nuôi xong`. Thành công giả, im lặng.
    """
    async def _mot_lan() -> bool:
        try:
            if await page.evaluate(
                    "() => !!document.querySelector('input[type=\"password\"], "
                    "input[name=\"pass\"], input[name=\"email\"]')"):
                return True
        except Exception:
            pass    # trang chưa dựng xong / bị điều hướng giữa lúc đọc
        url = page.url or ""
        return "login" in url or "checkpoint" in url

    if not await _mot_lan():
        return False

    # Lần đầu bảo "chưa đăng nhập" thì CHỜ RỒI HỎI LẠI, chưa kết luận vội.
    #
    # Vì sao: lịch tham gia nhóm mở tới 5 Chromium cùng lúc trên một máy. Trang
    # tải chậm, `domcontentloaded` bắn sớm, và lúc đó Facebook có thể chưa dựng
    # xong phần của người đã đăng nhập — dò ngay thì thấy giống hệt trang chưa
    # đăng nhập. Log ngày 25/08 có 8 dòng "Cookie hết hạn" trong khi CẢ 14 acc
    # đều còn cookie đủ trường, và cùng những acc đó chạy phiên khác thì xong
    # bình thường.
    #
    # Cookie chết thật thì hỏi lại vẫn chết — chỉ tốn thêm vài giây, và chỉ tốn
    # trong đúng trường hợp sắp báo lỗi. Đổi lại, không còn tắt nhầm acc còn sống.
    try:
        await asyncio.sleep(4)
        await page.reload(wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
    except Exception:
        pass
    return await _mot_lan()


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


# Dialog "Sự việc" / "Trạng thái tài khoản" — Facebook bật lên khi vừa gỡ nội
# dung của nick. Nó gây HAI hỏng hóc, không chỉ một:
#   1. Nổi đè lên newfeed → click vào ô soạn bài trúng nền mờ → "Không mở được
#      composer".
#   2. Mang role=dialog → bước xác minh "chờ dialog đóng" sau khi bấm Đăng
#      không bao giờ thấy nó biến mất → báo thất bại dù bài ĐÃ lên.
# Đóng nó đi là an toàn: đây chỉ là thông báo, Facebook đã gỡ nội dung từ trước.
CANH_BAO_MOC = (
    "chúng tôi đã gỡ một số nội dung", "trạng thái tài khoản",
    "tiêu chuẩn cộng đồng",
    "we removed some of your", "account status", "community standards",
)

# Bảng thông báo cũng là role=dialog, và từng thông báo bên trong nó cũng chứa
# các cụm trên ("Chúng tôi đã gỡ nội dung ... của thành viên khỏi nhóm"). Đã bắt
# nhầm một lần thật — log 09:42:28 ngày 7/8. Loại theo tiêu đề dòng đầu.
_KHONG_PHAI_CANH_BAO = ("thông báo", "notifications")

_NUT_DONG = (
    "div[role='button'][aria-label='Đóng']",
    "div[role='button'][aria-label='Close']",
    "[aria-label='Đóng']", "[aria-label='Close']",
    # Facebook đổi nhãn theo ngữ cảnh ("Đóng thông báo", "Close dialog"...)
    "div[role='button'][aria-label*='óng']",
    "div[role='button'][aria-label*='lose']",
)


async def _tim_dialog_canh_bao(page):
    """Trả về (element, text) của dialog cảnh báo đang hiện, hoặc (None, "")."""
    try:
        dialogs = await page.query_selector_all("div[role='dialog']")
    except Exception:
        return None, ""

    for dlg in dialogs:
        try:
            if not await dlg.is_visible():
                continue
            text = (await dlg.inner_text()) or ""
        except Exception:
            continue

        thap = text.lower()
        if thap.strip().split("\n", 1)[0].strip() in _KHONG_PHAI_CANH_BAO:
            continue
        if any(m in thap for m in CANH_BAO_MOC):
            return dlg, text
    return None, ""


async def _nut_dong(dlg):
    """Nút X đang hiện trong dialog, None nếu dialog không có nút nào."""
    for sel in _NUT_DONG:
        try:
            btn = await dlg.query_selector(sel)
            if btn and await btn.is_visible():
                return btn
        except Exception:
            continue
    return None


async def _thu_dong(page, dlg, buoc: int, cho_escape: bool = True) -> None:
    """
    Đóng dialog, LEO THANG theo từng lượt — cách sau xuyên được thứ mà cách
    trước thua:
      0   bấm nút X như người thật
      1   bắn chuột thẳng vào tâm nút
      2+  gọi click bằng JS, rồi Escape

    Bắn chuột theo toạ độ KHÔNG cứu được lớp phủ: chuột vẫn trúng thứ nằm trên
    cùng tại điểm đó, tức là chính lớp phủ. Đã dựng lại đúng cảnh này trong
    Chromium và nó thua — nên mới cần bước JS phía sau.
    """
    btn = await _nut_dong(dlg)

    if btn is not None and buoc == 0:
        try:
            # timeout ngắn: có lớp phủ chặn thì bỏ qua ngay để còn thử cách
            # khác, thay vì đứng chờ hết 30s mặc định của Playwright.
            await btn.click(timeout=4000)
            return
        except Exception:
            pass

    if btn is not None and buoc <= 1:
        try:
            box = await btn.bounding_box()
            if box:
                await page.mouse.click(box["x"] + box["width"] / 2,
                                       box["y"] + box["height"] / 2)
                return
        except Exception:
            pass

    # Chốt hạ: click bằng JS bắn thẳng vào phần tử, KHÔNG dò xem cái gì đang
    # nằm trên cùng — nên xuyên qua được lớp phủ.
    if btn is not None:
        try:
            await btn.evaluate("el => el.click()")
        except Exception:
            pass

    # Escape đóng được dialog nhưng đóng CẢ thứ khác đang mở. Gọi giữa lúc
    # trình xem story đang chạy thì nó tắt luôn story — nên bên gọi phải tắt
    # bước này ở những chỗ có cửa sổ mình muốn giữ.
    if cho_escape:
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass


async def kiem_vi_pham(page, acc_name: str, sau_viec: str = "phiên") -> bool:
    """Sau mỗi phiên đăng bài / comment: xem Facebook có vừa gỡ gì không.

    Trả True nếu VỪA dính spam (có vụ mới so với lần đo trước).

    Đặt ở đây để cả bốn đường — đăng Hybrid, đăng VIA, đăng tường Page, và đi
    comment — dùng chung MỘT bản. Trước đây chỉ đường Hybrid có kiểm, ba đường
    kia không; acc bị gỡ trong phiên comment hay phiên đăng VIA thì không ai
    biết. Chép ra bốn chỗ thì sớm muộn bốn chỗ trôi khác nhau.

    HAI ĐIỀU QUAN TRỌNG, đừng rút gọn:

    1. Phải chờ vài chục giây SAU khi đăng. Facebook gỡ bài rồi mới đổ thông
       báo về, dò sớm quá chỉ thấy vụ của hôm trước.
    2. KHÔNG tin "thấy dialog = vừa dính". Dialog hiện lại y nguyên nhiều ngày
       sau đó. Phải so SỐ VỤ với lần đo trước mới biết có vụ mới.
    """
    try:
        import suc_khoe_acc as _sk
        import db as _db
        await page.goto("https://www.facebook.com/",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(random.uniform(4, 6))
        txt = await dong_dialog_canh_bao(page)
        vp = _sk.doc_vi_pham(txt)
        if not vp:
            logger.info("  ✅ Không thấy cảnh báo gỡ bài")
            return False
        moi, cu = _db.ghi_nhan_vi_pham(acc_name, vp["so"], vp["spam"])
        logger.warning(f"  ⚠️  FB đã gỡ {vp['so']} bài của '{acc_name}'"
                       f" (lần đo trước: {'chưa đo' if cu < 0 else cu})")
        if moi:
            n, moc = _db.danh_dau_spam(acc_name, f"{vp['so'] - cu} bài mới bị gỡ")
            logger.error(
                f"  🚫 '{acc_name}' DÍNH SPAM sau {sau_viec} — nghỉ đăng và "
                f"comment, {n} slot còn lại chuyển sang nuôi nick, nhử lại lúc "
                f"{moc:%H:%M}")
        return bool(moi)
    except Exception as e:
        logger.warning(f"  ⚠️  Không dò được cảnh báo spam: {e}")
        return False


async def dong_dialog_canh_bao(page, so_lan: int = 3, cho_escape: bool = True) -> str:
    """
    Đóng dialog cảnh báo vi phạm nếu đang mở. Trả về nội dung cảnh báo (rút
    gọn) để bên gọi ghi log, "" nếu không có gì.

    CHỈ đóng dialog khớp mốc cảnh báo. Ô soạn bài và hộp "Chuyển sang Trang"
    cũng là role=dialog — đóng nhầm là hỏng luôn phiên đăng.

    Bấm xong PHẢI kiểm tra lại. Bản đầu bấm rồi đi luôn nên khi cú bấm trượt
    (lớp phủ chặn, nút chưa gắn xong) log vẫn báo êm trong khi dialog còn
    nguyên trên màn hình — đúng thứ người dùng nhìn thấy.
    """
    canh_bao = ""

    for lan in range(max(1, so_lan)):
        dlg, text = await _tim_dialog_canh_bao(page)
        if dlg is None:
            if canh_bao:
                logger.info("    ✔️  Đã đóng dialog cảnh báo")
            return canh_bao

        if not canh_bao:
            # Giữ 1200 ký tự chứ không phải 110 như bản đầu. Dòng tiêu đề
            # ("Chúng tôi đã gỡ một số nội dung...") chỉ ~70 ký tự, nên cắt ở
            # 110 là vứt sạch phần THÂN — nơi chứa "Spam / Đã gỡ bài viết" và
            # nút "Xem tất cả (N)". Đó chính là dữ liệu suc_khoe_acc.doc_vi_pham
            # cần để biết acc vừa bị gỡ mấy bài.
            canh_bao = " ".join(text.split())[:1200]
            logger.warning(f"    ⚠️  FB cảnh báo nick này: {canh_bao[:110]}")

        await _thu_dong(page, dlg, buoc=lan, cho_escape=cho_escape)
        await asyncio.sleep(1.2)

    logger.error("    ❌ KHÔNG đóng được dialog cảnh báo — nó sẽ chặn thao tác kế tiếp")
    return canh_bao


async def _vong_canh(page, chu_ky: float):
    """Vòng lặp nền của bat_dau_canh_dialog — xem chú thích ở hàm đó."""
    while True:
        try:
            await asyncio.sleep(chu_ky)
            if page.is_closed():
                return

            dlg, text = await _tim_dialog_canh_bao(page)
            if dlg is None:
                continue

            btn = await _nut_dong(dlg)
            if btn is None:
                continue        # để lời gọi trực tiếp (có Escape) xử lý

            logger.warning(f"    ⚠️  FB cảnh báo (vòng canh): "
                           f"{' '.join(text.split())[:90]}")
            try:
                await btn.click(timeout=3000)
            except Exception:
                try:
                    await btn.evaluate("el => el.click()")
                except Exception:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:
            if page.is_closed():
                return


def bat_dau_canh_dialog(page, chu_ky_giay: float = 5.0):
    """
    Chạy nền suốt phiên, cứ vài giây quét và đóng dialog cảnh báo một lần.

    Cần vòng canh vì Facebook bật lại dialog này liên tục ở thời điểm không
    đoán trước được — đo thực tế: cùng một nick bị bật lại sau 110 giây. Rải
    lời gọi ở từng điểm nghi ngờ thì lần nào cũng sót một chỗ mới, và giữa hai
    điểm kiểm tra dialog vẫn nằm chình ình trên màn hình.

    Vòng canh chạy XEN KẼ với luồng chính nên bị giới hạn có chủ đích: chỉ bấm
    đúng nút X nằm bên trong dialog cảnh báo, KHÔNG bấm Escape và KHÔNG bắn
    chuột theo toạ độ. Hai thứ đó tác động ra ngoài phạm vi dialog nên có thể
    đóng nhầm ô soạn bài hoặc khung chat mà luồng chính đang mở dở. Trường hợp
    dialog không có nút X thì để các lời gọi trực tiếp lo.

    Task tự huỷ khi page đóng, bên gọi không phải dọn gì.
    """
    task = asyncio.create_task(_vong_canh(page, chu_ky_giay))
    try:
        page.once("close", lambda *_: task.cancel())
    except Exception:
        pass
    return task


# Ô soạn bài là dialog DUY NHẤT chứa vùng nhập nội dung. Bám vào đặc điểm đó
# để xác minh, thay vì "bất kỳ role=dialog nào" — vế sau dính cả dialog cảnh
# báo, hộp quyền riêng tư, popup gợi ý, và báo thất bại oan cho bài đã đăng.
COMPOSER_DIALOG = "div[role='dialog']:has(div[contenteditable='true'])"


async def cho_composer_dong(page, timeout_ms: int = 30000) -> bool:
    """Chờ ô soạn bài đóng — dấu hiệu Facebook đã nhận bài. True = đã đóng."""
    from playwright.async_api import TimeoutError as PWTimeout
    try:
        await page.wait_for_selector(COMPOSER_DIALOG, state="hidden", timeout=timeout_ms)
        return True
    except PWTimeout:
        pass
    except Exception:
        return False

    # Hết giờ chưa chắc đã hỏng: mạng chậm hoặc ảnh nặng thì composer đóng muộn.
    await asyncio.sleep(9)
    try:
        return await page.query_selector(COMPOSER_DIALOG) is None
    except Exception:
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

    # Dọn dialog cảnh báo TRƯỚC: nó đè lên newfeed nên cú bấm vào story trúng
    # nền mờ, Playwright ném lỗi và cả bước xem story bị bỏ qua.
    await dong_dialog_canh_bao(page)

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
            # Facebook hay bật dialog cảnh báo NGAY khi vừa mở trình xem story
            # và đè lên nó — dọn lần nữa, nếu không thì cả phần xem lẫn nút đóng
            # đều bấm không trúng. cho_escape=False vì Escape lúc này sẽ tắt
            # luôn story vừa mở.
            await dong_dialog_canh_bao(page, cho_escape=False)
            await page.wait_for_timeout(duration_sec * 1000)
            await dong_dialog_canh_bao(page, cho_escape=False)
            for csel in ["[aria-label='Đóng']", "[aria-label='Close']"]:
                try:
                    btn = await page.wait_for_selector(csel, timeout=2000, state="visible")
                    if btn:
                        # timeout=3000: không có nó thì cú bấm bị chặn sẽ đứng
                        # hết 30s mặc định của Playwright rồi mới chịu thua —
                        # đo được đúng 30s lãng phí khi dựng lại cảnh có lớp phủ.
                        await btn.click(timeout=3000)
                        break
                except PWTimeout:
                    continue
            await page.keyboard.press("Escape")
            await jwait(page, 1500)
            logger.info(f"    ✅ Đã xem story")
        else:
            logger.info(f"    ⏭️  Không tìm thấy story — bỏ qua")
    except Exception as e:
        # Kèm LÝ DO: bản cũ chỉ ghi "bỏ qua" nên khi dialog cảnh báo chặn mất cú
        # bấm, log trông y hệt lúc nick đó đơn giản là không có story nào.
        logger.info(f"    ⏭️  Story: bỏ qua ({type(e).__name__}: {str(e)[:80]})")


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

    # Dialog cảnh báo khoá cứng việc cuộn trang và nuốt mọi cú bấm like
    await dong_dialog_canh_bao(page)

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
