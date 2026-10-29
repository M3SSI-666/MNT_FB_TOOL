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


# Cảnh báo TRÙNG của Facebook, hiện ở mục "Cần chú ý" (đo thật 28/10, Dang Xuan
# Duy): "Bài niêm yết này có vẻ giống một bài niêm yết khác nên chúng tôi không
# đăng. Hãy xóa bài niêm yết này rồi thử lại." — bài này KHÔNG được hiển thị, giữ
# lại chỉ làm loãng trang bán → xóa luôn, bất kể mới đăng bao lâu.
_RE_TRUNG = re.compile(
    r"giống một bài niêm yết khác|không đăng\.\s*Hãy xóa bài niêm yết"
    r"|similar to another listing", re.IGNORECASE)


def la_bi_trung(text: str) -> bool:
    """Thẻ bài có cảnh báo trùng của Facebook không."""
    return bool(_RE_TRUNG.search(text or ""))


_RE_GIA_DONG = re.compile(r"^\s*[\d.,]+\s*₫\s*$")


def _tieu_de(text: str) -> str:
    """Dòng tiêu đề của thẻ bài = dòng NGAY TRƯỚC dòng giá ("338 ₫").

    Không lấy dòng đầu: thẻ là bài DUY NHẤT còn lại của một mục thì khối leo lên
    (_JS_LEO_THE) gồm cả tiêu đề mục — đo thật 29/10, Dang Xuan Duy: "Cần chú ý\\nẨn\\n
    BÁN 3PN Parkhill…" → lấy nhầm "Cần chú ý" làm tiêu đề, không khớp bài trùng đã ghi
    ở khổ rộng, bài đó sót lại. Không có dòng giá thì lấy dòng đầu không phải cảnh báo."""
    dong = [ln.strip() for ln in (text or "").split("\n")]
    dong = [ln for ln in dong if ln and not la_bi_trung(ln)
            and not ln.lower().startswith("bài niêm yết này")]
    for i, ln in enumerate(dong):
        if _RE_GIA_DONG.match(ln) and i > 0:
            return dong[i - 1]
    return dong[0] if dong else ""


_RE_GIA = re.compile(r"^\s*[\d.,]+\s*₫\s*$")


def chu_ky_the(text: str) -> tuple:
    """(tiêu đề, giá, ngày niêm yết) của một thẻ bài — để nhận ra CÙNG MỘT bài ở hai
    khổ màn hình. Giá Marketplace là số ngẫu nhiên mỗi bài (332 ₫, 82 ₫…) nên bộ ba
    này gần như chỉ khớp đúng một bài."""
    gia = next((ln.strip() for ln in (text or "").split("\n") if _RE_GIA.match(ln)), "")
    return (_tieu_de(text), gia, _trich_ngay(text))


def loc_can_xoa(bai: list, so_ngay: int) -> list:
    """Bài phải xóa: QUÁ HẠN (tuổi rõ ràng > so_ngay) HOẶC bị cảnh báo TRÙNG."""
    return [b for b in bai
            if b.get("trung")
            or (b.get("tuoi") is not None and b["tuoi"] > max(0, int(so_ngay)))]


# Leo từ một phần tử lên tới KHỐI LỚN NHẤT vẫn chỉ chứa ĐÚNG MỘT "Ngày niêm yết:"
# — tức trọn thẻ của MỘT bài, gồm cả dòng cảnh báo trùng đứng trên tiêu đề (bản
# đầu dừng ở khối nhỏ nhất có ngày nên có thể hụt dòng cảnh báo). Gặp khối chứa
# từ 2 ngày trở lên là đã sang khối nhiều bài → thôi leo.
_JS_LEO_THE = r"""
function leoThe(el) {
  let r = el, ok = null;
  for (let i = 0; i < 12 && r.parentElement; i++) {
    r = r.parentElement;
    const n = ((r.innerText || '').match(/Ngày niêm yết:/g) || []).length;
    if (n === 1) ok = r; else if (n > 1) break;
  }
  return ok ? (ok.innerText || '') : (el.innerText || '');
}
"""

