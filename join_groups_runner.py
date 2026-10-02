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

# Tên acc của phiên đang chạy. Mỗi lịch tham gia nhóm chạy trong MỘT TIẾN TRÌNH
# RIÊNG nên biến này không lẫn giữa các phiên — nhưng cả 5 tiến trình cùng ghi
# vào MỘT file log, nên không gắn tên acc thì các dòng trộn vào nhau và không
# cách nào biết dòng lỗi là của acc nào.
#
# Đã xảy ra thật: log có 8 dòng "Cookie hết hạn" mà không dòng nào nói acc nào,
# trong khi 32 phiên đã chạy chung file đó.
_ACC = ""


def _log(muc, msg):
    """Ghi log kèm tên acc của phiên. `muc` là info / warning / error."""
    dau = "[" + _ACC + "] " if _ACC else ""
    xuong_dong = msg.startswith(chr(10))
    if xuong_dong:
        msg = msg.lstrip(chr(10))
    getattr(logger, muc)((chr(10) if xuong_dong else "") + "  " + dau + msg)


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
    _log("info", f"[Switch] Goto Page {page_uid}")
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
                _log("info", "[Switch] ✅ Switched to Page")
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
# Trạng thái thành viên, đọc từ NÚT ĐANG NHÌN THẤY và khớp CHÍNH XÁC cả chuỗi.
#
# Bản cũ quét mọi [role="button"] rồi hỏi textContent có CHỨA "đã tham gia"
# không. Trang nhóm đầy chỗ mang chữ đó mà chẳng liên quan trạng thái: "N người
# bạn đã tham gia", bài trong feed "... đã tham gia nhóm". Trúng một cái là nó
# kết luận đã là thành viên rồi BỎ QUA, không bấm Tham gia.
#
# Đo thật ngày 01/10 trên nick Thị Sữa: phiên báo "đã là thành viên: 16", kiểm
# lại từng nhóm thì 17/25 nhóm nút vẫn là "Tham gia nhóm" — chưa vào, chưa cả
# gửi yêu cầu. Bộ dò khớp chính xác đọc đúng 25/25.
_DETECT_STATE_JS = r"""() => {
    const t = e => (e.innerText || e.textContent || '').trim().replace(/\s+/g,' ');
    const nhin = e => {
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 14) return false;
        const x = Math.round(r.left + r.width/2), y = Math.round(r.top + r.height/2);
        const tr = document.elementFromPoint(x, y);
        return !!tr && (e.contains(tr) || tr.contains(e));
    };
    const chu = [];
    for (const e of document.querySelectorAll('[role="button"],button,a[role="button"]')) {
        if (!nhin(e)) continue;
        const s = t(e).toLowerCase();
        if (s && s.length < 30) chu.push(s);
    }
    const co = re => chu.some(s => re.test(s));
    if (co(/^(đã tham gia|joined)$/))                              return 'da_join';
    if (co(/^(huỷ yêu cầu|hủy yêu cầu|cancel request|đã gửi yêu cầu|request sent)$/))
        return 'cho_duyet';
    if (co(/^(tham gia nhóm|tham gia|join group|join)$/))          return 'need_join';
    return '';
}"""

_JOIN_SELS = [
    'div[role="button"]:has-text("Tham gia nhóm")',
    'div[role="button"]:has-text("Join Group")',
    'div[role="button"]:has-text("Join group")',
    'a[role="button"]:has-text("Tham gia nhóm")',
    '[data-testid="group-join-button"]',
]


def _url_chong_cache(url: str) -> str:
    """URL nhóm kèm tham số thời gian, để vào lại trang mà KHÔNG nhận bản cũ.

    Bấm Tham gia xong mà `goto` lại ĐÚNG URL đang mở thì Chromium trả bản trang
    cũ, nút vẫn là "Tham gia nhóm". Đo 02/10 trên nick Tuan Ngoc Mai: 15/15 nhóm
    vào thật bị ghi thành lỗi vì vậy. Cùng lúc đó URL có tham số và tab mới đều
    đọc ra "Đã tham gia".
    """
    return f"{url}{'&' if '?' in url else '?'}_t={int(time.time())}"


