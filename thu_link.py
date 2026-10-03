"""
thu_link.py — Thu link các bài vừa đăng, để đưa vào danh sách đi comment.

Bài toán
────────
Luồng đăng chéo dùng tính năng "Thêm nhóm" có sẵn của Facebook: một cú bấm Đăng
tạo ra 9 bài ở 9 nhóm. Giao diện **không trả về URL nào** — composer chỉ đóng
lại. Nhưng muốn đi comment để đẩy bài lên thì phải có URL.

Hai cách thu, dùng bổ trợ cho nhau
──────────────────────────────────
1. `BoBatLink` — nghe phản hồi mạng ngay lúc bấm Đăng. Facebook trả ID bài mới
   trong phản hồi GraphQL. Lấy được thì là chính xác tuyệt đối: đúng bài vừa
   đăng, không phải đoán.

2. `thu_tu_nhat_ky_page()` — đọc nhật ký hoạt động của Page sau khi đăng:
   `profile.php?id=<PAGE_UID>&sk=allactivity&category_key=GROUPPOSTS`
   Chậm hơn vài giây nhưng đã kiểm chứng là chạy được.

**Phải là nhật ký của PAGE, không phải của acc cá nhân.** Bài đăng chéo mang
tên Page (luồng đăng có bước switch sang Page), nên nhật ký acc cá nhân chỉ
hiện các bài cũ do chính người đó đăng — lấy nhầm là đi comment vào bài từ
nhiều tháng trước.
"""

import re
import json
import asyncio

from utils import logger

# Chờ bao lâu sau khi bấm Đăng rồi mới mở trang thông báo.
# Facebook đẩy thông báo "Đã đăng chéo…" theo từng nhóm và KHÔNG đồng thời —
# mở quá sớm thì mới về vài cái, thu thiếu link.
#
# Từng để 90s. Hạ xuống 60s vì 90s chiếm tới 37% cả chu trình đăng bài mà
# phần lớn là đứng im. Đây là ĐÁNH ĐỔI có ý thức: đo cũ cho thấy 60s thu được
# 8/9 nhóm, tức có thể hụt một link mỗi phiên. Chấp nhận được vì còn nguồn (c)
# — nhật ký Page — tự chạy bù khi số link thu được ít hơn số nhóm đã tick.
#
# ĐÃ THỬ cách dò lặp để dừng sớm rồi BỎat: mỗi lượt dò tốn ~13s tải trang,
# nên khi thông báo về chậm thì tổng lên tới 136s — tệ hơn cả ngủ thẳng 90s.
# Một con số cố định đoán trước được tốt hơn một vòng lặp thông minh nửa vời.
CHO_THONG_BAO_GIAY = 60

# Số link lấy về mỗi lượt thu, tính từ bài MỚI NHẤT trở xuống.
#
# Từ bản 2.33 việc thu link chuyển sang đầu phiên sau, nên cửa sổ thời gian nới
# rộng tới 24 giờ — đọc một lần là thấy thông báo của nhiều phiên trước. Đo ngày
# 02/10: một lượt đọc ra 52 thông báo, 31 link mới. Nhiều hơn mức cần.
#
# Thư viện comment là CỬA SỔ TRƯỢT có hạn mức: link mới đẩy link cũ ra. Đổ 31
# link mỗi phiên vào đó thì danh sách bị thay gần hết trước khi kịp đi comment.
# Mười link gần nhất là đủ để luôn có bài mới mà không xáo tung thư viện.
#
# `thu_tu_thong_bao` xếp kết quả theo thứ tự ĐÁNG THU NHẤT trước khi trả về
# (chưa đọc trước, rồi mới tới cũ — xem `xep_uu_tien`), nên cắt 10 phần tử đầu
# là 10 bài cần thu nhất, không phải 10 dòng Facebook tình cờ bày lên trên.
#
# Đo 03/10 trên Page Jenniee Homestay: một đợt đăng chéo để lại ĐÚNG 8 thông
# báo chưa đọc — khớp số nhóm đăng được. Mười chỗ là vừa đủ phủ một phiên mà
# còn hai chỗ bù cho phiên trước.
THU_LINK_MOI_NHAT = 10

