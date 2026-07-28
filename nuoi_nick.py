"""
================================================================================
nuoi_nick.py — Tính năng NUÔI NICK
================================================================================
Mục tiêu: cho các nick được tick chọn "khỏe dần theo thời gian" bằng cách xen
các phiên hoạt động giống người vào lịch, THAY CHO một số slot đăng bài.

BỐN hành động nuôi (bật/tắt riêng từng cái trong Cài đặt nuôi):
   story   — xem story
   feed    — lướt newsfeed (không like)
   like    — like dạo (số like theo cấu hình)
   message — nhắn tin vào nhóm chat nội bộ

Hai phần tách bạch:
  1. Logic thuần (test được, không cần Playwright):
       - plan_warming_conversion()  : đổi slot đăng thành slot nuôi theo CHU KỲ
       - build_warming_schedule()   : lịch cho acc CHỈ NUÔI
       - select_session_activities(): bốc TẬP CON hành động + xáo thứ tự
  2. Bộ máy chạy phiên nuôi bằng Playwright (chỉ chạy thật với FB):
       - run_warming_session()      : điểm vào cho scheduler
       - _run_warming()             : orchestrator — chạy trong ngân sách 5–8
                                      phút, mỗi hành động bọc try/except riêng.

LƯU Ý: selector nhắn tin là best-effort, CẦN chạy thử non-headless lần đầu.
Acc bị FB hạn chế nhắn tin sẽ tự bị bỏ qua, quay về lướt feed/story/like.
================================================================================
"""

import time
import asyncio
import random
from collections import defaultdict

from utils import logger, CookieDeadError
from config import HEADLESS
from cookie_exporter import load_cookie
from fb_common import (browser_launch_kwargs, find_profile_dir, human_delay,
                       jwait, view_stories, browse_and_like)


# ═══════════════════════════════════════════════════════════════
# Cài đặt (đọc từ bảng settings, có mặc định)
# ═══════════════════════════════════════════════════════════════

DEFAULTS = {
    "nuoi_session_min_sec": 300,   # phiên nuôi ngắn nhất (5 phút)
    "nuoi_session_max_sec": 480,   # phiên nuôi dài nhất (8 phút)
    "nuoi_like_count":      1,      # số like mỗi phiên (mặc định 1)
    "nuoi_msg_min":         2,      # số tin nhắn mỗi phiên: tối thiểu
    "nuoi_msg_max":         3,      # số tin nhắn mỗi phiên: tối đa
    "nuoi_msg_group_url":   "",     # link nhóm chat nội bộ
    "nuoi_msg_pool":        "",     # thư viện câu, mỗi dòng 1 câu
    # Bật/tắt từng hành động — cái nào hỏng thì tắt riêng cái đó
    "nuoi_enable_story":    1,      # xem story
    "nuoi_enable_feed":     1,      # lướt newsfeed (không like)
    "nuoi_enable_like":     1,      # like dạo
    "nuoi_enable_message":  1,      # nhắn tin nhóm nội bộ
}


def get_settings() -> dict:
    """Đọc settings với ép kiểu theo DEFAULTS (int giữ int, str giữ str)."""
    from db import get_setting
    out = {}
    for k, dv in DEFAULTS.items():
        raw = get_setting(k, "")
        if raw == "" or raw is None:
            out[k] = dv
        elif isinstance(dv, str):
            out[k] = raw
        else:
            try:
                out[k] = int(raw)
            except (TypeError, ValueError):
                out[k] = dv
    return out


# ═══════════════════════════════════════════════════════════════
# Logic thuần — xếp phiên nuôi theo CHU KỲ (KHÔNG cần Playwright, test được)
# ═══════════════════════════════════════════════════════════════

DEFAULT_INTERVAL_MIN = 150     # 2h30 — mỗi acc nuôi 1 lần mỗi chừng này phút
MIN_INTERVAL_MIN     = 20      # chặn nhập quá dày (mở trình duyệt liên tục)
MIN_GAP_MIN          = 10      # 2 phiên nuôi bất kỳ phải cách nhau ít nhất ngần này phút


