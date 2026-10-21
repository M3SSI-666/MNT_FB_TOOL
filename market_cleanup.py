"""
================================================================================
market_cleanup.py — Dọn (tự XÓA) bài niêm yết Marketplace quá X ngày
================================================================================
Bài niêm yết cũ đọng lại làm trang bán của nick loãng + dễ bị coi là đăng trùng.
Module này để nick tự ghé trang "Bài niêm yết của bạn" (định kỳ 1 lần/ngày, do
runner của mảng gọi — xem scheduler._xoa_mkt_worker), ĐỌC danh sách + NGÀY NIÊM
YẾT từng bài, rồi XÓA những bài quá hạn. Có chế độ CHẠY THỬ (chay_thu=True): chỉ
liệt kê bài quá hạn, KHÔNG xóa (dùng khi cần xem trước; runner KHÔNG dùng).

NGUYÊN TẮC AN TOÀN:
  - Xóa KHÔNG hồi lại được → mặc định TẮT (db setting mkt_xoa_bat=0). Bật là tự
    xóa, ghi log nội bộ, KHÔNG báo Telegram.
  - Chỉ xóa bài đọc được tuổi RÕ RÀNG và > ngưỡng. Tuổi không đọc được (None) thì
    BỎ QUA, tuyệt đối không xóa (thà sót còn hơn xóa nhầm).

DOM đã ĐO THẬT trên nick Sa Tran Anh 21/10/2026 (xem huy_hieu/scratchpad):
  - Trang `/marketplace/you/selling/` ở VIEWPORT RỘNG chỉ hiện thẻ tóm tắt; ở
    VIEWPORT HẸP (~700px) mới ra DANH SÁCH DỌC từng bài. → ép hẹp bằng
    set_viewport_size trước khi đọc.
  - Mỗi dòng bài có nút "Đánh dấu là hết hàng" + chữ "Ngày niêm yết: DD/MM"
    (ngày tuyệt đối, KHÔNG năm — suy năm từ hôm nay).
  - Nút "..." của dòng: aria-label = "Lựa chọn khác cho <tiêu đề>" (có cả bản
    ẩn/ảo hóa → chỉ bấm cái ĐANG HIỆN). Menu có mục "Xóa bài niêm yết".
  - Bấm "Xóa bài niêm yết" → hộp xác nhận "Bạn có chắc chắn..." → nút "Xóa".
================================================================================
"""

import asyncio
import re
import random
import datetime

from utils import logger, CookieDeadError
from config import HEADLESS

# 4 lý do FB hỏi SAU khi bấm Xóa ("Bạn đã bán mặt hàng này chưa?") — chọn NGẪU
# NHIÊN 1 để trả lời cho tự nhiên. Đo thật trên nick Sa Tran Anh 21/10/2026. Đây
# là khảo sát TÙY CHỌN: bài đã bị xóa ở bước xác nhận "Xóa", trả lời hay không
# không ảnh hưởng việc xóa.
LY_DO_XOA = [
    "Tôi đã bán trên Facebook rồi",
    "Tôi bán ở nơi khác rồi",
    "Tôi chưa bán",
    "Tôi không muốn trả lời",
]

# Trang quản lý bài niêm yết đang bán của chính nick.
SELLING_URL = "https://www.facebook.com/marketplace/you/selling/"
# Ép khổ hẹp để FB render DANH SÁCH DỌC (có "Ngày niêm yết" + nút "..." mỗi dòng).
VIEWPORT_HEP = {"width": 700, "height": 900}
# DOM đã đo thật (đã chạy xóa thật thành công) nên cho phép xóa thật. Còn False
# thì xoa_bai_cu tự ép về chạy thử (chốt an toàn).
_XOA_DA_DO_DOM = True

# Trần số bài xóa mỗi phiên — chặn vòng lặp xóa chạy mất kiểm soát nếu DOM đổi.
_TRAN_XOA = 30


# ── Đọc tuổi ────────────────────────────────────────────────────────────────
_RE_NGAY_NY = re.compile(r"Ngày niêm yết:\s*(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?")


