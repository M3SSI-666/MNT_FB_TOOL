"""
market_poster.py — Đăng một bài niêm yết Marketplace, tự tick nhóm.

Khác ba luồng đăng kia ở mấy điểm cốt lõi, đã đo thật trước khi viết (xem lịch
sử phát triển trong git):

  · Đăng dưới tên ACC CÁ NHÂN, KHÔNG chuyển sang Page. Bài niêm yết luôn mang
    tên người bán cá nhân.
  · Chọn nhóm NGAY TRÊN TRANG, không mượn composer: trang chọn nhóm liệt kê
    sẵn mọi nhóm acc đã vào, lọc theo từ khoá rồi bốc ngẫu nhiên tối đa 20.
  · Ảnh được dán HUY HIỆU SỐ ĐIỆN THOẠI (chỉ Marketplace), không phải mã 8 ký
    tự như các luồng khác — truyền `sdt` cho prepare_images_for_post.
  · Giá SINH ngẫu nhiên mỗi bài (chẵn, dưới 1000).

Luồng, đo trên nick Sa Tran Anh ~145 giây/bài:
  khởi động (lướt newsfeed) → trang điền thông tin (ảnh, tiêu đề, giá, hạng
  mục, tình trạng, mô tả) → Tiếp → trang chọn nhóm (tick 20) → Đăng → kết
  phiên (lướt + like + kiểm vi phạm).

GIỚI HẠN ĐÃ BIẾT — đọc trước khi mong đợi:
Facebook so bài mới với bài CŨ CÒN SỐNG của chính nick đó. Trùng tiêu đề + mô
tả + ảnh thì bị từ chối thẳng ("có vẻ giống một bài niêm yết khác"). Giá và
huy hiệu KHÔNG cứu được — đã đo. Cách duy nhất hiệu quả là MỖI PHIÊN MỘT
CONTENT khác: lịch truyền `ma_content` riêng cho từng slot, hai content khác
nhau lệch 26–36 bit pHash. Poster này đăng đúng content được giao, việc xoay
content là ở khâu lập lịch.
"""

import asyncio
import random

from cookie_exporter import load_cookie
from utils import logger, CookieDeadError, LoiBuoc
from fb_common import (browser_launch_kwargs, browse_and_like, chua_dang_nhap,
                       danh_dau_da_dang, dong_dialog_canh_bao, dong_hop_cookie,
                       find_profile_dir, human_delay, kiem_vi_pham)
from config import HEADLESS

import db

# Cùng khoảng với các luồng khác — hai luồng lướt khác nhau thì chính cái khác
# nhau đó thành dấu vết nhận ra máy.
FEED_GIAY = (8, 12)      # lướt đầu phiên, KHÔNG like
KET_GIAY  = (8, 12)      # lướt cuối phiên
KET_LIKE  = 1            # chỗ DUY NHẤT có like trong phiên

# Đọc danh sách nhóm ở trang chọn nhóm. Gắn data-mnt vào CHÍNH phần tử đọc được
# rồi bấm theo nhãn đó — đánh số theo danh sách đã lọc rồi lấy phần tử theo chỉ
# số ấy từ selector khác thì lệch hàng, tick sai nhóm mà vẫn báo thành công.
# `chu` phải là CẢ DÒNG ("<tên> 5,3K thành viên · Công khai") để lọc từ khoá.
_JS_NHOM = r"""() => {
  const nhin = e => {const b=e.getBoundingClientRect(); return b.width>0&&b.height>0;};
  const ra = []; let i = 0;
  for (const el of document.querySelectorAll('input[type=checkbox],[role=checkbox]')) {
    let t = el, chu = '';
    for (let k = 0; k < 8 && t; k++) {
      t = t.parentElement; if (!t) break;
      const c = (t.innerText || '').trim().replace(/\s+/g, ' ');
      if (c && c.length > 3 && c.length < 160) { chu = c; break; }
    }
    // Input thật hay bị div phủ lên; bấm thẳng vào nó là bấm chỗ không nhận
    // click. Tìm tổ tiên bấm được gần nhất.
    let bam = el, p = el;
    for (let k = 0; k < 5 && p; k++) {
      p = p.parentElement; if (!p) break;
      const r = p.getAttribute('role');
      if (p.tagName === 'LABEL' || r === 'button' || r === 'checkbox') { bam = p; break; }
    }
    el.setAttribute('data-mnt', String(i));
    bam.setAttribute('data-mnt-bam', String(i));
    ra.push({i, chu, hien: nhin(el),
             tick: el.type === 'checkbox' ? !!el.checked
                   : el.getAttribute('aria-checked') === 'true'});
    i++;
  }
  return ra;
}"""