def _parse_hhmm(s: str) -> int:
    h, m = map(int, str(s).strip().split(":"))
    return h * 60 + m


def _min_to_hhmm(m: int) -> str:
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def _unwrap_times(times: list) -> list:
    """
    'HH:MM' theo thứ tự thời gian → phút liên tục, cộng 24h mỗi lần qua nửa đêm.
    Cần vì lịch chạy xuyên đêm (vd 05:00 → 03:00 hôm sau) nên 02:00 phải được
    hiểu là SAU 23:00, không phải trước.
    """
    out, prev, offset = [], None, 0
    for t in times:
        v = _parse_hhmm(t)
        if prev is not None and v < prev:
            offset += 24 * 60
        prev = v
        out.append(v + offset)
    return out


def normalize_interval(value, default=DEFAULT_INTERVAL_MIN) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_INTERVAL_MIN, v) if v > 0 else default


def plan_warming_conversion(schedule: list, warm_accs: dict,
                            min_gap: int = None) -> int:
    """
    Với acc BẬT nuôi: cứ mỗi `chu kỳ` phút thì MỘT slot đăng của acc đó bị đổi
    thành phiên nuôi (nuôi chen thẳng vào lịch đăng, không thêm slot mới nên
    lịch không dày lên và một slot chỉ đăng HOẶC nuôi → không đụng nhau).

    schedule  : list row đã gen, thứ tự theo thời gian; mỗi row có 'ten_acc','gio_dang'.
    warm_accs : {ten_acc: chu_kỳ_phút} — CHỈ chứa acc đang bật nuôi.
    Sửa `schedule` tại chỗ, trả về số slot đã chuyển.

    Hai lớp TÁCH GIÃN các phiên nuôi ra khỏi nhau:
      1. Lệch pha — acc thứ k dời phiên nuôi đầu tiên đi k/n chu kỳ. Không có
         bước này thì các acc cùng chu kỳ, cùng bắt đầu một giờ sẽ nuôi dính
         chùm nhau suốt ngày (05:03/05:06/05:09 → 07:39/07:42/07:45...).
      2. Giãn cách tối thiểu toàn cục — slot nào quá sát một phiên nuôi đã đặt
         (của bất kỳ acc nào) thì bỏ, lùi sang slot kế tiếp của chính acc đó.
         Cần vì các acc chu kỳ khác nhau vẫn trôi vào gần nhau sau vài vòng.
    """
    if min_gap is None:
        min_gap = MIN_GAP_MIN

    by_acc = defaultdict(list)
    for i, row in enumerate(schedule):
        row.setdefault("hoat_dong", "dang_bai")
        by_acc[row["ten_acc"]].append(i)

    accs = [a for a in by_acc if a in warm_accs]
    n    = max(1, len(accs))

    converted   = 0
    placed: list = []            # mốc phút của MỌI phiên nuôi đã đặt
    for k, acc in enumerate(accs):
        idxs     = by_acc[acc]
        interval = normalize_interval(warm_accs[acc])
        mins     = _unwrap_times([schedule[i]["gio_dang"] for i in idxs])
        # Lớp 1 — lệch pha: acc thứ k chờ thêm k/n chu kỳ mới nuôi lần đầu.
        first_at = mins[0] + round(k * interval / n)
        last     = None
        for pos, i in enumerate(idxs):
            t = mins[pos]
            if last is None:
                if t < first_at:
                    continue
            elif (t - last) < interval:
                continue
            # Lớp 2 — giãn cách toàn cục: sát quá thì thử slot sau của acc này.
            if any(abs(t - u) < min_gap for u in placed):
                continue
            schedule[i]["hoat_dong"] = "nuoi_nick"
            last = t
            placed.append(t)
            converted += 1
    return converted