def doc_ngay_niem_yet(text: str, hom_nay: datetime.date = None):
    """'... Ngày niêm yết: 8/10' → số NGÀY tính tới hôm nay. Ngày dạng DD/MM (có
    thể kèm /YYYY). Không có năm thì suy theo hôm nay; nếu ra tương lai (vd hôm
    nay đầu tháng 1, bài ghi 30/12) thì lùi 1 năm. Không khớp → None."""
    m = _RE_NGAY_NY.search(text or "")
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    today = hom_nay or datetime.date.today()
    if m.group(3):
        yr = int(m.group(3))
        if yr < 100:
            yr += 2000
    else:
        yr = today.year
    try:
        ngay = datetime.date(yr, mo, d)
    except ValueError:
        return None
    if not m.group(3) and ngay > today:      # DD/MM không năm mà ra tương lai
        try:
            ngay = datetime.date(yr - 1, mo, d)
        except ValueError:
            return None
    return max(0, (today - ngay).days)


# Bộ đọc tuổi TƯƠNG ĐỐI (dự phòng / nơi khác hiển thị '... trước'). Trả số ngày
# hoặc None. CHỈ truyền chuỗi tuổi (một dòng), không truyền cả card.
_DV_NGAY = [
    (r"(\d+)\s*phút", 0), (r"(\d+)\s*giờ", 0),
    (r"(\d+)\s*ngày", 1), (r"(\d+)\s*tuần", 7),
    (r"(\d+)\s*tháng", 30), (r"(\d+)\s*năm", 365),
    (r"(\d+)\s*(?:minute|min|hour|hr)s?", 0),
    (r"(\d+)\s*days?", 1), (r"(\d+)\s*weeks?", 7),
    (r"(\d+)\s*months?", 30), (r"(\d+)\s*years?", 365),
]


def doc_tuoi_ngay(text: str):
    """'5 ngày trước' → 5; 'hôm qua' → 1; '3 giờ trước' / 'vừa xong' → 0. Không
    nhận ra → None."""
    if not text:
        return None
    s = text.lower().strip()
    if "hôm qua" in s or "yesterday" in s:
        return 1
    if ("hôm nay" in s or "vừa xong" in s or "just now" in s
            or re.search(r"\btoday\b", s)):
        return 0
    for pat, nhan in _DV_NGAY:
        m = re.search(pat, s)
        if m:
            return int(m.group(1)) * nhan if nhan else 0
    if re.search(r"\b(một|1)\s*ngày", s) or re.search(r"\ba\s+day\b", s):
        return 1
    if re.search(r"\ban?\s+(hour|minute)\b", s):
        return 0
    if re.search(r"\b(một|1)\s*tuần", s) or re.search(r"\ba\s+week\b", s):
        return 7
    return None


_CO_MOC = re.compile(
    r"(trước|vừa xong|hôm nay|hôm qua|ago|yesterday|today|just now)",
    re.IGNORECASE)


def _tim_tuoi(lines: list):
    """Trong các dòng của card, lấy tuổi từ dòng có mốc rõ ràng ('… trước', 'hôm
    qua'…). Tránh đọc nhầm số trong tiêu đề/giá. Không có → None."""
    for ln in lines:
        if _CO_MOC.search(ln or ""):
            t = doc_tuoi_ngay(ln)
            if t is not None:
                return t
    return None


def loc_qua_han(bai: list, so_ngay: int) -> list:
    """Bài có tuổi RÕ RÀNG và > so_ngay. Tuổi None (không đọc được) → bỏ qua."""
    return [b for b in bai
            if b.get("tuoi") is not None and b["tuoi"] > max(0, int(so_ngay))]


# ── Đọc danh sách bài trên trang selling (viewport hẹp) ──────────────────────
# Mỗi dòng bài = khối chứa nút "Đánh dấu là hết hàng" và chữ "Ngày niêm yết:".
_JS_DOC_ROWS = r"""
() => {
  const rows = [], seen = new Set();
  const btns = [...document.querySelectorAll('[role="button"],button')]
    .filter(b => /Đánh dấu là hết hàng/i.test(b.innerText || ''));
  for (const b of btns) {
    let row = b;
    for (let i = 0; i < 8 && row.parentElement; i++) {
      row = row.parentElement;
      if (/Ngày niêm yết/i.test(row.innerText || '')) break;
    }
    const txt = (row.innerText || '').trim();
    if (!txt || !/Ngày niêm yết/i.test(txt) || seen.has(txt)) continue;
    seen.add(txt);
    const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
    rows.push({ tieu_de: lines[0] || '', text: txt });
  }
  return rows;
}
"""

