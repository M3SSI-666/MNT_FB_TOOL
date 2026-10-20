"""
================================================================================
market_inbox.py — Quét hộp thư Marketplace tìm tin khách MỚI
================================================================================
Marketplace đăng bằng nick cá nhân nên tin khách rải khắp các nick. Module này
để nick tự ghé hộp thư Marketplace (định kỳ, do runner của mảng gọi — xem
scheduler._scan_mkt_worker), ĐỌC danh sách hội thoại rồi về. Việc so "tin mới"
và báo Telegram nằm ở nơi gọi.

NGUYÊN TẮC SỐNG CÒN:
  - CHỈ ĐỌC danh sách, TUYỆT ĐỐI KHÔNG click vào hội thoại nào. Click = Facebook
    đánh dấu "đã đọc" + khách thấy "Đã xem" mà mình chưa trả lời.
  - Đọc thụ động: lỗi thì log rồi thôi, KHÔNG tính vào sức khoẻ acc.

CHỈ ĐỌC PANEL MARKETPLACE — đo thật trên nick Sa Tran Anh 19/10/2026:
  `facebook.com/marketplace/inbox/` KHÔNG phải một trang riêng — nó mở giao diện
  Messenger đầy đủ, panel GIỮA (`[role="main"]`, hai tab "Bán hàng"/"Mua hàng")
  là hộp thư Marketplace, còn toàn bộ Messenger thường (các `/messages/e2ee/t/…`,
  nhóm chat…) nằm NGOÀI `main` nhưng vẫn ở trong DOM (FB nạp ngầm). Bản đầu quét
  cả document nên vơ luôn tin Messenger thường — SAI. Nay chỉ quét trong
  `[role="main"]`.

  Card hội thoại Marketplace là một ô bấm được (`div[role="button"][tabindex]`,
  có lúc `div[role="row"]`), KHÔNG phải thẻ `<a href>`. Chữ nhiều dòng: tên/tiêu
  đề bài → nội dung tin → giờ. Tin do CHÍNH MÌNH vừa trả lời có preview mở đầu
  "Bạn:" → loại ra, không báo.

CARD KHÔNG GHI AI LÀ NGƯỜI GỬI — đo thật trên nick Dang Xuan Duy 20/10/2026:
  tin chính mình gửi khách ("Chị có dùng zalo k ạ?…") hiện y hệt tin khách:
  không "Bạn:", không avatar "đã xem", không aria-label nào. Lọc theo "Bạn:" vì
  thế để lọt, và Telegram báo luôn cả tin mình vừa nhắn. Dấu hiệu phân biệt duy
  nhất trên card là CHƯA ĐỌC (chữ in đậm): tin mình gửi thì luôn ở trạng thái đã
  đọc (đo thật: tên nét 500, nội dung nét 400), còn tin khách mới tới thì in đậm
  cho tới khi mình mở ra. → CHỈ BÁO hội thoại CHƯA ĐỌC. Tin khách mà mình đã mở
  đọc trước lần quét thì không báo nữa — đằng nào mình cũng đã thấy.

  Thêm: tin HỆ THỐNG của Facebook (vd "Cảnh giác với các hành vi lừa đảo thường
  gặp thông qua ứng dụng thanh toán") đứng làm tin cuối của hội thoại, không phải
  khách nhắn → bỏ (xem `_TIN_HE_THONG`).
================================================================================
"""

import asyncio
import re

from utils import logger, CookieDeadError
from config import HEADLESS

# URL mở hộp thư Marketplace (thực chất là Messenger, panel giữa là Marketplace).
INBOX_URL = "https://www.facebook.com/marketplace/inbox/"

