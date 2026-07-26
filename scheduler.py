"""
scheduler.py — MNT_FB Scheduler
Đọc lịch từ SQLite local, không cần Google Sheets API.
SCHEDULER_LOAI env var xác định loại lịch cần chạy.
"""

import os
import sys
import re
import time
import threading
from datetime import datetime, timedelta

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import (
    get_schedules, update_schedule_status,
    get_content_by_code, get_uid_groups_by_code,
    get_account_by_name, get_page_by_name, get_accounts,
    update_account_field,
)
from cookie_exporter import load_cookie, export_all_accounts
from utils import logger, jitter, CookieDeadError, classify_error
from config import CHECK_EVERY_SEC, WINDOW_MINUTES, MAX_WORKERS

# ── Cấu hình ─────────────────────────────────────────────────
LOAI = os.environ.get("SCHEDULER_LOAI", "").strip()
if not LOAI:
    logger.error("❌ Thiếu SCHEDULER_LOAI env var")
    sys.exit(1)

LOAI_SHEET_MAP = {
    "homestay": "Chéo Homestay",
    "thue":     "Chéo Thuê",
    "ban":      "Chéo Bán",
    "page":     "Đăng bài Page",
}

logger.info("=" * 60)
logger.info(f"🚀 SCHEDULER — {LOAI.upper()}")
logger.info(f"   Kiểm tra mỗi {CHECK_EVERY_SEC}s | Cửa sổ ±{WINDOW_MINUTES} phút")
logger.info("=" * 60)

# Stagger delay
_start_delay = int(os.environ.get("SCHEDULER_START_DELAY", "0"))
if _start_delay > 0:
    logger.info(f"⏳ Stagger {_start_delay}s...")
    time.sleep(_start_delay)


# ── Helpers ───────────────────────────────────────────────────

def _parse_schedule_time(gio_dang: str):
    try:
        h, m  = map(int, gio_dang.strip().split(":"))
        now   = datetime.now().replace(second=0, microsecond=0)
        base  = now.replace(hour=h, minute=m)
        if h < 7 and now.hour >= 7:
            base += timedelta(days=1)
        return base
    except Exception:
        return None


def _parse_first_group_uid(ma_nhom: str) -> str:
    """
    Lấy UID nhóm đầu để mở composer.
    Chấp nhận: URL Facebook nhóm, UID số, hoặc mã nhóm TIME1-7.
    """
    if not ma_nhom:
        return ""
    val = ma_nhom.strip().split("\n")[0].strip()

    # URL Facebook → parse UID
    m = re.search(r"facebook\.com/groups/([^/?&#\s]+)", val)
    if m:
        return m.group(1)

    # Chuỗi chỉ là số → UID trực tiếp
    if re.match(r"^\d{5,}$", val):
        return val

    # Slug không số (homestaytimescity, v.v.) → dùng trực tiếp
    if re.match(r"^[a-zA-Z]", val) and "." not in val and len(val) > 5:
        # Không phải TIME code
        if not re.match(r"^TIME\d+$", val, re.IGNORECASE):
            return val

    # Mã nhóm TIME1-7 → lấy nhóm đầu tiên từ db
    groups = get_uid_groups_by_code(val)
    if groups:
        return groups[0]["uid"]

    return ""


def _is_due(gio_dang: str) -> bool:
    scheduled = _parse_schedule_time(gio_dang)
    if not scheduled:
        return False
    diff = (datetime.now() - scheduled).total_seconds() / 60
    return 0 <= diff <= WINDOW_MINUTES


def _update_status(schedule_id: int, status: str):
    update_schedule_status(schedule_id, status)


# ── Run 1 dòng lịch ──────────────────────────────────────────

# Lỗi mạng thoáng qua không nên làm mất luôn lượt đăng của cả ngày.
# CHỈ thử lại nhóm 'transient'; 'ratelimit' cố tình KHÔNG retry vì đăng dồn
# khi Facebook đang chặn là cách nhanh nhất để acc bị khoá.
MAX_ATTEMPTS      = 3
RETRY_BASE_SEC    = 30


def _should_retry(cat: str, attempt: int) -> bool:
    return cat == "transient" and attempt < MAX_ATTEMPTS