async def _cho_trang_thai(page, giay: int) -> str:
    """Đọc trạng thái thành viên, chờ tối đa `giay` giây tới khi rõ ràng."""
    st = ""
    for _ in range(giay):
        try:
            st = await page.evaluate(_DETECT_STATE_JS)
        except Exception:
            st = ""
        if st in ("da_join", "cho_duyet"):
            break
        await page.wait_for_timeout(1000)
    return st


_JS_HOP_THOAI = r"""() => [...document.querySelectorAll('[role="dialog"],[role="alertdialog"]')]
  .filter(d => { const r = d.getBoundingClientRect(); return r.width > 50 && r.height > 50; })
  .map(d => ({
     chu: (d.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 300),
     nut: [...d.querySelectorAll('[role="button"],button')]
            .map(b => (b.innerText || b.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' '))
            .filter(s => s && s.length < 40),
  }))"""

_SO_ANH_LOI = 0          # mỗi phiên chụp tối đa 5 ảnh, đủ để biết lỗi gì
_GIU_ANH_LOI = 50        # thư mục ảnh lỗi giữ 50 ảnh mới nhất


async def _ghi_chan_doan(page, ten_nhom: str, hop=None, anh: bytes = None):
    """Lỗi không rõ nguyên nhân thì ghi lại Facebook đang hiện gì.

    Trước đây log chỉ có "vẫn chưa vào" — không biết là Facebook chặn, hỏi câu
    hỏi thành viên, hay phần mềm đọc sai. Phải chạy thử lại bằng tay mới biết.

    `hop` / `anh` là thứ đã chụp sẵn từ trước (khi trang đã bị tải lại); không
    có thì đọc từ trang hiện tại.
    """
    global _SO_ANH_LOI
    if hop is None:
        try:
            hop = await page.evaluate(_JS_HOP_THOAI)
        except Exception:
            hop = []
    if not hop:
        _log("warning", "   (không có hộp thoại nào đang mở)")
    for h in hop:
        _log("warning", f"   hộp thoại: {h['chu']} | nút: {', '.join(h['nut'])}")

    if _SO_ANH_LOI >= 5:
        return
    _SO_ANH_LOI += 1
    try:
        from config import LOG_DIR
        thu_muc = Path(LOG_DIR) / "join_loi"
        thu_muc.mkdir(parents=True, exist_ok=True)
        ten = re.sub(r"\W+", "_", f"{_ACC}_{ten_nhom}")[:60]
        tep = thu_muc / f"{time.strftime('%Y%m%d_%H%M%S')}_{ten}.png"
        if anh:
            tep.write_bytes(anh)
        else:
            await page.screenshot(path=str(tep))
        _log("warning", f"   ảnh màn hình: logs/join_loi/{tep.name}")
        for cu in sorted(thu_muc.glob("*.png"))[:-_GIU_ANH_LOI]:
            cu.unlink(missing_ok=True)
    except Exception as e:
        _log("warning", f"   không chụp được màn hình: {e}")


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