# ── Đọc danh sách bài trên trang selling (viewport hẹp) ──────────────────────
# Mỗi dòng bài = khối chứa nút "Đánh dấu là hết hàng" và chữ "Ngày niêm yết:".
_JS_DOC_ROWS = "() => {" + _JS_LEO_THE + r"""
  const rows = [], seen = new Set();
  // "hết hàng" = bài Còn hàng; "đã bán" = bài Đang hoạt động (đăng kèm nhóm) —
  // 28/10 bài 14/10 của Alex Tường là kiểu sau, bản đầu không đếm tới.
  const btns = [...document.querySelectorAll('[role="button"],button')]
    .filter(b => /Đánh dấu là (hết hàng|đã bán)/i.test(b.innerText || ''));
  for (const b of btns) {
    const txt = leoThe(b).trim();
    if (!txt || !/Ngày niêm yết/i.test(txt) || seen.has(txt)) continue;
    seen.add(txt);
    rows.push({ text: txt });
  }
  return rows;
}
"""

# Chữ của TRỌN thẻ bài quanh nút "..." (dùng lúc xóa).
_JS_THE_CUA_NUT = "el => {" + _JS_LEO_THE + " return leoThe(el); }"

# Chữ của các thẻ CÓ dòng cảnh báo trùng (đọc ở khổ RỘNG — xem doc_bai_trung).
_JS_THE_CANH_BAO = "() => {" + _JS_LEO_THE + r"""
  const ra = [], seen = new Set();
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    if (!/giống một bài niêm yết khác|similar to another listing/i.test(n.textContent)) continue;
    const t = leoThe(n.parentElement).trim();
    if (t && /Ngày niêm yết/.test(t) && !seen.has(t)) { seen.add(t); ra.push(t); }
  }
  return ra;
}
"""

VIEWPORT_RONG = {"width": 1280, "height": 900}


async def doc_bai_trung(page) -> set:
    """Chữ ký (chu_ky_the) các bài bị Facebook cảnh báo TRÙNG.

    Đo thật 28/10 (Dang Xuan Duy): ở khổ HẸP (danh sách dọc, nơi phần mềm đọc và
    xóa) Facebook KHÔNG hiện dòng cảnh báo trùng — 0 lần; ở khổ RỘNG thì có (6 lần).
    Bản trước chỉ đọc khổ hẹp nên mọi phiên dọn đều ghi "bị cảnh báo trùng: 0". Nên:
    phóng rộng đọc cảnh báo → ghi chữ ký → trả về khổ hẹp (cuộn nạp lại) để xóa."""
    try:
        await page.set_viewport_size(VIEWPORT_RONG)
        await page.wait_for_timeout(3500)
        the = await page.evaluate(_JS_THE_CANH_BAO)
    except Exception:
        the = []
    finally:
        try:
            await page.set_viewport_size(VIEWPORT_HEP)
            await page.wait_for_timeout(2500)
            await _cuon_tai_het(page)
        except Exception:
            pass
    return {chu_ky_the(t) for t in the if chu_ky_the(t)[0]}

_RE_NGAY_HIEN = re.compile(r"Ngày niêm yết:\s*[\d/]+")


def _trich_ngay(text: str) -> str:
    m = _RE_NGAY_HIEN.search(text or "")
    return m.group(0) if m else ""


_JS_DEM_DONG = "() => (document.body.innerText.match(/Ngày niêm yết/g) || []).length"


async def _cuon_tai_het(page, toi_da: int = 25):
    """Cuộn xuống đáy tới khi số dòng 'Ngày niêm yết' thôi tăng — FB chỉ nạp
    thêm bài khi cuộn tới, mà danh sách xếp MỚI → CŨ nên bài quá hạn luôn nằm
    dưới cùng. Cuộn xong về lại đầu trang.

    Phải KIÊN NHẪN: 27/10 bản đầu (chờ 0,9s, dừng sau 2 lượt đứng yên) dừng sớm
    ở nick 43 bài khi FB nạp chậm — Mai Trung Thao xóa 5/18 rồi tưởng hết."""
    truoc, dung_yen = -1, 0
    for _ in range(toi_da):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)
        n = await page.evaluate(_JS_DEM_DONG)
        dung_yen = dung_yen + 1 if n == truoc else 0
        if dung_yen >= 3:            # 3 lượt liền (~4,5s) không thêm dòng → đã đủ
            break
        truoc = n
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(500)


