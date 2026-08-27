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

import db
from db import (
    get_schedules, update_schedule_status,
    get_content_by_code, get_uid_groups_by_code,
    get_account_by_name, get_page_by_name,
    update_account_field,
)
from cookie_exporter import load_cookie
from utils import logger, jitter, CookieDeadError, ComposerBiChan, classify_error
from config import CHECK_EVERY_SEC, WINDOW_MINUTES, MAX_WORKERS

# ── Cấu hình ─────────────────────────────────────────────────
# Ưu tiên biến môi trường; server còn truyền thêm qua dòng lệnh để bên ngoài
# nhìn vào tiến trình là biết nó chạy loại nào (phục vụ việc diệt runner mồ côi).
LOAI = os.environ.get("SCHEDULER_LOAI", "").strip()
if not LOAI and len(sys.argv) > 1:
    LOAI = sys.argv[1].strip()
if not LOAI:
    logger.error("❌ Thiếu SCHEDULER_LOAI (env var hoặc tham số dòng lệnh)")
    sys.exit(1)

LOAI_SHEET_MAP = {
    "homestay": "Chéo Homestay",
    "thue":     "Chéo Thuê",
    "ban":      "Chéo Bán",
    "page":     "Đăng bài Page",
    "nuoi":     "Nuôi nick",
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

    # PHẢI truyền loại: mã content chỉ duy nhất trong một mảng, không duy nhất
    # toàn bảng. Thiếu nó thì lịch Bán lấy content của Thuê (13 mã đang trùng),
    # và sửa content Bán sẽ không ăn — hỏng im lặng.
    ct = get_content_by_code(ma_ct, LOAI)
    if not ct:
        raise Exception(f"Không tìm thấy mã content '{ma_ct}'")
    content  = ct.get("noi_dung", "").strip()
    link_anh = ct.get("link_anh", "").strip()

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
            # Link bài vừa đăng được lưu vào danh sách comment của ĐÚNG loại
            # lịch đang chạy — lưu nhầm thì acc homestay đi comment bài bán nhà.
            loai_comment=LOAI,
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


def _don_cache_sau_phien(acc_name: str):
    """
    Dọn cache trình duyệt của acc NGAY SAU khi phiên vừa đóng.

    Đúng thời điểm này là an toàn nhất: trình duyệt của acc đó chắc chắn đã
    thoát, mà các acc khác dùng profile riêng nên không đụng nhau. Cache mọc
    vài GB mỗi ngày nếu không dọn (đo thực tế: 143MB -> 8,3GB sau vài giờ).
    Không dọn nổi (file còn khoá) cũng không sao — lần chạy sau dọn tiếp.
    """
    if not acc_name:
        return
    try:
        from fb_common import find_profile_dir, don_cache_profile
        a = get_account_by_name(acc_name)
        don_cache_profile(find_profile_dir(acc_name, (a or {}).get("c_user", "")))
    except Exception as e:
        logger.warning(f"  ⚠️  Dọn cache '{acc_name}' lỗi (bỏ qua): {e}")


def _mark_cookie_dead(acc_name: str):
    """Đánh dấu account để dễ thấy trong tab Tài khoản, và đánh 'X😴' các slot
    lịch còn lại hôm nay của acc để nhìn bảng là biết ngay acc này ngưng chạy."""
    try:
        a = get_account_by_name(acc_name)
        if a:
            update_account_field(a["id"], "trang_thai", "Cookie hết hạn")
    except Exception as e:
        logger.warning(f"⚠️  Không đánh dấu được acc '{acc_name}' hết cookie: {e}")
    try:
        from db import danh_dau_x_con_lai_hom_nay
        n = danh_dau_x_con_lai_hom_nay(acc_name)
        if n:
            logger.info(f"  🚫 Đã đánh X {n} slot còn lại hôm nay của '{acc_name}'")
    except Exception as e:
        logger.warning(f"⚠️  Không đánh X được lịch của '{acc_name}': {e}")


def _run_warming(item: dict, ghi_chu: str = ""):
    """Slot đã bị chuyển thành nuôi nick — chạy phiên nuôi thay vì đăng bài.

    `ghi_chu` hiện thêm trên bảng lịch để phân biệt hai đường tới đây: slot vốn
    đã là nuôi nick, và slot đăng/comment bị đổi sang nuôi vì acc dính spam.
    """
    sid      = item["id"]
    stt      = item.get("stt", sid)
    acc_name = item["ten_acc"]
    ts       = datetime.now().strftime("%H:%M")

    logger.info(f"\n{'='*55}")
    logger.info(f"🌱 [{LOAI}] STT {stt} | {acc_name} | NUÔI NICK | {item['gio_dang']}")
    logger.info(f"{'='*55}")
    _update_status(sid, f"🌱 Đang nuôi {ts}" + (f" ({ghi_chu})" if ghi_chu else ""))

    try:
        from nuoi_nick import run_warming_session
        acc_data = get_account_by_name(acc_name)
        c_user_v = acc_data.get("c_user", "") if acc_data else ""
        run_warming_session(acc_name=acc_name, c_user=c_user_v)
        done = datetime.now().strftime("%H:%M")
        _update_status(sid, f"🌱 {done} (đã nuôi{' — ' + ghi_chu if ghi_chu else ''})")
        # Đánh mốc để lần sau biết đã tới nhịp nuôi chưa. Ghi cho CẢ hai đường —
        # slot nuôi vốn có và slot thay cho phiên bị chặn — không thì hai đường
        # đếm nhịp riêng và acc bị nuôi dày gấp đôi.
        db.ghi_nhan_nuoi(acc_name)
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


def _run_commenting(item: dict):
    """Slot đã bị chuyển thành phiên comment — đi comment thay vì đăng bài."""
    sid      = item["id"]
    stt      = item.get("stt", sid)
    acc_name = item["ten_acc"]
    ts       = datetime.now().strftime("%H:%M")

    logger.info(f"\n{'='*55}")
    logger.info(f"💬 [{LOAI}] STT {stt} | {acc_name} | COMMENT | {item['gio_dang']}")
    logger.info(f"{'='*55}")
    _update_status(sid, f"💬 Đang comment {ts}")

    try:
        from comment_bai import chay_phien_comment
        acc_data = get_account_by_name(acc_name)
        c_user_v = acc_data.get("c_user", "") if acc_data else ""
        # Một phiên kéo dài 12–18 phút. Cập nhật đếm sau mỗi bài để nhìn bảng
        # lịch là biết đang chạy tới đâu, thay vì đứng im ở "Đang comment".
        def _bao(da_xong, tong):
            _update_status(sid, f"💬 {da_xong}/{tong} · {ts}")

        # Page được phân công cho slot này — phiên comment ghé qua đó ở bước
        # khởi động, giống luồng đăng bài.
        kq   = chay_phien_comment(acc_name=acc_name, loai=LOAI, c_user=c_user_v,
                                  page_name=item.get("ten_page", ""),
                                  tien_trinh=_bao)
        done = datetime.now().strftime("%H:%M")
        if kq.get("bo_qua"):
            # Không có bài/câu để chạy KHÔNG phải lỗi acc — ghi rõ để khỏi đi
            # soi cookie hay trình duyệt trong khi chỉ là chưa nhập danh sách.
            _update_status(sid, f"💬 {done} bỏ qua: {kq['bo_qua']}")
        else:
            ok, tong = kq.get("da_comment", 0), kq.get("tong_bai", 0)
            phu = ""
            if kq.get("link_chet"):
                phu += f" · {kq['link_chet']} chết"
            if kq.get("loi"):
                phu += f" · {kq['loi']} lỗi"
            _update_status(sid, f"💬 {done} · {ok}/{tong} bài{phu}")
        logger.info(f"✅ STT {stt} comment xong: {kq}")
    except CookieDeadError:
        ts2 = datetime.now().strftime("%H:%M")
        _update_status(sid, f"❌ {ts2} Cookie hết hạn")
        logger.error(f"❌ STT {stt}: Cookie hết hạn khi comment — acc '{acc_name}'")
        _mark_cookie_dead(acc_name)
    except Exception as e:
        ts2 = datetime.now().strftime("%H:%M")
        cat, label = classify_error(e)
        # Bị chặn comment là tin quan trọng nhất của tính năng này — acc mất nốt
        # đường cuối cùng. Ghi hẳn ra trạng thái chứ đừng gộp vào "lỗi chung".
        if type(e).__name__ == "CommentRestricted":
            _update_status(sid, f"❌ {ts2} BỊ CHẶN COMMENT")
            logger.error(f"⛔ STT {stt}: acc '{acc_name}' bị chặn comment — {e}")
        else:
            _update_status(sid, f"❌ {ts2} Comment lỗi: {label}")
            logger.error(f"❌ STT {stt} comment lỗi [{cat}]: {e}")


def _bao_suc_khoe(stt, acc_name: str, hanh_dong: str, ly_do: str):
    """In ra log quyết định của bộ theo dõi sức khoẻ acc."""
    if hanh_dong == "nghi":
        logger.warning(f"😴 STT {stt}: cho acc '{acc_name}' nghỉ — {ly_do}")


def _run_one(item: dict):
    # Slot nuôi nick / comment đi đường riêng, không dùng retry của đăng bài.
    hd = item.get("hoat_dong") or "dang_bai"

    # Nghỉ đủ một tiếng rồi thì slot kế tiếp là PHIÊN NHỬ, và phiên nhử LUÔN là
    # đăng bài — kể cả khi slot đó vốn là slot comment. Một loại phiên nhử thì
    # chỉ có một đường code và một chỗ ghi nhận kết quả.
    #
    # Đổi được vì slot comment vẫn giữ nguyên ma_content / ma_nhom / tu_khoa:
    # lúc gen lịch, chuyển sang comment chỉ đổi mỗi cột hoat_dong.
    if hd == "comment" and db.acc_can_tham_do(item["ten_acc"]):
        logger.info(f"🔎 STT {item.get('stt', item['id'])} — acc "
                    f"'{item['ten_acc']}' hết giờ nghỉ, đổi slot comment thành "
                    f"PHIÊN NHỬ bằng đăng bài")
        hd = "dang_bai"
        item = {**item, "hoat_dong": "dang_bai"}

    # Acc đang nghỉ hoặc đã bị tắt thì bỏ qua slot. Ghi trạng thái riêng chứ
    # KHÔNG ghi "❌ lỗi": đếm nó là lỗi thì bộ theo dõi tự bơm phồng chính mình —
    # acc nghỉ sinh ra thêm "lỗi", thêm lỗi lại kéo dài nghỉ.
    ok_chay, vi_sao = db.acc_duoc_chay(item["ten_acc"], hd)
    if not ok_chay:
        # Acc dính spam: slot đăng/comment có thể chuyển thành phiên NUÔI NICK —
        # nhưng CHỈ KHI acc có tick Nuôi VÀ đã tới nhịp `nuoi_interval` của nó.
        #
        # Bản đầu của tôi đổi MỌI slot còn lại thành nuôi nick. Sai hai chuyện:
        #   - acc KHÔNG tick Nuôi cũng bị nuôi, trong khi người dùng cố ý không
        #     muốn (acc 'Ngân Nấm' đúng như vậy: 110 slot, 0 slot nuôi)
        #   - acc CÓ tick thì bị nuôi liên tục mỗi slot, thay vì giữ nhịp 150
        #     phút như lúc chạy bình thường
        # Không tới lượt nuôi thì slot nghỉ hẳn, đúng như trước.
        if db.acc_dang_spam_nghi(item["ten_acc"]) and hd in ("dang_bai", "comment"):
            if db.den_gio_nuoi(item["ten_acc"]):
                logger.info(f"🌱 STT {item.get('stt', item['id'])} — acc "
                            f"'{item['ten_acc']}' dính spam, đổi sang nuôi nick")
                _run_warming(item, ghi_chu="thay cho phiên bị spam")
                return
            _update_status(item["id"], f"😴 {vi_sao}")
            logger.info(f"😴 STT {item.get('stt', item['id'])} bỏ qua — "
                        f"acc '{item['ten_acc']}' {vi_sao} (chưa tới nhịp nuôi)")
            return
        _update_status(item["id"], f"😴 {vi_sao}")
        logger.info(f"😴 STT {item.get('stt', item['id'])} bỏ qua — "
                    f"acc '{item['ten_acc']}' {vi_sao}")
        return

    if hd == "nuoi_nick":
        _run_warming(item)
        return
    if hd == "comment":
        _run_commenting(item)
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
            db.ghi_nhan_phien_dang(acc_name, True)
            return

        except CookieDeadError:
            ts2 = datetime.now().strftime("%H:%M")
            _update_status(sid, f"❌ {ts2} Cookie hết hạn")
            logger.error(f"❌ STT {stt}: Cookie hết hạn — acc '{acc_name}' cần đăng nhập lại")
            _mark_cookie_dead(acc_name)
            # Cookie chết đã có trạng thái riêng và cách xử lý riêng (đăng nhập
            # lại), đừng tính vào sức khoẻ — nó không phải dấu hiệu bị FB chặn.
            return

        except ComposerBiChan:
            # Facebook chặn acc đăng: hộp thoại "Tạo bài viết" mở ra nhưng rỗng.
            # Cùng loại tín hiệu với "bài bị gỡ" nên đi ĐÚNG đường Spam: nghỉ,
            # slot còn lại chuyển sang nuôi nick, một tiếng sau nhử lại.
            #
            # KHÔNG để nó rơi vào nhánh lỗi chung bên dưới: ở đó nó bị ghi là
            # "lỗi [other]" và cộng vào lịch sử hỏng, tức là đẩy acc vào đường
            # nghỉ-vì-lỗi-kỹ-thuật — sai bản chất, và không chuyển slot sang
            # nuôi nick.
            ts2 = datetime.now().strftime("%H:%M")
            _update_status(sid, f"🚫 {ts2} Chặn Composer")
            n, moc = db.danh_dau_spam(acc_name, "Chặn Composer — hộp thoại đăng bài rỗng",
                                      ly_do="Lỗi Composer")
            logger.error(f"🚫 STT {stt}: acc '{acc_name}' BỊ CHẶN COMPOSER — "
                         f"{n} slot còn lại chuyển sang nuôi nick, "
                         f"nhử lại lúc {moc:%H:%M}")
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
            _bao_suc_khoe(stt, acc_name, *db.ghi_nhan_phien_dang(acc_name, False))
            return


# ── Auto-refresh cookie ───────────────────────────────────────

def _check_refresh():
    # Logic nằm ở cookie_exporter để nút "Refresh ngay" trên giao diện chạy y
    # hệt vòng lặp này — trước đây mỗi bên một bản dễ sửa lệch nhau.
    try:
        from cookie_exporter import refresh_pending_accounts
        refresh_pending_accounts()
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
            _don_cache_sau_phien(item.get("ten_acc", ""))
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

                # Quét dọn cache: bắt cả profile của acc đã ngừng dùng — loại
                # mà việc dọn-sau-mỗi-phiên không bao giờ chạm tới. Chạy lúc
                # khởi động và mỗi đầu ngày; profile đang mở được bỏ qua.
                try:
                    from fb_common import don_cache_tat_ca
                    don_cache_tat_ca()
                except Exception as e:
                    logger.warning(f"⚠️  Quét dọn cache lỗi (bỏ qua): {e}")

            # Refresh cookie mỗi 10 phút
            if time.time() - last_refresh_check >= 600:
                _check_refresh()
                last_refresh_check = time.time()

            logger.info(f"⏰ [{now.strftime('%H:%M:%S')}] Kiểm tra lịch {LOAI}...")

            # Acc dính spam đã nghỉ đủ giờ thì trả lịch về 'Chờ' để chạy MỘT
            # phiên thăm dò. Vẫn giữ trạng thái Spam — được thì phiên đó tự thả,
            # hỏng thì tự nghỉ thêm một lượt. Quét mỗi vòng (60s).
            try:
                for _hs in db.mo_duong_tham_do():
                    logger.info(f"🔍 '{_hs['ten_acc']}' hết giờ nghỉ spam — mở "
                                f"{_hs['so_slot']} slot để chạy phiên thăm dò")
            except Exception as e:
                logger.warning(f"⚠️  Không mở được đường thăm dò: {e}")

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