# Đọc danh sách hội thoại trong PANEL MARKETPLACE (`[role="main"]`) — KHÔNG đụng
# Messenger thường ở ngoài. Không click gì, chỉ đọc DOM. Trả [{name, bai, preview,
# unread}] (bai = tên bài niêm yết, tách khỏi nội dung). Gom theo name|bai|preview
# để khỏi trùng dòng.
_JS_DOC_LIST = r"""
() => {
  const main = document.querySelector('[role="main"]');
  if (!main) return [];
  const vis = el => {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    const s = getComputedStyle(el);
    return !(s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0);
  };
  // Nhãn tab / nút đầu panel — KHÔNG phải hội thoại.
  const BO_QUA = new Set(['bán hàng', 'mua hàng', 'xem thêm', 'marketplace',
                          'hộp thư', 'tất cả', 'chưa đọc']);
  const laGio = s => /^[·•\s]*\d{1,2}:\d{2}$/.test(s) ||
                     /(phút|giờ|ngày|tuần|năm|vừa xong)/i.test(s) ||
                     /^[·•\s]*(th|thg)\s?\d/i.test(s);
  const out = [], seen = new Set();
  const rows = main.querySelectorAll(
    'a[href*="/t/"], div[role="button"][tabindex], div[role="row"]');
  for (const r of rows) {
    if (!vis(r)) continue;
    const raw = (r.innerText || '').trim();
    if (!raw) continue;
    const lines = raw.split('\n').map(s => s.trim()).filter(Boolean);
    if (lines.length < 2) continue;                 // card thật: có tên + nội dung
    const name = lines[0];
    if (BO_QUA.has(name.toLowerCase())) continue;
    let body = lines.slice(1);
    while (body.length && laGio(body[body.length - 1])) body = body.slice(0, -1);
    // Dòng mở đầu bằng "·"/"•" là TÊN BÀI niêm yết (FB chèn vào card) — tách ra
    // khỏi nội dung tin cho gọn.
    let bai = '';
    const con = [];
    for (const ln of body) {
      const m = ln.match(/^[·•∙]\s*(.+)$/);
      if (m && !bai) bai = m[1].trim();
      else con.push(ln);
    }
    const preview = con.join(' ').replace(/\s+/g, ' ').trim();
    if (!preview && !bai) continue;
    const key = name + '|' + bai + '|' + preview.slice(0, 40);
    if (seen.has(key)) continue;
    seen.add(key);
    // Chưa đọc = có chữ in ĐẬM (nét >= 600). Chỉ xét phần chữ của CHÍNH phần
    // tử (text node con trực tiếp), không lấy innerText của khối cha — khối cha
    // gom chữ của cả card nên nét chữ của nó không nói lên gì. Đo thật một card
    // ĐÃ ĐỌC: tên nét 500, nội dung + giờ nét 400.
    let fw = 0;
    for (const el of r.querySelectorAll('*')) {
      const own = [...el.childNodes].filter(n => n.nodeType === 3)
                    .map(n => n.textContent).join('').trim();
      if (own.length < 2) continue;
      fw = Math.max(fw, +getComputedStyle(el).fontWeight || 0);
    }
    out.push({ name, bai, preview, unread: fw >= 600, fw });
  }
  return out;
}
"""


# Tin HỆ THỐNG Facebook chèn vào hội thoại Marketplace — không phải khách nhắn.
# Gặp thật 20/10: "Cảnh giác với các hành vi lừa đảo thường gặp thông qua ứng
# dụng thanh toán" (kèm nút "Tìm hiểu thêm"). Khớp ĐẦU câu, không khớp lỏng chữ
# "lừa đảo" ở bất kỳ đâu — khách hỏi "bên em có lừa đảo không" vẫn phải báo.
_TIN_HE_THONG = re.compile(
    r"^(cảnh giác với|hãy đề phòng|hãy cẩn thận với|lưu ý an toàn|mẹo an toàn"
    r"|be cautious|watch out for|beware of|stay safe|safety tips?)\b"
    r"|hành vi lừa đảo thường gặp|common scams?", re.IGNORECASE)