_JS_NUT = r"""() => {
  const ra = [];
  for (const el of document.querySelectorAll('[role=button],button')) {
    const b = el.getBoundingClientRect();
    if (b.width <= 0 || b.height <= 0) continue;
    const c = (el.innerText || '').trim().replace(/\s+/g, ' ');
    if (!c || c.length > 60) continue;
    ra.push({chu: c, khoa: el.getAttribute('aria-disabled') === 'true',
             x: Math.round(b.x + b.width / 2), y: Math.round(b.y + b.height / 2)});
  }
  return ra;
}"""

# Một ô tick đọc theo nhãn, để kiểm chứng TỪNG cú bấm thay vì đếm số lần click.
_JS_MOT_O = """(n) => {
    const e = document.querySelector('[data-mnt="' + n + '"]');
    if (!e) return null;
    return e.type === 'checkbox' ? !!e.checked
           : e.getAttribute('aria-checked') === 'true';
}"""


async def _bam_dung_chu(page, chu: str):
    """Bấm nút có innerText ĐÚNG BẰNG `chu`. Trả (bấm được, có khoá không).

    Khớp chính xác chứ không phải ':has-text' (khớp chuỗi con): trên trang điền
    thông tin, chữ "...bạn có thể TIẾP cận nhiều người mua" nằm trong một nút
    bấm được, khớp lỏng là trúng nó chứ không trúng nút Tiếp thật.
    """
    hop = [n for n in await page.evaluate(_JS_NUT) if n["chu"] == chu]
    if not hop:
        return False, None
    n = sorted(hop, key=lambda z: -z["y"])[0]     # nút điều hướng nằm dưới cùng
    if n["khoa"]:
        return False, True
    await page.mouse.click(n["x"], n["y"])
    return True, False


async def _chon_lua(page, gt: str) -> bool:
    """Bấm một lựa chọn trong menu vừa bung. Khớp CHÍNH XÁC trước rồi mới tiền
    tố — "Mới" là chuỗi con của nhiều mục khác, khớp lỏng là chọn nhầm."""
    js = """(gt) => {
        const nhin = e => {const b=e.getBoundingClientRect(); return b.width>0&&b.height>0;};
        const chu = e => (e.innerText || '').trim().replace(/\\s+/g, ' ');
        const ds = [...document.querySelectorAll(
            '[role=option],[role=menuitem],[role=menuitemradio],div[role=button]')];
        const el = ds.find(e => nhin(e) && chu(e) === gt)
                || ds.find(e => nhin(e) && chu(e).startsWith(gt));
        if (!el) return null;
        const b = el.getBoundingClientRect();
        return [Math.round(b.x + b.width / 2), Math.round(b.y + b.height / 2)];
    }"""
    xy = await page.evaluate(js, gt)
    if not xy:
        return False
    await page.mouse.click(xy[0], xy[1])
    return True