async def _lay_nhom_da_vao(page, chu_the: str = "Page") -> set:
    """
    Đọc danh sách nhóm ĐÃ tham gia của chủ thể đang hoạt động, từ `groups/joins`.

    Trang này trả về nhóm của CHỦ THỂ ĐANG HOẠT ĐỘNG. Với lịch Page thì phải gọi
    SAU khi đã switch; với lịch Marketplace thì không switch bao giờ, nên nó trả
    về nhóm của chính nick cá nhân — đúng thứ cần.

    `chu_the` chỉ để ghi log cho đúng: nói "Page đã tham gia" trong lúc chạy
    Marketplace là nói sai, mà log sai thì lần sau đọc lại càng rối.

    Dò thật ba trang: `groups/joins` cho 40 định danh (38 khớp tag), còn
    `groups/` và `groups/feed` chỉ ra 22 — chúng là thanh bên newsfeed, không
    phải danh sách đầy đủ.

    Cuộn tới khi số nhóm thôi tăng, tối đa `so_cuon` lượt, chứ không cuộn cứng
    một số lần: Page ít nhóm thì xong sớm, Page nhiều nhóm mới cuộn lâu.
    """
    await page.goto("https://www.facebook.com/groups/joins/",
                    wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(4000)

    # Cuộn bằng CẢ HAI cách. `mouse.wheel` chỉ cuộn khung đang nằm dưới con trỏ
    # — con trỏ ở đâu thì Playwright không bảo đảm, nên có lúc nó cuộn nhầm khung
    # hoặc không cuộn gì. `window.scrollBy` cuộn chính tài liệu, luôn ăn.
    #
    # VÀ KIÊN NHẪN HƠN HẲN BẢN CŨ: 20 lượt, nghỉ 1,2 giây, dừng sau 3 lượt im.
    # Facebook nạp danh sách này rất chậm nên nó dừng quá sớm — đo ngày 01/10
    # trên nick Thị Sữa: đọc ra 11 nhóm trong khi nick ở ít nhất 27 nhóm, và 16
    # nhóm bị bỏ sót đều là nhóm mục tiêu.
    da_thay, yen = set(), 0
    for _ in range(45):
        truoc = len(da_thay)
        try:
            da_thay |= set(await page.evaluate(_JS_BOC_NHOM))
        except Exception:
            pass
        await page.evaluate("window.scrollBy(0, 2200)")
        try:
            await page.mouse.wheel(0, 2200)
        except Exception:
            pass
        await page.wait_for_timeout(1800)
        try:
            da_thay |= set(await page.evaluate(_JS_BOC_NHOM))
        except Exception:
            pass
        yen = yen + 1 if len(da_thay) == truoc else 0
        if yen >= 6:                      # sáu lượt liền không thêm được gì
            break

    _log("info", f"📋 {chu_the} đã tham gia {len(da_thay)} nhóm (đọc từ groups/joins)")
    return da_thay


# Nút "Đã tham gia" xuất hiện HAI LẦN trên trang nhóm: một ở thanh dính, một ở
# phần chính. Bấm nhầm cái đang bị che thì menu không mở — đo thật ngày 01/10:
# bấm cái đầu theo thứ tự DOM ra `menu hiện ra: []`. Lọc bằng elementFromPoint:
# điểm giữa nút phải trả về chính nó thì mới là nút đang nhìn thấy.
_JS_NUT_HIEN = r"""(chu) => {
    const t = e => (e.innerText || e.textContent || '').trim().replace(/\s+/g,' ');
    for (const e of document.querySelectorAll('[role="button"],button')) {
        const s = t(e), lab = e.getAttribute('aria-label') || '';
        if (!(s + lab).toLowerCase().includes(chu.toLowerCase())) continue;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 14) continue;
        const x = Math.round(r.left + r.width/2), y = Math.round(r.top + r.height/2);
        const tren = document.elementFromPoint(x, y);
        if (tren && (e.contains(tren) || tren.contains(e))) return {x, y};
    }
    return null;
}"""


async def _roi_mot_nhom(page, uid: str, ten_nhom: str, link_url: str) -> str:
    """Rời MỘT nhóm. Trả về "da_roi" | "khong_o_trong" | "loi".

    Đường đi đo thật ngày 01/10 trên nick Nguyen Ngan:
        bấm "Đã tham gia"  →  menu [Quản lý thông báo · Bỏ theo dõi nhóm · Rời nhóm]
        →  bấm "Rời nhóm"  →  (có thể) hộp xác nhận

    XÁC MINH sau khi bấm chứ không tin là xong: chỉ tính đã rời khi nút đổi
    thành "Tham gia". Đếm số lần bấm thay vì đếm kết quả chính là lỗi đã mắc ở
    bước tick nhóm Marketplace — log báo 20 mà thực tế chỉ 16.
    """
    url = link_url if link_url and link_url.startswith("http") \
          else f"https://www.facebook.com/groups/{uid}/"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _human_delay(2000, 3000)
    except Exception as e:
        _log("error", f"❌ Không mở được nhóm '{ten_nhom or uid}': {e}")
        return "loi"

    vi_tri = await page.evaluate(_JS_NUT_HIEN, "Đã tham gia")
    if not vi_tri:
        _log("info", f"⏭️  Không còn ở trong nhóm: {ten_nhom or uid}")
        return "khong_o_trong"

    await page.mouse.click(vi_tri["x"], vi_tri["y"])
    await _human_delay(1500, 2500)

    # "Rời nhóm" là một role=menuitem trong menu vừa mở.
    try:
        muc = await page.wait_for_selector(
            '[role="menuitem"]:has-text("Rời nhóm")', timeout=5000, state="visible")
    except Exception:
        muc = None
    if not muc:
        _log("warning", f"⚠️  Không thấy mục 'Rời nhóm': {ten_nhom or uid}")
        await page.keyboard.press("Escape")
        return "loi"
    await muc.click()
    await _human_delay(2000, 3000)

    # Facebook có thể hỏi lại trong hộp thoại. Chỉ bấm nút nằm TRONG dialog —
    # bấm bừa chữ "Rời nhóm" ở ngoài là bấm lại chính cái menu vừa đóng.
    for sel in ('div[role="dialog"] div[role="button"]:has-text("Rời nhóm")',
                'div[role="dialog"] div[role="button"]:has-text("Rời khỏi nhóm")',
                'div[role="dialog"] div[role="button"]:has-text("Xác nhận")'):
        try:
            nut = await page.wait_for_selector(sel, timeout=3000, state="visible")
            if nut:
                await nut.click()
                await _human_delay(2000, 3000)
                break
        except Exception:
            continue

    # Xác minh: nút phải đổi thành "Tham gia".
    # Vào LẠI bằng goto chứ không page.reload(): rời nhóm xong Facebook tự điều
    # hướng đi, reload lúc đó ném `ERR_ABORTED; maybe frame was detached` —
    # gặp thật ngày 01/10 ở nhóm 719961823676435, nhóm đã rời được nhưng bị ghi
    # thành lỗi. goto vào thẳng URL nhóm thì không phụ thuộc trang đang đứng ở đâu.
    # URL chống cache: nếu Facebook không điều hướng đi thì goto lại đúng URL đang
    # mở sẽ nhận bản trang cũ, nút vẫn "Đã tham gia" dù đã rời — xem `_url_chong_cache`.
    try:
        await page.goto(_url_chong_cache(url), wait_until="domcontentloaded", timeout=30000)
        await _human_delay(2500, 3500)
    except Exception as e:
        _log("warning", f"⚠️  Không vào lại được để kiểm: {ten_nhom or uid} ({e})")
        return "loi"
    con_o = await page.evaluate(_JS_NUT_HIEN, "Đã tham gia")
    if con_o:
        _log("warning", f"⚠️  Bấm rồi mà VẪN còn trong nhóm: {ten_nhom or uid}")
        return "loi"
    _log("info", f"🚪 Đã rời: {ten_nhom or uid}")
    return "da_roi"


async def _lam_sach_nhom(page, muc_tieu: list, dang_o: set = None, bao=None) -> int:
    """Rời mọi nhóm nick đang ở mà KHÔNG nằm trong danh sách mục tiêu.

    Mục đích: để nick chỉ còn đúng các nhóm đã duyệt Marketplace, lúc tick nhóm
    ở bước đăng bài khỏi phải lọc giữa một rừng nhóm không liên quan.

    Đọc danh sách nhóm của CHÍNH NICK CÁ NHÂN (luồng Marketplace không switch
    sang Page), nên không đụng tới nhóm của Page. `dang_o` là danh sách đã đọc
    sẵn — có thì khỏi đọc lại (mỗi lần đọc mất cả phút cuộn trang).

    `bao(da_roi)` được gọi sau mỗi 5 nhóm để bảng hiện tiến độ. Không có nó thì
    cột "Đã rời" đứng ở 0 suốt cả buổi: ngày 02/10 nick Mai Tùng phải rời 425
    nhóm, mất gần 3 tiếng, nhìn bảng tưởng tool đã treo.

    Trả về số nhóm ĐÃ RỜI THẬT — đếm kết quả xác minh, không đếm số lần bấm.
    """
    giu = set()
    for g in muc_tieu:
        giu |= _dinh_danh_nhom(g["uid"], g["link_url"])

    if dang_o is None:
        try:
            dang_o = await _lay_nhom_da_vao(page, "Nick")
        except Exception as e:
            _log("warning", f"⚠️  Không đọc được danh sách nhóm để làm sạch: {e}")
            return 0

    thua = sorted(dang_o - giu)
    _log("info", f"\n🧹 LÀM SẠCH: đang ở {len(dang_o)} nhóm, "
                 f"giữ {len(dang_o & giu)}, rời {len(thua)}")
    if not thua:
        return 0
    for x in thua:
        _log("info", f"     sẽ rời: {x}")

    da_roi = 0
    for i, uid in enumerate(thua, 1):
        _log("info", f"\n[rời {i}/{len(thua)}] {uid}")
        try:
            if await _roi_mot_nhom(page, uid, "", "") == "da_roi":
                da_roi += 1
        except Exception as e:
            _log("error", f"❌ Lỗi khi rời {uid}: {e}")
        if bao and i % 5 == 0:
            try:
                bao(da_roi)
            except Exception:
                pass
        # Rời nhóm dồn dập cũng là hành vi bất thường như tham gia dồn dập.
        await asyncio.sleep(_DELAY_SKIP_SEC + random.randint(0, 4))

    _log("info", f"\n🧹 Đã rời {da_roi}/{len(thua)} nhóm")
    return da_roi


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
        _log("error", f"❌ Không load được nhóm '{ten_nhom}': {e}")
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
        _log("info", f"⏭️  Đã là thành viên: {ten_nhom}")
        return "da_join"
    if state == "cho_duyet":
        _log("info", f"⏳ Đang chờ duyệt: {ten_nhom}")
        return "cho_duyet"
    if state != "need_join":
        # KHÔNG được coi "không đọc được" là "đã là thành viên". Suy đoán đó
        # chính là thứ làm phiên ngày 01/10 báo "đã là thành viên: 16" trong khi
        # 17/25 nhóm nút vẫn là "Tham gia nhóm" — nó bỏ qua, không bấm gì cả, mà
        # bảng vẫn hiện số đẹp. Thà báo lỗi để còn nhìn thấy mà chạy lại.
        _log("warning", f"⚠️  Không đọc được trạng thái thành viên: {ten_nhom}")
        await _ghi_chan_doan(page, ten_nhom)
        return "loi"

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
            _log("info", f"✅ Đã click 'Tham gia nhóm': {ten_nhom}")
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        _log("info", f"⏭️  Đã là thành viên: {ten_nhom}")
        return "da_join"

    # XÁC MINH sau khi bấm, không tin là xong. Nhóm cần duyệt thì bấm Tham gia
    # mới chỉ là GỬI YÊU CẦU — đếm nó vào "đã tham gia" là báo cáo sai.
    #
    # Đọc NGAY TRÊN TRANG trước: đo 02/10, bấm xong 2 giây nút đã thành "Đã tham
    # gia". Bản cũ `goto` lại đúng URL đang mở và nhận bản trang cũ (xem
    # `_url_chong_cache`), nên 15/15 nhóm vào thật bị ghi thành lỗi — và vì bị
    # coi là lỗi nên chỉ nghỉ 5 giây thay vì 15 giây giữa hai lần tham gia.
    sau = await _cho_trang_thai(page, 6)

    if sau not in ("da_join", "cho_duyet"):
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
        sau = await _cho_trang_thai(page, 4)

    hop, anh = None, None
    if sau not in ("da_join", "cho_duyet"):
        # Chụp lại TRƯỚC khi vào lại trang: vào lại là hộp thoại (nếu có) mất.
        # Chỉ ghi ra đĩa nếu rốt cuộc vẫn là lỗi.
        try:
            hop = await page.evaluate(_JS_HOP_THOAI)
            anh = await page.screenshot()
        except Exception:
            pass
        # Vẫn chưa rõ thì vào lại trang — bằng URL chống cache.
        try:
            await page.goto(_url_chong_cache(url), wait_until="domcontentloaded", timeout=30000)
            await _human_delay(2500, 3500)
            sau = await _cho_trang_thai(page, 5)
        except Exception:
            sau = ""

    if sau == "da_join":
        return "moi_join"
    if sau == "cho_duyet":
        _log("info", f"⏳ Đã gửi yêu cầu, chờ duyệt: {ten_nhom}")
        return "cho_duyet"
    _log("warning", f"⚠️  Bấm Tham gia rồi mà vẫn chưa vào: {ten_nhom}")
    await _ghi_chan_doan(page, ten_nhom, hop, anh)
    return "loi"


# ─── Main flow ────────────────────────────────────────────────────────────────

async def _run_join(schedule_id: int, acc_name: str, page_uid: str, nguon: str = ""):
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    # Nguồn nhóm: '' = sheet UID Nhóm, 'MARKET' = nhóm đã duyệt Marketplace.
    with _conn() as con:
        if nguon == "MARKET":
            rows = con.execute(
                "SELECT uid, ten_nhom, link_url FROM uid_groups "
                "WHERE ma_nhom='MARKET' ORDER BY order_idx, id"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT uid, ten_nhom, link_url FROM uid_groups WHERE ma_nhom='' OR ma_nhom IS NULL ORDER BY id"
            ).fetchall()

    groups = [{"uid": r[0], "ten_nhom": r[1], "link_url": r[2]} for r in rows]
    # Giữ bản GỐC: `groups` lát nữa bị thay bằng danh sách đã lọc bớt nhóm đã
    # tham gia, mà bước làm sạch cần biết TOÀN BỘ nhóm mục tiêu để chừa lại.
    groups_goc = list(groups)
    total  = len(groups)

    with _conn() as con:
        _r = con.execute("SELECT lam_sach FROM join_schedules WHERE id=?",
                         (schedule_id,)).fetchone()
    lam_sach = bool(_r and _r[0])
    if lam_sach:
        _log("info", "🧹 Lịch này BẬT làm sạch — xong phần tham gia sẽ rời "
                     "mọi nhóm ngoài danh sách (bỏ qua nếu chưa vào được nhóm "
                     "mục tiêu nào)")
    _log("info", f"📋 Tổng {total} nhóm cần kiểm tra")

    def _update_status(status, **kwargs):
        with _conn() as con:
            sets = ", ".join(f"{k}=?" for k in kwargs)
            vals = list(kwargs.values()) + [schedule_id]
            con.execute(f"UPDATE join_schedules SET trang_thai=?, {sets} WHERE id=?",
                        [status] + vals)

    # da_roi về 0 ngay từ đầu: để nguyên là số của lượt TRƯỚC còn hiện trên
    # bảng suốt lượt này, nhìn tưởng vừa rời ngần ấy nhóm.
    _update_status("Đang chạy", tong_nhom=total, da_roi=0)

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
            _log("error", "❌ Cookie hết hạn — cần lấy lại cookie cho acc này")
            _update_status("Lỗi - cookie hết hạn")
            # ĐÁNH DẤU CẢ TÀI KHOẢN, không chỉ dòng lịch. Trước đây chỉ đổi
            # trạng thái của lịch tham gia nhóm, mà lịch đó bị ghi đè ngay ở
            # lần chạy sau — nên nhìn tab Tài khoản không thấy gì cả, dù log
            # đầy dòng "Cookie hết hạn". Không biết acc nào thì không sửa được.
            #
            # Luồng đăng bài đã làm đúng việc này từ trước (_mark_cookie_dead);
            # chỉ luồng tham gia nhóm là bỏ sót.
            tt_cu = ""
            try:
                with _conn() as con:
                    # Đọc trạng thái cũ trước khi ghi đè: chỉ báo khi acc đang
                    # CHẠY mà hết cookie, không báo lại khi nó vốn đã hết rồi.
                    _r = con.execute("SELECT trang_thai FROM accounts "
                                     "WHERE ten_acc=? LIMIT 1", (acc_name,)).fetchone()
                    tt_cu = (_r["trang_thai"] or "") if _r else ""
                    con.execute(
                        "UPDATE accounts SET trang_thai='Cookie hết hạn', "
                        "canh_bao_moi=? WHERE ten_acc=?",
                        (f"'{acc_name}' hết cookie khi đi tham gia nhóm — "
                         f"lấy lại cookie rồi đổi Trạng thái về Active", acc_name))
            except Exception as e:
                _log("warning", f"⚠️  Không đánh dấu được acc hết cookie: {e}")
            try:
                import thong_bao
                thong_bao.bao_doi_trang_thai(acc_name, "Cookie hết hạn",
                                             trang_thai_cu=tt_cu,
                                             ly_do="phát hiện khi đi tham gia nhóm")
            except Exception:
                pass
            await ctx.close()
            return

        # Nhóm Marketplace thì KHÔNG switch sang Page: bài niêm yết chỉ đăng
        # được dưới nick cá nhân, nên phải chính nick đó là thành viên nhóm.
        # Cho Page vào nhóm là vào nhầm danh nghĩa — tốn một lượt xin duyệt mà
        # nick cá nhân vẫn không đăng được vào nhóm đó.
        if nguon == "MARKET":
            _log("info", "👤 Nhóm Marketplace — vào bằng nick cá nhân, không switch Page")
        else:
            _log("info", f"🔄 Switch sang Page {page_uid}...")
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
        chu_the = "Nick" if nguon == "MARKET" else "Page"
        try:
            da_vao = await _lay_nhom_da_vao(page, chu_the)
        except Exception as e:
            _log("warning", f"⚠️  Không đọc được danh sách nhóm đã tham gia: {e}")
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
            _log("info", f"⏭️  Bỏ qua {bo_qua} nhóm {chu_the.lower()} đã tham gia — "
                        f"còn {len(con_lai)}/{total} nhóm cần vào")
            groups = con_lai

        # Duyệt từng nhóm
        nhom_loi = []
        for i, g in enumerate(groups, 1):
            _log("info", f"\n[{i}/{total}] {g['ten_nhom'] or g['uid']}")
            result = await _join_one_group(page, g["uid"], g["ten_nhom"], g["link_url"])
            stats[result] += 1
            results.append({"uid": g["uid"], "ten": g["ten_nhom"], "result": result})
            if result == "loi":
                nhom_loi.append(g)

            # Update progress mỗi 5 nhóm
            if i % 5 == 0:
                _update_status("Đang chạy",
                               moi_join=stats["moi_join"],
                               da_join=stats["da_join"],
                               loi=stats["loi"])

            if result == "moi_join":
                jitter = random.randint(0, max(1, _DELAY_NEW_SEC // 6))
                wait   = _DELAY_NEW_SEC + jitter
                _log("info", f"⏱️  Mới join → chờ {wait}s...")
            else:
                wait = _DELAY_SKIP_SEC
                _log("info", f"⏩ Bỏ qua → chờ {wait}s...")
            await asyncio.sleep(wait)

        # ── Đối chiếu lại, rồi mới LÀM SẠCH ───────────────────────────────
        # Đọc lại danh sách nhóm đã tham gia một lần. Hai việc dùng chung nó:
        #  1. Nhóm bị ghi lỗi mà thật ra đã vào → sửa thành "mới tham gia".
        #     Lưới an toàn cho mọi kiểu đọc sai trạng thái trên trang nhóm.
        #  2. Làm sạch: rời nhóm ngoài danh sách mục tiêu.
        lam_sach_nay = nguon == "MARKET" and lam_sach
        if nhom_loi or lam_sach_nay:
            try:
                dang_o = await _lay_nhom_da_vao(page, chu_the)
            except Exception as e:
                _log("warning", f"⚠️  Không đọc lại được danh sách nhóm: {e}")
                dang_o = None

            if dang_o and nhom_loi:
                sua = [g for g in nhom_loi
                       if _dinh_danh_nhom(g["uid"], g["link_url"]) & dang_o]
                for g in sua:
                    for r in results:
                        if r["uid"] == g["uid"] and r["result"] == "loi":
                            r["result"] = "moi_join"
                stats["loi"]      -= len(sua)
                stats["moi_join"] += len(sua)
                if sua:
                    _log("info", f"🔁 Đối chiếu: {len(sua)} nhóm ghi lỗi thật ra "
                                 f"đã vào — tính lại thành mới tham gia")

            # LÀM SAU khi tham gia, và CHỈ KHI đã vào được ít nhất một nhóm mục
            # tiêu. Bản cũ làm sạch TRƯỚC: bước tham gia mà hỏng thì nick rời
            # sạch nhóm cũ, không vào được nhóm mới — mất trắng, nhóm cần duyệt
            # phải xin lại từ đầu. Nhóm mới GỬI YÊU CẦU (chờ duyệt) không tính:
            # có thể không bao giờ được duyệt.
            if lam_sach_nay:
                if stats["moi_join"] + stats["da_join"] == 0:
                    _log("warning", "🧹 BỎ QUA làm sạch: chưa vào được nhóm mục "
                                    "tiêu nào — rời nhóm cũ lúc này là mất trắng")
                elif dang_o is None:
                    _log("warning", "🧹 BỎ QUA làm sạch: không đọc được danh sách nhóm")
                else:
                    # Ghi luôn số nhóm vừa đối chiếu lại: không thì bảng vẫn
                    # hiện số lỗi cũ suốt thời gian làm sạch.
                    _update_status("Đang chạy", moi_join=stats["moi_join"],
                                   da_join=stats["da_join"], loi=stats["loi"])
                    stats["da_roi"] = await _lam_sach_nhom(
                        page, groups_goc, dang_o,
                        bao=lambda n: _update_status("Đang chạy", da_roi=n))

        await ctx.close()

    ket_qua = json.dumps(results, ensure_ascii=False)
    _update_status("Hoàn thành",
                   tong_nhom=total,
                   moi_join=stats["moi_join"],
                   da_join=stats["da_join"],
                   loi=stats["loi"],
                   da_roi=stats.get("da_roi", 0),
                   ket_qua=ket_qua)

    _log("info", f"\n✅ HOÀN THÀNH:")
    _log("info", f"   Mới tham gia: {stats['moi_join']}")
    _log("info", f"   Đã join rồi:  {stats['da_join']}")
    _log("info", f"   Chờ duyệt:    {stats['cho_duyet']}")
    _log("info", f"   Lỗi:          {stats['loi']}")


def run_join_schedule(schedule_id: int, acc_name: str, page_uid: str, nguon: str = ""):
    """Sync wrapper — gọi từ scheduler."""
    global _ACC
    _ACC = acc_name          # mọi dòng log của phiên này gắn kèm tên acc
    asyncio.run(_run_join(schedule_id, acc_name, page_uid, nguon))