async def _tai_selling(page):
    """Mở (hoặc tải lại) trang selling rồi cuộn cho nạp ĐỦ danh sách."""
    await page.goto(SELLING_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(7000)
    # Khung "Đoạn chat" + hộp "Tạo mã PIN" của Messenger hay bật lên ĐÈ các bài dưới
    # cùng (đo thật 28/10, Alex Tường) → bấm "..." của bài cũ bị Timeout. Đóng trước.
    try:
        from nuoi_nick import _dismiss_pin_dialog
        await _dismiss_pin_dialog(page)
        await page.keyboard.press("Escape")
    except Exception:
        pass
    await _cuon_tai_het(page)


async def _mo_selling(p, acc_name, c_user, headless):
    from nuoi_nick import _open_context, _dismiss_pin_dialog
    ctx, page = await _open_context(p, acc_name, c_user, headless)
    await page.set_viewport_size(VIEWPORT_HEP)   # ép ra danh sách dọc
    try:
        await _dismiss_pin_dialog(page)
    except Exception:
        pass
    await _tai_selling(page)
    return ctx, page


async def _doc_rows(page, hom_nay, ky_trung: set = frozenset()) -> list:
    raw = await page.evaluate(_JS_DOC_ROWS)
    out = []
    for r in raw:
        txt = r.get("text", "")
        out.append({
            "tieu_de":   _tieu_de(txt),
            "ngay_text": _trich_ngay(txt),
            "tuoi":      doc_ngay_niem_yet(txt, hom_nay),
            "trung":     la_bi_trung(txt) or chu_ky_the(txt) in ky_trung,
        })
    return out


async def _quet(acc_name, c_user, headless) -> list:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        ctx, page = await _mo_selling(p, acc_name, c_user, headless)
        try:
            ky_trung = await doc_bai_trung(page)
            bai = await _doc_rows(page, datetime.date.today(), ky_trung)
            logger.info(f"  🧹 Bài niêm yết [{acc_name}]: đọc {len(bai)} bài"
                        + (f", {len(ky_trung)} bài bị cảnh báo trùng" if ky_trung else ""))
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


async def _xoa(acc_name, c_user, so_ngay, headless, chi_trung: bool = False) -> int:
    """`chi_trung=True`: CHỈ xóa bài bị cảnh báo trùng, không đụng bài quá hạn (dùng
    ngay sau mỗi phiên đăng Marketplace — xem scheduler).

    Mở trang selling rồi lặp: tìm 1 dòng QUÁ HẠN → bấm '...' → 'Xóa bài niêm
    yết' → xác nhận 'Xóa' → tải lại → lặp. Tải lại mỗi lần để DOM sạch, tránh
    phần tử cũ. Trả số bài đã xóa.

    Tải lại xong PHẢI cuộn cho nạp đủ danh sách (_tai_selling). Bản trước tải
    lại mà không cuộn: bài cũ nằm dưới cùng chưa được FB nạp → tưởng hết bài
    quá hạn → mỗi phiên chỉ xóa 1 bài. Đo thật 26/10: "xóa 1/10 bài quá 2 ngày"
    ở Dang Xuan Duy, Alex Tường; 1/7 Tien Duongg; 1/4 Hoàng Alex."""
    from playwright.async_api import async_playwright
    hom_nay = datetime.date.today()
    da_xoa = 0

    bo_qua = set()      # chữ ký các bài đã xóa HỎNG — không chọn lại trong phiên này
    ky_trung = set()    # chữ ký bài bị cảnh báo trùng (đọc ở khổ rộng — doc_bai_trung)

    async def _tim_muc_tieu():
        """(nút '...', chữ ký, tiêu đề, ngày, lý do) của một bài PHẢI XÓA đang
        hiện mà chưa bị bỏ qua; không có → None. Phải xóa = bị cảnh báo TRÙNG
        (bất kể tuổi) hoặc QUÁ HẠN.

        AN TOÀN: chữ quanh nút phải chứa ĐÚNG MỘT "Ngày niêm yết". Leo khối cha
        mà ra khối chứa nhiều bài thì không biết ngày nào của bài nào — bỏ, thà
        sót còn hơn xóa nhầm bài mới."""
        btns = page.locator('[aria-label^="Lựa chọn khác cho"]')
        n = await btns.count()
        for i in range(n):
            el = btns.nth(i)
            try:
                if not await el.is_visible():
                    continue
                row_text = await el.evaluate(_JS_THE_CUA_NUT)
            except Exception:
                continue
            if len(_RE_NGAY_HIEN.findall(row_text or "")) != 1:
                continue
            trung = la_bi_trung(row_text) or chu_ky_the(row_text) in ky_trung
            tuoi = doc_ngay_niem_yet(row_text, hom_nay)
            qua_han = (not chi_trung) and tuoi is not None and tuoi > max(0, int(so_ngay))
            if not (trung or qua_han):
                continue
            tieu_de, ngay = _tieu_de(row_text), _trich_ngay(row_text)
            ky = f"{tieu_de}|{ngay}|{'trung' if trung else ''}"
            if ky in bo_qua:
                continue
            return el, ky, tieu_de, ngay, ("bị cảnh báo trùng" if trung else "quá hạn")
        return None

    async def _bam(el):
        """Bấm bình thường; bị phần tử khác che (27/10: 'Locator.click: Timeout
        6000ms' ở 5 acc) thì bấm thẳng bằng JS."""
        try:
            await el.click(timeout=6000)
        except Exception:
            await el.evaluate("el => el.click()")

    async def _xoa_mot(muc_tieu) -> str | None:
        """Xóa MỘT bài: '...' → mục xóa → xác nhận 'Xóa'. Trả lý do khảo sát
        (hoặc ''); ném lỗi nếu hỏng ở bước nào."""
        try:
            await muc_tieu.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass
        await _bam(muc_tieu)
        # CHỜ menu hiện ra, không chờ cứng 1,5s: đo thật 28/10 (Alex Tường, bài 14/10
        # "Đang hoạt động"): menu kiểu bài này có 12 mục, mục "Xóa bài niêm yết" gần
        # cuối, hiện chậm — chờ cứng là tìm lúc menu chưa vẽ xong → báo "không có mục
        # xóa" dù mục đó có thật.
        try:
            await page.get_by_role("menuitem").first.wait_for(state="visible", timeout=5000)
            await page.wait_for_timeout(600)
        except Exception:
            await page.wait_for_timeout(1500)
        # Bài đăng kèm nhóm ("Đang hoạt động") có thể đặt tên mục khác. Chỉ nhận
        # đúng các tên XÓA BÀI — KHÔNG lấy kiểu "Xóa khỏi nhóm" (chỉ gỡ khỏi
        # nhóm, bài niêm yết vẫn còn).
        mi = None
        for ten in ("Xóa bài niêm yết", "Xóa bài viết", "Xóa"):
            loc = page.get_by_role("menuitem", name=ten, exact=True)
            if await loc.count():
                mi = loc.first
                break
        if mi is None:
            # Ghi lại menu THẬT có những mục gì — để biết bài kiểu này (vd "Đang hoạt
            # động", đăng kèm nhóm) đặt tên mục xóa ra sao, thay vì đoán.
            try:
                ten_muc = [((await m.inner_text()) or "").strip()
                           for m in await page.get_by_role("menuitem").all()][:15]
            except Exception:
                ten_muc = []
            await page.keyboard.press("Escape")
            raise RuntimeError(f"menu không có mục xóa bài — các mục: {ten_muc}")
        await _bam(mi)
        await page.wait_for_timeout(2000)
        # Hộp xác nhận → nút 'Xóa' (đúng chữ, không phải 'Xóa bài niêm yết').
        hop = page.locator('[role="dialog"]').last
        nut_xoa = hop.get_by_role("button", name="Xóa", exact=True)
        if not await nut_xoa.count():
            nut_xoa = hop.get_by_role("button", name="Xóa bài niêm yết", exact=True)
        if not await nut_xoa.count():
            await page.keyboard.press("Escape")
            raise RuntimeError("không thấy nút xác nhận 'Xóa'")
        await _bam(nut_xoa.first)
        await page.wait_for_timeout(2500)
        # FB hỏi lý do xóa (4 lựa chọn) → chọn ngẫu nhiên 1 + Tiếp. Bài đã bị
        # xóa ở bước trên rồi; đây chỉ cho tự nhiên, lỗi thì bỏ qua.
        ld = await _tra_loi_khao_sat(page)
        await page.wait_for_timeout(1200)
        return ld or ""

    async with async_playwright() as p:
        ctx, page = await _mo_selling(p, acc_name, c_user, headless)
        loi_lien = 0
        try:
            ky_trung.update(await doc_bai_trung(page))
            if chi_trung and not ky_trung:
                return da_xoa                       # không có bài trùng → xong ngay
            for _ in range(_TRAN_XOA + 5):          # +5 lượt dành cho bài bị bỏ qua
                if da_xoa >= _TRAN_XOA:
                    break
                ky = tieu_de = ngay = ""
                try:
                    tim = await _tim_muc_tieu()
                    if tim is None:
                        # Chưa thấy → cuộn nạp thêm một lượt nữa rồi mới kết luận.
                        await _cuon_tai_het(page)
                        tim = await _tim_muc_tieu()
                    if tim is None:
                        break   # không còn bài phải xóa
                    muc_tieu, ky, tieu_de, ngay, vi_sao = tim
                    ld = await _xoa_mot(muc_tieu)
                except CookieDeadError:
                    raise
                except Exception as e:
                    # MỘT bài hỏng không được bỏ cả phiên, và cũng không được
                    # CHẶN các bài khác: 28/10 bài 14/10 ("Đang hoạt động") của
                    # Alex Tường lần nào cũng hỏng → bản trước chọn lại đúng nó
                    # mãi. Nay ghi chữ ký để bỏ qua, chuyển sang bài kế tiếp.
                    # Chỉ dừng khi hỏng 3 lần LIÊN TIẾP (thường là FB đổi giao diện).
                    loi_lien += 1
                    if ky:
                        bo_qua.add(ky)
                    logger.warning(f"  ⚠️  [{acc_name}] xóa bài hỏng, bỏ qua ({loi_lien}/3)"
                                   + (f" — \"{tieu_de[:50]}\" {ngay}" if ky else "")
                                   + f": {e}")
                    if loi_lien >= 3:
                        break
                    try:
                        await page.keyboard.press("Escape")
                        await _tai_selling(page)
                    except Exception:
                        break
                    continue
                loi_lien = 0
                da_xoa += 1
                logger.info(f"  🧹 [{acc_name}] đã xóa 1 bài {vi_sao} ({da_xoa}): "
                            f"\"{tieu_de[:60]}\" · {ngay}"
                            + (f" · lý do: {ld}" if ld else ""))
                # Tải lại cho DOM sạch, CUỘN cho nạp đủ danh sách, rồi quét tiếp.
                await _tai_selling(page)
            try:
                _rows = await _doc_rows(page, hom_nay, ky_trung)
                con_lai = (sum(1 for b in _rows if b["trung"]) if chi_trung
                           else len(loc_can_xoa(_rows, so_ngay)))
                if con_lai:
                    nut = await page.locator('[aria-label^="Lựa chọn khác cho"]').count()
                    so_dong = await page.evaluate(_JS_DEM_DONG)
                    logger.warning(f"  ⚠️  [{acc_name}] dừng mà còn {con_lai} bài phải xóa "
                                   f"(đã nạp {so_dong} dòng, {nut} nút '...', "
                                   f"bỏ qua {len(bo_qua)} bài hỏng)")
            except Exception:
                pass
        except CookieDeadError:
            raise
        except Exception as e:
            # Lỗi ngoài vòng (mở trang…): vẫn trả số bài ĐÃ xóa — bản trước làm
            # mất con số này (Hoàng Alex xóa 9 bài mà tổng kết không ghi).
            logger.warning(f"⚠️  Xóa bài niêm yết [{acc_name}] lỗi giữa chừng: {e}")
        finally:
            try:
                await ctx.close()
            except Exception:
                pass
        return da_xoa


def xoa_bai_cu(acc_name: str, c_user: str = "", so_ngay: int = 3,
               chay_thu: bool = False, headless=None) -> dict:
    """Đọc bài niêm yết → lọc quá `so_ngay` ngày → xóa. `chay_thu=True` thì CHỈ
    liệt kê, không xóa (dùng khi cần xem trước, không nối vào runner).

    Trả {tong, qua_han:[{tieu_de,tuoi,ngay_text}], da_xoa, chay_thu}. Khi
    `_XOA_DA_DO_DOM` còn False thì ÉP chạy thử (chốt an toàn)."""
    bai = quet_bai_niem_yet(acc_name, c_user, headless=headless)
    qua_han = loc_qua_han(bai, so_ngay)
    can_xoa = loc_can_xoa(bai, so_ngay)          # quá hạn + bị cảnh báo trùng
    ep_thu = chay_thu or not _XOA_DA_DO_DOM
    kq = {
        "tong": len(bai),
        "qua_han": [{"tieu_de": b.get("tieu_de", ""), "tuoi": b.get("tuoi"),
                     "ngay_text": b.get("ngay_text", "")} for b in qua_han],
        "trung": sum(1 for b in bai if b.get("trung")),
        "can_xoa": len(can_xoa),
        "da_xoa": 0,
        "chay_thu": ep_thu,
    }
    if ep_thu or not can_xoa:
        if can_xoa:
            logger.info(f"  🧹 [{acc_name}] (chạy thử) {len(can_xoa)} bài phải xóa "
                        f"(quá {so_ngay} ngày / bị cảnh báo trùng) — CHƯA xóa")
        return kq
    try:
        kq["da_xoa"] = asyncio.run(
            _xoa(acc_name, c_user, so_ngay,
                 HEADLESS if headless is None else headless))
    except CookieDeadError:
        raise
    except Exception as e:
        logger.warning(f"⚠️  Xóa bài niêm yết [{acc_name}] lỗi (bỏ qua): {e}")
    # Chạm trần _TRAN_XOA bài/phiên → nhiều khả năng còn bài cũ: phiên Marketplace
    # kế tiếp trong ngày phải dọn TIẾP (28/10 Mai Tùng: 51 bài quá hạn, xóa 30, còn 28).
    kq["cham_tran"] = kq["da_xoa"] >= _TRAN_XOA
    return kq


def xoa_bai_trung(acc_name: str, c_user: str = "", headless=None) -> int:
    """CHỈ xóa bài bị Facebook cảnh báo trùng ("có vẻ giống một bài niêm yết khác
    nên chúng tôi không đăng") — gọi NGAY SAU mỗi phiên đăng Marketplace, vì bài trùng
    sinh ra đúng lúc đăng; chờ phiên dọn đầu ngày hôm sau thì nó nằm đó cả ngày.
    Không đụng bài quá hạn. Một lượt trình duyệt; không có bài trùng thì về ngay.
    Trả số bài đã xóa. Lỗi cookie → CookieDeadError; lỗi khác → log, trả 0."""
    if not _XOA_DA_DO_DOM:
        return 0
    try:
        return asyncio.run(_xoa(acc_name, c_user, 0,
                                HEADLESS if headless is None else headless,
                                chi_trung=True))
    except CookieDeadError:
        raise
    except Exception as e:
        logger.warning(f"⚠️  Xóa bài trùng [{acc_name}] lỗi (bỏ qua): {e}")
        return 0