async def _dien_thong_tin(page, cd: dict, tieu_de: str, gia: str, mo_ta: str, anh: list):
    """Trang điền thông tin: ảnh, tiêu đề, giá, hạng mục, tình trạng, mô tả.

    Tiêu đề lấy từ content (cột `tieu_de_mkt`), giá sinh ngẫu nhiên, tình
    trạng cố định `db.MKT_TINH_TRANG` — ba thứ này không còn ở cài đặt.
    """
    logger.info("  [2/5] 📝 Điền thông tin bài niêm yết...")
    await page.goto("https://www.facebook.com/marketplace/create/item",
                    wait_until="domcontentloaded", timeout=60000)
    await human_delay(7000, 9000)
    await dong_hop_cookie(page)
    await dong_dialog_canh_bao(page)

    if not anh:
        raise LoiBuoc("Marketplace bắt buộc có ảnh nhưng không tải được ảnh nào")
    await page.set_input_files("input[type=file]", anh[:3])
    await human_delay(6000, 8000)

    for nhan, gt in (("Tiêu đề", tieu_de), ("Giá", str(gia))):
        el = await page.wait_for_selector(
            f'label:has-text("{nhan}") input[type="text"]', timeout=8000, state="visible")
        await el.click()
        await human_delay(500, 900)
        await el.fill(gt)
        await human_delay(1500, 2200)

    for nhan, gt in (("Hạng mục", cd["mkt_hang_muc"]),
                     ("Tình trạng", db.MKT_TINH_TRANG)):
        el = await page.wait_for_selector(
            f'label[role="combobox"]:has-text("{nhan}")', timeout=8000, state="visible")
        await el.click()
        await human_delay(2000, 2800)
        if not await _chon_lua(page, gt):
            raise LoiBuoc(f"Không chọn được {nhan} = {gt!r}")
        await human_delay(2000, 2800)

    # Mô tả: ô textarea đầu tiên còn trống.
    for e in await page.query_selector_all("textarea"):
        try:
            if (await e.input_value()).strip():
                continue
            await e.scroll_into_view_if_needed()
            await human_delay(600, 1000)
            await e.click()
            await e.fill(mo_ta[:2000])
            break
        except Exception:
            continue
    await human_delay(2000, 3000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await human_delay(2000, 3000)

    ok, khoa = await _bam_dung_chu(page, "Tiếp")
    if not ok:
        # Nút Tiếp khoá tới khi đủ 5 ô bắt buộc — khoá nghĩa là một ô chưa vào.
        raise LoiBuoc(f"Không sang được trang chọn nhóm (nút Tiếp {'khoá' if khoa else 'không thấy'})")
    await human_delay(8000, 10000)
    await dong_dialog_canh_bao(page)


async def _tick_nhom(page, tu_khoa: str, so_nhom: int) -> int:
    """Trang chọn nhóm: lọc theo từ khoá, bốc ngẫu nhiên, tick. Trả số nhóm đã
    tick (đã kiểm chứng từng ô, không phải đếm số lần bấm)."""
    logger.info("  [3/5] ☑️  Chọn nhóm để niêm yết...")
    # Cuộn hết để Facebook dựng đủ danh sách nhóm ra DOM.
    for _ in range(5):
        await page.mouse.wheel(0, 1000)
        await human_delay(800, 1200)
    await page.evaluate("window.scrollTo(0, 0)")
    await human_delay(1500, 2200)

    ds = await page.evaluate(_JS_NHOM)
    # Ô "Niêm yết công khai Marketplace" cũng là checkbox nhưng KHÔNG phải nhóm
    # (không có "thành viên" trong dòng chữ), tick sẵn và không bỏ được — để yên.
    nhom = [x for x in ds if "thành viên" in x["chu"]]
    if not nhom:
        raise LoiBuoc("Không đọc được nhóm nào ở trang chọn nhóm")

    chon, _loai = db.chon_nhom_marketplace(
        [{"ten": x["chu"], "i": x["i"]} for x in nhom], tu_khoa, so_nhom)
    if not chon:
        raise LoiBuoc(f"Không nhóm nào khớp từ khoá {tu_khoa!r} trong {len(nhom)} nhóm")

    da = 0
    for c in chon:
        i = c["i"]
        if ds[i]["tick"]:
            da += 1
            continue
        try:
            o = await page.query_selector(f'[data-mnt-bam="{i}"]')
            await o.scroll_into_view_if_needed()
            await human_delay(400, 800)
            await o.click()
            await human_delay(500, 900)
            if await page.evaluate(_JS_MOT_O, i):
                da += 1
        except Exception as e:
            logger.debug(f"    tick nhóm {i} hỏng: {str(e)[:50]}")

    logger.info(f"  ☑️  Đã tick {da}/{len(chon)} nhóm")
    if da == 0:
        raise LoiBuoc("Bấm nhưng không tick được nhóm nào")
    return da


async def _bam_dang(page, acc_name: str) -> bool:
    """Bấm Đăng rồi chờ Facebook xác nhận bài đã lên. Trả True nếu đăng xong."""
    logger.info("  [4/5] 📤 Đăng...")
    ok, khoa = await _bam_dung_chu(page, "Đăng")
    if not ok:
        raise LoiBuoc(f"Không thấy nút Đăng (khoá={khoa})")

    # KHÔNG đóng dialog trước khi đọc: popup sau khi đăng chính là tín hiệu
    # dính spam, đóng trước khi đọc là mất bằng chứng.
    js = """() => {
        const d = [...document.querySelectorAll('[role=dialog],[role=alertdialog]')]
          .filter(e => {const b=e.getBoundingClientRect(); return b.width>0&&b.height>0;})
          .map(e => (e.innerText||'').replace(/\\s+/g,' ').slice(0,200));
        return {url: location.href, dialog: d};
    }"""
    for _ in range(5):
        await asyncio.sleep(10)
        r = await page.evaluate(js)
        if r["dialog"]:
            logger.warning(f"  ⚠️  Popup sau khi đăng: {r['dialog']}")
        if "/marketplace/item/" in r["url"] or "/you/selling" in r["url"]:
            # Mốc "đã đưa nội dung lên", đánh NGAY khi biết bài đã lên: kiem_vi_pham
            # dựa vào mốc này để phân biệt cảnh báo CÓ TRƯỚC hay SAU lúc đăng.
            danh_dau_da_dang(page)
            import nhip_dap
            nhip_dap.ghi("dang_marketplace")
            logger.info(f"  ✅ [{acc_name}] ĐĂNG THÀNH CÔNG!")
            return True
    logger.warning(f"  ⚠️  [{acc_name}] Hết 50s vẫn ở trang tạo bài — không chắc đã đăng")
    return False


_DAU_BI_CHAN = "giống một bài niêm yết khác"


async def _dem_bi_chan(page) -> int:
    """Đếm số bài đang bị chặn vì trùng content ở trang Đang bán. -1 nếu đọc hỏng.

    Phải ĐẾM chứ không chỉ kiểm "có hay không": nick dùng lâu sẽ còn nhiều bài
    cũ bị từ chối nằm lại trong mục "Cần chú ý", nên "có bài bị chặn" luôn đúng
    và thành báo động giả mọi phiên. So số TRƯỚC và SAU khi đăng thì mới biết
    bài VỪA đăng có bị chặn hay không.
    """
    try:
        await page.goto("https://www.facebook.com/marketplace/you/selling",
                        wait_until="domcontentloaded", timeout=30000)
        await human_delay(5000, 7000)
        await dong_dialog_canh_bao(page)
        return await page.evaluate(
            """(dau) => {
                const t = (document.body.innerText || '');
                let n = 0, i = 0;
                while ((i = t.indexOf(dau, i)) !== -1) { n++; i += dau.length; }
                return n;
            }""", _DAU_BI_CHAN)
    except Exception as e:
        logger.debug(f"    đếm bài bị chặn hỏng: {str(e)[:50]}")
        return -1


async def _run_marketplace(acc_name: str, message: str, local_photos: list,
                           c_user: str = "", tieu_de: str = "") -> int:
    from playwright.async_api import async_playwright

    cd = db.doc_cai_dat_mkt()
    gia = db.sinh_gia()
    so_nhom = db.MKT_SO_NHOM
    mo_ta = (message or "").strip()
    if not mo_ta:
        raise LoiBuoc("Content rỗng — không có mô tả để đăng")

    profile_dir = find_profile_dir(acc_name, c_user)
    logger.info(f"  🗂️  Profile: {profile_dir}")
    logger.info(f"  🏷️  Tiêu đề: {tieu_de}")
    logger.info(f"  💰 Giá: {gia}  ·  📦 {cd['mkt_hang_muc']}/{db.MKT_TINH_TRANG}  "
                f"·  🔑 từ khoá: {cd['mkt_tu_khoa']}")

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir, **browser_launch_kwargs(HEADLESS))
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Cookie: y như via_poster — c_user/xs là httpOnly.
        ck = load_cookie(acc_name, c_user)
        if not ck:
            await ctx.close()
            raise LoiBuoc("Không có cookie trong máy")
        _ci = []
        for name in ("c_user", "xs"):
            if ck.get(name):
                _ci.append({"name": name, "value": ck[name], "domain": ".facebook.com",
                            "path": "/", "httpOnly": True, "secure": True, "sameSite": "None"})
        for name in ("datr", "sb", "fr", "wd"):
            if ck.get(name):
                _ci.append({"name": name, "value": ck[name], "domain": ".facebook.com",
                            "path": "/", "httpOnly": False, "secure": True, "sameSite": "None"})
        await ctx.add_cookies(_ci)
        await page.set_viewport_size({"width": 1400, "height": 1000})

        # ── [1/5] Khởi động: lướt newsfeed cá nhân ──────────────────────
        # Giống luồng comment/hybrid. KHÔNG like, KHÔNG chuyển Page. Bọc
        # try/except: hỏng khởi động mà mất cả lượt đăng thì lỗ hơn.
        logger.info("  [1/5] 🔥 Khởi động: lướt newsfeed...")
        try:
            await page.goto("https://www.facebook.com/",
                            wait_until="domcontentloaded", timeout=30000)
            await human_delay(1500, 2500)
            if await chua_dang_nhap(page):
                await ctx.close()
                raise CookieDeadError(acc_name)
            await dong_hop_cookie(page)
            await dong_dialog_canh_bao(page)
            await browse_and_like(page, duration_sec=random.randint(*FEED_GIAY),
                                  max_likes=0)
        except CookieDeadError:
            raise
        except Exception as e:
            logger.warning(f"    ⚠️  Lướt newsfeed không trọn vẹn: {str(e)[:60]}")

        # Đếm bài đang bị chặn TRƯỚC khi đăng, để cuối phiên so xem bài vừa đăng
        # có làm con số tăng không. Một người bán ghé xem bài của mình trước khi
        # đăng bài mới cũng là hành vi bình thường.
        bi_chan_truoc = await _dem_bi_chan(page)

        # ── [2/5] Điền thông tin · [3/5] Tick nhóm · [4/5] Đăng ─────────
        await _dien_thong_tin(page, cd, tieu_de, gia, mo_ta, local_photos)
        so_tick = await _tick_nhom(page, cd["mkt_tu_khoa"], so_nhom)
        da_dang = await _bam_dang(page, acc_name)

        # ── [5/5] Kết phiên: lướt + like + kiểm vi phạm ─────────────────
        # Đăng xong tắt máy ngay cũng là khuôn máy. Quãng lướt này còn là CỬA SỔ
        # để Facebook kịp đổ cảnh báo về — bỏ đi thì kiem_vi_pham phán khi thông
        # báo chưa tới, thành ra luôn sạch.
        logger.info("  [5/5] 🏁 Kết phiên...")
        try:
            await page.goto("https://www.facebook.com/",
                            wait_until="domcontentloaded", timeout=30000)
            await human_delay(1500, 2500)
            await dong_dialog_canh_bao(page)
            await browse_and_like(page, duration_sec=random.randint(*KET_GIAY),
                                  max_likes=KET_LIKE)
            await kiem_vi_pham(page, acc_name, "phiên Marketplace")
        except Exception as e:
            logger.warning(f"    ⚠️  Kết phiên không trọn vẹn: {str(e)[:60]}")

        # Dò trùng content: chỉ cảnh báo khi số bài bị chặn TĂNG so với trước
        # khi đăng — tức bài vừa đăng bị Facebook chặn vì trùng. Bài cũ bị chặn
        # còn nằm lại không tính. Không tính là lỗi phiên: bài đã bấm đăng rồi.
        if da_dang and bi_chan_truoc >= 0:
            bi_chan_sau = await _dem_bi_chan(page)
            if bi_chan_sau > bi_chan_truoc:
                logger.warning(f"  ⚠️  [{acc_name}] Bài vừa đăng BỊ CHẶN vì trùng "
                               f"nội dung — đổi content cho nick này")
                try:
                    import thong_bao
                    thong_bao.gui(f"⚠️ Marketplace [{acc_name}]: bài vừa đăng bị "
                                  f"chặn vì trùng nội dung. Nên đổi content.")
                except Exception:
                    pass

        await ctx.close()
        if not da_dang:
            raise LoiBuoc("Bấm Đăng rồi nhưng không xác nhận được bài đã lên")
        return so_tick


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def post_marketplace(acc_name: str, message: str, image_url: str = "",
                     c_user: str = "", tieu_de: str = "") -> int:
    """
    Hàm đồng bộ — gọi từ scheduler (chạy trong thread).

    Args:
        acc_name:  Tên acc đăng (dưới tên cá nhân, không qua Page)
        message:   Nội dung bài — dùng làm Mô tả. Lịch truyền ma_content riêng
                   từng slot, nên mỗi phiên một content khác để tránh bị Facebook
                   từ chối vì trùng bài cũ.
        image_url: Link ảnh (bắt buộc — Marketplace không đăng được nếu thiếu ảnh)
        c_user:    c_user của acc, khi có nhiều acc trùng tên
        tieu_de:   Tiêu đề bài niêm yết — cột "Tiêu đề Market Place" của content

    Returns:
        Số nhóm đã tick nếu thành công. Raise LoiBuoc / CookieDeadError nếu hỏng.
    """
    # Kiểm TRƯỚC khi tải ảnh và mở trình duyệt: thiếu tiêu đề thì nút "Tiếp"
    # của Facebook khoá cứng, phiên chạy hết bước điền mới hỏng — phí cả phiên.
    tieu_de = (tieu_de or "").strip()
    if not tieu_de:
        raise LoiBuoc("Content chưa có Tiêu đề Market Place")
    if not image_url:
        raise LoiBuoc("Marketplace bắt buộc có ảnh")

    local_photos = []
    temp_dir = None
    try:
        from storage import prepare_images_for_post as smart_download
        # sdt → dán huy hiệu số điện thoại, CHỈ Marketplace. Không truyền thì
        # ảnh quay về đánh mã 8 ký tự như các luồng khác.
        sdt = db.doc_cai_dat_mkt().get("mkt_sdt_anh", "")
        local_photos, temp_dir = smart_download(image_url, seed_key=acc_name, sdt=sdt)
        logger.info(f"  📥 {len(local_photos)} ảnh đã chuẩn bị")
    except Exception as e:
        logger.warning(f"  ⚠️  Chuẩn bị ảnh hỏng: {e}")

    try:
        return asyncio.run(_run_marketplace(
            acc_name=acc_name, message=message,
            local_photos=local_photos, c_user=c_user, tieu_de=tieu_de))
    except CookieDeadError:
        raise
    except Exception as e:
        logger.error(f"❌ [{acc_name}] Lỗi Marketplace: {e}")
        raise
    finally:
        if temp_dir:
            try:
                from storage import cleanup_temp
                cleanup_temp(temp_dir)
            except Exception:
                pass