# Định danh nhóm có thể là SỐ hoặc SLUG chữ ("homestaytimescity",
# "homestay.timescity.hanoi"). Chỉ khớp \d+ là bỏ sót các nhóm dùng slug —
# đo thật: 2/7 nhóm trong một đợt đăng chéo dùng slug.
_GID = r"[0-9A-Za-z._-]+"

# https://www.facebook.com/groups/424606314926955/posts/1966984447355793/
RE_LINK_NHOM = re.compile(rf"/groups/({_GID})/(?:permalink|posts)/(\d+)")
# Trong JSON của GraphQL, id bài thường nằm ở các khoá này.
RE_ID_BAI = re.compile(r'"(?:post_id|story_fbid|legacy_story_id)"\s*:\s*"?(\d{8,})"?')

# Thông báo "Đã đăng chéo bài viết của bạn lên <nhóm>":
#   /groups/<gid>/?multi_permalinks=<pid>&notif_t=group_crossposting_published
RE_THONG_BAO_CHEO = re.compile(rf"/groups/({_GID})/\?[^\"'\s]*multi_permalinks=(\d+)")
# Thông báo "Quản trị viên đã phê duyệt bài/ảnh của bạn":
#   /groups/<gid>/posts/<pid>/?notif_t=group_post_approved
RE_THONG_BAO_DUYET = re.compile(rf"/groups/({_GID})/posts/(\d+)/\?[^\"'\s]*notif_t=group_post_approved")

# "13 phút" / "1 giờ" / "2 ngày" → số phút
RE_TUOI = re.compile(r"(\d+)\s*(phút|giờ|ngày|tuần|minute|hour|day|week)")
_HE_SO = {"phút": 1, "minute": 1, "giờ": 60, "hour": 60,
          "ngày": 1440, "day": 1440, "tuần": 10080, "week": 10080}

# Facebook dán hẳn chữ "Chưa đọc" vào đầu mỗi dòng thông báo chưa xem — đo
# 03/10 trên Page Jenniee Homestay: cả 14/14 mẫu đều mở đầu bằng chữ này.
#
# Đã thử hai manh mối khác và BỎ: màu nền (`backgroundColor`) trả
# `rgba(0,0,0,0)` cho cả đọc lẫn chưa đọc, còn "có chấm tròn" thì `true` cho
# tất cả vì trang đầy `svg circle` của thứ khác. Chữ là manh mối duy nhất chắc.
_DAU_CHUA_DOC = "chưa đọc"


def tuoi_phut(text: str):
    """Thông báo này bao nhiêu phút trước? Không đọc được thì None."""
    m = RE_TUOI.search(text or "")
    if not m:
        return None
    return int(m.group(1)) * _HE_SO.get(m.group(2).lower(), 1)


def la_chua_doc(mo_ta: str) -> bool:
    """
    Thông báo này CHƯA ĐỌC chưa?

    Chỉ soi 20 ký tự đầu, không soi cả chuỗi: tên nhóm nằm ở giữa mô tả và
    hoàn toàn có thể chứa chữ "chưa đọc" — soi cả chuỗi là tự tạo dương tính giả.
    """
    return _DAU_CHUA_DOC in (mo_ta or "")[:20].lower()