def build_warming_schedule(accs: list, start_str: str = "07:00",
                           end_str: str = "23:00", min_gap: int = MIN_GAP_MIN) -> list:
    """
    Lịch cho acc CHỈ NUÔI (cột Loại Đăng để trống): không đăng gì, cứ mỗi
    `chu kỳ` phút vào một phiên nuôi.

    accs: [{"ten": str, "interval": phút}, ...]

    Hai lớp chống trùng giờ:
      1. Lệch pha ban đầu — mỗi acc bắt đầu ở một mốc khác nhau.
      2. Giãn cách tối thiểu — quét theo thứ tự thời gian, phiên nào rơi quá sát
         phiên trước thì đẩy lùi. Cần vì các acc có chu kỳ KHÁC nhau vẫn sẽ trôi
         vào trùng nhau sau vài vòng (vd 150' và 120' gặp nhau ở 12:00).
    """
    start = _parse_hhmm(start_str)
    end   = _parse_hhmm(end_str)
    if end <= start:
        end += 24 * 60

    rows = []
    n = max(1, len(accs))
    for i, a in enumerate(accs):
        interval = normalize_interval(a.get("interval"))
        # Lệch pha: acc thứ i bắt đầu trễ hơn một nhịp chia đều trong chu kỳ.
        t = start + round(i * interval / n)
        while t <= end:
            rows.append({"ten_acc": a["ten"], "_t": t})
            t += interval

    # Giãn cách: đẩy lùi phiên bị sát nhau (bỏ nếu đẩy quá khung giờ).
    rows.sort(key=lambda r: r["_t"])
    spaced, last = [], None
    for r in rows:
        t = r["_t"] if last is None else max(r["_t"], last + min_gap)
        if t > end:
            continue
        r["_t"] = t
        r["gio_dang"] = _min_to_hhmm(t)
        spaced.append(r)
        last = t
    rows = spaced

    out = []
    for k, r in enumerate(rows, 1):
        out.append({
            "loai":       "nuoi",
            "stt":        k,
            "ma_content": "",
            "ten_acc":    r["ten_acc"],
            "ten_page":   "",
            "gio_dang":   r["gio_dang"],
            "ma_nhom":    "",
            "tu_khoa":    "",
            "mode":       "Nuoi",
            "trang_thai": "Chờ",
            "hoat_dong":  "nuoi_nick",
        })
    return out


# ═══════════════════════════════════════════════════════════════
# Playwright — mở context (giống poster, tái dùng cookie/profile)
# ═══════════════════════════════════════════════════════════════

async def _open_context(p, acc_name: str, c_user: str, headless: bool = None):
    profile_dir = find_profile_dir(acc_name, c_user)
    logger.info(f"  🗂️  Profile: {profile_dir}")
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        **browser_launch_kwargs(HEADLESS if headless is None else headless),
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    cookie_data = load_cookie(acc_name, c_user)
    if not cookie_data:
        await ctx.close()
        raise CookieDeadError(f"{acc_name}: không có cookie")

    _ci = []
    for name in ("c_user", "xs"):
        v = cookie_data.get(name, "")
        if v:
            _ci.append({"name": name, "value": v, "domain": ".facebook.com",
                        "path": "/", "httpOnly": True, "secure": True, "sameSite": "None"})
    for name in ("datr", "sb", "fr", "wd"):
        v = cookie_data.get(name, "")
        if v:
            _ci.append({"name": name, "value": v, "domain": ".facebook.com",
                        "path": "/", "httpOnly": False, "secure": True, "sameSite": "None"})
    await ctx.add_cookies(_ci)

    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    await human_delay(2000, 3000)
    if "login" in page.url or "checkpoint" in page.url:
        await ctx.close()
        raise CookieDeadError(acc_name)
    return ctx, page


# ═══════════════════════════════════════════════════════════════
# Các hành động nuôi — mỗi cái độc lập, tự mở–làm–xong
# (orchestrator bọc try/except riêng nên một cái hỏng không kéo sập phiên)
# ═══════════════════════════════════════════════════════════════

