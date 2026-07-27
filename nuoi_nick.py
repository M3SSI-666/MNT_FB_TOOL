"""
================================================================================
nuoi_nick.py — Tính năng NUÔI NICK
================================================================================
Mục tiêu: cho các nick được tick chọn "khỏe dần theo thời gian" bằng cách xen
các phiên hoạt động giống người (lướt feed, xem story, like, kết bạn, nhắn tin)
vào lịch, THAY CHO một số slot đăng bài — nick càng non thì càng nhiều slot bị
chuyển thành nuôi (đăng ít, nuôi nhiều), càng già thì càng ít.

Hai phần tách bạch:
  1. Logic thuần (test được, không cần Playwright):
       - warm_ratio()               : tỷ lệ slot chuyển thành nuôi theo tuổi nick
       - account_age_days()         : tính tuổi nick
       - plan_warming_conversion()  : đánh dấu slot nào thành 'nuoi_nick'
  2. Bộ máy chạy phiên nuôi bằng Playwright (chỉ chạy thật với FB):
       - run_warming_session()      : điểm vào cho scheduler
       - _run_warming()             : orchestrator — bốc TẬP CON hành động, XÁO
                                      thứ tự, chạy trong ngân sách 5–8 phút, mỗi
                                      hành động bọc try/except riêng.

LƯU Ý: các selector kết bạn / nhắn tin là best-effort, CẦN chạy thử non-headless
lần đầu để chỉnh. Nhắn tin mặc định TẮT cho tới khi có thư viện câu (content pool).
================================================================================
"""

import time
import asyncio
import random
from datetime import datetime, date
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
    "nuoi_friend_min":      5,      # gửi lời mời kết bạn: tối thiểu
    "nuoi_friend_max":      10,     # gửi lời mời kết bạn: tối đa
    "nuoi_friend_gap_sec":  30,     # giãn cách giữa mỗi lời mời (chống bot)
    "nuoi_msg_min":         2,      # số tin nhắn mỗi phiên: tối thiểu
    "nuoi_msg_max":         3,      # số tin nhắn mỗi phiên: tối đa
    "nuoi_msg_group_url":   "",     # link nhóm chat nội bộ (build sau)
    "nuoi_msg_pool":        "",     # thư viện câu, mỗi dòng 1 câu (build sau)
    # Bật/tắt từng hành động — để tách rủi ro, cái nào hỏng tắt riêng cái đó
    "nuoi_enable_feed":     1,
    "nuoi_enable_story":    1,
    "nuoi_enable_accept":   1,      # xác nhận lời mời đến (bị động, an toàn)
    "nuoi_enable_addfriend":0,      # chủ động gửi lời mời — MẶC ĐỊNH TẮT (rủi ro
                                    #   khóa nick cao nhất); tự bật khi đã test kỹ
    "nuoi_enable_message":  0,      # TẮT tới khi có content pool
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
# Logic thuần — ramp-up & chọn slot (KHÔNG cần Playwright, test được)
# ═══════════════════════════════════════════════════════════════

# Đường cong nuôi: (tuổi_tối_đa_ngày, tỷ_lệ_slot_chuyển_thành_nuôi).
# Nick non → chuyển nhiều (đăng ít, nuôi nhiều); nick già → chuyển ít.
STAGE_CURVE = [(7, 0.7), (14, 0.5), (30, 0.3), (10**9, 0.15)]


def warm_ratio(age_days: int, curve=STAGE_CURVE) -> float:
    for max_age, ratio in curve:
        if age_days <= max_age:
            return ratio
    return curve[-1][1]


def account_age_days(ngay_bat_dau_nuoi: str, created_at: str = "", today: date = None) -> int:
    """Tuổi nick tính từ ngày bắt đầu nuôi (rỗng thì dùng created_at)."""
    today = today or date.today()
    src = (ngay_bat_dau_nuoi or created_at or "").strip()
    if not src:
        return 0
    try:
        d = datetime.strptime(src[:10], "%Y-%m-%d").date()
        return max(0, (today - d).days)
    except Exception:
        return 0


