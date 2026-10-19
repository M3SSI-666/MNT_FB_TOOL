"""
================================================================================
market_inbox.py — Quét hộp thư Marketplace tìm tin khách MỚI
================================================================================
Marketplace đăng bằng nick cá nhân nên tin khách rải khắp các nick. Module này
để nick tự ghé hộp thư Marketplace (định kỳ, do runner của mảng gọi — xem
scheduler._scan_mkt_worker), ĐỌC danh sách hội thoại chưa đọc rồi về. Việc so
"tin mới" và báo Telegram nằm ở nơi gọi.

NGUYÊN TẮC SỐNG CÒN:
  - CHỈ ĐỌC danh sách, TUYỆT ĐỐI KHÔNG click vào hội thoại nào. Click = Facebook
    đánh dấu "đã đọc" + khách thấy "Đã xem" mà mình chưa trả lời.
  - Đọc thụ động: lỗi thì log rồi thôi, KHÔNG tính vào sức khoẻ acc.

Dò "chưa đọc" là best-effort (bám nhiều dấu hiệu: aria / chấm / chữ đậm), CẦN
chạy thử non-headless lần đầu để chốt — giống luồng nhắn tin của nuôi nick.
================================================================================
"""

import asyncio

from utils import logger, CookieDeadError
from config import HEADLESS

# URL hộp thư Marketplace (đã lọc sẵn chỉ chat về tin rao).
INBOX_URL = "https://www.facebook.com/marketplace/inbox/"

# Đọc danh sách hội thoại + đoán hội thoại CHƯA ĐỌC. Không click gì — chỉ đọc
# DOM. Trả [{name, preview, unread}]. Gom theo name|preview để khỏi trùng dòng.
_JS_DOC_LIST = r"""
() => {
  const out = [], seen = new Set();
  // Mỗi hội thoại là một link trong vùng danh sách của inbox.
  const rows = document.querySelectorAll(
    'a[role="link"][href*="/marketplace/t/"], a[href*="/messages/t/"], ' +
    'a[role="link"][href*="/t/"], div[role="row"]');
  for (const r of rows) {
    const txt = (r.innerText || '').trim();
    if (!txt) continue;
    const aria = (r.getAttribute('aria-label') || '').toLowerCase();
    let unread = aria.includes('chưa đọc') || aria.includes('unread');
    // Tên hội thoại IN ĐẬM thường là dấu hiệu chưa đọc.
    if (!unread) {
      for (const el of r.querySelectorAll('span,div')) {
        const t = (el.innerText || '').trim();
        if (!t) continue;
        const w = getComputedStyle(el).fontWeight;
        if (w === '700' || w === '600' || (+w >= 600)) { unread = true; break; }
      }
    }
    const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
    const name = lines[0] || '';
    const preview = lines.slice(1).join(' ');
    const key = name + '|' + preview.slice(0, 40);
    if (!name || seen.has(key)) continue;
    seen.add(key);
    out.push({ name, preview, unread });
  }
  return out;
}
"""


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
            # Danh sách tải sau vài giây; chờ một nhịp cho các hội thoại hiện ra.
            await page.wait_for_timeout(4000)

            ds = await page.evaluate(_JS_DOC_LIST)
            chua_doc = [d for d in ds if d.get("unread")]
            logger.info(f"  📥 Inbox Market [{acc_name}]: {len(ds)} hội thoại, "
                        f"{len(chua_doc)} chưa đọc")
            return chua_doc
        finally:
            try:
                await ctx.close()
            except Exception:
                pass


def quet_inbox_market(acc_name: str, c_user: str = "", headless=None) -> list:
    """Sync — gọi từ scheduler (chạy trong thread). Trả list hội thoại CHƯA ĐỌC
    hiện tại: [{"name","preview","unread"}]. Lỗi cookie → ném CookieDeadError;
    lỗi khác → log rồi trả [] (đọc thụ động, không làm hỏng runner)."""
    try:
        return asyncio.run(_quet(acc_name, c_user,
                                 HEADLESS if headless is None else headless))
    except CookieDeadError:
        raise
    except Exception as e:
        logger.warning(f"⚠️  Quét inbox Market [{acc_name}] lỗi (bỏ qua): {e}")
        return []


def chu_ky(hoi_thoai: dict) -> str:
    """Chữ ký một hội thoại chưa đọc — để so 'tin mới' giữa hai lần quét.
    Cùng người + cùng đoạn trích = coi như tin cũ, không báo lại."""
    return f"{(hoi_thoai.get('name') or '').strip()}|{(hoi_thoai.get('preview') or '').strip()[:60]}"