async def _act_feed(page, ctx, st):
    """Lướt newsfeed — chỉ đọc, KHÔNG like (like là hành động riêng)."""
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    await human_delay(1500, 2500)
    await browse_and_like(page, duration_sec=random.randint(30, 60), max_likes=0)


async def _act_like(page, ctx, st):
    """Like dạo — lướt feed và thả like theo số lượng cấu hình."""
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    await human_delay(1500, 2500)
    await browse_and_like(page, duration_sec=random.randint(40, 70),
                          max_likes=max(1, int(st.get("nuoi_like_count", 1))))


async def _act_story(page, ctx, st):
    """Xem story."""
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    await human_delay(1500, 2500)
    await view_stories(page, duration_sec=random.randint(10, 20))


class MessagingRestricted(Exception):
    """FB chặn acc này gửi tin nhắn (đòi xác nhận danh tính) — bỏ nhắn, nuôi kiểu khác."""


# Dấu hiệu FB chặn gửi tin nhắn. Khi thấy là DỪNG nhắn ngay: cố gửi tiếp lúc
# đang bị hạn chế chỉ khiến nick bị soi nặng hơn.
RESTRICT_MARKERS = (
    "xác nhận danh tính",
    "cách xác nhận",
    "bị hạn chế do có hoạt động bất thường",
    "hành động đã bị hạn chế",
    "confirm your identity",
    "you can't send messages",
    "temporarily restricted",
    "unusual activity",
)


def is_messaging_restricted(page_text: str) -> bool:
    """Đọc text trang, nhận biết acc có đang bị chặn nhắn tin không."""
    t = (page_text or "").lower()
    return any(m in t for m in RESTRICT_MARKERS)


def pick_messages(pool: list, n: int, rng=random) -> list:
    """
    Bốc n câu từ thư viện, KHÔNG lặp lại câu vừa nhắn liền trước (nhắn 2 câu
    giống hệt nhau liên tiếp trông rất máy). Thư viện ít câu hơn n thì cho phép
    dùng lại, miễn không dính hai câu kề nhau.
    """
    out = []
    for _ in range(max(0, n)):
        cands = [m for m in pool if not out or m != out[-1]] or list(pool)
        if not cands:
            break
        out.append(rng.choice(cands))
    return out


# Messenger hay chặn đường bằng hộp thoại "Nhập mã PIN để khôi phục đoạn chat".
# Không cần lịch sử chat để nhắn, nên bỏ qua: bấm X → "Không khôi phục tin nhắn".
PIN_DIALOG_MARKERS = (
    "nhập mã pin",
    "khôi phục đoạn chat",
    "khôi phục lịch sử chat",
    "enter your pin",
    "restore your chat",
)


def has_pin_dialog(page_text: str) -> bool:
    t = (page_text or "").lower()
    return any(m in t for m in PIN_DIALOG_MARKERS)


# Bấm bằng JS thay vì selector CSS: nút X của hộp thoại PIN nằm ngoài
# div[role='dialog'] và không có aria-label ổn định, nên selector hay trượt.
_JS_CLICK_CLOSE = """() => {
    const visible = el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    // 1) Nút có nhãn Đóng / Close
    for (const el of document.querySelectorAll('[aria-label]')) {
        const l = (el.getAttribute('aria-label') || '').toLowerCase();
        if ((l.includes('đóng') || l.includes('dong') || l.includes('close')) && visible(el)) {
            el.click();
            return 'aria:' + l;
        }
    }
    // 2) Nút tròn chứa svg nằm ở góc trên–phải của hộp thoại
    let best = null, bestTop = 1e9;
    for (const el of document.querySelectorAll('div[role="button"], button')) {
        if (!visible(el) || !el.querySelector('svg, i')) continue;
        const r = el.getBoundingClientRect();
        if (r.width > 60 || r.height > 60) continue;          // nút nhỏ
        if (r.top > window.innerHeight * 0.6) continue;        // nửa trên màn hình
        if (r.left < window.innerWidth * 0.4) continue;        // lệch phải
        if (r.top < bestTop) { bestTop = r.top; best = el; }
    }
    if (best) { best.click(); return 'svg-button'; }
    return '';
}"""