def plan_warming_conversion(schedule: list, warm_info: dict, curve=STAGE_CURVE) -> int:
    """
    Đánh dấu một tập con slot của mỗi acc BẬT nuôi thành hoat_dong='nuoi_nick'.
    Sửa `schedule` tại chỗ. Trả về tổng số slot đã chuyển.

    schedule : list row dict đã gen (mỗi row có 'ten_acc'); thứ tự = thứ tự giờ.
    warm_info: {ten_acc: age_days} — CHỈ chứa acc đang bật nuôi.

    Cách chọn: rải đều khắp các slot của acc (không cụm) để phiên nuôi trải đều
    cả ngày, thừa hưởng luôn cách stagger sẵn có của lịch đăng.
    """
    by_acc = defaultdict(list)
    for i, row in enumerate(schedule):
        row.setdefault("hoat_dong", "dang_bai")
        by_acc[row["ten_acc"]].append(i)

    converted = 0
    for acc, idxs in by_acc.items():
        if acc not in warm_info:
            continue
        n = len(idxs)
        if n == 0:
            continue
        ratio     = warm_ratio(warm_info[acc], curve)
        n_convert = max(0, min(round(ratio * n), n))
        if n_convert == 0:
            continue
        # Chọn đều: slot thứ round((j+0.5)*n/n_convert) — rải khắp dải thời gian.
        chosen = set()
        for j in range(n_convert):
            k = min(n - 1, int((j + 0.5) * n / n_convert))
            chosen.add(k)
        for k in chosen:
            schedule[idxs[k]]["hoat_dong"] = "nuoi_nick"
        converted += len(chosen)
    return converted


# ═══════════════════════════════════════════════════════════════
# Playwright — mở context (giống poster, tái dùng cookie/profile)
# ═══════════════════════════════════════════════════════════════

async def _open_context(p, acc_name: str, c_user: str):
    profile_dir = find_profile_dir(acc_name, c_user)
    logger.info(f"  🗂️  Profile: {profile_dir}")
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        **browser_launch_kwargs(HEADLESS),
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
    """Lướt newsfeed + like theo số lượng cấu hình."""
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    await human_delay(1500, 2500)
    await browse_and_like(page, duration_sec=random.randint(30, 60),
                          max_likes=int(st.get("nuoi_like_count", 1)))


async def _act_story(page, ctx, st):
    """Xem story."""
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    await human_delay(1500, 2500)
    await view_stories(page, duration_sec=random.randint(10, 20))


async def _act_accept_friends(page, ctx, st):
    """Xác nhận mọi lời mời kết bạn đến — bị động, an toàn."""
    await page.goto("https://www.facebook.com/friends/requests/",
                    wait_until="domcontentloaded", timeout=30000)
    await human_delay(2000, 3500)
    accepted = 0
    for _ in range(15):   # trần vòng lặp, tránh kẹt
        btn = page.locator(
            "div[role='button']:has-text('Xác nhận'), div[role='button']:has-text('Confirm')"
        ).first
        try:
            if await btn.count() == 0 or not await btn.is_visible():
                break
            await btn.click()
            accepted += 1
            await human_delay(1200, 2500)
        except Exception:
            break
    logger.info(f"    🤝 Xác nhận {accepted} lời mời kết bạn")


async def _act_add_friends(page, ctx, st):
    """Chủ động gửi lời mời kết bạn, RẢI CHẬM (giãn cách chống bot)."""
    n_target = random.randint(int(st.get("nuoi_friend_min", 5)),
                              int(st.get("nuoi_friend_max", 10)))
    gap      = int(st.get("nuoi_friend_gap_sec", 30))
    await page.goto("https://www.facebook.com/friends/suggestions",
                    wait_until="domcontentloaded", timeout=30000)
    await human_delay(2500, 4000)
    sent = 0
    for _ in range(n_target * 3):   # thử nhiều hơn vì có nút click hụt
        if sent >= n_target:
            break
        btn = page.locator(
            "div[aria-label='Thêm bạn bè'], div[aria-label='Add friend']"
        ).first
        try:
            if await btn.count() == 0 or not await btn.is_visible():
                await page.mouse.wheel(0, random.randint(500, 900))
                await human_delay(1500, 3000)
                continue
            await btn.scroll_into_view_if_needed()
            await btn.click()
            sent += 1
            logger.info(f"    ➕ Gửi lời mời #{sent}/{n_target}")
            # Rải chậm: đây là hành động dễ bị chặn nhất, cố ý giãn rộng.
            await asyncio.sleep(max(5, jitter_sec(gap)))
        except Exception:
            await page.mouse.wheel(0, random.randint(400, 800))
            await human_delay(1500, 3000)
    logger.info(f"    ✅ Đã gửi {sent} lời mời kết bạn")