def _retry_delay(attempt: int) -> float:
    """Backoff tăng gấp đôi mỗi lần, có jitter để 15 worker gặp sự cố mạng
    cùng lúc không cùng thử lại một thời điểm."""
    return jitter(RETRY_BASE_SEC * (2 ** (attempt - 1)), pct=0.3, floor=5)


def _attempt_post(item: dict) -> str:
    """Thực hiện đăng 1 dòng lịch. Trả về hậu tố trạng thái khi thành công,
    raise exception khi thất bại (để lớp ngoài phân loại và quyết định retry)."""
    acc_name  = item["ten_acc"]
    page_name = item["ten_page"]
    ma_ct     = item["ma_content"]
    ma_nhom   = item["ma_nhom"]
    tu_khoa   = item.get("tu_khoa", "")
    mode      = (item.get("mode", "Hybrid") or "Hybrid").upper()

    ct = get_content_by_code(ma_ct)
    if not ct:
        raise Exception(f"Không tìm thấy mã content '{ma_ct}'")
    content  = ct.get("noi_dung", "").strip()
    hook_anh = ct.get("link_anh_hook", "").strip()
    link_anh = ct.get("link_anh", "").strip()

    # Hook đứng đầu
    if hook_anh:
        others   = [u.strip() for u in link_anh.split(",") if u.strip() and u.strip() != hook_anh]
        link_anh = ", ".join([hook_anh] + others)

    logger.info(f"📝 Content ({len(content)}c): {content[:60]}...")

    # ── ĐĂNG BÀI PAGE (wall) — Playwright ────────────────────
    if LOAI == "page":
        from page_via_poster import post_page_wall
        acc_data = get_account_by_name(acc_name)
        if not acc_data:
            raise Exception(f"Không tìm thấy acc '{acc_name}'")
        page_info = get_page_by_name(page_name)
        page_uid  = page_info.get("page_uid", "") if page_info else ""
        if not page_uid:
            raise Exception(f"Không có Page UID cho '{page_name}'")
        ok = post_page_wall(
            acc_name=acc_name,
            page_uid=page_uid,
            message=content,
            image_url=link_anh,
            c_user=acc_data.get("c_user", ""),
        )
        if not ok:
            raise Exception("Đăng tường Page thất bại")
        return ""

    # ── MODE HYBRID / PAGEVIA ─────────────────────────────────
    if mode in ("HYBRID", "PAGEVIA"):
        from page_via_poster import post_page_via
        if not tu_khoa:
            raise Exception("Mode=Hybrid nhưng thiếu Từ khóa")
        page_info = get_page_by_name(page_name)
        page_uid  = page_info.get("page_uid", "") if page_info else ""
        if not page_uid:
            raise Exception(f"Không có Page UID cho '{page_name}'")
        first_uid = _parse_first_group_uid(ma_nhom)
        if not first_uid:
            raise Exception("Thiếu UID nhóm đầu để mở composer")
        acc_data  = get_account_by_name(acc_name, page_name)
        c_user_v  = acc_data.get("c_user", "") if acc_data else ""
        count = post_page_via(
            acc_name=acc_name, page_uid=page_uid,
            first_group_uid=first_uid, search_kw=tu_khoa,
            message=content, image_url=link_anh,
            c_user=c_user_v,
        )
        if not count:
            raise Exception("Hybrid thất bại")
        return f" ({count} nhóm)"

    # ── MODE VIA ──────────────────────────────────────────────
    if mode == "VIA":
        from via_poster import post_via_crosspost
        if not tu_khoa:
            raise Exception("Mode=Via nhưng thiếu Từ khóa")
        first_uid = _parse_first_group_uid(ma_nhom)
        if not first_uid:
            raise Exception("Thiếu UID nhóm đầu để mở composer")
        acc_data  = get_account_by_name(acc_name, page_name)
        c_user_v  = acc_data.get("c_user", "") if acc_data else ""
        count = post_via_crosspost(
            acc_name=acc_name, search_kw=tu_khoa,
            message=content, image_url=link_anh,
            first_group_uid=first_uid,
            c_user=c_user_v,
        )
        if not count:
            raise Exception("Via thất bại")
        return f" ({count} nhóm)"

    # ── MODE không hỗ trợ ──────────────────────────────────────
    # Mode "Page" (đăng qua HTTP API) đã bị loại bỏ — chỉ còn Playwright.
    raise Exception(f"Mode '{mode}' không được hỗ trợ (chỉ còn Hybrid/Via — Playwright)")