# Bấm nút theo TEXT. Phải khớp chính xác và ưu tiên phần tử bấm được thật sự:
# khối div cha bọc cả 2 nút có textContent = "Không khôi phục tin nhắnHủy" nên
# kiểu khớp "chứa chuỗi" sẽ bấm trúng khối cha → không có tác dụng gì.
_JS_CLICK_TEXT = """(needles) => {
    const visible = el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
    // Nút THẬT không chứa nút khác bên trong — loại khối cha bọc nhiều nút.
    const btns = [...document.querySelectorAll('[role="button"], button')]
        .filter(el => visible(el) && !el.querySelector('[role="button"], button'));

    for (const n of needles) {
        // 1) Nút khớp CHÍNH XÁC
        let hit = btns.find(el => norm(el.textContent) === n);
        // 2) Nút bắt đầu bằng chuỗi cần tìm, không dài hơn mấy (tránh khối cha)
        if (!hit) hit = btns.find(el => {
            const t = norm(el.textContent);
            return t.startsWith(n) && t.length <= n.length + 8;
        });
        // 3) Text nằm trong span/div → leo lên nút bấm được gần nhất
        if (!hit) {
            const el = [...document.querySelectorAll('span, div')]
                .find(e => visible(e) && norm(e.textContent) === n);
            if (el) hit = el.closest('[role="button"], button') || el;
        }
        if (hit) { hit.click(); return norm(hit.textContent).slice(0, 40); }
    }
    return '';
}"""

# Chờ hộp xác nhận hiện ra rồi mới bấm (nó xuất hiện sau khi bấm X).
_JS_HAS_TEXT = """(needles) => {
    const t = (document.body.innerText || '').toLowerCase();
    return needles.some(n => t.includes(n));
}"""


async def _dismiss_pin_dialog(page) -> bool:
    """
    Đóng hộp thoại đòi mã PIN khôi phục chat.
    Thao tác tay tương ứng: bấm X → "Không khôi phục tin nhắn".
    Trả về True nếu có gặp hộp thoại (dù đóng được hay không).
    """
    try:
        if not has_pin_dialog(await page.inner_text("body")):
            return False
    except Exception:
        return False

    logger.info("    🔑 Gặp hộp thoại mã PIN — chọn không khôi phục")

    async def _con_hien() -> bool:
        try:
            return has_pin_dialog(await page.inner_text("body"))
        except Exception:
            return False

    # ── Bước 1: đóng hộp thoại PIN (X, hoặc Escape) ──
    for lan in range(3):
        try:
            r = await page.evaluate(_JS_CLICK_CLOSE)
            if r:
                logger.info(f"    ✔️  Đã bấm nút đóng ({r})")
        except Exception as e:
            logger.warning(f"    ⚠️  Bấm nút đóng lỗi: {e}")
        await human_delay(900, 1600)

        # Hộp xác nhận "Tiếp tục mà không khôi phục?" → chọn không khôi phục.
        # Nó hiện ra SAU khi bấm X nên phải chờ, đừng bấm ngay.
        nhan = ["không khôi phục tin nhắn", "không khôi phục",
                "don't restore messages", "don’t restore messages", "don't restore"]
        try:
            for _ in range(10):          # chờ tối đa ~5s
                if await page.evaluate(_JS_HAS_TEXT, nhan):
                    break
                await asyncio.sleep(0.5)
            hit = await page.evaluate(_JS_CLICK_TEXT, nhan)
            if hit:
                logger.info(f"    ✔️  Đã chọn '{hit}'")
                await human_delay(900, 1600)
        except Exception as e:
            logger.warning(f"    ⚠️  Bấm 'không khôi phục' lỗi: {e}")

        if not await _con_hien():
            logger.info("    ✅ Đã bỏ qua khôi phục tin nhắn")
            return True

        # Chưa đóng được → thử Escape rồi lặp lại
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await human_delay(700, 1200)
        if not await _con_hien():
            logger.info("    ✅ Đã đóng hộp thoại PIN (Escape)")
            return True

    logger.warning("    ⚠️  Không đóng được hộp thoại mã PIN — bỏ qua nhắn tin phiên này")
    return True