def xep_uu_tien(cap_link: list) -> list:
    """
    Xếp [(url, mo_ta), ...] theo thứ tự CẦN THU TRƯỚC: chưa đọc trước đã đọc,
    trong mỗi nhóm thì mới trước cũ.

    Để bên gọi cắt N phần tử đầu là được đúng N bài đáng thu nhất.

    **Chưa đọc là tiêu chí YẾU, tuổi mới là thứ gánh việc.** Ý ban đầu là
    "chưa đọc" = "về sau lần thu gần nhất" = bài mình chưa lấy, và dấu này tự
    bảo trì vì mở trang thông báo thì Facebook đánh dấu đã đọc.
    ĐO 03/10 BÁC BỎ ĐIỀU ĐÓ: mở trang thông báo của Page hai lần trong 7 phút,
    cả 45/45 thông báo vẫn còn "Chưa đọc" — kể cả cái 8 tiếng tuổi. Facebook
    không tự xoá dấu chỉ vì mình vào xem.

    Nên trong thực tế mọi thông báo đăng chéo đều chưa đọc, hai hạng gộp làm
    một, và thứ tự rút về đúng bằng xếp theo tuổi. Vẫn giữ tiêu chí này vì khi
    nào nó CÓ khác thì cái khác đó là tín hiệu thật, và nó không tốn gì — nhưng
    đừng tin nó nhận ra được "bài đã thu rồi". Việc chống thu lại nằm ở chỗ
    khác: `them_comment_posts` bỏ trùng theo URL.

    **Vì sao XẾP chứ không LỌC lấy riêng chưa đọc.** Nếu có ngày Facebook đánh
    dấu đã đọc thật, mà một phiên lại hỏng giữa đường sau khi đã mở trang thông
    báo, thì mớ đó thành "đã đọc" trong khi chưa kịp vào thư viện — lọc là mất
    hẳn. Xếp thì hết chưa đọc sẽ tự bù bằng bài đã đọc mới nhất, không mất gì.

    **Tuổi.** Không đọc được tuổi ("Vừa xong", "Just now") thì coi là 0 phút —
    đúng là mới nhất, và mất một mốc tuổi không được phép đẩy nó xuống cuối.

    Trước bản 2.33 hàm thu trả về nguyên thứ tự `querySelectorAll`, tức thứ tự
    Facebook bày trên trang. Nó tình cờ đúng vì trang xếp mới nhất trước, nhưng
    đó là giả định về giao diện người khác chứ không phải điều mình bảo đảm.

    `sort` của Python ổn định, nên hai thông báo CÙNG hạng vẫn giữ thứ tự trang.
    Điều này có ý nghĩa thật: nhãn tuổi của Facebook chỉ đến từng phút, nên 8
    nhóm của cùng một đợt đăng chéo đều ghi "8 phút" và không tài nào phân biệt
    được bằng tuổi. Xếp theo tuổi phân đúng GIỮA các phiên; trong cùng một
    phiên thì vị trí trang vẫn là tiêu chí phụ.
    """
    return sorted(cap_link,
                  key=lambda x: (0 if la_chua_doc(x[1]) else 1,
                                 tuoi_phut(x[1]) or 0))


# ĐÃ THỬ kiểm link sống/chết ngay tại đây và BỎ — đo 03/10:
#
#   • Cách rẻ `ctx.request.get(url)` (chỉ tải HTML, không dựng trang): Facebook
#     trả HTTP 400 "Error" dài đúng 1542 ký tự cho MỌI link, sống chết như
#     nhau. Không có đường nào nhẹ hơn là mở trang thật.
#   • Mở trang thật: 4,9s/link, hạ xuống 1,6s/link khi mở 4 tab cùng lúc —
#     tức +16s mỗi phiên cho 10 link.
#   • Hai lượt đo, 21 link, CHẾT ĐÚNG 0 CÁI.
#
# Lý do không bắt được gì: bài bị admin gỡ MUỘN HƠN lúc thu. Con số 20–30% bài
# chết (xem `db.ghi_nhan_comment`) là đo ở lúc đi comment, cách đó nhiều giờ.
# Mà phiên comment thì đã mở sẵn từng bài rồi, nên phát hiện và xoá link chết ở
# đó không tốn thêm giây nào — cơ chế ấy đã chạy từ trước.
#
# Nên: thu 10 link rồi ném thẳng vào thư viện. Để `comment_bai` dọn link chết.
#
# Còn bài CHỜ DUYỆT thì không cần lọc: Facebook không gửi thông báo nào cho bài
# còn trong hàng chờ (đo 03/10: 53 thông báo, 0 cái thuộc loại chờ duyệt), nên
# nó không bao giờ vào danh sách để mà phải loại.


def _chuan_hoa(gid: str, pid: str) -> str:
    return f"https://www.facebook.com/groups/{gid}/posts/{pid}/"


