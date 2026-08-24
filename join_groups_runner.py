"""
join_groups_runner.py — Acc cá nhân → switch sang Page → tham gia tất cả nhóm trong UID Nhóm.

Playwright tự động:
  1. Login acc cá nhân
  2. Switch sang Page actor
  3. Duyệt từng nhóm trong db (ma_nhom = '')
  4. Nếu chưa tham gia → click "Tham gia nhóm"
  5. Ghi kết quả vào db
"""

import os, sys, asyncio, random, json, re, sqlite3, time
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cookie_exporter import load_cookie
from utils import logger
from fb_common import chua_dang_nhap
from db import _conn

# Đọc runtime — không dùng config.py để env var có hiệu lực ngay
_HEADLESS       = os.environ.get("HEADLESS",           "true").lower() == "true"
from db import JOIN_NGHI_MOI_MAC_DINH, JOIN_NGHI_BO_QUA_MAC_DINH
_DELAY_NEW_SEC  = int(os.environ.get("JOIN_DELAY_NEW",  str(JOIN_NGHI_MOI_MAC_DINH)))
_DELAY_SKIP_SEC = int(os.environ.get("JOIN_DELAY_SKIP", str(JOIN_NGHI_BO_QUA_MAC_DINH)))

# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _human_delay(min_ms=600, max_ms=1800):
    await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)


def _c_user_cua(acc_name: str) -> str:
    """c_user của acc — cần để tìm ĐÚNG profile và dựng cookie mới nhất từ DB."""
    with _conn() as con:
        r = con.execute("SELECT c_user FROM accounts WHERE ten_acc=? LIMIT 1",
                        (acc_name,)).fetchone()
    return (r[0] if r else "") or ""


def _find_profile_dir(acc_name: str, c_user: str = "") -> str:
    """
    Dùng chung hàm của fb_common thay vì giữ bản sao riêng.

    Bản sao cũ ở đây chỉ dò `Xuan_Khoa` (khớp chính xác / bỏ dấu / không phân
    biệt hoa thường), KHÔNG biết dạng `{Tên}_{c_user}` mà poster thật sự tạo ra.
    Kết quả: nó tạo mới một thư mục TRẮNG rồi chạy phiên tham gia nhóm trên đó —
    mất phiên đăng nhập bền, dễ vấp checkpoint hơn hẳn. Đúng lỗi mà
    fb_common.find_profile_dir đã được vá và có assertion canh riêng.
    """
    from fb_common import find_profile_dir
    return find_profile_dir(acc_name, c_user or _c_user_cua(acc_name))