async def _find_chat_box(page):
    """Tìm ô soạn tin của Messenger — thử vài selector vì giao diện hay đổi."""
    selectors = [
        "div[role='textbox'][contenteditable='true']",
        "div[aria-label='Tin nhắn'][contenteditable='true']",
        "div[aria-label='Message'][contenteditable='true']",
        "p[contenteditable='true']",
    ]
    for sel in selectors:
        try:
            box = page.locator(sel).last
            if await box.count() and await box.is_visible():
                return box
        except Exception:
            continue
    return None


async def _act_message(page, ctx, st):
    """Vào nhóm chat nội bộ, nhắn vài câu bốc từ thư viện."""
    group_url = (st.get("nuoi_msg_group_url", "") or "").strip()
    pool = [ln.strip() for ln in (st.get("nuoi_msg_pool", "") or "").splitlines() if ln.strip()]
    if not group_url or not pool:
        logger.info("    ⏭️  Nhắn tin: chưa có link nhóm / thư viện câu — bỏ qua")
        return

    await page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
    await human_delay(2500, 4000)

    # Dẹp hộp thoại đòi mã PIN trước — nó che mất ô soạn tin.
    if await _dismiss_pin_dialog(page):
        await human_delay(1000, 2000)
        # Vẫn còn che → bỏ nhắn phiên này, để orchestrator bù bằng feed/story/like
        # thay vì đứng chờ ô soạn tin không bao giờ bấm được.
        try:
            if has_pin_dialog(await page.inner_text("body")):
                raise MessagingRestricted("hộp thoại mã PIN chưa đóng được")
        except MessagingRestricted:
            raise
        except Exception:
            pass

    # Acc đang bị hạn chế nhắn tin → bỏ hẳn, KHÔNG thử gửi.
    try:
        body_text = await page.inner_text("body")
    except Exception:
        body_text = ""
    if is_messaging_restricted(body_text):
        raise MessagingRestricted("FB đòi xác nhận danh tính mới cho nhắn tin")

    box = await _find_chat_box(page)
    if box is None:
        raise Exception("Không tìm thấy ô soạn tin nhắn (FB đổi giao diện?)")

    n_msg = random.randint(int(st.get("nuoi_msg_min", 2)), int(st.get("nuoi_msg_max", 3)))
    sent  = 0
    for msg in pick_messages(pool, n_msg):
        try:
            await box.click()
            await human_delay(500, 1200)
            # Gõ từng ký tự có độ trễ — giống người gõ hơn là dán cả câu.
            await box.type(msg, delay=random.randint(40, 110))
            await human_delay(400, 900)
            await page.keyboard.press("Enter")
            sent += 1
            logger.info(f"    💬 Đã nhắn: {msg[:40]}")
            # Nghỉ giữa 2 tin như người đang trò chuyện.
            await human_delay(2500, 6000)
        except Exception as e:
            logger.warning(f"    ⚠️  Nhắn tin dừng giữa chừng: {e}")
            break

        # FB có thể chặn NGAY SAU vài tin đầu — kiểm lại để dừng đúng lúc.
        try:
            if is_messaging_restricted(await page.inner_text("body")):
                raise MessagingRestricted(f"bị chặn sau khi gửi {sent} tin")
        except MessagingRestricted:
            raise
        except Exception:
            pass

    logger.info(f"    ✅ Nhắn tin xong — {sent}/{n_msg} tin")


# ═══════════════════════════════════════════════════════════════
# Chọn hành động cho phiên — logic thuần, test được
# ═══════════════════════════════════════════════════════════════