class BoBatLink:
    """
    Nghe phản hồi mạng để tóm ID bài vừa đăng.

    Cách dùng:
        bat = BoBatLink(page)
        bat.bat_dau()
        ... bấm Đăng, chờ composer đóng ...
        links = await bat.ket_qua()

    Toàn bộ được bọc try/except: đây là tính năng phụ, hỏng ở đây tuyệt đối
    không được làm hỏng việc đăng bài.
    """

    def __init__(self, page):
        self.page = page
        self.links = []          # URL đầy đủ bắt được
        self.id_le  = []         # id bài không kèm id nhóm — cần ghép sau
        self._dang_nghe = False
        self._raw = []           # giữ vài mẫu thô để soi khi selector hỏng

    def bat_dau(self):
        if self._dang_nghe:
            return
        try:
            self.page.on("response", self._nghe)
            self._dang_nghe = True
        except Exception as e:
            logger.warning(f"    ⚠️  Không gắn được bộ bắt link: {e}")

    def dung(self):
        try:
            if self._dang_nghe:
                self.page.remove_listener("response", self._nghe)
        except Exception:
            pass
        self._dang_nghe = False

    async def _nghe(self, resp):
        try:
            if "/api/graphql" not in resp.url and "/graphql" not in resp.url:
                return
            body = await resp.text()
        except Exception:
            return                      # phản hồi nhị phân / đã bị huỷ
        try:
            for gid, pid in RE_LINK_NHOM.findall(body):
                u = _chuan_hoa(gid, pid)
                if u not in self.links:
                    self.links.append(u)
            for pid in RE_ID_BAI.findall(body):
                if pid not in self.id_le:
                    self.id_le.append(pid)
            if (RE_LINK_NHOM.search(body) or RE_ID_BAI.search(body)) and len(self._raw) < 3:
                self._raw.append(body[:1500])
        except Exception:
            pass

    def ket_qua(self) -> dict:
        return {"links": list(self.links), "id_le": list(self.id_le),
                "mau_tho": list(self._raw)}


async def thu_tu_thong_bao(page, toi_da_phut: int = 180,
                           so_luot_cuon: int = 4) -> list:
    """
    Thu link từ TRANG THÔNG BÁO — nguồn tốt nhất trong ba cách.

    Sau mỗi lần đăng chéo, Facebook đẩy về **một thông báo cho TỪNG nhóm**:
        "Đã đăng chéo bài viết của bạn lên <tên nhóm>."
    Link của thông báo chứa sẵn `multi_permalinks=<id bài>`, nên **không cần bấm
    vào từng thông báo** — đọc thẳng href là ra.

    Đo thật trên một đợt đăng chéo của Page Jenniee Homestay:
        • trang thông báo : 7 link
        • nhật ký Page    : 2 link
        • phản hồi mạng   : 1 link
    Thông báo còn kèm "13 phút"/"1 giờ" nên lọc được đúng đợt vừa đăng, và bắt
    thêm cả loại `group_post_approved` (bài được duyệt muộn).

    GỌI SAU KHI ĐÃ CHUYỂN SANG PAGE — thông báo của Page khác của acc cá nhân.

    `toi_da_phut`: chỉ lấy thông báo mới hơn bấy nhiêu phút (0 = lấy tất).
    Trả về [(url, mo_ta), ...] XẾP THEO TUỔI, mới nhất đứng đầu — nên bên gọi
    cắt N phần tử đầu là lấy đúng N bài gần nhất.
    """
    from fb_common import human_delay, dong_dialog_canh_bao

    JS = r"""() => {
      const ra = [], seen = new Set();
      for (const a of document.querySelectorAll('a[href*="/groups/"]')) {
        const h = a.href || '';
        if (!/notif_t=group_(crossposting_published|post_approved)/.test(h)) continue;
        let b = a, t = '';
        for (let i = 0; i < 6 && b; i++) {
          b = b.parentElement;
          if (b && b.innerText && b.innerText.length > 15) { t = b.innerText; break; }
        }
        const key = h.split('&notif_id')[0];
        if (seen.has(key)) continue;
        seen.add(key);
        ra.push({h, t: (t || '').replace(/\s+/g, ' ').slice(0, 160)});
      }
      return ra;
    }"""

    await page.goto("https://www.facebook.com/notifications",
                    wait_until="domcontentloaded", timeout=45000)
    await human_delay(4000, 6000)
    await dong_dialog_canh_bao(page)
    for _ in range(max(0, so_luot_cuon)):
        try:
            await page.mouse.wheel(0, 2500)
            await human_delay(1500, 2400)
        except Exception:
            break

    try:
        tho = await page.evaluate(JS)
    except Exception as e:
        logger.warning(f"    ⚠️  Không đọc được trang thông báo: {e}")
        return []

    ra, da_co = [], set()
    for x in tho:
        href, mo_ta = x.get("h", ""), x.get("t", "")
        if toi_da_phut:
            t = tuoi_phut(mo_ta)
            if t is not None and t > toi_da_phut:
                continue
        m = RE_THONG_BAO_CHEO.search(href) or RE_THONG_BAO_DUYET.search(href)
        if not m:
            continue
        u = _chuan_hoa(m.group(1), m.group(2))
        if u in da_co:
            continue
        da_co.add(u)
        ra.append((u, mo_ta))

    # Tuổi và dấu "Chưa đọc" đã đọc được ở vòng lọc trên rồi, xếp lại gần như
    # không tốn gì — mà đổi "đáng thu nhất" từ chỗ đoán theo thứ tự trang thành
    # chỗ đo được.
    return xep_uu_tien(ra)