def la_tin_he_thong(hoi_thoai: dict) -> bool:
    """Tin cuối của hội thoại là cảnh báo/lời khuyên do Facebook chèn vào."""
    return bool(_TIN_HE_THONG.search((hoi_thoai.get("preview") or "").strip()))


def la_tin_khach(hoi_thoai: dict) -> bool:
    """Tin ĐÁNG BÁO = tin khách gửi tới mà mình CHƯA ĐỌC.

    - Phải CHƯA ĐỌC: card không ghi người gửi, nên chưa đọc là dấu hiệu duy nhất
      tách được tin khách với tin mình vừa nhắn (xem đầu file).
    - Bỏ tiền tố "Bạn:" / "You:" (vài giao diện FB vẫn đặt khi tin cuối là của mình).
    - Bỏ tin hệ thống của Facebook (cảnh báo lừa đảo…)."""
    if not hoi_thoai.get("unread"):
        return False
    pv = (hoi_thoai.get("preview") or "").strip().lower()
    if pv.startswith("bạn:") or pv.startswith("bạn ") or pv.startswith("you:"):
        return False
    return not la_tin_he_thong(hoi_thoai)


async def _quet(acc_name: str, c_user: str, headless) -> list:
    from playwright.async_api import async_playwright
    # Mở profile dùng chung với nuôi nick (cookie + login + dọn dialog cảnh báo).
    from nuoi_nick import _open_context, _dismiss_pin_dialog

    async with async_playwright() as p:
        ctx, page = await _open_context(p, acc_name, c_user, headless)
        try:
            # Hộp PIN / dialog cảnh báo che danh sách — dọn trước khi đọc.
            try:
                await _dismiss_pin_dialog(page)
            except Exception:
                pass

            await page.goto(INBOX_URL, wait_until="domcontentloaded", timeout=30000)
            # Panel Marketplace tải sau vài giây; chờ cho các hội thoại hiện ra.
            await page.wait_for_timeout(6000)

            ds = await page.evaluate(_JS_DOC_LIST)
            khach = [d for d in ds if la_tin_khach(d)]
            n_doc = sum(1 for d in ds if not d.get("unread"))
            n_ht  = sum(1 for d in ds if d.get("unread") and la_tin_he_thong(d))
            logger.info(f"  📥 Inbox Market [{acc_name}]: {len(ds)} hội thoại → "
                        f"{len(khach)} tin khách chưa đọc (bỏ {n_doc} đã đọc / tin mình "
                        f"nhắn, {n_ht} tin hệ thống)")
            return khach
        finally:
            try:
                await ctx.close()
            except Exception:
                pass


def quet_inbox_market(acc_name: str, c_user: str = "", headless=None) -> list:
    """Sync — gọi từ scheduler (chạy trong thread). Trả list hội thoại Marketplace
    mà tin cuối là CỦA KHÁCH (bỏ tin mình vừa trả lời):
    [{"name","preview","unread"}]. Lỗi cookie → ném CookieDeadError; lỗi khác →
    log rồi trả [] (đọc thụ động, không làm hỏng runner)."""
    try:
        return asyncio.run(_quet(acc_name, c_user,
                                 HEADLESS if headless is None else headless))
    except CookieDeadError:
        raise
    except Exception as e:
        logger.warning(f"⚠️  Quét inbox Market [{acc_name}] lỗi (bỏ qua): {e}")
        return []


def chu_ky(hoi_thoai: dict) -> str:
    """Chữ ký một hội thoại — để so 'tin mới' giữa hai lần quét. Cùng người +
    cùng bài + cùng đoạn trích = coi như tin cũ, không báo lại. Khách gửi tin mới
    thì đoạn trích đổi → chữ ký đổi → báo."""
    return (f"{(hoi_thoai.get('name') or '').strip()}"
            f"|{(hoi_thoai.get('bai') or '').strip()}"
            f"|{(hoi_thoai.get('preview') or '').strip()[:60]}")