# (tên, xác suất được chọn mỗi phiên, cờ bật/tắt trong settings)
_ACTIVITY_SPECS = [
    ("story",   0.70, "nuoi_enable_story"),
    ("feed",    0.90, "nuoi_enable_feed"),
    ("like",    0.70, "nuoi_enable_like"),
    ("message", 0.50, "nuoi_enable_message"),
]
_ACTIVITY_FNS = {
    "story":   _act_story,
    "feed":    _act_feed,
    "like":    _act_like,
    "message": _act_message,
}


def select_session_activities(st: dict, rng=random) -> list:
    """
    Bốc TẬP CON hành động cho một phiên (không phiên nào giống phiên nào) rồi
    XÁO thứ tự — để FB khó nhận ra khuôn. Chỉ lấy hành động đang bật trong
    settings; đảm bảo tối thiểu 1 hành động nếu có cái nào bật.
    """
    pool = [(name, prob) for name, prob, flag in _ACTIVITY_SPECS if st.get(flag)]
    chosen = [name for name, prob in pool if rng.random() <= prob]
    if not chosen and pool:
        chosen = [rng.choice(pool)[0]]
    rng.shuffle(chosen)
    return chosen


# ═══════════════════════════════════════════════════════════════
# Orchestrator — chạy các hành động đã chọn trong ngân sách 5–8'
# ═══════════════════════════════════════════════════════════════

async def _run_warming(acc_name: str, c_user: str, st: dict,
                       headless: bool = None) -> bool:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        ctx, page = await _open_context(p, acc_name, c_user, headless)
        try:
            budget   = random.randint(int(st["nuoi_session_min_sec"]),
                                      int(st["nuoi_session_max_sec"]))
            deadline = time.monotonic() + budget
            logger.info(f"  🌱 Phiên nuôi '{acc_name}' — ngân sách {budget}s")

            chosen = select_session_activities(st)
            logger.info(f"  🎲 Hành động phiên này: {', '.join(chosen) or '(không có)'}")

            done = []
            for idx, name in enumerate(chosen):
                if time.monotonic() >= deadline:
                    logger.info("  ⏱️  Hết ngân sách phiên — dừng")
                    break
                try:
                    await _ACTIVITY_FNS[name](page, ctx, st)
                    done.append(name)
                except CookieDeadError:
                    raise
                except MessagingRestricted as e:
                    # Acc đang bị hạn chế nhắn tin → bỏ hẳn, quay về lướt
                    # newsfeed / story cho phiên vẫn có ích.
                    logger.warning(f"  🚫 [{acc_name}] Nhắn tin bị chặn: {e}")
                    con_lai = set(chosen[idx + 1:])
                    for fb, flag in (("feed",  "nuoi_enable_feed"),
                                     ("story", "nuoi_enable_story"),
                                     ("like",  "nuoi_enable_like")):
                        if fb in done or fb in con_lai or not st.get(flag):
                            continue          # đã làm rồi / lát nữa cũng làm / đang tắt
                        if time.monotonic() >= deadline:
                            break
                        try:
                            logger.info(f"  ↩️  Bù lại bằng '{fb}'")
                            await _ACTIVITY_FNS[fb](page, ctx, st)
                            done.append(fb)
                        except Exception as e2:
                            logger.warning(f"  ⚠️  Bù '{fb}' lỗi: {e2}")
                except Exception as e:
                    logger.warning(f"  ⚠️  Hành động '{name}' lỗi (bỏ qua): {e}")
                await human_delay(1500, 3500)

            logger.info(f"  ✅ Phiên nuôi xong — đã làm: {', '.join(done) or '(không có)'}")
            return True
        finally:
            await ctx.close()


def run_warming_session(acc_name: str, c_user: str = "", headless: bool = None) -> bool:
    """Điểm vào cho scheduler. Trả về True nếu phiên chạy (kể cả vài hành động
    lỗi lẻ); raise CookieDeadError nếu cookie hỏng để scheduler đánh dấu acc.
    headless=None → theo cấu hình chung; đặt False để xem tận mắt lúc test."""
    return asyncio.run(_run_warming(acc_name, c_user, get_settings(), headless))