def _mark_cookie_dead(acc_name: str):
    """Đánh dấu account để dễ thấy trong tab Tài khoản."""
    try:
        a = get_account_by_name(acc_name)
        if a:
            update_account_field(a["id"], "trang_thai", "Cookie hết hạn")
    except Exception as e:
        logger.warning(f"⚠️  Không đánh dấu được acc '{acc_name}' hết cookie: {e}")


def _run_warming(item: dict):
    """Slot đã bị chuyển thành nuôi nick — chạy phiên nuôi thay vì đăng bài."""
    sid      = item["id"]
    stt      = item.get("stt", sid)
    acc_name = item["ten_acc"]
    ts       = datetime.now().strftime("%H:%M")

    logger.info(f"\n{'='*55}")
    logger.info(f"🌱 [{LOAI}] STT {stt} | {acc_name} | NUÔI NICK | {item['gio_dang']}")
    logger.info(f"{'='*55}")
    _update_status(sid, f"🌱 Đang nuôi {ts}")

    try:
        from nuoi_nick import run_warming_session
        acc_data = get_account_by_name(acc_name)
        c_user_v = acc_data.get("c_user", "") if acc_data else ""
        run_warming_session(acc_name=acc_name, c_user=c_user_v)
        done = datetime.now().strftime("%H:%M")
        _update_status(sid, f"🌱 {done} (đã nuôi)")
        logger.info(f"✅ STT {stt} nuôi xong")
    except CookieDeadError:
        ts2 = datetime.now().strftime("%H:%M")
        _update_status(sid, f"❌ {ts2} Cookie hết hạn")
        logger.error(f"❌ STT {stt}: Cookie hết hạn khi nuôi — acc '{acc_name}'")
        _mark_cookie_dead(acc_name)
    except Exception as e:
        ts2 = datetime.now().strftime("%H:%M")
        cat, label = classify_error(e)
        _update_status(sid, f"❌ {ts2} Nuôi lỗi: {label}")
        logger.error(f"❌ STT {stt} nuôi lỗi [{cat}]: {e}")


def _run_one(item: dict):
    # Slot nuôi nick đi đường riêng, không dùng retry của đăng bài.
    if (item.get("hoat_dong") or "dang_bai") == "nuoi_nick":
        _run_warming(item)
        return

    sid      = item["id"]
    stt      = item.get("stt", sid)
    acc_name = item["ten_acc"]
    mode     = (item.get("mode", "Hybrid") or "Hybrid").upper()
    ts       = datetime.now().strftime("%H:%M")

    logger.info(f"\n{'='*55}")
    logger.info(f"▶ [{LOAI}] STT {stt} | {acc_name} | Mode={mode} | {item['ma_content']} | {item['gio_dang']}")
    logger.info(f"{'='*55}")

    _update_status(sid, f"🔄 Đang chạy {ts}")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            suffix = _attempt_post(item)
            done   = datetime.now().strftime("%H:%M")
            _update_status(sid, f"✅ {done}{suffix}")
            logger.info(f"✅ STT {stt} hoàn thành{suffix}")
            return

        except CookieDeadError:
            ts2 = datetime.now().strftime("%H:%M")
            _update_status(sid, f"❌ {ts2} Cookie hết hạn")
            logger.error(f"❌ STT {stt}: Cookie hết hạn — acc '{acc_name}' cần đăng nhập lại")
            _mark_cookie_dead(acc_name)
            return

        except Exception as e:
            cat, label = classify_error(e)

            if _should_retry(cat, attempt):
                delay = _retry_delay(attempt)
                logger.warning(
                    f"⚠️  STT {stt} lỗi tạm thời (lần {attempt}/{MAX_ATTEMPTS}): {e} "
                    f"— thử lại sau {delay:.0f}s"
                )
                _update_status(sid, f"🔄 Thử lại {attempt+1}/{MAX_ATTEMPTS} sau {delay:.0f}s")
                time.sleep(delay)
                continue

            ts2 = datetime.now().strftime("%H:%M")
            if cat == "transient":
                label = f"{label} (đã thử {MAX_ATTEMPTS} lần)"
            _update_status(sid, f"❌ {ts2} {label}")
            logger.error(f"❌ STT {stt} lỗi [{cat}]: {e}")
            return