async def _act_message(page, ctx, st):
    """Vào nhóm chat nội bộ, nhắn 2–3 câu bốc từ thư viện. TẮT tới khi có pool."""
    group_url = (st.get("nuoi_msg_group_url", "") or "").strip()
    pool = [ln.strip() for ln in (st.get("nuoi_msg_pool", "") or "").splitlines() if ln.strip()]
    if not group_url or not pool:
        logger.info("    ⏭️  Nhắn tin: chưa có nhóm/thư viện câu — bỏ qua")
        return
    await page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
    await human_delay(2500, 4000)
    n_msg = random.randint(int(st.get("nuoi_msg_min", 2)), int(st.get("nuoi_msg_max", 3)))
    box = page.locator("div[role='textbox'][contenteditable='true']").first
    sent = 0
    for _ in range(n_msg):
        msg = random.choice(pool)
        try:
            await box.click()
            await human_delay(500, 1200)
            await box.type(msg, delay=random.randint(40, 110))
            await human_delay(400, 900)
            await page.keyboard.press("Enter")
            sent += 1
            await human_delay(2000, 4500)
        except Exception:
            break
    logger.info(f"    💬 Đã nhắn {sent} tin")


def jitter_sec(base: int) -> float:
    """Giãn ngẫu nhiên quanh base ±40% (dùng cho khoảng chờ giữa lời mời)."""
    return base * random.uniform(0.6, 1.4)


# ═══════════════════════════════════════════════════════════════
# Chọn hành động cho phiên — logic thuần, test được
# ═══════════════════════════════════════════════════════════════

# (tên, xác suất được chọn mỗi phiên, cờ bật/tắt trong settings)
_ACTIVITY_SPECS = [
    ("feed",    0.90, "nuoi_enable_feed"),
    ("story",   0.70, "nuoi_enable_story"),
    ("accept",  0.80, "nuoi_enable_accept"),
    ("friend",  0.50, "nuoi_enable_addfriend"),
    ("message", 0.50, "nuoi_enable_message"),
]
_ACTIVITY_FNS = {
    "feed":    _act_feed,
    "story":   _act_story,
    "accept":  _act_accept_friends,
    "friend":  _act_add_friends,
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

async def _run_warming(acc_name: str, c_user: str, st: dict) -> bool:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        ctx, page = await _open_context(p, acc_name, c_user)
        try:
            budget   = random.randint(int(st["nuoi_session_min_sec"]),
                                      int(st["nuoi_session_max_sec"]))
            deadline = time.monotonic() + budget
            logger.info(f"  🌱 Phiên nuôi '{acc_name}' — ngân sách {budget}s")

            chosen = select_session_activities(st)
            logger.info(f"  🎲 Hành động phiên này: {', '.join(chosen) or '(không có)'}")

            done = []
            for name in chosen:
                if time.monotonic() >= deadline:
                    logger.info("  ⏱️  Hết ngân sách phiên — dừng")
                    break
                try:
                    await _ACTIVITY_FNS[name](page, ctx, st)
                    done.append(name)
                except CookieDeadError:
                    raise
                except Exception as e:
                    logger.warning(f"  ⚠️  Hành động '{name}' lỗi (bỏ qua): {e}")
                await human_delay(1500, 3500)

            logger.info(f"  ✅ Phiên nuôi xong — đã làm: {', '.join(done) or '(không có)'}")
            return True
        finally:
            await ctx.close()


def run_warming_session(acc_name: str, c_user: str = "") -> bool:
    """Điểm vào cho scheduler. Trả về True nếu phiên chạy (kể cả vài hành động
    lỗi lẻ); raise CookieDeadError nếu cookie hỏng để scheduler đánh dấu acc."""
    return asyncio.run(_run_warming(acc_name, c_user, get_settings()))