# ═══════════════════════════════════════════════════════════════
# Chạy thử 1 phiên nuôi (xem tận mắt) — không đụng lịch, không đăng gì
#   python nuoi_nick.py "Tên acc"                   → hiện cửa sổ Chrome
#   python nuoi_nick.py "Tên acc" --headless        → chạy ẩn
#   python nuoi_nick.py "Tên acc" --only message    → ép chạy đúng hành động đó
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    raw = sys.argv[1:]
    want_headless = "--headless" in raw

    # --only story,message : bỏ bốc ngẫu nhiên, ép chạy đúng các hành động này
    # (để test có chủ đích thay vì chạy lại nhiều lần chờ bốc trúng).
    only = []
    if "--only" in raw:
        i = raw.index("--only")
        if i + 1 < len(raw):
            only = [x.strip() for x in raw[i + 1].split(",") if x.strip()]
        raw = raw[:i] + raw[i + 2:]

    argv = [a for a in raw if a != "--headless"]

    if only:
        _xau = [x for x in only if x not in _ACTIVITY_FNS]
        if _xau:
            print(f"❌ Hành động không hợp lệ: {', '.join(_xau)}")
            print(f"   Hợp lệ: {', '.join(_ACTIVITY_FNS)}")
            sys.exit(1)
        select_session_activities = lambda st, rng=random: list(only)

    if not argv:
        from db import get_accounts
        print("Cách dùng:  python nuoi_nick.py \"Tên acc\" [--headless] [--only story,message]\n")
        print(f"  --only : ép chạy đúng hành động chỉ định ({', '.join(_ACTIVITY_FNS)})")
        print("           bỏ bốc ngẫu nhiên — dùng khi muốn test 1 thứ cụ thể.\n")
        print("Các acc đang bật nuôi:")
        found = False
        for a in get_accounts():
            if int(a.get("nuoi_nick", 0) or 0) == 1:
                found = True
                loai = (a.get("loai_dang") or "").strip() or "(trống → chỉ nuôi)"
                print(f"   • {a['ten_acc']:24} loại đăng: {loai}")
        if not found:
            print("   (chưa có acc nào tick Nuôi ở bảng Tài khoản)")
        sys.exit(1)

    acc_name = argv[0]
    from db import get_account_by_name
    acc = get_account_by_name(acc_name)
    if not acc:
        print(f"❌ Không tìm thấy acc '{acc_name}' (kiểm tra Trạng thái = Active)")
        sys.exit(1)

    st = get_settings()
    bat = [ten for ten, _p, co in _ACTIVITY_SPECS if st.get(co)]
    print("=" * 58)
    print(f"🌱 CHẠY THỬ PHIÊN NUÔI — {acc_name}")
    if only:
        print(f"   ÉP chạy            : {', '.join(only)}")
    print(f"   Hành động đang BẬT : {', '.join(bat) or '(không có)'}")
    print(f"   Độ dài phiên       : {st['nuoi_session_min_sec']}–{st['nuoi_session_max_sec']}s")
    print(f"   Chrome             : {'ẩn' if want_headless else 'HIỆN cửa sổ'}")
    if st.get("nuoi_enable_message"):
        n_cau = len([l for l in (st.get('nuoi_msg_pool') or '').splitlines() if l.strip()])
        print(f"   Nhắn tin           : {n_cau} câu | nhóm: {st.get('nuoi_msg_group_url') or '(chưa đặt)'}")
    print("=" * 58)

    try:
        run_warming_session(acc_name, acc.get("c_user", ""), headless=want_headless)
        print("\n✅ Phiên thử xong — xem log phía trên để biết đã làm gì.")
    except CookieDeadError:
        print(f"\n❌ Cookie của '{acc_name}' đã hết hạn — cần lấy lại xs.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Phiên thử lỗi: {e}")
        sys.exit(1)