async def _switch_to_page(page, ctx, page_uid: str):
    from playwright.async_api import TimeoutError as PWTimeout
    logger.info(f"  [Switch] Goto Page {page_uid}")
    await page.goto(f"https://www.facebook.com/profile.php?id={page_uid}",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    for sel in ['div[role="button"]:has-text("Dùng Trang")',
                'div[role="button"]:has-text("Use Page")']:
        try:
            btn = await page.wait_for_selector(sel, timeout=1500, state="visible")
            if btn: await btn.click(); await page.wait_for_timeout(1000); break
        except (PWTimeout, Exception): pass

    try:
        btn = await page.wait_for_selector('div[role="button"]:has-text("Chuyển ngay")',
                                            timeout=2000, state="visible")
        if btn: await btn.click(); await page.wait_for_timeout(1500)
    except (PWTimeout, Exception): pass

    for sel in ['div[role="dialog"] div[role="button"]:has-text("Chuyển")',
                'div[role="button"]:has-text("Chuyển")',
                'div[role="dialog"] div[role="button"]:has-text("Switch")']:
        try:
            btn = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if btn:
                await btn.click(); await page.wait_for_timeout(2000)
                logger.info("  [Switch] ✅ Switched to Page")
                break
        except (PWTimeout, Exception): pass

    await ctx.add_cookies([{
        "name": "i_user", "value": page_uid,
        "domain": ".facebook.com", "path": "/",
        "httpOnly": False, "secure": True, "sameSite": "None",
    }])


# ─── Core: join 1 nhóm ────────────────────────────────────────────────────────

# Quét toàn bộ nút 1 lần, phân loại trạng thái nhóm. Thứ tự ưu tiên:
# đã tham gia > đang chờ duyệt > có nút tham gia (chưa join).
_DETECT_STATE_JS = """() => {
    const btns = [...document.querySelectorAll('[role="button"], a[role="button"]')];
    const texts = btns.map(b => (b.textContent||'').trim().toLowerCase()).filter(Boolean);
    // 1) Đã là thành viên — nút "Đã tham gia" / "Joined"
    if (texts.some(t => t.includes('đã tham gia') || t === 'joined'))
        return 'da_join';
    // 2) Đang chờ duyệt
    if (texts.some(t => t.includes('huỷ yêu cầu') || t.includes('hủy yêu cầu')
                     || t.includes('cancel request') || t.includes('pending')
                     || t.includes('đang chờ') || t.includes('requested')))
        return 'cho_duyet';
    // 3) Có nút tham gia (chưa join) — loại trừ "Mời"
    if (texts.some(t => (t.includes('tham gia nhóm') || t === 'tham gia'
                          || t.includes('join group'))
                     && !t.includes('mời') && !t.includes('invite')))
        return 'need_join';
    return '';
}"""

_JOIN_SELS = [
    'div[role="button"]:has-text("Tham gia nhóm")',
    'div[role="button"]:has-text("Join Group")',
    'div[role="button"]:has-text("Join group")',
    'a[role="button"]:has-text("Tham gia nhóm")',
    '[data-testid="group-join-button"]',
]


# Bóc mọi id/slug nhóm từ link trên trang. Nhận cả UID số lẫn slug chữ vì tag
# đang có cả hai dạng (54/58 là số, còn lại như "lucnhare24h").
_JS_BOC_NHOM = r"""() => {
  const ra = new Set();
  for (const a of document.querySelectorAll('a[href*="/groups/"]')) {
    const m = (a.href || '').match(/\/groups\/([0-9A-Za-z._-]+)/);
    if (!m) continue;
    const g = m[1];
    if (['joins','feed','discover','create','search','browse'].includes(g)) continue;
    ra.add(g);
  }
  return [...ra];
}"""


def _dinh_danh_nhom(uid: str, link_url: str) -> set:
    """
    Mọi cách gọi tên một nhóm, để đối chiếu không phụ thuộc dạng lưu.

    Tag UID có cả uid số lẫn slug chữ, mà link Facebook trả về có thể dùng dạng
    còn lại — so một dạng thôi là bỏ sót.
    """
    ra = {(uid or "").strip()}
    m = re.search(r"/groups/([0-9A-Za-z._-]+)", link_url or "")
    if m:
        ra.add(m.group(1))
    return {x for x in ra if x}


async def _lay_nhom_da_vao(page) -> set:
    """
    Đọc danh sách nhóm Page đang đứng tên ĐÃ tham gia, từ trang `groups/joins`.

    Gọi SAU khi đã chuyển sang Page — trang này trả về nhóm của chủ thể đang
    hoạt động, nên đọc trước lúc switch sẽ ra nhóm của acc cá nhân.

    Dò thật ba trang: `groups/joins` cho 40 định danh (38 khớp tag), còn
    `groups/` và `groups/feed` chỉ ra 22 — chúng là thanh bên newsfeed, không
    phải danh sách đầy đủ.

    Cuộn tới khi số nhóm thôi tăng, tối đa `so_cuon` lượt, chứ không cuộn cứng
    một số lần: Page ít nhóm thì xong sớm, Page nhiều nhóm mới cuộn lâu.
    """
    await page.goto("https://www.facebook.com/groups/joins/",
                    wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(4000)

    da_thay, yen = set(), 0
    for _ in range(20):
        try:
            da_thay |= set(await page.evaluate(_JS_BOC_NHOM))
        except Exception:
            pass
        truoc = len(da_thay)
        await page.mouse.wheel(0, 2500)
        await page.wait_for_timeout(1200)
        try:
            da_thay |= set(await page.evaluate(_JS_BOC_NHOM))
        except Exception:
            pass
        yen = yen + 1 if len(da_thay) == truoc else 0
        if yen >= 3:                      # ba lượt liền không thêm được gì
            break

    logger.info(f"  📋 Page đã tham gia {len(da_thay)} nhóm (đọc từ groups/joins)")
    return da_thay


async def _join_one_group(page, uid: str, ten_nhom: str, link_url: str) -> str:
    """
    Returns: "moi_join" | "da_join" | "cho_duyet" | "loi"
    """
    from playwright.async_api import TimeoutError as PWTimeout

    url = link_url if link_url and link_url.startswith("http") \
          else f"https://www.facebook.com/groups/{uid}/"

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _human_delay(1500, 2500)
    except Exception as e:
        logger.error(f"  ❌ Không load được nhóm '{ten_nhom}': {e}")
        return "loi"

    # ── Xác minh nhanh: quét nút 1 lần, lặp tối đa ~6s tới khi có tín hiệu ──
    # "Đã tham gia" ⇒ xác nhận ngay, không chờ (trước đây tốn ~20s/nhóm).
    state = ""
    for _ in range(6):
        try:
            state = await page.evaluate(_DETECT_STATE_JS)
        except Exception:
            state = ""
        if state:
            break
        await page.wait_for_timeout(1000)

    if state == "da_join":
        logger.info(f"  ⏭️  Đã là thành viên: {ten_nhom}")
        return "da_join"
    if state == "cho_duyet":
        logger.info(f"  ⏳ Đang chờ duyệt: {ten_nhom}")
        return "cho_duyet"
    if state != "need_join":
        # Không thấy nút tham gia sau ~6s → coi như đã là thành viên (tránh click sai)
        logger.info(f"  ⏭️  Không thấy nút tham gia — coi như đã là thành viên: {ten_nhom}")
        return "da_join"

    # ── need_join: click nút "Tham gia nhóm" (nút đã có sẵn, query nhanh) ──
    clicked = False
    for sel in _JOIN_SELS:
        try:
            btn = await page.query_selector(sel)
            if not btn or not await btn.is_visible():
                continue
            txt = ((await btn.text_content()) or "").strip().lower()
            if "mời" in txt or "invite" in txt:
                continue
            await btn.hover(); await _human_delay(400, 700)
            await btn.click()
            await _human_delay(2000, 3000)
            logger.info(f"  ✅ Đã click 'Tham gia nhóm': {ten_nhom}")
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        logger.info(f"  ⏭️  Đã là thành viên: {ten_nhom}")
        return "da_join"

    # Xử lý dialog xác nhận nếu có
    for sel in ['div[role="dialog"] div[role="button"]:has-text("Tham gia")',
                'div[role="dialog"] div[role="button"]:has-text("Join")',
                'div[role="dialog"] div[role="button"]:has-text("Xác nhận")',
                'div[role="dialog"] div[role="button"]:has-text("Confirm")']:
        try:
            btn = await page.wait_for_selector(sel, timeout=3000, state="visible")
            if btn: await btn.click(); await _human_delay(1500, 2500)
        except PWTimeout:
            pass

    return "moi_join"


# ─── Main flow ────────────────────────────────────────────────────────────────

async def _run_join(schedule_id: int, acc_name: str, page_uid: str):
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    # Lấy danh sách nhóm (ma_nhom = '' → từ sheet UID Nhóm)
    with _conn() as con:
        rows = con.execute(
            "SELECT uid, ten_nhom, link_url FROM uid_groups WHERE ma_nhom='' OR ma_nhom IS NULL ORDER BY id"
        ).fetchall()

    groups = [{"uid": r[0], "ten_nhom": r[1], "link_url": r[2]} for r in rows]
    total  = len(groups)
    logger.info(f"  📋 Tổng {total} nhóm cần kiểm tra")

    def _update_status(status, **kwargs):
        with _conn() as con:
            sets = ", ".join(f"{k}=?" for k in kwargs)
            vals = list(kwargs.values()) + [schedule_id]
            con.execute(f"UPDATE join_schedules SET trang_thai=?, {sets} WHERE id=?",
                        [status] + vals)

    _update_status("Đang chạy", tong_nhom=total)

    profile_dir = _find_profile_dir(acc_name)
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    stats   = {"moi_join": 0, "da_join": 0, "cho_duyet": 0, "loi": 0}
    results = []

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir, headless=_HEADLESS, slow_mo=100,
            args=["--disable-blink-features=AutomationControlled","--no-sandbox",
                  "--start-maximized","--disable-notifications"],
            user_agent=UA, viewport={"width":1920,"height":1080}, no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Inject cookies
        # Kèm c_user để load_cookie dựng từ DB — cột xs trong DB là nguồn
        # mới nhất, file JSON có thể cũ hơn.
        cookie_data = load_cookie(acc_name, _c_user_cua(acc_name))
        if cookie_data:
            cookies = []
            for n, k in [("c_user","c_user"),("xs","xs")]:
                v = cookie_data.get(k,"")
                if v: cookies.append({"name":n,"value":v,"domain":".facebook.com",
                                       "path":"/","httpOnly":True,"secure":True,"sameSite":"None"})
            for n in ["datr","sb","fr","wd"]:
                v = cookie_data.get(n,"")
                if v: cookies.append({"name":n,"value":v,"domain":".facebook.com",
                                       "path":"/","httpOnly":False,"secure":True,"sameSite":"None"})
            await ctx.add_cookies(cookies)

        # Login check
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await _human_delay(2000, 3000)
        if await chua_dang_nhap(page):
            logger.error(f"  ❌ Cookie hết hạn!")
            _update_status("Lỗi - cookie hết hạn")
            await ctx.close()
            return

        # Switch sang Page
        logger.info(f"  🔄 Switch sang Page {page_uid}...")
        await _switch_to_page(page, ctx, page_uid)

        # ── Bỏ qua nhóm Page ĐÃ tham gia, không mở từng trang để hỏi lại ──
        # Đo thật trên Page 'Bồ Công Anh': phiên cũ mở 30 trang nhóm trong 10
        # phút chỉ để phát hiện cả 30 đều "đã là thành viên" — ~20 giây mỗi nhóm
        # đổi lấy không gì. Đọc danh sách một lần rồi lọc thì 30 lượt truy cập đó
        # biến mất; ít thao tác tự động hơn cũng đỡ bị soi hơn.
        #
        # Danh sách THIẾU thì vô hại: nhóm không có trong đó vẫn được vào thăm
        # như cũ. Chiều nguy hiểm là nhóm CHƯA vào mà lại nằm trong danh sách —
        # không xảy ra được, vì nguồn của nó chính là "nhóm bạn đã tham gia".
        try:
            da_vao = await _lay_nhom_da_vao(page)
        except Exception as e:
            logger.warning(f"  ⚠️  Không đọc được danh sách nhóm đã tham gia: {e}")
            da_vao = set()

        if da_vao:
            con_lai, bo_qua = [], 0
            for g in groups:
                if _dinh_danh_nhom(g["uid"], g["link_url"]) & da_vao:
                    bo_qua += 1
                else:
                    con_lai.append(g)
            stats["da_join"] += bo_qua
            results += [{"uid": g["uid"], "ten": g["ten_nhom"], "result": "da_join"}
                        for g in groups if g not in con_lai]
            logger.info(f"  ⏭️  Bỏ qua {bo_qua} nhóm Page đã tham gia — "
                        f"còn {len(con_lai)}/{total} nhóm cần vào")
            groups = con_lai

        # Duyệt từng nhóm
        for i, g in enumerate(groups, 1):
            logger.info(f"\n  [{i}/{total}] {g['ten_nhom'] or g['uid']}")
            result = await _join_one_group(page, g["uid"], g["ten_nhom"], g["link_url"])
            stats[result] += 1
            results.append({"uid": g["uid"], "ten": g["ten_nhom"], "result": result})

            # Update progress mỗi 5 nhóm
            if i % 5 == 0:
                _update_status("Đang chạy",
                               moi_join=stats["moi_join"],
                               da_join=stats["da_join"],
                               loi=stats["loi"])

            if result == "moi_join":
                jitter = random.randint(0, max(1, _DELAY_NEW_SEC // 6))
                wait   = _DELAY_NEW_SEC + jitter
                logger.info(f"  ⏱️  Mới join → chờ {wait}s...")
            else:
                wait = _DELAY_SKIP_SEC
                logger.info(f"  ⏩ Bỏ qua → chờ {wait}s...")
            await asyncio.sleep(wait)

        await ctx.close()

    ket_qua = json.dumps(results, ensure_ascii=False)
    _update_status("Hoàn thành",
                   tong_nhom=total,
                   moi_join=stats["moi_join"],
                   da_join=stats["da_join"],
                   loi=stats["loi"],
                   ket_qua=ket_qua)

    logger.info(f"\n  ✅ HOÀN THÀNH:")
    logger.info(f"     Mới tham gia: {stats['moi_join']}")
    logger.info(f"     Đã join rồi:  {stats['da_join']}")
    logger.info(f"     Chờ duyệt:    {stats['cho_duyet']}")
    logger.info(f"     Lỗi:          {stats['loi']}")


def run_join_schedule(schedule_id: int, acc_name: str, page_uid: str):
    """Sync wrapper — gọi từ scheduler."""
    asyncio.run(_run_join(schedule_id, acc_name, page_uid))