# ── Auto-refresh cookie ───────────────────────────────────────

def _check_refresh():
    try:
        accs = [a for a in get_accounts() if str(a.get("refresh","")).strip().lower() == "yes"]
        for a in accs:
            logger.info(f"🔄 Refresh cookie: '{a['ten_acc']}'...")
            try:
                export_all_accounts(target_acc=a["ten_acc"])
                from db import update_account_field
                update_account_field(a["id"], "refresh", "Done")
                logger.info(f"✅ '{a['ten_acc']}': cookie refreshed")
            except Exception as e:
                logger.error(f"❌ '{a['ten_acc']}': lỗi refresh: {e}")
    except Exception as e:
        logger.error(f"❌ _check_refresh: {e}")


# ── Main loop ─────────────────────────────────────────────────

def main():
    semaphore  = threading.Semaphore(MAX_WORKERS)
    running    = set()
    lock       = threading.Lock()
    active_threads = []
    last_reset_date    = None
    last_refresh_check = 0

    def _worker(item):
        key = item["id"]
        try:
            _run_one(item)
        finally:
            with lock:
                running.discard(key)
            semaphore.release()

    try:
        while True:
            now = datetime.now()

            # Reset đầu ngày — đưa MỌI dòng về Chờ (trừ 'X' tắt thủ công).
            # Không khớp đúng phút 00:01: vòng lặp ngủ 60s CỘNG thời gian giãn
            # cách giữa các worker, nên hoàn toàn có thể trôi qua phút đó và bỏ
            # lỡ reset cả ngày. Chỉ cần đã sang ngày mới là reset.
            if last_reset_date != now.date():
                first_run       = last_reset_date is None
                last_reset_date = now.date()
                if first_run:
                    # Khởi động giữa ngày: chỉ ghi nhận ngày hiện tại. Reset ở
                    # đây sẽ đưa các dòng ĐÃ đăng hôm nay về Chờ và đăng lại.
                    logger.info(f"📅 Bắt đầu theo dõi ngày {now.date()} — không reset")
                else:
                    from db import reset_schedules_to_wait
                    n = reset_schedules_to_wait(LOAI)
                    logger.info(f"🌅 Reset ngày mới — {LOAI}: {n} dòng về Chờ")

            # Refresh cookie mỗi 10 phút
            if time.time() - last_refresh_check >= 600:
                _check_refresh()
                last_refresh_check = time.time()

            logger.info(f"⏰ [{now.strftime('%H:%M:%S')}] Kiểm tra lịch {LOAI}...")

            rows = get_schedules(LOAI, trang_thai="Chờ")
            due  = [r for r in rows if r["gio_dang"] and _is_due(r["gio_dang"])]

            if due:
                logger.info(f"📋 {len(due)} dòng cần chạy")
                for item in due:
                    with lock:
                        if item["id"] in running:
                            continue
                    acquired = semaphore.acquire(blocking=False)
                    if not acquired:
                        logger.warning(f"⚠️  Đã đạt {MAX_WORKERS} workers — bỏ qua STT {item['stt']}")
                        continue
                    with lock:
                        running.add(item["id"])
                    t = threading.Thread(target=_worker, args=(item,), daemon=True)
                    t.start()
                    active_threads.append(t)
                    # Giãn cách ngẫu nhiên ~2–6s giữa mỗi lần khởi động worker
                    # (thay vì cố định 3s — tránh mẫu thời gian đều đặn)
                    time.sleep(jitter(4, pct=0.5, floor=1.5))
            else:
                logger.info("   (Không có dòng nào đến giờ)")

            active_threads[:] = [t for t in active_threads if t.is_alive()]
            next_check = now + timedelta(seconds=CHECK_EVERY_SEC)
            logger.info(f"   Kiểm tra tiếp lúc {next_check.strftime('%H:%M:%S')}\n")
            time.sleep(CHECK_EVERY_SEC)

    except KeyboardInterrupt:
        logger.info(f"\n⛔ Dừng scheduler {LOAI}.")
        for t in active_threads:
            t.join(timeout=120)


if __name__ == "__main__":
    main()
