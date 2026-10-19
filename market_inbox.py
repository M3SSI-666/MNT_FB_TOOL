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
================================================================================
"""

import asyncio

from utils import logger, CookieDeadError
from config import HEADLESS

# URL mở hộp thư Marketplace (thực chất là Messenger, panel giữa là Marketplace).
INBOX_URL = "https://www.facebook.com/marketplace/inbox/"

# Đọc danh sách hội thoại trong PANEL MARKETPLACE (`[role="main"]`) — KHÔNG đụng
# Messenger thường ở ngoài. Không click gì, chỉ đọc DOM. Trả [{name, preview,
# unread}]. Gom theo name|preview để khỏi trùng dòng.
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
    const preview = body.join(' ').replace(/\s+/g, ' ').trim();
    if (!preview) continue;
    const key = name + '|' + preview.slice(0, 40);
    if (seen.has(key)) continue;
    seen.add(key);
    // Chưa đọc (gợi ý): có chữ ĐẬM dài (preview in đậm). Tên bài có thể luôn đậm
    // nên chỉ tính span đủ dài để khỏi nhầm với tiêu đề ngắn.
    let unread = false;
    for (const el of r.querySelectorAll('span,div')) {
      const t = (el.innerText || '').trim();
      if (t.length >= 12 && +getComputedStyle(el).fontWeight >= 600) { unread = true; break; }
    }
    out.push({ name, preview, unread });
  }
  return out;
}
"""


def la_tin_khach(hoi_thoai: dict) -> bool:
    """Tin ĐÁNG BÁO = tin khách gửi tới, KHÔNG phải mình vừa trả lời.
    FB đặt tiền tố "Bạn:" / "You:" cho preview khi tin cuối là của mình."""
    pv = (hoi_thoai.get("preview") or "").strip().lower()
    return not (pv.startswith("bạn:") or pv.startswith("bạn ") or pv.startswith("you:"))


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
            logger.info(f"  📥 Inbox Market [{acc_name}]: {len(ds)} hội thoại, "
                        f"{len(khach)} là tin khách (loại tin mình vừa rep)")
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
    cùng đoạn trích = coi như tin cũ, không báo lại. Khách gửi tin mới thì đoạn
    trích đổi → chữ ký đổi → báo."""
    return f"{(hoi_thoai.get('name') or '').strip()}|{(hoi_thoai.get('preview') or '').strip()[:60]}"