async def thu_tu_nhat_ky_page(page, page_uid: str, so_luot_cuon: int = 4,
                              gioi_han: int = 40) -> list:
    """
    Đọc nhật ký hoạt động của Page, trả về [(url, mo_ta), ...] mới nhất trước.

    Chỉ lấy mục "đã đăng trong" — nhật ký trộn lẫn cả bình luận, trả lời bình
    luận, đổi ảnh bìa. Lấy nhầm mục bình luận thì danh sách sẽ đầy link bài của
    người khác.

    GỌI SAU KHI ĐÃ CHUYỂN SANG PAGE (`_switch_to_page`), nếu không sẽ ra nhật ký
    của acc cá nhân — toàn bài cũ, sai hoàn toàn.
    """
    from fb_common import human_delay, dong_dialog_canh_bao

    if not page_uid:
        return []

    JS = r"""() => {
      const ra = [], seen = new Set();
      for (const a of document.querySelectorAll('a[href*="/groups/"]')) {
        const m = a.href.match(/[/]groups[/](\d+)[/](?:permalink|posts)[/](\d+)/);
        if (!m) continue;
        const key = m[1] + '/' + m[2];
        if (seen.has(key)) continue;
        seen.add(key);
        let box = a, txt = '';
        for (let i = 0; i < 9 && box; i++) {
          box = box.parentElement;
          if (box && box.innerText && box.innerText.length > 40) { txt = box.innerText; break; }
        }
        ra.push({gid: m[1], pid: m[2], txt: (txt || '').replace(/\s+/g, ' ')});
      }
      return ra;
    }"""

    url = (f"https://www.facebook.com/profile.php?id={page_uid}"
           f"&sk=allactivity&category_key=GROUPPOSTS")
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await human_delay(4000, 6000)
    await dong_dialog_canh_bao(page)

    for _ in range(max(0, so_luot_cuon)):
        try:
            await page.mouse.wheel(0, 3000)
            await human_delay(1500, 2400)
        except Exception:
            break

    try:
        tho = await page.evaluate(JS)
    except Exception as e:
        logger.warning(f"    ⚠️  Không đọc được nhật ký Page: {e}")
        return []

    ra = []
    for x in tho:
        mo_ta = x.get("txt", "")
        # "… đã đăng trong <Tên nhóm>." — mục bình luận có chữ "đã bình luận".
        if "đã đăng trong" not in mo_ta and "posted in" not in mo_ta.lower():
            continue
        ra.append((_chuan_hoa(x["gid"], x["pid"]), mo_ta[:160]))
        if len(ra) >= gioi_han:
            break
    return ra