_RE_NGAY_HIEN = re.compile(r"Ngày niêm yết:\s*[\d/]+")


def _trich_ngay(text: str) -> str:
    m = _RE_NGAY_HIEN.search(text or "")
    return m.group(0) if m else ""


async def _mo_selling(p, acc_name, c_user, headless):
    from nuoi_nick import _open_context, _dismiss_pin_dialog
    ctx, page = await _open_context(p, acc_name, c_user, headless)
    await page.set_viewport_size(VIEWPORT_HEP)   # ép ra danh sách dọc
    try:
        await _dismiss_pin_dialog(page)
    except Exception:
        pass
    await page.goto(SELLING_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(7000)
    for _ in range(6):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(800)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(500)
    return ctx, page


async def _doc_rows(page, hom_nay) -> list:
    raw = await page.evaluate(_JS_DOC_ROWS)
    out = []
    for r in raw:
        out.append({
            "tieu_de":   r.get("tieu_de", ""),
            "ngay_text": _trich_ngay(r.get("text", "")),
            "tuoi":      doc_ngay_niem_yet(r.get("text", ""), hom_nay),
        })
    return out


async def _quet(acc_name, c_user, headless) -> list:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        ctx, page = await _mo_selling(p, acc_name, c_user, headless)
        try:
            bai = await _doc_rows(page, datetime.date.today())
            logger.info(f"  🧹 Bài niêm yết [{acc_name}]: đọc {len(bai)} bài")
            return bai
        finally:
            try:
                await ctx.close()
            except Exception:
                pass


def quet_bai_niem_yet(acc_name: str, c_user: str = "", headless=None) -> list:
    """Sync — đọc danh sách bài niêm yết đang bán của nick (KHÔNG xóa). Trả
    [{tieu_de, ngay_text, tuoi (ngày|None)}]. Lỗi cookie → CookieDeadError; lỗi
    khác → log rồi trả [] (đọc thụ động)."""
    try:
        return asyncio.run(_quet(acc_name, c_user,
                                 HEADLESS if headless is None else headless))
    except CookieDeadError:
        raise
    except Exception as e:
        logger.warning(f"⚠️  Quét bài niêm yết [{acc_name}] lỗi (bỏ qua): {e}")
        return []


async def _tra_loi_khao_sat(page):
    """Sau khi xóa, FB hiện hộp 'Bạn đã bán mặt hàng này chưa?' với 4 lý do +
    nút 'Tiếp' (nút mờ tới khi chọn 1 lý do). Chọn NGẪU NHIÊN 1 lý do rồi bấm
    Tiếp. Là khảo sát TÙY CHỌN (bài đã bị xóa) → lỗi thì bỏ qua, trả None."""
    try:
        ks = page.get_by_role("dialog").filter(has_text="Bạn đã bán mặt hàng này")
        if not await ks.count():
            return None
        ld = random.choice(LY_DO_XOA)
        await ks.last.get_by_text(ld, exact=True).first.click(timeout=4000)
        await page.wait_for_timeout(700)
        await ks.last.get_by_role("button", name="Tiếp").first.click(timeout=4000)
        await page.wait_for_timeout(1500)
        return ld
    except Exception as e:
        logger.info(f"  (khảo sát lý do xóa — bỏ qua: {e})")
        return None


async def _xoa(acc_name, c_user, so_ngay, headless) -> int:
    """Mở trang selling rồi lặp: tìm 1 dòng QUÁ HẠN → bấm '...' → 'Xóa bài niêm
    yết' → xác nhận 'Xóa' → tải lại → lặp. Tải lại mỗi lần để DOM sạch, tránh
    phần tử cũ. Trả số bài đã xóa."""
    from playwright.async_api import async_playwright
    hom_nay = datetime.date.today()
    da_xoa = 0
    async with async_playwright() as p:
        ctx, page = await _mo_selling(p, acc_name, c_user, headless)
        try:
            for _ in range(_TRAN_XOA):
                # Tìm nút '...' ĐANG HIỆN của một dòng quá hạn.
                btns = page.locator('[aria-label^="Lựa chọn khác cho"]')
                n = await btns.count()
                muc_tieu = None
                for i in range(n):
                    el = btns.nth(i)
                    try:
                        if not await el.is_visible():
                            continue
                        row_text = await el.evaluate(
                            "el => { let r = el;"
                            " for (let i=0;i<8&&r.parentElement;i++){ r=r.parentElement;"
                            "  if(/Ngày niêm yết/.test(r.innerText)) return r.innerText; }"
                            " return el.innerText; }")
                    except Exception:
                        continue
                    tuoi = doc_ngay_niem_yet(row_text, hom_nay)
                    if tuoi is not None and tuoi > max(0, int(so_ngay)):
                        muc_tieu = el
                        break
                if muc_tieu is None:
                    break   # không còn bài quá hạn
                await muc_tieu.scroll_into_view_if_needed(timeout=5000)
                await muc_tieu.click(timeout=6000)
                await page.wait_for_timeout(1500)
                mi = page.get_by_role("menuitem", name="Xóa bài niêm yết")
                if not await mi.count():
                    await page.keyboard.press("Escape")
                    break
                await mi.first.click(timeout=6000)
                await page.wait_for_timeout(2000)
                # Hộp xác nhận → nút 'Xóa' (đúng chữ, không phải 'Xóa bài niêm yết').
                nut_xoa = page.locator('[role="dialog"]').last.get_by_role(
                    "button", name="Xóa", exact=True)
                if not await nut_xoa.count():
                    await page.keyboard.press("Escape")
                    break
                await nut_xoa.first.click(timeout=6000)
                await page.wait_for_timeout(2500)
                # FB hỏi lý do xóa (4 lựa chọn) → chọn ngẫu nhiên 1 + Tiếp. Bài
                # đã bị xóa ở bước trên rồi; đây chỉ cho tự nhiên, lỗi thì bỏ qua.
                ld = await _tra_loi_khao_sat(page)
                await page.wait_for_timeout(1200)
                da_xoa += 1
                logger.info(f"  🧹 [{acc_name}] đã xóa 1 bài quá hạn ({da_xoa})"
                            + (f" · lý do: {ld}" if ld else ""))
                # Tải lại cho DOM sạch rồi quét tiếp.
                await page.goto(SELLING_URL, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(6000)
            return da_xoa
        finally:
            try:
                await ctx.close()
            except Exception:
                pass


def xoa_bai_cu(acc_name: str, c_user: str = "", so_ngay: int = 3,
               chay_thu: bool = False, headless=None) -> dict:
    """Đọc bài niêm yết → lọc quá `so_ngay` ngày → xóa. `chay_thu=True` thì CHỈ
    liệt kê, không xóa (dùng khi cần xem trước, không nối vào runner).

    Trả {tong, qua_han:[{tieu_de,tuoi,ngay_text}], da_xoa, chay_thu}. Khi
    `_XOA_DA_DO_DOM` còn False thì ÉP chạy thử (chốt an toàn)."""
    bai = quet_bai_niem_yet(acc_name, c_user, headless=headless)
    qua_han = loc_qua_han(bai, so_ngay)
    ep_thu = chay_thu or not _XOA_DA_DO_DOM
    kq = {
        "tong": len(bai),
        "qua_han": [{"tieu_de": b.get("tieu_de", ""), "tuoi": b.get("tuoi"),
                     "ngay_text": b.get("ngay_text", "")} for b in qua_han],
        "da_xoa": 0,
        "chay_thu": ep_thu,
    }
    if ep_thu or not qua_han:
        if qua_han:
            logger.info(f"  🧹 [{acc_name}] (chạy thử) {len(qua_han)} bài quá "
                        f"{so_ngay} ngày — CHƯA xóa")
        return kq
    try:
        kq["da_xoa"] = asyncio.run(
            _xoa(acc_name, c_user, so_ngay,
                 HEADLESS if headless is None else headless))
    except CookieDeadError:
        raise
    except Exception as e:
        logger.warning(f"⚠️  Xóa bài niêm yết [{acc_name}] lỗi (bỏ qua): {e}")
    return kq
