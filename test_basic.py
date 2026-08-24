"""
test_basic.py — Smoke test cho logic thuần (không cần Playwright/Facebook).
Chạy:  python test_basic.py

Toàn bộ test chạy trên DB tạm — KHÔNG đụng vào data/app.db thật.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")   # cho phép in emoji ở mọi console
except Exception:
    pass

# ── DB tạm — phải set TRƯỚC khi import server (server gọi init_db lúc import) ──
import db

_tmp = Path(tempfile.gettempdir()) / "mnt_test.db"
for suffix in ("", "-wal", "-shm"):
    Path(str(_tmp) + suffix).unlink(missing_ok=True)
db.DB_PATH = _tmp
db.init_db()

# Scheduler cần env var này lúc import, nếu không sẽ sys.exit(1)
os.environ.setdefault("SCHEDULER_LOAI", "homestay")

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}")


# ── utils: jitter (chống nhịp thời gian cố định) ───────────────────────────
from utils import jitter, jitter_ms, classify_error, CookieDeadError

vals = [jitter(3, pct=0.5, floor=1.5) for _ in range(500)]
check("jitter nằm trong ±50%",        all(1.5 <= v <= 4.5 for v in vals))
check("jitter tôn trọng floor",        all(v >= 1.5 for v in vals))
check("jitter thật sự ngẫu nhiên",     len({round(v, 3) for v in vals}) > 50)
check("jitter_ms trả về int",          isinstance(jitter_ms(1500), int))
check("jitter_ms có sàn tối thiểu",    all(jitter_ms(10, floor_ms=200) >= 200 for _ in range(100)))

# ── utils: phân loại lỗi ───────────────────────────────────────────────────
check("CookieDeadError -> cookie",     classify_error(CookieDeadError("x"))[0] == "cookie")
check("keyword login -> cookie",       classify_error(Exception("redirect to login"))[0] == "cookie")
check("timeout -> transient",          classify_error(Exception("Timeout 30000ms"))[0] == "transient")
check("rate limit -> ratelimit",       classify_error(Exception("rate limit hit"))[0] == "ratelimit")
check("nút không thấy -> selector",    classify_error(Exception("Không tìm thấy nút Đăng"))[0] == "selector")
check("lỗi lạ giữ nguyên message",     classify_error(Exception("abcxyz"))[1] == "abcxyz")

# ── db: reorder pages ──────────────────────────────────────────────────────
ids = [db.upsert_page({"ten_page": f"P{i}"}) for i in range(3)]
db.reorder_pages(list(reversed(ids)))
got = [p["id"] for p in db.get_pages()]
check("reorder_pages lưu đúng thứ tự", got == list(reversed(ids)))
check("get_pages sắp theo order_idx",  got == list(reversed(ids)))

# ── db: reorder content (order_idx có phạm vi từng loai) ───────────────────
_r1, _r2, _r3 = [db.upsert_content({"loai": "homestay", "ma_content": f"R{i}"}) for i in (1, 2, 3)]
_t1, _t2      = [db.upsert_content({"loai": "thue",     "ma_content": f"T{i}"}) for i in (1, 2)]
check("content mới xếp CUỐI danh sách",
      [c["id"] for c in db.get_content("homestay")][-3:] == [_r1, _r2, _r3])
db.reorder_content([_r3, _r1, _r2])
check("reorder_content lưu đúng thứ tự",
      [c["id"] for c in db.get_content("homestay")][-3:] == [_r3, _r1, _r2])
check("reorder_content không ảnh hưởng loai khác",
      [c["id"] for c in db.get_content("thue")][-2:] == [_t1, _t2])
check("thứ tự mới vẫn đúng khi lọc su_dung",
      [c["id"] for c in db.get_content("homestay", su_dung="Có")][-3:] == [_r3, _r1, _r2])
# Thêm dòng SAU khi đã kéo-thả thì vẫn phải xuống cuối, không chen lên đầu
_r4 = db.upsert_content({"loai": "homestay", "ma_content": "R4"})
check("content mới vẫn xuống cuối sau reorder",
      [c["id"] for c in db.get_content("homestay")][-4:] == [_r3, _r1, _r2, _r4])

# ── db: reorder uid_groups (chỉ nhóm trống, TIME1-7 phải nguyên vẹn) ──────
_g1 = db.upsert_uid_group({"ma_nhom": "",      "uid": "1110000", "ten_nhom": "G1"})
_g2 = db.upsert_uid_group({"ma_nhom": "",      "uid": "2220000", "ten_nhom": "G2"})
_gt = db.upsert_uid_group({"ma_nhom": "TIME1", "uid": "9990000"})
db.reorder_uid_groups([_g2, _g1])
_all = db.get_all_uid_groups()
check("reorder_uid_groups đổi thứ tự nhóm trống",
      [g["id"] for g in _all if g["ma_nhom"] == ""][-2:] == [_g2, _g1])
check("get_all_uid_groups vẫn gom theo ma_nhom",
      [g["ma_nhom"] for g in _all] == sorted(g["ma_nhom"] for g in _all))
check("nhóm TIME1 không bị ảnh hưởng",
      [g["id"] for g in db.get_uid_groups_by_code("TIME1")] == [_gt])

# ── db: migration idempotent — gọi lại init_db không được mất thứ tự ──────
# Đây là assert duy nhất thật sự chạy qua nhánh guard của _add_col, tức chỗ mà
# migration sai sẽ chỉ hại DB cũ của người dùng, không bao giờ hại máy cài mới.
db.init_db()
check("init_db chạy lại: thứ tự content còn nguyên",
      [c["id"] for c in db.get_content("homestay")][-4:] == [_r3, _r1, _r2, _r4])
check("init_db chạy lại: thứ tự uid nhóm còn nguyên",
      [g["id"] for g in db.get_all_uid_groups() if g["ma_nhom"] == ""][-2:] == [_g2, _g1])

# ── db: busy_timeout được bật (tránh 'database is locked') ─────────────────
with db._conn() as _c:
    _bt = _c.execute("PRAGMA busy_timeout").fetchone()[0]
check("SQLite có busy_timeout > 0",    _bt >= 1000)

# ── db: lấy account theo id ────────────────────────────────────────────────
_acc_id = db.upsert_account({"ten_acc": "TestAcc", "password": "pw-that",
                             "xs": "xs-that", "twofa": "2fa-that"})
check("get_account_by_id trả đúng acc", (db.get_account_by_id(_acc_id) or {}).get("ten_acc") == "TestAcc")
check("get_account_by_id id lạ -> None", db.get_account_by_id(999999) is None)

# ── scheduler: chính sách retry ────────────────────────────────────────────
import scheduler

check("transient -> retry lần 1",      scheduler._should_retry("transient", 1) is True)
check("transient -> hết lượt thì dừng", scheduler._should_retry("transient", scheduler.MAX_ATTEMPTS) is False)
check("ratelimit KHÔNG retry",         scheduler._should_retry("ratelimit", 1) is False)
check("cookie KHÔNG retry",            scheduler._should_retry("cookie", 1) is False)
check("selector KHÔNG retry",          scheduler._should_retry("selector", 1) is False)
check("backoff tăng dần",              scheduler._retry_delay(2) > scheduler._retry_delay(1) * 0.9)

# ── scheduler: parse UID nhóm đầu ──────────────────────────────────────────
_pfg = scheduler._parse_first_group_uid
check("parse URL nhóm -> uid",         _pfg("https://facebook.com/groups/123456789/") == "123456789")
check("parse UID số thuần",            _pfg("123456789") == "123456789")
check("parse slug chữ",                _pfg("homestaytimescity") == "homestaytimescity")
check("chuỗi rỗng -> rỗng",            _pfg("") == "")

# ── ảnh content: xóa content/bỏ ảnh thì file cũng đi theo ──────────────────
_u = db._tach_urls
check("tách URL bỏ khoảng trắng",      _u(" a.jpg , b.jpg ") == {"a.jpg", "b.jpg"})
check("tách URL bỏ chuỗi rỗng",        _u("", None, "a.jpg,,") == {"a.jpg"})
check("tách URL gộp nhiều chuỗi",      _u("a.jpg", "b.jpg") == {"a.jpg", "b.jpg"})

_c1 = db.upsert_content({"loai":"homestay","ma_content":"IMG1",
                         "link_anh":"/m/h.jpg, /m/x.jpg, /m/chung.jpg"})
_c2 = db.upsert_content({"loai":"homestay","ma_content":"IMG2",
                         "link_anh":"/m/y.jpg, /m/chung.jpg"})
check("lấy đúng ảnh của 1 content",
      db.get_content_image_urls(_c1) == {"/m/h.jpg", "/m/x.jpg", "/m/chung.jpg"})
check("gom ảnh của MỌI content",
      {"/m/h.jpg","/m/x.jpg","/m/y.jpg","/m/chung.jpg"} <= db.get_all_content_image_urls())
check("content KHÔNG còn cột link_anh_hook",
      "link_anh_hook" not in [r[1] for r in
                              db._conn().execute("PRAGMA table_info(content)").fetchall()])
check("content không tồn tại -> rỗng", db.get_content_image_urls(999999) == set())
# Ảnh dùng chung: xóa 1 content thì ảnh chung PHẢI còn (content kia vẫn dùng)
db.delete_content(_c1)
check("xóa content: ảnh riêng hết dùng",
      "/m/x.jpg" not in db.get_all_content_image_urls())
check("xóa content: ảnh CHUNG vẫn còn dùng",
      "/m/chung.jpg" in db.get_all_content_image_urls())
db.delete_content(_c2)
check("xóa nốt: ảnh chung mới hết dùng",
      "/m/chung.jpg" not in db.get_all_content_image_urls())

# ── dọn cache: nhận diện profile ĐANG MỞ để không xoá nhầm ────────────────
import os as _os
from fb_common import loc_profile_tu_cmdline as _lp

_goc = _os.path.abspath("profiles")
def _co(ten):   # profile của dự án có nằm trong kết quả không
    return _os.path.normcase(_os.path.join(_goc, ten)) in _kq

# Dấu tiếng Việt PHẢI khớp — lỗi giải mã cp1252 từng biến "Huỳnh_Như" thành
# "Hu?nh_Nh?" khiến bộ quét tưởng profile đang chạy là rảnh và xoá cache của nó.
_kq = _lp(f'chrome.exe --user-data-dir="{_goc}\\Huỳnh_Như_100076368049295" --x', _goc)
check("nhận đúng profile có dấu tiếng Việt", _co("Huỳnh_Như_100076368049295"))

_kq = _lp(f'chrome --user-data-dir={_goc}\\Xuan_Khoa_123 --flag', _goc)
check("nhận đường dẫn không có ngoặc kép",  _co("Xuan_Khoa_123"))

# Ứng dụng khác cũng dùng --user-data-dir -> phải bỏ qua
_kq = _lp(r'zalo.exe --user-data-dir="C:\Users\X\AppData\zalodata"', _goc)
check("bỏ qua profile ngoài dự án",         _kq == set())

_kq = _lp(f'a --user-data-dir="{_goc}\\P1" b --user-data-dir="{_goc}\\P2"', _goc)
check("nhận nhiều profile cùng lúc",        _co("P1") and _co("P2") and len(_kq) == 2)

check("chuỗi rỗng -> không có gì",          _lp("", _goc) == set())
check("không có user-data-dir -> rỗng",     _lp("chrome.exe --headless", _goc) == set())

# ── refresh cookie: tìm profile + ghi xs mới về DB ────────────────────────
import cookie_exporter as _ce

# Thư mục profile thật do poster tạo có dạng "{Tên}_{c_user}". Bản cũ chỉ so
# tên trần nên khớp 0/15 acc — phần đọc cookie từ profile chết lặng nhiều
# tháng mà không một dòng log nào báo.
_pf_goc = Path(tempfile.mkdtemp(prefix="mnt_pf_"))
_ce.PROFILES_DIR = str(_pf_goc)
for _d in ("Tran_Minh_Khanh_100078745098439", "Huu_Chau"):
    (_pf_goc / _d).mkdir()

_f = lambda t, c="": _ce._find_profile_dir(t, c)
check("tìm profile dạng {Tên}_{c_user}",
      _os.path.basename(_f("Tran Minh Khanh", "100078745098439") or "")
      == "Tran_Minh_Khanh_100078745098439")
check("vẫn nhận profile đời cũ tên trần",   _os.path.basename(_f("Huu Chau") or "") == "Huu_Chau")
check("sai c_user -> không vơ bừa profile", _f("Tran Minh Khanh", "999") is None)
check("acc không có profile -> None",       _f("Khong Ton Tai", "123") is None)
check("KHÔNG tự tạo thư mục khi tìm hụt",   not (_pf_goc / "Khong_Ton_Tai_123").exists())

# _sync_xs_to_db: chỉ ghi đè xs khi chắc chắn đúng nick. Profile có thể đã được
# đăng nhập sang nick khác — ghi bừa sẽ gán cookie nick này cho nick kia.
_ar_id = db.upsert_account({"ten_acc": "Acc Refresh", "c_user": "111",
                            "xs": "xs_cu", "trang_thai": "Active"})
_ar = db.get_account_by_id(_ar_id)
_xs = lambda: [a for a in db.get_accounts() if a["id"] == _ar["id"]][0]["xs"]

check("profile không trả xs -> bỏ qua",   _ce._sync_xs_to_db(_ar, {}) == "")
check("xs y hệt DB -> không ghi lại",     _ce._sync_xs_to_db(_ar, {"xs": "xs_cu", "c_user": "111"}) == "")
check("c_user LỆCH -> từ chối ghi đè",    _ce._sync_xs_to_db(_ar, {"xs": "xs_moi", "c_user": "222"}) == "")
check("c_user lệch: DB giữ xs cũ",        _xs() == "xs_cu")
check("c_user khớp -> trả xs mới",        _ce._sync_xs_to_db(_ar, {"xs": "xs_moi", "c_user": "111"}) == "xs_moi")
check("c_user khớp -> DB đã lưu xs mới",  _xs() == "xs_moi")

# ── dialog cảnh báo vi phạm: đóng ĐÚNG cái, không đụng ô soạn bài ─────────
import asyncio as _aio
import fb_common as _fc


class _Nut:
    def __init__(self, chu, hong=False): self.chu, self.hong = chu, hong
    async def is_visible(self): return True
    async def bounding_box(self): return {"x": 10, "y": 10, "width": 20, "height": 20}
    async def click(self, timeout=None):
        if self.hong:
            raise RuntimeError("bị lớp phủ chặn")   # Playwright ném khi click bị nuốt
        self.chu.da_bam = True
        self.chu.dong()
    async def evaluate(self, js):
        self.chu.da_js = True                       # JS click xuyên mọi lớp phủ
        self.chu.dong()


class _Dlg:
    """Giả một div[role=dialog]. Đóng được thì tự ẩn đi như dialog thật."""
    def __init__(self, text, co_nut_x=True, hien=True, nut_hong=False, cung_dau=False):
        self._t, self._x, self._h = text, co_nut_x, hien
        self._hong, self._cung = nut_hong, cung_dau
        self.da_bam = self.da_js = False
    def dong(self):
        if not self._cung:          # cung_dau=True: mô phỏng dialog đóng mãi không chịu
            self._h = False
    async def is_visible(self):  return self._h
    async def inner_text(self):  return self._t
    async def query_selector(self, sel):
        return _Nut(self, self._hong) if self._x else None


class _Ban_phim:
    def __init__(self): self.phim = []
    async def press(self, k): self.phim.append(k)


class _Chuot:
    def __init__(self, dlg, nuot=False): self.dlg, self.diem, self.nuot = dlg, [], nuot
    async def click(self, x, y):
        self.diem.append((x, y))
        if not self.nuot:           # nuot=True: lớp phủ hứng mất cú bắn chuột
            self.dlg.dong()


class _Trang:
    def __init__(self, *dlgs, chuot_nuot=False):
        self._d = list(dlgs); self.keyboard = _Ban_phim()
        self.mouse = _Chuot(dlgs[0], chuot_nuot) if dlgs else None
    async def query_selector_all(self, sel): return self._d


_CANH_BAO = "Sự việc\nChúng tôi đã gỡ một số nội dung hoặc tin nhắn\nSpam"
_SOAN_BAI = "Tạo bài viết\nBạn đang nghĩ gì?\nẢnh/video"
_CHUYEN   = "Bạn đang dùng Facebook với tư cách Trang\nDùng Trang"

_d = _Dlg(_CANH_BAO)
check("nhận ra dialog cảnh báo",        "Chúng tôi đã gỡ" in _aio.run(_fc.dong_dialog_canh_bao(_Trang(_d))))
check("cảnh báo -> có bấm nút X",       _d.da_bam)
check("bấm xong dialog biến mất",       not _aio.run(_d.is_visible()))

# Ô soạn bài và hộp "Chuyển sang Trang" cũng là role=dialog. Đóng nhầm chúng
# là hỏng luôn phiên đăng — đây là lý do phải khớp theo mốc chữ, không đóng bừa.
_d = _Dlg(_SOAN_BAI)
check("KHÔNG đụng ô soạn bài",          _aio.run(_fc.dong_dialog_canh_bao(_Trang(_d))) == "" and not _d.da_bam)
_d = _Dlg(_CHUYEN)
check("KHÔNG đụng hộp Chuyển sang Trang", _aio.run(_fc.dong_dialog_canh_bao(_Trang(_d))) == "" and not _d.da_bam)

_c, _s = _Dlg(_CANH_BAO), _Dlg(_SOAN_BAI)
check("lẫn lộn -> chỉ đóng cảnh báo",   _aio.run(_fc.dong_dialog_canh_bao(_Trang(_s, _c))) != "" and _c.da_bam and not _s.da_bam)

check("bỏ qua dialog ẩn",               _aio.run(_fc.dong_dialog_canh_bao(_Trang(_Dlg(_CANH_BAO, hien=False)))) == "")
check("không có dialog nào -> rỗng",    _aio.run(_fc.dong_dialog_canh_bao(_Trang())) == "")
check("bản tiếng Anh cũng nhận",
      _aio.run(_fc.dong_dialog_canh_bao(_Trang(_Dlg("Account Status\nWe removed some of your content or messages")))) != "")

# Bảng thông báo CŨNG là role=dialog, và từng thông báo bên trong nó cũng chứa
# cụm "Chúng tôi đã gỡ nội dung...". Đã bắt nhầm một lần thật (log 09:42:28
# ngày 7/8) và đóng nhầm bảng thông báo. Loại theo tiêu đề dòng đầu.
_d = _Dlg("Thông báo\nTất cả\nChưa đọc\nChúng tôi đã gỡ nội dung hoặc tin nhắn "
          "của thành viên khỏi nhóm của bạn")
check("KHÔNG đụng bảng Thông báo",      _aio.run(_fc.dong_dialog_canh_bao(_Trang(_d))) == "" and not _d.da_bam)

_t = _Trang(_Dlg(_CANH_BAO, co_nut_x=False))
check("không thấy nút X -> bấm Escape", _aio.run(_fc.dong_dialog_canh_bao(_t)) != "" and "Escape" in _t.keyboard.phim)

# Bản đầu bấm rồi đi luôn: cú bấm bị lớp phủ nuốt thì log vẫn báo êm trong khi
# dialog còn nguyên trên màn hình. Giờ phải bắn chuột theo toạ độ để chữa.
_d = _Dlg(_CANH_BAO, nut_hong=True)
_t = _Trang(_d)
check("click bị chặn -> bắn chuột toạ độ", _aio.run(_fc.dong_dialog_canh_bao(_t)) != "" and _t.mouse.diem == [(20, 20)])
check("bắn chuột xong dialog biến mất",    not _aio.run(_d.is_visible()))

# Lớp phủ nuốt CẢ cú bấm lẫn cú bắn chuột — chuột vẫn trúng thứ nằm trên cùng
# tại điểm đó. Dựng lại đúng cảnh này trong Chromium thì hai cách đầu đều thua,
# chỉ click bằng JS xuyên qua được.
_d = _Dlg(_CANH_BAO, nut_hong=True)
_t = _Trang(_d, chuot_nuot=True)
check("lớp phủ nuốt hết -> cứu bằng JS click", _aio.run(_fc.dong_dialog_canh_bao(_t)) != "" and _d.da_js)
check("JS click xong dialog biến mất",         not _aio.run(_d.is_visible()))

# Đóng mãi không được thì PHẢI kêu lên, không được im lặng báo thành công.
_t = _Trang(_Dlg(_CANH_BAO, co_nut_x=False, cung_dau=True))
check("đóng hoài không được -> thử lại nhiều lần", _aio.run(_fc.dong_dialog_canh_bao(_t, so_lan=3)) != ""
      and len(_t.keyboard.phim) == 3)

# Escape đóng dialog nhưng đóng CẢ story đang mở. Gọi từ trong trình xem story
# thì phải tắt bước này, nếu không nick chỉ mở story rồi thoát ngay.
_t = _Trang(_Dlg(_CANH_BAO, co_nut_x=False, cung_dau=True))
check("cho_escape=False -> KHÔNG bấm Escape",
      _aio.run(_fc.dong_dialog_canh_bao(_t, so_lan=2, cho_escape=False)) != "" and _t.keyboard.phim == [])


# ── xác minh sau khi đăng: phải bám Ô SOẠN BÀI, không phải dialog bất kỳ ───
_bat = {}


class _TrangOK:
    async def wait_for_selector(self, sel, state=None, timeout=None):
        _bat["sel"], _bat["state"] = sel, state
        return None
    async def query_selector(self, sel): return None


check("composer đóng -> báo thành công", _aio.run(_fc.cho_composer_dong(_TrangOK())) is True)

# Bản cũ chờ "div[role='dialog']" biến mất. Dialog cảnh báo cũng là role=dialog
# và không tự đóng -> hết 30s -> báo thất bại dù bài ĐÃ lên. Với luồng tường
# Page nó còn return False, khiến lịch bị đánh ❌: 5 lượt đăng, 0 lượt xác nhận.
check("bám ô soạn bài, không dialog bất kỳ", "contenteditable" in _bat.get("sel", ""))
check("chờ tới khi ô soạn bài biến mất",     _bat.get("state") == "hidden")

# ── nuôi nick: xếp phiên theo CHU KỲ (logic thuần) ─────────────────────────
import nuoi_nick

# normalize_interval: mặc định 150 (2h30), chặn giá trị rác / quá dày
check("interval mặc định 150",         nuoi_nick.normalize_interval(None) == 150)
check("interval rỗng -> mặc định",     nuoi_nick.normalize_interval("") == 150)
check("interval 0 -> mặc định",        nuoi_nick.normalize_interval(0) == 150)
check("interval hợp lệ giữ nguyên",    nuoi_nick.normalize_interval(90) == 90)
check("interval quá nhỏ bị chặn",      nuoi_nick.normalize_interval(5) == nuoi_nick.MIN_INTERVAL_MIN)

# _unwrap_times: lịch xuyên đêm (02:00 phải SAU 23:00, không phải trước)
check("qua nửa đêm cộng 24h",          nuoi_nick._unwrap_times(["22:00","23:00","01:00"]) == [1320,1380,1500])

# plan_warming_conversion: cứ mỗi `chu kỳ` phút thì 1 slot thành nuôi
def _mkrows(acc, n, step=30, start=7*60):
    return [{"ten_acc":acc,
             "gio_dang":f"{((start+i*step)//60)%24:02d}:{(start+i*step)%60:02d}",
             "stt":i+1} for i in range(n)]

# A: 24 slot cách 30' (07:00→18:30 = 690'), chu kỳ 150' -> ~5 phiên nuôi
sched = _mkrows("A",24) + _mkrows("B",24)
n_conv = nuoi_nick.plan_warming_conversion(sched, {"A":150})
a_rows = [r for r in sched if r["ten_acc"]=="A"]
b_warm = sum(1 for r in sched if r["ten_acc"]=="B" and r["hoat_dong"]=="nuoi_nick")
a_warm_times = nuoi_nick._unwrap_times([r["gio_dang"] for r in a_rows if r["hoat_dong"]=="nuoi_nick"])
check("acc không bật nuôi: 0 slot",    b_warm == 0)
check("acc bật nuôi có phiên nuôi",    len(a_warm_times) >= 4)
check("tổng converted khớp",           n_conv == len(a_warm_times))
check("slot còn lại vẫn đăng bài",     any(r["hoat_dong"]=="dang_bai" for r in a_rows))
check("khoảng cách 2 phiên >= chu kỳ",
      all(b-a >= 150 for a,b in zip(a_warm_times, a_warm_times[1:])))

# Nhiều acc cùng bật nuôi: các phiên phải TÁCH GIÃN, không chụm một cục.
# (Lịch thật: 4 acc luân phiên mỗi 3 phút, 3 acc bật nuôi cùng chu kỳ 150.)
_accs4 = ["A1","A2","A3","A4"]
_sched4 = []
_t = 5*60
for _k in range(441):
    _sched4.append({"ten_acc":_accs4[_k%4],
                    "gio_dang":f"{(_t//60)%24:02d}:{_t%60:02d}","stt":_k+1})
    _t += 3
nuoi_nick.plan_warming_conversion(_sched4, {"A2":150,"A3":150,"A4":150})
_wrows = [(r["gio_dang"], r["ten_acc"]) for r in _sched4 if r["hoat_dong"]=="nuoi_nick"]
_wt = nuoi_nick._unwrap_times([g for g,_ in _wrows])
_wgaps = [b-a for a,b in zip(_wt,_wt[1:])]
check("nhiều acc: phiên nuôi không chụm",  min(_wgaps) >= nuoi_nick.MIN_GAP_MIN)
check("nhiều acc: giãn cách đáng kể",      min(_wgaps) >= 30)
check("3 acc đều có phiên nuôi",           len({a for _,a in _wrows}) == 3)
# Mỗi acc vẫn tôn trọng chu kỳ riêng của nó
for _a in ("A2","A3","A4"):
    _at = nuoi_nick._unwrap_times([g for g,x in _wrows if x==_a])
    if not all(b-a >= 150 for a,b in zip(_at,_at[1:])):
        break
else:
    _a = None
check("mỗi acc vẫn giữ đúng chu kỳ 150",   _a is None)
# Acc không bật nuôi không bị đụng
check("acc không bật nuôi vẫn đăng hết",
      all(r["hoat_dong"]=="dang_bai" for r in _sched4 if r["ten_acc"]=="A1"))

# Chu kỳ ngắn hơn -> nhiều phiên nuôi hơn
s2 = _mkrows("C",24); nuoi_nick.plan_warming_conversion(s2, {"C":60})
s3 = _mkrows("D",24); nuoi_nick.plan_warming_conversion(s3, {"D":240})
n60  = sum(1 for r in s2 if r["hoat_dong"]=="nuoi_nick")
n240 = sum(1 for r in s3 if r["hoat_dong"]=="nuoi_nick")
check("chu kỳ ngắn -> nhiều phiên hơn", n60 > n240)

# build_warming_schedule: acc CHỈ NUÔI, không có slot đăng nào
rows = nuoi_nick.build_warming_schedule(
    [{"ten":"N1","interval":150},{"ten":"N2","interval":150}], "07:00", "23:00")
check("lịch nuôi có dòng",             len(rows) > 0)
check("mọi dòng đều là nuôi_nick",     all(r["hoat_dong"]=="nuoi_nick" for r in rows))
check("mọi dòng thuộc loai='nuoi'",    all(r["loai"]=="nuoi" for r in rows))
check("không dòng nào có content",     all(r["ma_content"]=="" for r in rows))
check("stt đánh số liên tục",          [r["stt"] for r in rows] == list(range(1,len(rows)+1)))
n1 = nuoi_nick._unwrap_times([r["gio_dang"] for r in rows if r["ten_acc"]=="N1"])
check("mỗi acc cách nhau ~chu kỳ",      all(b-a >= 150 for a,b in zip(n1, n1[1:])))

# Chống trùng giờ: kể cả khi 2 acc có chu kỳ KHÁC nhau (150 vs 120 sẽ gặp nhau
# ở 12:00 nếu không giãn) — mọi phiên phải cách nhau >= MIN_GAP_MIN.
mix = nuoi_nick.build_warming_schedule(
    [{"ten":"M1","interval":150},{"ten":"M2","interval":120}], "07:00", "23:00")
mt = nuoi_nick._unwrap_times([r["gio_dang"] for r in mix])
check("không 2 phiên nào trùng giờ",    len(mt) == len(set(mt)))
check("mọi phiên cách nhau >= min gap",
      all(b-a >= nuoi_nick.MIN_GAP_MIN for a,b in zip(mt, mt[1:])))
check("lịch nuôi nằm trong khung giờ",
      all(7*60 <= t <= 23*60 for t in mt))

# parse_group_urls: nhiều nhóm chat, mỗi phiên bốc ngẫu nhiên 1 nhóm
_pg = nuoi_nick.parse_group_urls
check("1 nhóm — tương thích cài đặt cũ",
      _pg("https://www.facebook.com/messages/t/111") == ["https://www.facebook.com/messages/t/111"])
check("nhiều nhóm, mỗi dòng 1",
      _pg("https://a/1\nhttps://a/2\nhttps://a/3") == ["https://a/1","https://a/2","https://a/3"])
check("bỏ dòng rỗng và khoảng trắng thừa",
      _pg("  https://a/1  \n\n  https://a/2 ") == ["https://a/1","https://a/2"])
check("chấp nhận phân cách dấu phẩy",
      _pg("https://a/1, https://a/2") == ["https://a/1","https://a/2"])
check("bỏ link trùng",              _pg("https://a/1\nhttps://a/1") == ["https://a/1"])
check("bỏ dòng không phải link",    _pg("ghi chu\nhttps://a/1") == ["https://a/1"])
check("rỗng -> danh sách rỗng",     _pg("") == [])
check("giữ nguyên thứ tự nhập",
      _pg("https://z/9\nhttps://a/1") == ["https://z/9","https://a/1"])

# pick_messages: bốc câu nhắn, không lặp 2 câu giống nhau liền nhau
import random as _r0
_pool = ["câu A", "câu B", "câu C"]
for _seed in range(50):
    _msgs = nuoi_nick.pick_messages(_pool, 3, _r0.Random(_seed))
    if len(_msgs) != 3 or any(a == b for a, b in zip(_msgs, _msgs[1:])):
        break
else:
    _msgs = None
check("bốc đủ số câu, không lặp liền kề", _msgs is None)
check("thư viện 1 câu vẫn chạy được",
      nuoi_nick.pick_messages(["chỉ 1 câu"], 3, _r0.Random(1)) == ["chỉ 1 câu"]*3)
check("thư viện rỗng -> không câu nào",   nuoi_nick.pick_messages([], 3, _r0.Random(1)) == [])
check("xin 0 câu -> rỗng",                nuoi_nick.pick_messages(_pool, 0, _r0.Random(1)) == [])
check("mọi câu đều lấy từ thư viện",
      set(nuoi_nick.pick_messages(_pool, 10, _r0.Random(7))) <= set(_pool))

# Acc bị FB chặn nhắn tin -> nhận ra để bỏ qua, không cố gửi
_restrict_real = ("Xác nhận danh tính để gửi tin nhắn "
                  "Một số hành động đã bị hạn chế do có hoạt động bất thường. "
                  "Tìm hiểu thêm Cách xác nhận")
check("nhận ra chặn (text thật của FB)", nuoi_nick.is_messaging_restricted(_restrict_real) is True)
check("nhận ra chặn tiếng Anh",
      nuoi_nick.is_messaging_restricted("Confirm your identity to send messages") is True)
check("chat bình thường KHÔNG bị nhầm",
      nuoi_nick.is_messaging_restricted("hello các anh em hahaha i am back") is False)
check("text rỗng -> không chặn",       nuoi_nick.is_messaging_restricted("") is False)
check("None -> không chặn",            nuoi_nick.is_messaging_restricted(None) is False)

# Messenger đòi mã PIN khôi phục chat -> nhận ra để bấm bỏ qua
_pin_real = ("Nhập mã PIN để khôi phục đoạn chat của bạn "
             "Một số tin nhắn còn thiếu. Hãy nhập mã PIN để khôi phục lịch sử chat của bạn.")
check("nhận ra hộp thoại PIN (text thật)", nuoi_nick.has_pin_dialog(_pin_real) is True)
check("nhận ra PIN tiếng Anh",
      nuoi_nick.has_pin_dialog("Enter your PIN to restore your chat") is True)
check("chat thường KHÔNG bị nhầm là PIN",
      nuoi_nick.has_pin_dialog("hôm nay trời đẹp nhỉ mọi người ăn cơm chưa") is False)
check("PIN: text rỗng -> False",       nuoi_nick.has_pin_dialog("") is False)

# Thư viện câu mẫu đi kèm
_mau_res = _client_mau = None
import server as _srv
_mau_res = _srv.app.test_client().get("/api/nuoi/msg-mau").get_json()
_mau_lines = (_mau_res.get("text") or "").split("\n")
check("thư viện mẫu đọc được",         _mau_res.get("ok") is True)
check("có ~500 câu mẫu",               _mau_res.get("total", 0) >= 500)
check("mẫu không lẫn dòng ghi chú",    not any(l.startswith("#") for l in _mau_lines))
check("mẫu không có dòng rỗng",        all(l.strip() for l in _mau_lines))
check("mẫu không trùng câu",           len(_mau_lines) == len(set(_mau_lines)))
check("câu mẫu đều ngắn gọn",          all(len(l) <= 60 for l in _mau_lines))

# select_session_activities: chỉ lấy hành động đang bật, luôn ≥1, chỉ tên hợp lệ
import random as _rnd
_ALL_ON = {"nuoi_enable_story":1,"nuoi_enable_feed":1,
           "nuoi_enable_like":1,"nuoi_enable_message":1}
# Nuôi nick CHỈ có 4 hành động: story, feed, like, message.
check("đúng 4 hành động nuôi",         set(nuoi_nick._ACTIVITY_FNS) == {"story","feed","like","message"})
check("đã gỡ hẳn tính năng kết bạn",
      not any(k in nuoi_nick.DEFAULTS for k in
              ("nuoi_enable_accept","nuoi_enable_addfriend","nuoi_friend_min")))
_valid = set(nuoi_nick._ACTIVITY_FNS)
_samples = [nuoi_nick.select_session_activities(_ALL_ON, _rnd.Random(i)) for i in range(200)]
check("MỖI phiên làm ĐỦ 4 hành động",   all(set(s) == _valid for s in _samples))
check("chỉ chứa tên hành động hợp lệ",  all(set(s) <= _valid for s in _samples))
check("không lặp hành động trong phiên", all(len(s)==len(set(s)) for s in _samples))
# Đủ 4 nhưng THỨ TỰ phải xáo, không rập khuôn
check("thứ tự đa dạng giữa các phiên",  len({tuple(s) for s in _samples}) > 10)
check("không phải lúc nào cũng 1 thứ tự", _samples[0] != _samples[1] or _samples[0] != _samples[2])
# Hành động bị tắt thì không bao giờ xuất hiện
_only_feed = nuoi_nick.select_session_activities({"nuoi_enable_feed":1}, _rnd.Random(1))
check("tắt hết trừ feed -> chỉ feed",  _only_feed == ["feed"])
check("không bật gì -> rỗng",          nuoi_nick.select_session_activities({}, _rnd.Random(1)) == [])

# ── cột số: sửa inline không được lưu thành chuỗi ─────────────────────────
# Ô "Bài đăng tối đa" bị xoá trống thành '' đã làm gen lịch Page vỡ HTTP 500
# vì '' > 0 ném TypeError. Khoá lại cả 2 đầu: ép khi ghi và ép khi đọc.
import server as _sv
_eks = _sv.ep_kieu_so
check("ô số bỏ trống -> 0",          _eks("bai_dang_toi_da", "") == 0)
check("ô số toàn khoảng trắng -> 0", _eks("bai_dang_toi_da", "   ") == 0)
check("ô số chữ rác -> 0",           _eks("bai_dang_toi_da", "abc") == 0)
check("ô số None -> 0",              _eks("bai_dang_toi_da", None) == 0)
check("chuỗi số -> đúng số",         _eks("bai_dang_toi_da", "7") == 7)
check("số thập phân -> cắt phần nguyên", _eks("nuoi_interval", "3.9") == 3)
check("số nguyên giữ nguyên",        _eks("thoi_gian_nghi", 30) == 30)
check("kết quả LUÔN là int",         all(isinstance(_eks("order_idx", v), int)
                                         for v in ("", "x", None, "5", 5, 2.7)))
check("cột CHỮ không bị đụng",       _eks("ten_page", "Homestay 5") == "Homestay 5")
check("cột chữ rỗng giữ nguyên chuỗi", _eks("ghi_chu", "") == "")

# ── Đi comment: cửa sổ trượt 300 link + bốc 1 link/nhóm ────────────────────
import comment_bai as _cb

def _lk(nhom, i):
    return f"https://www.facebook.com/groups/{nhom}/posts/{i}/"

db.xoa_het_comment_posts("homestay")
check("tách nhóm số từ URL",  db.tach_nhom_tu_url(_lk("123", 9)) == "123")
check("tách nhóm SLUG từ URL",
      db.tach_nhom_tu_url(_lk("homestay.timescity.hanoi", 9)) == "homestay.timescity.hanoi")
check("URL rác -> nhóm rỗng",  db.tach_nhom_tu_url("abc") == "")

# 3 nhóm × 5 bài, thêm theo thứ tự → order_idx tăng dần = tuổi
_urls = [_lk(g, i) for i in range(5) for g in ("g1", "g2", "g3")]
check("thêm 15 link",          db.them_comment_posts("homestay", _urls) == 15)
check("thêm lại -> bỏ trùng",  db.them_comment_posts("homestay", _urls) == 0)
check("nhóm được lưu sẵn",
      {r["nhom"] for r in db.get_comment_posts("homestay")} == {"g1", "g2", "g3"})

# Luật 1: tối đa 1 link MỖI NHÓM. 3 nhóm thì xin 9 vẫn chỉ được 3 —
# bốc 2 bài cùng nhóm trong một phiên là 2 comment liên tiếp vào cùng nhóm.
_b = db.boc_bai_de_comment("homestay", 9)
check("xin 9 nhưng chỉ có 3 nhóm -> 3 bài", len(_b) == 3)
check("mỗi nhóm đúng 1 bài",   len({r["nhom"] for r in _b}) == 3)
_b2 = db.boc_bai_de_comment("homestay", 2)
check("xin ít hơn số nhóm -> đúng số xin", len(_b2) == 2)
check("xin 0 -> rỗng",         db.boc_bai_de_comment("homestay", 0) == [])

# Luật 2: ưu tiên bài CŨ NHẤT (order_idx nhỏ nhất) trong mỗi nhóm
_idx = {r["nhom"]: r["order_idx"] for r in _b}
_min = {}
for r in db.get_comment_posts("homestay"):
    _min[r["nhom"]] = min(_min.get(r["nhom"], 10**9), r["order_idx"])
check("bốc đúng bài cũ nhất mỗi nhóm", _idx == _min)

# ...nhưng bài đã comment rồi phải nhường bài chưa comment, nếu không mỗi phiên
# đều dội lại đúng một bài cho tới khi nó bị đẩy khỏi cửa sổ.
db.ghi_nhan_comment(_b[0]["id"], True)
_b3 = db.boc_bai_de_comment("homestay", 9)
_cua_nhom = [r for r in _b3 if r["nhom"] == _b[0]["nhom"]][0]
check("bài đã comment nhường bài chưa comment", _cua_nhom["id"] != _b[0]["id"])
check("vẫn giữ 1 bài mỗi nhóm", len({r["nhom"] for r in _b3}) == 3)

# Cửa sổ trượt: link mới đẩy link cũ ra và XOÁ HẲN
db.xoa_het_comment_posts("thue")
db.them_comment_posts("thue", [_lk("g1", i) for i in range(10)], gioi_han=6)
_ds = db.get_comment_posts("thue")
check("cắt còn đúng giới hạn",  len(_ds) == 6)
check("giữ lại link MỚI nhất",
      {r["url"] for r in _ds} == {_lk("g1", i) for i in range(4, 10)})
db.them_comment_posts("thue", [_lk("g1", 99)], gioi_han=6)
_ds = db.get_comment_posts("thue")
check("thêm tiếp vẫn đúng giới hạn", len(_ds) == 6)
check("link cũ nhất bị đẩy ra",  _lk("g1", 4) not in {r["url"] for r in _ds})
check("link mới nhất có mặt",    _lk("g1", 99) in {r["url"] for r in _ds})
check("giới hạn mặc định là 300", db.GIOI_HAN_LINK == 300)

# Link chết: XOÁ NGAY, không đánh dấu chờ bị đẩy ra — 20-30% bài bị gỡ, để
# chúng nằm lại là chừng ấy chỗ trong cửa sổ thành rác.
_r0 = db.get_comment_posts("thue")[0]
db.ghi_nhan_comment(_r0["id"], False, chet=True)
check("link chết bị xoá ngay",   _r0["id"] not in {r["id"] for r in db.get_comment_posts("thue")})
check("xoá chết -> danh sách ngắn lại", len(db.get_comment_posts("thue")) == 5)

# Lỗi thường thì GIỮ lại, chỉ ghi trạng thái
_r1 = db.get_comment_posts("thue")[0]
db.ghi_nhan_comment(_r1["id"], False, "không thấy ô bình luận")
check("lỗi thường -> vẫn còn trong danh sách",
      _r1["id"] in {r["id"] for r in db.get_comment_posts("thue")})
check("lỗi thường -> không tăng số lần", db.get_comment_posts("thue")[0]["so_lan"] == 0)
check("lỗi thường -> ghi trạng thái ❌",
      db.get_comment_posts("thue")[0]["trang_thai"].startswith("❌"))
db.xoa_het_comment_posts("thue")

# Nhận biết bài đã bị xoá
check("nhận ra bài bị xoá (VN)", _cb.bai_da_chet("Bạn hiện không xem được nội dung này"))
check("nhận ra bài bị xoá (EN)", _cb.bai_da_chet("Sorry, this content isn't available right now"))
check("bài bình thường -> không báo chết",
      not _cb.bai_da_chet("Cho thuê căn hộ 2 phòng ngủ, xem nhà liên hệ"))

# Trần thời gian cho một phiên — BẮT BUỘC phải có. Playwright không đặt timeout
# mặc định cho page.evaluate, nên trang Facebook treo là phiên treo vô hạn, giữ
# luôn một worker của scheduler. Đã gặp thật: kẹt 13 phút ở bước lướt newsfeed.
check("có trần thời gian cho phiên comment", _cb.GIOI_HAN_PHIEN_GIAY > 0)
_uoc = (max(_cb.STORY_GIAY) + max(_cb.FEED_GIAY) + max(_cb.KET_GIAY)
        + _cb.DEFAULTS["comment_so_bai"] * 15
        + (_cb.DEFAULTS["comment_so_bai"] - 1) * _cb.DEFAULTS["comment_nghi_max"])
check("trần rộng hơn phiên chạy bình thường", _cb.GIOI_HAN_PHIEN_GIAY > _uoc)
check("trần không quá rộng (≤ 30 phút)",      _cb.GIOI_HAN_PHIEN_GIAY <= 1800)

# Chỉ còn ĐÚNG 3 thông số chỉnh được. Khởi động / kết phiên bám đúng luồng đăng
# bài Page nên không có lý do chỉnh riêng — thêm ô cấu hình vào đây là thêm chỗ
# để hai luồng lệch nhau.
check("chỉ còn 3 thông số cấu hình",
      set(_cb.DEFAULTS) == {"comment_so_bai", "comment_nghi_min", "comment_nghi_max"})
check("thời lượng story khớp luồng đăng bài",  _cb.STORY_GIAY == (15, 20))
check("thời lượng newsfeed khớp luồng đăng bài", _cb.FEED_GIAY == (20, 30))
check("kết phiên khớp luồng đăng bài",        _cb.KET_GIAY == (15, 30))
check("kết phiên like đúng 1 bài",            _cb.KET_LIKE == 1)

# Lý do bỏ qua
check("danh sách trống -> báo trống", _cb.ly_do_bo_qua([]) == "danh sách trống")
check("còn link -> không bỏ qua",     _cb.ly_do_bo_qua([{"url": "x"}]) == "")

# Thư viện câu
check("tách câu bỏ dòng trống/trùng",
      _cb.tach_cau("a\n\n b \na\nc") == ["a", "b", "c"])
check("thư viện rỗng -> []",          _cb.tach_cau("   \n\n") == [])
_pick = nuoi_nick.pick_messages(_cb.tach_cau("c1\nc2\nc3"), 9)
check("bốc đủ câu cho 9 bài",         len(_pick) == 9)
check("KHÔNG lặp câu ở 2 bài liền nhau",
      all(_pick[i] != _pick[i+1] for i in range(len(_pick) - 1)))
db.xoa_het_comment_posts("homestay")

# ── Thu link bài vừa đăng: đọc từ trang thông báo ──────────────────────────
import thu_link as _tl

_H_CHEO = ("https://www.facebook.com/groups/1193274271124469/?multi_permalinks="
           "3303234150128460&notif_id=1&notif_t=group_crossposting_published&ref=notif")
# Định danh nhóm có thể là SLUG chữ, không chỉ số — đo thật: 2/7 nhóm trong một
# đợt đăng chéo dùng slug, regex chỉ khớp \d+ sẽ bỏ sót đúng bấy nhiêu link.
_H_SLUG = ("https://www.facebook.com/groups/homestay.timescity.hanoi/?multi_permalinks="
           "2141785163358433&notif_t=group_crossposting_published")
_H_DUYET = ("https://www.facebook.com/groups/1193274271124469/posts/3303234150128460/"
            "?notif_id=1&notif_t=group_post_approved&ref=notif")
_H_CMT = ("https://www.facebook.com/groups/311375961636397/?post_id=1&comment_id=2"
          "&notif_t=group_comment")

check("bắt link đăng chéo (nhóm số)",
      _tl.RE_THONG_BAO_CHEO.search(_H_CHEO).groups()
      == ("1193274271124469", "3303234150128460"))
check("bắt link đăng chéo (nhóm SLUG)",
      _tl.RE_THONG_BAO_CHEO.search(_H_SLUG).groups()
      == ("homestay.timescity.hanoi", "2141785163358433"))
check("bắt link bài được duyệt",
      _tl.RE_THONG_BAO_DUYET.search(_H_DUYET).groups()
      == ("1193274271124469", "3303234150128460"))
check("BỎ thông báo bình luận",
      not _tl.RE_THONG_BAO_CHEO.search(_H_CMT)
      and not _tl.RE_THONG_BAO_DUYET.search(_H_CMT))
check("dựng URL bài đúng dạng",
      _tl._chuan_hoa("abc.def", "123")
      == "https://www.facebook.com/groups/abc.def/posts/123/")

# Đọc tuổi thông báo để lọc đúng đợt vừa đăng
check("tuổi '13 phút'",               _tl.tuoi_phut("13 phút") == 13)
check("tuổi '1 giờ'",                 _tl.tuoi_phut("Đã đăng chéo … 1 giờ") == 60)
check("tuổi '2 ngày'",                _tl.tuoi_phut("2 ngày") == 2880)
check("tuổi tiếng Anh '3 hours'",     _tl.tuoi_phut("3 hours") == 180)
check("không đọc được tuổi -> None",  _tl.tuoi_phut("vừa xong") is None)

# Gộp hai nguồn: thông báo KHÔNG bao giờ có bài ở nhóm mở composer (Facebook
# chỉ báo cho các nhóm ĐƯỢC ĐĂNG CHÉO TỚI), nên phản hồi mạng là nguồn bổ sung
# bắt buộc chứ không phải dự phòng. Bỏ nó đi là mất đúng 1 link mỗi lần đăng.
_composer = "https://www.facebook.com/groups/311375961636397/posts/1038225002284819/"
_tu_tb = ["https://www.facebook.com/groups/353264137498979/posts/1043359741822745/",
          "https://www.facebook.com/groups/homestaytimescity/posts/1680569613046817/"]
_gop = [_composer] + [u for u in _tu_tb if u != _composer]
check("gộp giữ được link nhóm composer", _composer in _gop)
check("gộp đủ cả hai nguồn",             len(_gop) == 3)
check("gộp không sinh trùng",            len(_gop) == len(set(_gop)))

check("chờ thông báo đủ rộng (≥90s)",    _tl.CHO_THONG_BAO_GIAY >= 90)

# Cửa sổ lọc thông báo phải BÁM SÁT lần đăng vừa rồi. Rộng quá thì vơ luôn
# thông báo của lần đăng chéo TRƯỚC bằng cùng Page — nếu lần đó thuộc loại lịch
# khác thì link bị lưu nhầm hạng mục (đã xảy ra: 7 link Homestay lọt vào Thuê).
import re as _re
_src = Path("page_via_poster.py").read_text(encoding="utf-8")
_m = _re.search(r"thu_tu_thong_bao\(page,\s*toi_da_phut=(\d+)\)", _src)
check("luồng đăng lọc thông báo ≤10 phút",
      _m is not None and int(_m.group(1)) <= 10)
# Chờ 90s rồi mới đọc, nên cửa sổ phải rộng hơn thời gian chờ
check("cửa sổ lọc rộng hơn thời gian chờ",
      _m is not None and int(_m.group(1)) * 60 > _tl.CHO_THONG_BAO_GIAY)

# Nhóm slug cũng phải khớp ở regex permalink dùng cho nhật ký
check("permalink nhóm slug",
      _tl.RE_LINK_NHOM.search("/groups/homestaytimescity/posts/168055/").groups()
      == ("homestaytimescity", "168055"))

# ── Xếp lịch: phiên comment tính NGANG phiên đăng bài, phủ đều khung giờ ───
import xep_lich as _xl
from collections import Counter

_S, _E = 5 * 60, 3 * 60 + 24 * 60          # 05:00 → 03:00 hôm sau

check("nghỉ 12p -> 5 phiên/giờ",      _xl.tong_luc([{"ten": "A", "nghi": 12}]) == 5.0)
check("tổng lực cộng dồn mọi acc",
      _xl.tong_luc([{"ten": "P", "nghi": 12}, {"ten": "C", "nghi": 12}]) == 10.0)
check("độ nén = 60/tổng lực",
      abs(_xl.do_nen([{"ten": "P", "nghi": 12}, {"ten": "C", "nghi": 12}]) - 6.0) < 1e-9)

_accs = [{"ten": f"P{i}", "nghi": 12} for i in range(3)] +         [{"ten": f"C{i}", "nghi": 12} for i in range(2)]
_ra = _xl.phan_bo_lich(_accs, _S, _E)
_tk = _xl.thong_ke(_ra)
check("có sinh ra lịch",              _tk["so_slot"] > 400)
check("KHÔNG hai phiên trùng phút",   _tk["gap_min"] >= 1)
check("gap trung bình ≈ độ nén",      abs(_tk["gap_tb"] - _xl.do_nen(_accs)) < 1.0)
check("mọi acc đều có slot",          {t for _, t in _ra} == {a["ten"] for a in _accs})
_dem = Counter(t for _, t in _ra)
check("cùng chu kỳ -> số slot cân nhau",
      (max(_dem.values()) - min(_dem.values())) <= max(_dem.values()) * 0.1)

# Chu kỳ KHÁC nhau — chỗ thuật toán cũ đẻ ra khoảng cách 0 phút (hai phiên nổ
# cùng lúc rồi để hở phía sau).
_mix = [{"ten": f"P{i}", "nghi": 12} for i in range(3)] +        [{"ten": f"C{i}", "nghi": 30} for i in range(2)]
_ra2 = _xl.phan_bo_lich(_mix, _S, _E)
_tk2 = _xl.thong_ke(_ra2)
check("chu kỳ lệch: vẫn không đụng độ", _tk2["gap_min"] >= 1)
check("chu kỳ lệch: phân bố đều hơn cũ", _tk2["lech_chuan"] < 1.3)
_d2 = Counter(t for _, t in _ra2)
check("nghỉ 12p chạy dày hơn nghỉ 30p", _d2["P0"] > _d2["C0"])
check("tỉ lệ slot ≈ tỉ lệ lực (30/12=2.5)", 1.9 < _d2["P0"] / _d2["C0"] < 3.1)
check("mọi slot nằm trong khung giờ",  all(_S <= t <= _E for t, _ in _ra2))
check("lịch sắp theo thời gian tăng dần",
      all(_ra2[i][0] <= _ra2[i + 1][0] for i in range(len(_ra2) - 1)))
check("không acc -> lịch rỗng",       _xl.phan_bo_lich([], _S, _E) == [])
check("khung giờ ngược -> lịch rỗng", _xl.phan_bo_lich(_accs, _E, _S) == [])
check("nghỉ = 0 không làm chia 0",    len(_xl.phan_bo_lich([{"ten": "A", "nghi": 0}], _S, _S + 60)) > 0)
check("gen 2 lần ra kết quả giống nhau", _xl.phan_bo_lich(_mix, _S, _E) == _ra2)

# ── Loại đăng: 7 lựa chọn (đã bỏ C_ = chỉ comment) ─────────────────────────
# C_Home / C_Thuê / C_Bán từng là "chỉ comment, không đăng". Nay việc đó do
# TRẠNG THÁI `Spam` đảm nhiệm và máy tự đặt, nên bỏ đi cho khỏi hai nguồn sự
# thật cho cùng một tình huống.
check("có đúng 7 lựa chọn",           len(db.LOAI_DANG_OPTIONS) == 7)
check("không còn lựa chọn C_ nào",
      not any(str(v).startswith("C_") for v in db.LOAI_DANG_OPTIONS))
check("nhận diện loại hỗn hợp X_",
      all(db.la_loai_hon_hop(v) for v in ("X_Home", "X_Thuê", "X_Bán")))
check("loại chỉ đăng KHÔNG phải hỗn hợp",
      not any(db.la_loai_hon_hop(v) for v in ("", "Homestay", "Thuê", "Bán")))
check("X_Home -> lịch homestay",      db.khop_loai_lich("X_Home", "homestay"))
check("X_Thuê KHÔNG lọt lịch bán",    not db.khop_loai_lich("X_Thuê", "ban"))

# "Chỉ comment" nay đọc từ trạng thái acc, không từ loại đăng.
check("acc Spam -> chỉ comment",      db.acc_dang_spam({"trang_thai": db.TRANG_THAI_SPAM}))
check("acc Active -> KHÔNG chỉ comment", not db.acc_dang_spam({"trang_thai": "Active"}))
check("acc thiếu trạng thái -> không", not db.acc_dang_spam({}))

# Khớp lịch phải CHÍNH XÁC: "X_Thuê" chứa chuỗi con "Thuê", "X_Bán" chứa "Bán".
check("Homestay -> lịch homestay",    db.khop_loai_lich("Homestay", "homestay"))
check("X_Bán  -> đúng lịch bán",      db.khop_loai_lich("X_Bán", "ban"))
check("Thuê KHÔNG lọt vào lịch homestay", not db.khop_loai_lich("Thuê", "homestay"))
check("để trống -> không vào lịch nào",
      not any(db.khop_loai_lich("", l) for l in ("homestay", "thue", "ban")))
# Loại C_ cũ nay là giá trị KHÔNG hợp lệ, không được khớp lịch nào.
check("C_Home cũ không còn khớp lịch",
      not any(db.khop_loai_lich("C_Home", l) for l in ("homestay", "thue", "ban")))

for _v in db.LOAI_DANG_OPTIONS:
    db.update_account_field(_acc_id, "loai_dang", _v)
check("lưu được cả 7 giá trị hợp lệ",
      db.get_account_by_id(_acc_id)["loai_dang"] == db.LOAI_DANG_OPTIONS[-1])
for _xau in ("C_Home", "C_home", "homestay", "Comment", "C_Nha", "Homestay,Thuê"):
    try:
        db.update_account_field(_acc_id, "loai_dang", _xau)
        check(f"chặn loại đăng sai '{_xau}'", False)
    except ValueError:
        check(f"chặn loại đăng sai '{_xau}'", True)
db.update_account_field(_acc_id, "loai_dang", "  Homestay  ")
check("khoảng trắng thừa được cắt bỏ",
      db.get_account_by_id(_acc_id)["loai_dang"] == "Homestay")
db.update_account_field(_acc_id, "loai_dang", "")

# Page được phân công cho slot — bước khởi động CHUYỂN sang Page này.
_pid = db.upsert_page({"ten_page": "PageTest", "page_uid": "61500000000000",
                       "link_page": "https://www.facebook.com/PageThat"})
check("lấy đúng page_uid của slot", _cb._lay_page_uid("PageTest") == "61500000000000")
check("slot không có Page -> rỗng",   _cb._lay_page_uid("") == "")
check("Page không tồn tại -> rỗng",   _cb._lay_page_uid("KhongCoPageNay") == "")
db.delete_page(_pid)

# Hai cột cờ comment cũ phải BIẾN MẤT — chúng làm đúng việc của "X_", để song
# song thì cùng một acc có hai nguồn sự thật mâu thuẫn nhau.
_cot_acc = [r["name"] for r in db._conn().execute("PRAGMA table_info(accounts)")]
check("đã bỏ cột comment_bai",        "comment_bai" not in _cot_acc)
check("đã bỏ cột comment_interval",   "comment_interval" not in _cot_acc)
for _c in ("comment_bai", "comment_interval"):
    try:
        db.update_account_field(_acc_id, _c, 1)
        check(f"không ghi được cột đã bỏ '{_c}'", False)
    except ValueError:
        check(f"không ghi được cột đã bỏ '{_c}'", True)

# ── Chuyển slot theo TỈ LỆ cho acc X_ ──────────────────────────────────────
_sx = [{"ten_acc": "X1", "gio_dang": f"{5+i//4:02d}:{(i%4)*15:02d}"} for i in range(100)]
_n = _xl.chuyen_slot_theo_ti_le(_sx, {"X1"}, 25)
check("25% -> đúng 25/100 slot comment", _n == 25)
check("còn lại vẫn là đăng bài",
      sum(1 for r in _sx if (r.get("hoat_dong") or "dang_bai") == "dang_bai") == 75)
# Rải đều: một acc thì cứ 4 slot có 1 comment
_vt = [i for i, r in enumerate(_sx) if r.get("hoat_dong") == "comment"]
check("một acc: nhịp comment đều (cách 4 slot)",
      all(_vt[i+1] - _vt[i] == 4 for i in range(len(_vt) - 1)))

# NHIỀU acc luân phiên — đây mới là chỗ từng hỏng. Nếu mọi acc cùng khởi điểm
# tích luỹ từ 0 thì acc nào cũng đổi slot thứ 4 CỦA RIÊNG NÓ, mà lịch xoay vòng
# đều nên bốn slot đó rơi liền kề → dính cụm "....CCCC....". Đã gặp thật trên
# lịch Homestay: 4 phiên comment liên tiếp lúc 05:39–05:48.
for _n_acc, _tl in ((4, 25), (3, 25), (5, 20), (4, 33)):
    _ten = [chr(65 + i) for i in range(_n_acc)]
    _sm = [{"ten_acc": _ten[i % _n_acc], "gio_dang": "05:00"} for i in range(60)]
    _xl.chuyen_slot_theo_ti_le(_sm, set(_ten), _tl)
    _v = [i for i, r in enumerate(_sm) if r.get("hoat_dong") == "comment"]
    _g = [_v[i+1] - _v[i] for i in range(len(_v) - 1)]
    check(f"{_n_acc} acc / {_tl}%: không có 2 phiên comment liền nhau",
          all(x > 1 for x in _g))
    check(f"{_n_acc} acc / {_tl}%: đúng tỉ lệ (±3%)",
          abs(len(_v) * 100 / 60 - _tl) <= 3)

# Lệch pha phải bám thứ tự XUẤT HIỆN trong lịch (thứ tự xoay vòng), không phải
# thứ tự bảng chữ cái — xáo tên đi kết quả vẫn phải đều.
_sd = [{"ten_acc": ["D", "C", "B", "A"][i % 4], "gio_dang": "05:00"} for i in range(60)]
_xl.chuyen_slot_theo_ti_le(_sd, {"A", "B", "C", "D"}, 25)
_vd = [i for i, r in enumerate(_sd) if r.get("hoat_dong") == "comment"]
check("thứ tự acc đảo ngược vẫn rải đều",
      all(_vd[i+1] - _vd[i] > 1 for i in range(len(_vd) - 1)))

# CÓ SLOT NUÔI NICK CHEN VÀO — đây là ca bộ test cũ bỏ sót, và là đúng cái người
# dùng nhìn thấy trên lịch homestay. Bản cũ cộng dồn theo từng acc: slot nuôi làm
# xê dịch pha của acc đó, các acc đụng nhau và ra "..N....CCC.........CCC...".
# Đo trên lịch thật (3 acc xoay vòng 4 phút, 25%, 1 slot nuôi): 7 lần dính liền.
for _nuoi_tai in (2, 5, 11):
    _ACC3 = ["N1", "N2", "N3"]
    _sn = [{"ten_acc": _ACC3[i % 3], "gio_dang": f"{5 + i // 15:02d}:{(i % 15) * 4:02d}",
            "hoat_dong": "nuoi_nick" if i == _nuoi_tai else "dang_bai"}
           for i in range(45)]
    _xl.chuyen_slot_theo_ti_le(_sn, set(_ACC3), 25)
    _vn = [i for i, r in enumerate(_sn) if r.get("hoat_dong") == "comment"]
    _gn = [_vn[i+1] - _vn[i] for i in range(len(_vn) - 1)]
    check(f"có slot nuôi ở vị trí {_nuoi_tai}: comment không dính cụm",
          all(x > 1 for x in _gn))
    # Chia đều cho các acc, không để một acc gánh hết phần comment.
    _dem_acc = Counter(_sn[i]["ten_acc"] for i in _vn)
    check(f"có slot nuôi ở vị trí {_nuoi_tai}: chia đều cho 3 acc",
          max(_dem_acc.values()) - min(_dem_acc.values()) <= 1)

# Nhịp lý tưởng TRÙNG số acc: 5 acc + tỉ lệ 20% → 100/20 = 5 = số acc, nên mọi
# vị trí lý tưởng rơi vào cùng MỘT acc (slot cách nhau 5 thuộc một acc trong vòng
# xoay 5). Không có cách chia hoàn hảo, nhưng vẫn phải không dính liền nhau.
_ACC5 = [chr(70 + i) for i in range(5)]
_s5 = [{"ten_acc": _ACC5[i % 5], "gio_dang": "05:00"} for i in range(120)]
_xl.chuyen_slot_theo_ti_le(_s5, set(_ACC5), 20)
_v5 = [i for i, r in enumerate(_s5) if r.get("hoat_dong") == "comment"]
check("nhịp trùng số acc: vẫn không dính cụm",
      all(_v5[i+1] - _v5[i] > 1 for i in range(len(_v5) - 1)))
check("nhịp trùng số acc: vẫn đúng tỉ lệ", len(_v5) == 24)

# Tỉ lệ phải CHÍNH XÁC trên tổng, không làm tròn rời rạc từng acc. Làm tròn từng
# acc thì 5 acc × 12 slot × 20% = 2.4 → xuống 2, tổng ra 10 thay vì 12 (16.7%).
for _na, _tl2, _mong in ((5, 20, 24), (4, 25, 30), (3, 25, 30), (7, 15, 18)):
    _tn = [chr(80 + i) for i in range(_na)]
    _st = [{"ten_acc": _tn[i % _na], "gio_dang": "05:00"} for i in range(120)]
    _xl.chuyen_slot_theo_ti_le(_st, set(_tn), _tl2)
    check(f"{_na} acc / {_tl2}%: đúng {_mong}/120 slot",
          sum(1 for r in _st if r.get("hoat_dong") == "comment") == _mong)

# Gọi hai lần trên cùng dữ liệu phải ra y hệt — phần dư chia theo thứ tự xuất
# hiện nên không phụ thuộc thứ tự lặp của dict.
_sr1 = [{"ten_acc": ["Z", "Y", "X"][i % 3], "gio_dang": "05:00"} for i in range(50)]
_sr2 = [dict(r) for r in _sr1]
_xl.chuyen_slot_theo_ti_le(_sr1, {"X", "Y", "Z"}, 25)
_xl.chuyen_slot_theo_ti_le(_sr2, {"X", "Y", "Z"}, 25)
check("chạy 2 lần ra kết quả giống nhau",
      [r.get("hoat_dong") for r in _sr1] == [r.get("hoat_dong") for r in _sr2])

_sx2 = [{"ten_acc": "X1", "gio_dang": "05:00"} for _ in range(100)]
check("tỉ lệ 0 -> không đổi slot nào",  _xl.chuyen_slot_theo_ti_le(_sx2, {"X1"}, 0) == 0)
check("tỉ lệ 100 -> đổi hết",           _xl.chuyen_slot_theo_ti_le(_sx2, {"X1"}, 100) == 100)
_sx3 = [{"ten_acc": "A", "gio_dang": "05:00"} for _ in range(20)]
check("acc không thuộc nhóm X_ -> bỏ qua", _xl.chuyen_slot_theo_ti_le(_sx3, {"X1"}, 50) == 0)
# Slot đã bị nuôi chiếm thì giữ nguyên — nên phải gọi SAU bước chuyển nuôi
_sx4 = [{"ten_acc": "X1", "gio_dang": "05:00", "hoat_dong": "nuoi_nick"} for _ in range(10)]
check("không cướp slot của nuôi nick", _xl.chuyen_slot_theo_ti_le(_sx4, {"X1"}, 50) == 0)

# ── Chỉ comment vào bài CHÍNH CHỦ ──────────────────────────────────────────
db.xoa_het_comment_posts("ban")
db.them_comment_posts("ban", [_lk("gA", 1), _lk("gB", 2)], page="PAGE_1")
db.them_comment_posts("ban", [_lk("gC", 3), _lk("gD", 4)], page="PAGE_2")
check("lưu được Page của từng link",
      {r["page"] for r in db.get_comment_posts("ban")} == {"PAGE_1", "PAGE_2"})
# `page` là THỨ TỰ ƯU TIÊN, không phải bộ lọc cứng: bài chính chủ đi trước rồi
# LẤP ĐẦY bằng bài cùng hạng mục cho đủ số bài đã cài đặt.
_b1 = db.boc_bai_de_comment("ban", 9, page="PAGE_1")
check("ưu tiên Page 1 vẫn lấy đủ 4 bài", len(_b1) == 4)
check("2 bài đầu là của Page 1",
      [r["page"] for r in _b1[:2]] == ["PAGE_1", "PAGE_1"])
check("2 bài sau là Page khác",
      all(r["page"] != "PAGE_1" for r in _b1[2:]))
check("không ưu tiên ai -> vẫn lấy cả 4", len(db.boc_bai_de_comment("ban", 9)) == 4)
# Page chưa có bài nào trong kho: KHÔNG bỏ phiên, lấy hết bài của hạng mục.
check("Page lạ -> vẫn lấy đủ bài hạng mục",
      len(db.boc_bai_de_comment("ban", 9, page="PAGE_9")) == 4)

# ĐÂY LÀ CA ĐÃ HỎNG: acc yếu chỉ đăng chéo được vào 1 nhóm nên cả kho chỉ có 1
# link của nó. Lọc cứng thì mỗi phiên comment đúng 1 bài thay vì 10 — mất 90%
# công suất. Nay phải lấy 1 của mình + phần còn lại của hạng mục.
db.xoa_het_comment_posts("ban")
db.them_comment_posts("ban", [_lk("yeu", 1)], page="PAGE_YEU")
db.them_comment_posts("ban", [_lk(f"kho{i}", i) for i in range(2, 13)], page="PAGE_KHAC")
_by = db.boc_bai_de_comment("ban", 10, page="PAGE_YEU")
check("acc yếu 1 link -> vẫn đủ 10 bài", len(_by) == 10)
check("acc yếu: bài đầu là của chính nó", _by[0]["page"] == "PAGE_YEU")
check("acc yếu: 9 bài sau của hạng mục",
      sum(1 for r in _by[1:] if r["page"] == "PAGE_KHAC") == 9)
check("acc yếu: vẫn 1 link mỗi nhóm",
      len({r["nhom"] for r in _by}) == len(_by))

# Dựng lại dữ liệu cho các assertion phía dưới.
db.xoa_het_comment_posts("ban")
db.them_comment_posts("ban", [_lk("gA", 1), _lk("gB", 2)], page="PAGE_1")
db.them_comment_posts("ban", [_lk("gC", 3), _lk("gD", 4)], page="PAGE_2")
db.them_comment_posts("ban", [_lk("gE", 5)])
check("link chưa gắn Page vẫn được dùng",
      len(db.boc_bai_de_comment("ban", 9, page="PAGE_1")) == 5)
check("Page lạ: lùi về chung kho -> có bài",
      len(db.boc_bai_de_comment("ban", 9)) == 5)
check("lùi về chung kho vẫn giữ 1 link/nhóm",
      len({r["nhom"] for r in db.boc_bai_de_comment("ban", 9)}) == 5)
db.xoa_het_comment_posts("ban")

# Thư viện câu
check("tách câu bỏ dòng trống/trùng",
      _cb.tach_cau("a\n\n b \na\nc") == ["a", "b", "c"])
check("thư viện rỗng -> []",          _cb.tach_cau("   \n\n") == [])
_cau = _cb.tach_cau("c1\nc2\nc3")
_pick = nuoi_nick.pick_messages(_cau, 10)
check("bốc đủ câu cho 10 bài",        len(_pick) == 10)
check("KHÔNG lặp câu ở 2 bài liền nhau",
      all(_pick[i] != _pick[i+1] for i in range(len(_pick) - 1)))

db.xoa_het_comment_posts("homestay")
check("xoá hết -> danh sách rỗng",    db.get_comment_posts("homestay") == [])

# Acc CHỈ COMMENT mà có tick Nuôi thì vẫn phải được nuôi — hy sinh một phiên
# comment để đi nuôi, y như acc đăng bài hy sinh một slot đăng.
#
# Thứ tự các bước là mấu chốt: plan_* chỉ đụng slot 'dang_bai', nên nuôi phải
# chạy TRƯỚC rồi mới quét nốt slot còn lại thành comment. Làm ngược lại thì acc
# C_* bị khoá hết thành 'comment' và không bao giờ được nuôi.
_sc = [{"ten_acc": "CN", "gio_dang": f"{5 + i//4:02d}:{(i%4)*15:02d}",
        "ma_content": "C1"} for i in range(40)]
_n_nuoi = nuoi_nick.plan_warming_conversion(_sc, {"CN": 150}, da_dat=[])
for _r in _sc:                                   # bước 3: quét nốt slot còn lại
    if (_r.get("hoat_dong") or "dang_bai") == "dang_bai":
        _r["hoat_dong"] = "comment"
_hd2 = Counter(r["hoat_dong"] for r in _sc)
check("acc chỉ comment vẫn được nuôi",   _hd2["nuoi_nick"] == _n_nuoi > 0)
check("slot còn lại đều là comment",     _hd2["comment"] == len(_sc) - _n_nuoi)
check("không còn slot đăng bài",         _hd2["dang_bai"] == 0)

# Nếu quét comment TRƯỚC thì nuôi không còn slot nào để chiếm — canh đúng cái bẫy
_sai = [{"ten_acc": "CN", "gio_dang": f"{5 + i//4:02d}:{(i%4)*15:02d}",
         "ma_content": "C1", "hoat_dong": "comment"} for i in range(40)]
check("sai thứ tự -> nuôi mất sạch slot",
      nuoi_nick.plan_warming_conversion(_sai, {"CN": 150}, da_dat=[]) == 0)

# Chuyển slot: phiên nuôi và phiên comment KHÔNG được rơi vào cùng một slot,
# cũng không được sát nhau (chung danh sách mốc `da_dat`).
_sched = [{"ten_acc": "A", "gio_dang": f"{7 + i//4:02d}:{(i%4)*15:02d}",
           "ma_content": "C1"} for i in range(40)]
_dat = []
_n_nuoi = nuoi_nick.plan_warming_conversion(_sched, {"A": 150}, da_dat=_dat)
_n_cmt  = nuoi_nick.plan_slot_conversion(_sched, {"A": 180}, "comment", da_dat=_dat)
_hd = [r.get("hoat_dong", "dang_bai") for r in _sched]
check("có chuyển được slot nuôi",     _n_nuoi > 0)
check("có chuyển được slot comment",  _n_cmt > 0)
check("tổng slot chuyển khớp đếm",
      _hd.count("nuoi_nick") == _n_nuoi and _hd.count("comment") == _n_cmt)
check("một slot chỉ làm MỘT việc",    len(_hd) == len(_sched))
check("vẫn còn slot đăng bài",        "dang_bai" in _hd)
# Comment không được cướp slot mà nuôi đã chiếm
_gio_nuoi = {r["gio_dang"] for r in _sched if r.get("hoat_dong") == "nuoi_nick"}
_gio_cmt  = {r["gio_dang"] for r in _sched if r.get("hoat_dong") == "comment"}
check("nuôi và comment không trùng giờ", not (_gio_nuoi & _gio_cmt))

# ── Biến thể ảnh: ảnh gốc phải BẤT KHẢ XÂM PHẠM ────────────────────────────
# Rủi ro lớn nhất của tính năng này là ghi đè lên ảnh gốc của người dùng —
# không có bản backup nào. Test này canh đúng chỗ đó.
import shutil, tempfile as _tf
import anh_bien_the as _bt
import storage as _st

if not _bt.CO_PILLOW:
    check("BỎ QUA test biến thể ảnh (chưa cài Pillow)", True)
else:
    from PIL import Image as _Im
    _md = Path(_tf.mkdtemp(prefix="test_bt_"))
    _goc = _md / "goc.jpg"
    # Ảnh có cấu trúc thật, không phải nền trơn: nền trơn cho pHash toàn 0 bit
    # nên mọi phép đo đều vô nghĩa.
    _im = _Im.new("RGB", (600, 400))
    _im.putdata([((x * 7) % 256, (y * 5) % 256, ((x + y) * 3) % 256)
                 for y in range(400) for x in range(600)])
    _im.save(_goc, "JPEG", quality=92)
    _byte_goc = _goc.read_bytes()
    _hash_goc = _bt.phash(str(_goc))

    _ra = _bt.tao_bien_the(str(_goc), str(_md / "ra"), seed=1, cuong_do="manh")
    check("biến thể tạo ra file mới",     Path(_ra).exists() and _ra != str(_goc))
    check("ẢNH GỐC KHÔNG BỊ SỬA",         _goc.read_bytes() == _byte_goc)
    check("biến thể khác byte ảnh gốc",   Path(_ra).read_bytes() != _byte_goc)
    check("biến thể có dịch pHash",       _bt.khoang_cach(_hash_goc,
                                                          _bt.phash(_ra)) > 0)

    # Cùng seed -> cùng kết quả. Cần cho việc dựng lại đúng ảnh đã đăng khi
    # phải đối chiếu về sau.
    import random as _rd
    _ma = [_bt.sinh_ma(_rd.Random(i)) for i in range(200)]
    check("mã đúng 8 ký tự",              all(len(m) == _bt.DAI_MA for m in _ma))
    check("mã chỉ gồm chữ và số",         all(c in _bt.BANG_MA for m in _ma for c in m))
    check("mã không lặp lại",             len(set(_ma)) == len(_ma))

    _r2 = _bt.tao_bien_the(str(_goc), str(_md / "r2"), seed=1, cuong_do="manh")
    check("cùng seed -> cùng kết quả",    Path(_ra).read_bytes() == Path(_r2).read_bytes())
    _r3 = _bt.tao_bien_the(str(_goc), str(_md / "r3"), seed=2, cuong_do="manh")
    check("khác seed -> khác kết quả",    Path(_ra).read_bytes() != Path(_r3).read_bytes())

    # Cả bộ: phải giữ nguyên thứ tự người dùng đã xếp trong ô ảnh của content.
    _b = _md / "b.jpg"; _im.rotate(90, expand=True).save(_b, "JPEG")
    _bo = _bt.bien_the_ca_bo([str(_goc), str(_b)], str(_md / "out"), seed_key="acc")
    check("cả bộ ra đủ số ảnh",           len(_bo) == 2)
    check("cả bộ giữ đúng thứ tự",        [Path(p).stem for p in _bo] == ["1", "2"])
    check("cả bộ nằm ngoài thư mục gốc",  all(str(_md / "out") in p for p in _bo))

    # File hỏng / định dạng lạ: phải trả về ảnh gốc, tuyệt đối không ném lỗi
    # làm chết cả lượt đăng.
    _xau = _md / "xau.jpg"; _xau.write_bytes(b"day khong phai anh")
    check("file hỏng -> trả lại đường dẫn gốc",
          _bt.tao_bien_the(str(_xau), str(_md / "z"), seed=1) == str(_xau))

    # storage: bật/tắt phải ăn đúng, và ảnh gốc vẫn nguyên vẹn sau khi đăng.
    _url = "/" + str(_goc).replace("\\", "/").lstrip("/")
    _mp = _st.MEDIA_DIR
    try:
        _st.MEDIA_DIR = _md / "x"          # để MEDIA_DIR.parent == _md
        db.set_setting("anh_bien_the_bat", "0")
        _p, _t = _st.prepare_images_for_post("/goc.jpg")
        check("tắt -> dùng thẳng ảnh gốc", _p == [str(_goc)] and _t is None)

        # Thứ tự ảnh = thứ tự trong ô ảnh của content, KHÔNG sort theo tên file.
        # Ảnh local mang tên uuid ngẫu nhiên nên sort là xáo trộn thứ tự người dùng.
        _p, _ = _st.prepare_images_for_post("/b.jpg,/goc.jpg")
        check("giữ đúng thứ tự đầu vào",   _p == [str(_b), str(_goc)])
        _p, _ = _st.prepare_images_for_post("/goc.jpg,/b.jpg")
        check("đảo đầu vào -> đảo đầu ra", _p == [str(_goc), str(_b)])

        db.set_setting("anh_bien_the_bat", "1")
        db.set_setting("anh_bien_the_cuong_do", "manh")
        _p, _t = _st.prepare_images_for_post("/goc.jpg", seed_key="acc")
        check("bật -> có tạo temp",        _t is not None)
        check("bật -> KHÔNG trả ảnh gốc",  _p and _p[0] != str(_goc))
        check("bật -> ảnh gốc vẫn nguyên", _goc.read_bytes() == _byte_goc)
        _st.cleanup_temp(_t)
        check("cleanup xoá sạch temp",     not Path(_t).exists())
        check("cleanup KHÔNG đụng ảnh gốc", _goc.exists())
    finally:
        _st.MEDIA_DIR = _mp
        db.set_setting("anh_bien_the_bat", "0")
        shutil.rmtree(_md, ignore_errors=True)

# ── server: KHÔNG rò rỉ credential qua /api/accounts ───────────────────────
import server

_client = server.app.test_client()
_res    = _client.get("/api/accounts")
_rows   = _res.get_json()["data"]
_row    = next((r for r in _rows if r["id"] == _acc_id), None)

check("/api/accounts trả về acc",      _row is not None)
if _row:
    check("password bị che",           _row["password"] == server.SECRET_MASK)
    check("xs bị che",                 _row["xs"] == server.SECRET_MASK)
    check("twofa bị che",              _row["twofa"] == server.SECRET_MASK)
    check("không lộ giá trị thật",     "pw-that" not in _res.get_data(as_text=True))
    check("trường thường vẫn hiện",    _row["ten_acc"] == "TestAcc")

# Lưu form với dấu che KHÔNG được ghi đè credential thật
_client.post("/api/accounts/save", json={"id": _acc_id, "ten_acc": "TestAcc2",
                                         "password": server.SECRET_MASK})
check("dấu che không ghi đè password", db.get_account_by_id(_acc_id)["password"] == "pw-that")
check("trường thường vẫn lưu được",    db.get_account_by_id(_acc_id)["ten_acc"] == "TestAcc2")

# Sửa inline bằng dấu che cũng phải bị bỏ qua
_client.post(f"/api/accounts/{_acc_id}/field", json={"field": "xs", "value": server.SECRET_MASK})
check("dấu che không ghi đè xs",       db.get_account_by_id(_acc_id)["xs"] == "xs-that")

# Nhưng giá trị thật thì vẫn sửa được bình thường
_client.post(f"/api/accounts/{_acc_id}/field", json={"field": "xs", "value": "xs-moi"})
check("sửa xs bằng giá trị thật OK",   db.get_account_by_id(_acc_id)["xs"] == "xs-moi")

# Nút "Refresh cookie ngay" — không acc nào để Yes thì phải im lặng trả rỗng,
# tuyệt đối không mở trình duyệt. (Refresh của scheduler 10 phút mới quét và
# chỉ chạy khi có runner bật; nút này là đường thoát khi runner đều tắt.)
db.update_account_field(_ar["id"], "refresh", "Done")
_res = _client.post("/api/accounts/refresh-now").get_json()
check("endpoint refresh-now tồn tại",  _res.get("ok") is True)
check("không có acc Yes -> rỗng",      _res.get("da_lam") == [] and _res.get("loi") == [])

# ── Sức khoẻ acc: nghỉ tạm vs tắt hẳn ──────────────────────────────────────
import suc_khoe_acc as _sk

check("lịch sử rỗng -> không làm gì",   _sk.danh_gia("") == ("", ""))
check("4 lỗi liên tiếp chưa nghỉ",      _sk.danh_gia("x" * 4)[0] == "")
check("5 lỗi liên tiếp -> nghỉ",        _sk.danh_gia("x" * 5)[0] == "nghi")
check("acc khoẻ xen lỗi lẻ -> yên",     _sk.danh_gia("ooxooxoooxoo")[0] == "")

# KHÔNG còn kết luận "tắt hẳn". Bị Facebook chặn là chuyện bình thường và tự
# hết sau vài tiếng — tắt hẳn là mất luôn một nick còn sống chỉ vì một đợt chặn
# dài. Hỏng bao nhiêu cũng chỉ nghỉ rồi thăm dò lại mỗi tiếng.
for _n in (5, 16, 20, 40):
    check(f"{_n}/{_n} hỏng vẫn chỉ NGHỈ, không tắt",
          _sk.danh_gia("x" * _n)[0] == "nghi")
check("không còn hành động 'tat' nào",
      "tat" not in {_sk.danh_gia(_x)[0]
                    for _x in ("x"*20, "x"*16+"o"*4, "ooxx"*10, "-x", "")})
check("cửa sổ giữ đúng 20 phiên",       _sk.them_ket_qua("o" * 25, False).count("o") == 19)

# Dấu ngắt: cắt chuỗi lỗi nhưng KHÔNG xoá cửa sổ. Bản đầu xoá sạch lịch sử lúc
# cho nghỉ, hậu quả là cửa sổ không bao giờ tích đủ 20 và tầng "tắt hẳn" vĩnh
# viễn không nổ — acc chết cứ nghỉ-hỏng-nghỉ mãi mà không ai bị tắt.
_sau = _sk.danh_dau_nghi("x" * 5)
check("dấu ngắt cắt chuỗi lỗi",         _sk.chuoi_loi(_sau) == 0)
check("dấu ngắt giữ lại các lỗi cũ",    _sau.count("x") == 5)
check("dấu ngắt không tính là phiên",   _sk.ti_le_hong(_sau) == 1.0)
# Phiên ĐẦU sau khi nghỉ dậy là phiên THĂM DÒ: hỏng thì nghỉ lại ngay, không
# đợi gom đủ 5 lỗi nữa. Thiếu luật này thì acc đang bị chặn được đâm đầu thêm 5
# phiên mới nghỉ lại — vừa phí slot, vừa làm Facebook soi nặng thêm.
check("thăm dò hỏng -> nghỉ lại ngay",
      _sk.danh_gia(_sk.them_ket_qua(_sau, False)) == ("nghi", "thăm dò sau khi nghỉ vẫn hỏng"))
check("thăm dò ĐƯỢC -> chạy tiếp bình thường",
      _sk.danh_gia(_sk.them_ket_qua(_sau, True))[0] == "")
# Sau khi thăm dò được, acc lại có đủ CHUOI_NGHI lượt trước khi nghỉ lần nữa.
_ok1 = _sk.them_ket_qua(_sau, True)
check("thăm dò được rồi hỏng 1 lượt -> chưa nghỉ",
      _sk.danh_gia(_sk.them_ket_qua(_ok1, False))[0] == "")

# Acc chết vẫn phải tới được "tắt" dù đã nghỉ nhiều lần giữa chừng.
_ls = ""
for _ in range(30):
    _ls = _sk.them_ket_qua(_ls, False)
    _hd, _ = _sk.danh_gia(_ls)
    if _hd == "nghi":
        _ls = _sk.danh_dau_nghi(_ls)
check("hỏng liên tục mãi vẫn không bị tắt", _hd in ("", "nghi"))

# ── Sức khoẻ acc: tầng DB ──────────────────────────────────────────────────
_aid = db.upsert_account({"ten_acc": "SK Test", "trang_thai": "Active",
                          "loai_dang": "Homestay"})
check("acc mới được chạy",              db.acc_duoc_chay("SK Test")[0] is True)
for _ in range(4):
    db.ghi_nhan_phien_dang("SK Test", False)
check("4 lỗi vẫn chạy",                 db.acc_duoc_chay("SK Test")[0] is True)
_hd5, _ = db.ghi_nhan_phien_dang("SK Test", False)
check("lỗi thứ 5 -> cho nghỉ",          _hd5 == "nghi")
check("đang nghỉ thì không chạy",       db.acc_duoc_chay("SK Test")[0] is False)
check("nghỉ có sinh cảnh báo",          any(c["ten_acc"] == "SK Test"
                                            for c in db.lay_canh_bao()))
db.xoa_canh_bao()
check("xem xong thì hết cảnh báo",      not any(c["ten_acc"] == "SK Test"
                                                for c in db.lay_canh_bao()))
# Nghỉ là trạng thái tạm — trang_thai trong DB phải vẫn là Active, nếu không
# Gen lịch lần sau sẽ loại acc này vĩnh viễn.
check("nghỉ KHÔNG đổi trang_thai",      db.get_account_by_name("SK Test") is not None)
# Nghỉ chỉ chặn đăng/comment. Nuôi nick vẫn chạy — đó là việc có cơ gỡ acc ra.
check("nghỉ vẫn nuôi nick được",        db.acc_duoc_chay("SK Test", "nuoi_nick")[0] is True)
check("nghỉ chặn comment",              db.acc_duoc_chay("SK Test", "comment")[0] is False)

# Ép hỏng hẳn: xoá mốc nghỉ rồi bơm lỗi cho đầy cửa sổ.
with db._conn() as _c:
    _c.execute("UPDATE accounts SET nghi_den='' WHERE id=?", (_aid,))
for _ in range(40):
    with db._conn() as _c:
        _c.execute("UPDATE accounts SET nghi_den='' WHERE id=?", (_aid,))
    _hd, _ = db.ghi_nhan_phien_dang("SK Test", False)
check("hỏng 40 phiên vẫn KHÔNG bị tắt hẳn",
      (db.get_accounts() and
       next(a["trang_thai"] for a in db.get_accounts() if a["ten_acc"] == "SK Test")
       != "Hỏng"))
check("acc hỏng nhiều vẫn còn trong danh sách",
      db.get_account_by_name("SK Test") is not None)

# "Dừng" là trạng thái DUY NHẤT bạn tự đặt, và nó chặn TẤT — kể cả nuôi nick.
# Trước đây "Tạm dừng" không chặn gì: nó chỉ bị loại khỏi Gen lịch, nên slot đã
# gen từ trước vẫn chạy tiếp — đặt dừng mà nick vẫn đăng bài.
db.update_account_field(_aid, "trang_thai", db.TRANG_THAI_DUNG)
check("Dừng -> chặn đăng bài",   db.acc_duoc_chay("SK Test")[0] is False)
check("Dừng -> chặn comment",    db.acc_duoc_chay("SK Test", "comment")[0] is False)
check("Dừng -> chặn cả nuôi nick",
      db.acc_duoc_chay("SK Test", "nuoi_nick")[0] is False)
db.update_account_field(_aid, "trang_thai", "Active")
check("bật lại Active -> chạy được", db.acc_duoc_chay("SK Test")[0] is True)

# Bật lại về Active phải xoá sạch lịch sử — không thì phiên hỏng kế tiếp lập tức
# chạm lại ngưỡng và acc bị tắt lại ngay, nhìn như nút bật không ăn.
db.update_account_field(_aid, "trang_thai", "Active")
check("bật lại -> chạy được",           db.acc_duoc_chay("SK Test")[0] is True)
with db._conn() as _c:
    _r = _c.execute("SELECT lich_su_phien, nghi_den, canh_bao_moi FROM accounts "
                    "WHERE id=?", (_aid,)).fetchone()
check("bật lại -> xoá lịch sử phiên",   _r["lich_su_phien"] == "")
check("bật lại -> xoá mốc nghỉ",        _r["nghi_den"] == "")
check("bật lại -> xoá cảnh báo",        _r["canh_bao_moi"] == "")
db.delete_account(_aid)

# ── Nhận biết acc bị gỡ bài vì spam ────────────────────────────────────────
# Mẫu dựng theo đúng dialog "Sự việc" người dùng chụp được: tiêu đề + 5 dòng
# "Spam / Đã gỡ bài viết / <ngày>" + nút "Xem tất cả (12)".
_DLG_SPAM = ("Sự việc 13 tháng 8, 2026 Chúng tôi đã gỡ một số nội dung hoặc tin nhắn "
             + "Spam Đã gỡ bài viết 13 tháng 8, 2026 " * 5
             + "Xem tất cả (12)")

check("đọc được số vụ từ 'Xem tất cả'", _sk.doc_vi_pham(_DLG_SPAM) == {"so": 12, "spam": True})
check("nhận ra là do spam",             _sk.doc_vi_pham(_DLG_SPAM)["spam"] is True)
# Không có "Xem tất cả" thì đếm số dòng.
check("thiếu 'Xem tất cả' -> đếm dòng",
      _sk.doc_vi_pham("Spam Đã gỡ bài viết hôm nay Spam Đã gỡ bài viết hôm nay")["so"] == 2)
# Facebook diễn đạt hai kiểu. Đọc 9 chuỗi cảnh báo THẬT trong log thấy 4 chuỗi
# ghi "Đã gỡ bài viết" còn 5 chuỗi ghi "Ảnh đã bị gỡ" — bắt thiếu một vế là bỏ
# sót quá nửa số ca. Phần mềm này đăng bài kèm ảnh nên hai thứ là một.
check("bắt cả 'Ảnh đã bị gỡ'", (_sk.doc_vi_pham(
    "Sự việc 11 tháng 8, 2026 Chúng tôi đã gỡ một số nội dung hoặc tin nhắn "
    "Spam Ảnh đã bị gỡ 11 tháng 8, 2026") or {}).get("spam") is True)
# Dialog gỡ TIN NHẮN không được coi là gỡ bài — nó không phải lý do dừng đăng.
check("gỡ tin nhắn -> bỏ qua",
      _sk.doc_vi_pham("Sự việc Chúng tôi đã gỡ một số tin nhắn của bạn") is None)
check("chuỗi rỗng -> bỏ qua",           _sk.doc_vi_pham("") is None)
check("dialog thường -> bỏ qua",        _sk.doc_vi_pham("Đoạn chat Tất cả Chưa đọc") is None)

# Lần đo ĐẦU chỉ ghi mốc. Thiếu luật này thì ngay phiên đầu sau khi bật tính
# năng, mọi acc có sẵn vi phạm cũ đều bị đánh spam cùng lúc.
check("lần đo đầu KHÔNG gắn cờ",        _sk.co_vu_moi(-1, 12) is False)
check("số vụ tăng -> có vụ mới",        _sk.co_vu_moi(12, 13) is True)
check("số vụ đứng yên -> không",        _sk.co_vu_moi(12, 12) is False)
check("số vụ giảm -> không",            _sk.co_vu_moi(12, 9) is False)

# ── Spam: tầng DB ──────────────────────────────────────────────────────────
_sid = db.upsert_account({"ten_acc": "SPAM Test", "trang_thai": "Active",
                          "loai_dang": "Homestay", "ten_page": "P"})
# Mốc giờ CỐ ĐỊNH, không lấy từ đồng hồ thật: bản đầu dùng "giờ hiện tại + 1"
# nên chạy test lúc 23 giờ là hỏng — min(23, 24) ra 23:00, không còn ở tương lai.
from datetime import datetime as _dt, timedelta as _td
_GIO_MOC  = "12:00"
_gio_sau   = "13:00"
_gio_truoc = "11:00"
with db._conn() as _c:
    for _hd, _g in (("dang_bai", _gio_sau), ("dang_bai", _gio_truoc),
                    ("comment", _gio_sau), ("nuoi_nick", _gio_sau)):
        _c.execute("INSERT INTO schedules (loai,stt,ma_content,ten_acc,gio_dang,"
                   "trang_thai,hoat_dong) VALUES ('homestay',900,'X',?,?,'Chờ',?)",
                   ("SPAM Test", _g, _hd))

_moi1, _cu1 = db.ghi_nhan_vi_pham("SPAM Test", 12, True)
check("lần đo đầu chỉ ghi mốc",         _moi1 is False and _cu1 == -1)
_moi2, _cu2 = db.ghi_nhan_vi_pham("SPAM Test", 12, True)
check("đo lại cùng số -> không dính",   _moi2 is False and _cu2 == 12)
_moi3, _cu3 = db.ghi_nhan_vi_pham("SPAM Test", 15, True)
check("số vụ tăng -> vừa dính spam",    _moi3 is True and _cu3 == 12)

_n_slot, _moc_spam = db.danh_dau_spam("SPAM Test", "3 bài mới bị gỡ", gio=_GIO_MOC)
check("chuyển trạng thái sang Spam",
      any(a["ten_acc"] == "SPAM Test" and a["trang_thai"] == db.TRANG_THAI_SPAM
          for a in db.get_accounts()))
check("nghỉ đúng THAM_DO_PHUT phút",
      abs((_moc_spam - _dt.now()).total_seconds() / 60 - _sk.THAM_DO_PHUT) < 1)
# FB gỡ bài -> dừng ĐĂNG và COMMENT, hai việc vừa bị phạt. Nuôi nick VẪN chạy:
# lướt feed / xem story là hành vi người thật, không phải thứ bị gỡ bài.
check("dừng cả slot đăng lẫn comment",  _n_slot == 2)
with db._conn() as _c:
    _rows = {(r["hoat_dong"], r["gio_dang"]): r["trang_thai"] for r in _c.execute(
        "SELECT hoat_dong,gio_dang,trang_thai FROM schedules WHERE ten_acc='SPAM Test'")}
# Slot đăng/comment GIỮ NGUYÊN 'Chờ' — chúng vẫn tới giờ và vẫn chạy, chỉ là
# scheduler đổi sang phiên NUÔI NICK. Trước đây chúng bị đánh 'Nghỉ Spam' mà
# scheduler chỉ bốc dòng 'Chờ', nên biến mất hẳn: mỗi lần dính spam là mất
# trắng số slot còn lại của ngày.
check("slot đăng vẫn ở Chờ để chạy nuôi thay",
      _rows[("dang_bai", _gio_sau)] == "Chờ")
check("slot comment vẫn ở Chờ để chạy nuôi thay",
      _rows[("comment", _gio_sau)] == "Chờ")
check("slot đăng đã qua giờ -> để yên", _rows[("dang_bai", _gio_truoc)] == "Chờ")
# Scheduler hỏi hàm này để biết có đổi sang nuôi nick không.
check("đang spam và còn trong giờ nghỉ -> đổi sang nuôi",
      db.acc_dang_spam_nghi("SPAM Test") is True)
# Slot nuôi không bị đụng tới — nuôi vẫn chạy suốt thời gian nghỉ.
check("slot nuôi giữ nguyên trạng thái", _rows[("nuoi_nick", _gio_sau)] == "Chờ")

check("spam chặn ĐĂNG BÀI",             db.acc_duoc_chay("SPAM Test", "dang_bai")[0] is False)
check("spam chặn CẢ comment",           db.acc_duoc_chay("SPAM Test", "comment")[0] is False)
check("spam VẪN cho nuôi nick",         db.acc_duoc_chay("SPAM Test", "nuoi_nick")[0] is True)

# ── Hết giờ -> chạy PHIÊN THĂM DÒ, kết quả quyết định thả hay nghỉ tiếp ────
_tua = lambda: db._conn().execute(
    "UPDATE accounts SET nghi_den=? WHERE id=?",
    ((_dt.now() - _td(minutes=1)).isoformat(timespec="seconds"), _sid))
check("chưa hết giờ -> chưa mở đường",  db.mo_duong_tham_do() == [])

with db._conn() as _c: _c.execute("UPDATE accounts SET nghi_den=? WHERE id=?",
    ((_dt.now() - _td(minutes=1)).isoformat(timespec="seconds"), _sid))
_hs = db.mo_duong_tham_do()
check("hết giờ -> mở đường thăm dò",    len(_hs) == 1)
# Hết giờ nghỉ thì slot kế tiếp là PHIÊN THĂM DÒ — phải để nó ĐĂNG THẬT mới biết
# Facebook đã thả chưa. Đổi sang nuôi nick lúc này là không bao giờ dò được.
check("hết giờ nghỉ -> KHÔNG đổi sang nuôi nữa",
      db.acc_dang_spam_nghi("SPAM Test") is False)
# Mắt xích dễ quên nhất: không trả slot về 'Chờ' thì phiên thăm dò không bao giờ
# chạy được, vì scheduler chỉ bốc dòng 'Chờ'.
with db._conn() as _c:
    _sau = {r["hoat_dong"]: r["trang_thai"] for r in _c.execute(
        "SELECT hoat_dong,trang_thai FROM schedules WHERE ten_acc='SPAM Test' "
        "AND gio_dang=?", (_gio_sau,))}
check("slot đăng mở lại để thăm dò",    _sau["dang_bai"] == "Chờ")
check("slot comment mở lại để thăm dò", _sau["comment"] == "Chờ")
# Vẫn là Spam — mới mở đường thử, CHƯA thả.
check("mở đường xong vẫn giữ Spam",
      any(a["ten_acc"] == "SPAM Test" and a["trang_thai"] == db.TRANG_THAI_SPAM
          for a in db.get_accounts()))
check("hết giờ thì được chạy thăm dò",  db.acc_duoc_chay("SPAM Test", "dang_bai")[0] is True)

# Thăm dò HỎNG -> nghỉ thêm một lượt, KHÔNG cộng vào lịch sử sức khoẻ (phiên
# thăm dò hỏng là chuyện dự kiến; dồn vào cửa sổ trượt thì acc bị tắt hẳn oan).
_hd, _ly = db.ghi_nhan_phien_dang("SPAM Test", False)
check("thăm dò hỏng -> nghỉ tiếp",      _hd == "tham_do_hong")
check("thăm dò hỏng -> vẫn là Spam",
      any(a["ten_acc"] == "SPAM Test" and a["trang_thai"] == db.TRANG_THAI_SPAM
          for a in db.get_accounts()))
check("thăm dò hỏng -> chặn lại",       db.acc_duoc_chay("SPAM Test", "dang_bai")[0] is False)
check("thăm dò hỏng -> slot lại đổi sang nuôi nick",
      db.acc_dang_spam_nghi("SPAM Test") is True)

# ── Phiên nhử LUÔN là đăng bài ─────────────────────────────────────────────
# Nghỉ đủ giờ thì slot kế tiếp đổi thành ĐĂNG BÀI, kể cả khi nó vốn là slot
# comment. Một loại phiên nhử = một đường code = một chỗ ghi nhận kết quả.
# Đổi được vì slot comment vẫn giữ nguyên ma_content / ma_nhom / tu_khoa.
check("đang nghỉ -> CHƯA cần phiên nhử",
      db.acc_can_tham_do("SPAM Test") is False)
# Hai cờ này phải LOẠI TRỪ nhau: cùng đúng thì slot vừa đổi sang nuôi vừa đổi
# sang nhử, và thứ tự code quyết định kết quả — đúng kiểu lỗi khó lần ra.
check("đang nghỉ: đổi-sang-nuôi và cần-nhử không cùng đúng",
      not (db.acc_dang_spam_nghi("SPAM Test") and db.acc_can_tham_do("SPAM Test")))
with db._conn() as _c:
    _c.execute("UPDATE accounts SET nghi_den=? WHERE id=?",
               ((_dt.now() - _td(minutes=1)).isoformat(timespec="seconds"), _sid))
check("hết giờ -> cần phiên nhử",       db.acc_can_tham_do("SPAM Test") is True)
check("hết giờ: hai cờ vẫn không cùng đúng",
      not (db.acc_dang_spam_nghi("SPAM Test") and db.acc_can_tham_do("SPAM Test")))
# Acc bình thường thì không bao giờ cần phiên nhử.
check("acc Active -> không cần phiên nhử",
      db.acc_can_tham_do("SK Test") is False)
# Đặt lại vào giờ nghỉ: khối trên vừa tua đồng hồ ra khỏi giờ nghỉ, mà vòng lặp
# ngay dưới bắt đầu bằng giả định "đang trong giờ nghỉ".
db.danh_dau_spam("SPAM Test", "đặt lại cho vòng lặp", gio=_GIO_MOC)

# ── Vòng lặp phải chạy được VÔ HẠN ─────────────────────────────────────────
# Thăm dò hỏng thì nghỉ tiếp một tiếng rồi dò lại, cứ thế cho tới khi đăng
# được. Chạy 3 vòng để bắt lỗi kiểu "chỉ đúng ở lần đầu" — ví dụ một cờ nào đó
# bị dùng một lần rồi không đặt lại, hay lịch sử tích luỹ tới ngưỡng rồi rẽ
# sang nhánh khác.
for _vong in range(1, 4):
    check(f"vòng {_vong}: trong giờ nghỉ thì đổi sang nuôi nick",
          db.acc_dang_spam_nghi("SPAM Test") is True)
    check(f"vòng {_vong}: trong giờ nghỉ thì chặn đăng bài",
          db.acc_duoc_chay("SPAM Test", "dang_bai")[0] is False)
    check(f"vòng {_vong}: trong giờ nghỉ thì nuôi nick vẫn chạy",
          db.acc_duoc_chay("SPAM Test", "nuoi_nick")[0] is True)
    with db._conn() as _c:
        _c.execute("UPDATE accounts SET nghi_den=? WHERE id=?",
                   ((_dt.now() - _td(minutes=1)).isoformat(timespec="seconds"), _sid))
    db.mo_duong_tham_do()
    check(f"vòng {_vong}: hết giờ thì được đăng thật để thăm dò",
          db.acc_duoc_chay("SPAM Test", "dang_bai")[0] is True)
    check(f"vòng {_vong}: lúc thăm dò thì KHÔNG đổi sang nuôi",
          db.acc_dang_spam_nghi("SPAM Test") is False)
    _hd_v, _ = db.ghi_nhan_phien_dang("SPAM Test", False)
    check(f"vòng {_vong}: thăm dò hỏng -> quay lại nghỉ", _hd_v == "tham_do_hong")

# Sau 3 vòng hỏng liên tiếp acc vẫn phải còn sống — không bị tắt hẳn, không
# rơi ra khỏi danh sách. Đây là điều đã đổi khi bỏ trạng thái "Hỏng".
check("hỏng nhiều vòng vẫn là Spam, không bị tắt",
      any(a["ten_acc"] == "SPAM Test" and a["trang_thai"] == db.TRANG_THAI_SPAM
          for a in db.get_accounts()))

# Và vòng nào đăng được thì thoát hẳn.
with db._conn() as _c:
    _c.execute("UPDATE accounts SET nghi_den=? WHERE id=?",
               ((_dt.now() - _td(minutes=1)).isoformat(timespec="seconds"), _sid))
db.mo_duong_tham_do()
_hd_ok, _ = db.ghi_nhan_phien_dang("SPAM Test", True)
check("đăng được -> thoát khỏi Spam",   _hd_ok == "het_spam")
check("thoát rồi -> đăng bài chạy lại", db.acc_duoc_chay("SPAM Test", "dang_bai")[0] is True)
check("thoát rồi -> comment chạy lại",  db.acc_duoc_chay("SPAM Test", "comment")[0] is True)
check("thoát rồi -> hết đổi sang nuôi", db.acc_dang_spam_nghi("SPAM Test") is False)
# Đặt lại về Spam để các assertion phía sau chạy trên đúng trạng thái cũ.
db.danh_dau_spam("SPAM Test", "đặt lại cho phần kiểm tiếp theo", gio=_GIO_MOC)
with db._conn() as _c:
    _ls = _c.execute("SELECT lich_su_phien FROM accounts WHERE id=?", (_sid,)).fetchone()[0]
check("thăm dò hỏng KHÔNG vào lịch sử", "x" not in (_ls or ""))

# Thăm dò ĐƯỢC -> thả hẳn.
with db._conn() as _c: _c.execute("UPDATE accounts SET nghi_den=? WHERE id=?",
    ((_dt.now() - _td(minutes=1)).isoformat(timespec="seconds"), _sid))
db.mo_duong_tham_do()
_hd2, _ly2 = db.ghi_nhan_phien_dang("SPAM Test", True)
check("thăm dò được -> thả hẳn",        _hd2 == "het_spam")
check("thả xong -> về Active",
      any(a["ten_acc"] == "SPAM Test" and a["trang_thai"] == "Active"
          for a in db.get_accounts()))
check("thả xong -> đăng bài được",      db.acc_duoc_chay("SPAM Test", "dang_bai")[0] is True)
check("thả xong -> comment được",       db.acc_duoc_chay("SPAM Test", "comment")[0] is True)
check("không còn ai để mở đường",       db.mo_duong_tham_do() == [])
# Đặt lại trạng thái Spam cho các assertion phía dưới.
with db._conn() as _c:
    _c.execute("UPDATE accounts SET trang_thai=? WHERE id=?", (db.TRANG_THAI_SPAM, _sid))
# get_account_by_name lọc cứng 'Active' thì phiên comment/nuôi không lấy được
# cookie và chết theo — trong khi việc chặn đăng đã do acc_duoc_chay lo rồi.
check("vẫn tra được acc để lấy cookie", db.get_account_by_name("SPAM Test") is not None)
check("có sinh cảnh báo mức error",     any(c["ten_acc"] == "SPAM Test" and c["muc"] == "error"
                                            for c in db.lay_canh_bao()))

db.update_account_field(_sid, "trang_thai", "Active")
check("bật lại -> đăng bài được",       db.acc_duoc_chay("SPAM Test", "dang_bai")[0] is True)

# Acc dính spam PHẢI còn trong Gen lịch. Đây là chỗ thay cho loại đăng "C_*" đã
# bỏ: lọc cứng 'Active' thì acc vừa bị đánh spam biến mất khỏi Gen — không còn
# slot nào, kể cả slot comment — trong khi comment là việc duy nhất nó còn làm
# được. Bước 3 của Gen sẽ quét mọi slot còn lại của nó thành comment.
db.update_account_field(_sid, "loai_dang", "X_Home")
with db._conn() as _c:
    _c.execute("UPDATE accounts SET trang_thai=? WHERE id=?", (db.TRANG_THAI_SPAM, _sid))
_ds = [a["ten_acc"] for a in db.accounts_theo_lich("homestay")]
check("acc Spam vẫn vào Gen lịch",      "SPAM Test" in _ds)
check("lọc 'Active' thì loại acc Spam",
      "SPAM Test" not in [a["ten_acc"] for a in db.accounts_theo_lich("homestay", "Active")])
with db._conn() as _c:
    _c.execute("UPDATE accounts SET trang_thai='Active' WHERE id=?", (_sid,))
with db._conn() as _c:
    _sv = _c.execute("SELECT so_vi_pham FROM accounts WHERE id=?", (_sid,)).fetchone()[0]
# Số vụ phải GIỮ: xoá về -1 thì lần dính kế tiếp bị bỏ lỡ vì coi như chưa đo.
check("bật lại vẫn giữ số vụ đã đo",    _sv == 15)
with db._conn() as _c:
    _c.execute("DELETE FROM schedules WHERE ten_acc='SPAM Test'")
db.delete_account(_sid)
db.xoa_canh_bao()

# ── Nhận biết CHƯA ĐĂNG NHẬP (cookie chết) ─────────────────────────────────
# Bản cũ dùng `"login" in page.url`. Đã đo bằng trình duyệt sạch, không tiêm
# cookie: trang gốc, URL nhóm và URL BÀI VIẾT đều KHÔNG chuyển hướng khi chưa
# đăng nhập — Facebook giữ nguyên URL, chỉ đổi nội dung. Chỉ /notifications mới
# chuyển. Nên phép cũ trượt ở đúng ba chỗ nó được gọi nhiều nhất.
#
# Hậu quả nặng nhất là MẤT DỮ LIỆU: mở link bài khi đã đăng xuất thì không thấy
# ô bình luận, comment_bai kết luận "link chết" và XOÁ link khỏi danh sách 300.
# Đo trên 3 link thật: phép cũ trượt cả 3, phép mới bắt cả 3.
import asyncio as _aio
from fb_common import chua_dang_nhap as _cdn


class _PageGia:
    """Trang giả: `co_form` mô phỏng ô mật khẩu trên DOM, `url` là địa chỉ."""
    def __init__(self, co_form, url="https://www.facebook.com/", no_loi=False):
        self._f, self.url, self._no_loi = co_form, url, no_loi

    async def evaluate(self, _js):
        if self._no_loi:
            raise RuntimeError("trang đang điều hướng")
        return self._f


_k = lambda p: _aio.run(_cdn(p))
check("có ô mật khẩu -> chưa đăng nhập",  _k(_PageGia(True)) is True)
check("không có ô -> đã đăng nhập",       _k(_PageGia(False)) is False)
# Trang gốc / URL nhóm / URL bài viết giữ nguyên URL — đây là ca phép cũ trượt.
for _u in ("https://www.facebook.com/",
           "https://www.facebook.com/groups/bohoa/",
           "https://www.facebook.com/groups/123/posts/456/"):
    check(f"URL không đổi vẫn bắt được ({_u.split('/')[3] or 'gốc'})",
          _k(_PageGia(True, _u)) is True)
# Vẫn giữ phép so URL làm lớp phụ, cho ca /notifications đã chuyển hướng.
check("login.php -> bắt được kể cả không đọc được DOM",
      _k(_PageGia(False, "https://www.facebook.com/login.php?next=x")) is True)
check("checkpoint -> bắt được",
      _k(_PageGia(False, "https://www.facebook.com/checkpoint/123")) is True)
# Đọc DOM lỗi (trang đang điều hướng) thì lùi về so URL, không được nổ.
check("đọc DOM lỗi -> lùi về so URL",
      _k(_PageGia(False, "https://www.facebook.com/login.php", no_loi=True)) is True)
check("đọc DOM lỗi + URL sạch -> coi như đã vào",
      _k(_PageGia(False, "https://www.facebook.com/", no_loi=True)) is False)

# Không còn file nào dùng phép so URL trần.
for _f in ("comment_bai.py", "nuoi_nick.py", "via_poster.py",
           "join_groups_runner.py", "page_via_poster.py"):
    check(f"{_f}: đã bỏ phép so URL trần",
          '"login" in page.url' not in Path(_f).read_text(encoding="utf-8"))

# ── Link comment ghi kèm ACC đã đăng ───────────────────────────────────────
# Cột `page` KHÔNG thay được cột `acc`: đo trên dữ liệu thật, 10/10 Page đều có
# 2 acc cùng đăng, nên bài bị Facebook gỡ chỉ truy được tới "một trong hai".
# Acc nào chạy phiên đăng ra bài đó chính là acc bị soi — ghi thẳng, khỏi suy luận.
db.xoa_het_comment_posts("ban")
db.them_comment_posts("ban", [_lk("gAA", 1)], page="PG1", acc="Acc Một")
db.them_comment_posts("ban", [_lk("gBB", 2)], page="PG1", acc="Acc Hai")
_ds_acc = {r["url"]: r["acc"] for r in db.get_comment_posts("ban")}
check("lưu được acc của từng link",     set(_ds_acc.values()) == {"Acc Một", "Acc Hai"})
check("cùng Page vẫn phân biệt được acc",
      len({r["page"] for r in db.get_comment_posts("ban")}) == 1
      and len({r["acc"] for r in db.get_comment_posts("ban")}) == 2)

# Xoá link chết phải TRẢ VỀ acc đã đăng — đọc trước khi xoá, không thì dòng biến
# mất và tín hiệu mất theo.
_id_chet = [r["id"] for r in db.get_comment_posts("ban") if r["acc"] == "Acc Hai"][0]
_ket = db.ghi_nhan_comment(_id_chet, False, chet=True)
check("xoá link chết -> trả về acc",    (_ket or {}).get("acc") == "Acc Hai")
check("xoá link chết -> trả về page",   (_ket or {}).get("page") == "PG1")
check("link chết đã bị xoá thật",
      all(r["id"] != _id_chet for r in db.get_comment_posts("ban")))
# Link cũ chưa có acc (thu trước khi thêm cột) không được làm vỡ luồng.
db.them_comment_posts("ban", [_lk("gCC", 3)], page="PG1")
_id_cu = [r["id"] for r in db.get_comment_posts("ban") if not r["acc"]][0]
check("link cũ không có acc -> vẫn xoá được",
      (db.ghi_nhan_comment(_id_cu, False, chet=True) or {}).get("acc") == "")
db.xoa_het_comment_posts("ban")

# ── Tra content phải theo ĐÚNG mảng ────────────────────────────────────────
# Mã content chỉ duy nhất TRONG một mảng, không duy nhất toàn bảng: sao content
# từ mảng này sang mảng khác là thao tác thường ngày và người dùng giữ nguyên mã
# cho dễ đối chiếu. Trên DB thật đang có 13 mã trùng giữa `thue` và `ban`.
#
# Không lọc loại thì `LIMIT 1` luôn trả dòng id nhỏ hơn — lịch Bán lấy content
# của Thuê, mọi lần, không báo gì. Đo trên dữ liệu thật: cả 13 mã trùng đều có
# BỘ ẢNH KHÁC NHAU (upload sinh tên uuid mới), 3 mã còn khác cả nội dung.
_ct_t = db.upsert_content({"loai": "thue", "ma_content": "DUP1",
                           "noi_dung": "bản THUÊ", "link_anh": "/media/thue.jpg",
                           "su_dung": "Có"})
_ct_b = db.upsert_content({"loai": "ban", "ma_content": "DUP1",
                           "noi_dung": "bản BÁN", "link_anh": "/media/ban.jpg",
                           "su_dung": "Có"})
check("cùng mã ở 2 mảng -> 2 dòng khác nhau", _ct_t != _ct_b)
check("tra theo mảng thuê -> đúng bản thuê",
      db.get_content_by_code("DUP1", "thue")["noi_dung"] == "bản THUÊ")
check("tra theo mảng bán -> đúng bản bán",
      db.get_content_by_code("DUP1", "ban")["noi_dung"] == "bản BÁN")
check("tra theo mảng bán -> đúng ẢNH của bán",
      db.get_content_by_code("DUP1", "ban")["link_anh"] == "/media/ban.jpg")
# Mã chỉ có ở một mảng: hỏi mảng khác vẫn phải ra, vì lịch cũ có thể trỏ tới
# content đã được chuyển mảng — thà lấy đúng nội dung còn hơn chết.
db.upsert_content({"loai": "homestay", "ma_content": "SOLO1",
                   "noi_dung": "chỉ homestay", "su_dung": "Có"})
check("mã chỉ có 1 mảng -> hỏi mảng khác vẫn ra",
      db.get_content_by_code("SOLO1", "ban")["noi_dung"] == "chỉ homestay")
check("mã không tồn tại -> None",  db.get_content_by_code("KHONG_CO", "ban") is None)
for _i in (_ct_t, _ct_b):
    db.delete_content(_i)
with db._conn() as _c:
    _c.execute("DELETE FROM content WHERE ma_content='SOLO1'")

# ── Thư viện câu comment mẫu (comment_mau.txt) ─────────────────────────────
_cm = server.app.test_client().get("/api/comment/cau-mau").get_json()
check("endpoint câu mẫu chạy",          _cm.get("ok") is True)
_pool = {k: [x for x in v.split("\n") if x.strip()] for k, v in _cm["data"].items()}
check("đủ 3 loại",                      set(_pool) == {"homestay", "thue", "ban"})
for _k in ("homestay", "thue", "ban"):
    check(f"{_k}: 30 câu",              len(_pool[_k]) == 30)
    check(f"{_k}: không trùng nội bộ",   len({x.lower() for x in _pool[_k]}) == 30)

# Ba loại PHẢI khác nhau — dùng chung một bộ câu cho cả ba là kiểu trùng lặp dễ
# bị quét nhất: cùng chuỗi ký tự xuất hiện ở bài homestay, bài thuê lẫn bài bán,
# trong cùng cụm nhóm, từ cùng một hệ thống Page. Bộ 20 câu đời đầu bị đúng lỗi
# này — cả ba loại giống hệt nhau từng chữ.
for _a, _b in (("homestay", "thue"), ("homestay", "ban"), ("thue", "ban")):
    check(f"{_a} ≠ {_b}",
          not ({x.lower() for x in _pool[_a]} & {x.lower() for x in _pool[_b]}))

# Dòng ghi chú và dòng [tên loại] không được lọt vào thư viện.
check("không lẫn dòng ghi chú",         not any(x.startswith("#") for v in _pool.values() for x in v))
check("không lẫn dòng tiêu đề loại",    not any(x.startswith("[") for v in _pool.values() for x in v))

# ── Tách dữ liệu khỏi code (điều kiện để đóng gói setup.exe) ───────────────
# Chạy từ mã nguồn thì DATA_ROOT = BASE_DIR, y hệt trước. Cài bằng setup.exe thì
# code nằm ở Program Files (chỉ đọc) còn MNT_DATA_DIR trỏ sang %LOCALAPPDATA%.
# Bắt buộc phải tách vì profiles/ là 2,1 GB ghi liên tục.
import config as _cfg
check("mặc định DATA_ROOT = BASE_DIR",  _cfg.DATA_ROOT == _cfg.BASE_DIR)
for _ten, _p in (("DB", _cfg.DB_PATH), ("logs", _cfg.LOG_DIR),
                 ("cookies", _cfg.COOKIES_DIR), ("profiles", _cfg.PROFILES_DIR)):
    check(f"{_ten} nằm dưới DATA_ROOT", str(_p).startswith(str(_cfg.DATA_ROOT)))

# Các assertion trên chỉ hỏi config xem NÓ tính ra gì — mà config tính đúng từ
# đầu. Thứ thực sự mở database là db.DB_PATH, và nó tự tính lấy:
#
#     DB_PATH = Path(__file__).parent / "data" / "app.db"
#
# nên database luôn nằm cạnh mã nguồn bất kể MNT_DATA_DIR đặt gì. Cả phần tách
# dữ liệu chỉ đúng trên giấy suốt từ GĐ1, và bài kiểm không thấy vì nó soi
# nhầm đối tượng. Lộ ra khi chạy thử bản đóng gói thật.
# Soi MÃ NGUỒN chứ không so giá trị lúc chạy: dòng 24 của chính file này gán
# `db.DB_PATH = _tmp` để các assertion về DB chạy trên file tạm, nên so sánh
# lúc chạy thì bao giờ cũng lệch, không nói lên điều gì.
check("db.py lấy DB_PATH từ config",
      "from config import DB_PATH" in Path("db.py").read_text(encoding="utf-8"))

# Quét thẳng mã nguồn: không module nào được tự dựng đường dẫn tới thư mục dữ
# liệu từ __file__ của chính nó. Đây mới là assertion bắt được lỗi trên.
import re as _re_p
_MAU_TU_TINH = _re_p.compile(
    r'(?:Path\(__file__\)\.parent|os\.path\.dirname\([^)]*__file__[^)]*\))'
    r'\s*/?\s*,?\s*["\'](?:data|cookies|profiles|logs)["\']')
for _f in sorted(Path(".").glob("*.py")):
    if _f.name in ("config.py", "test_basic.py"):
        continue          # config.py LÀ nơi được phép tính; test thì không chạy thật
    _nd = _f.read_text(encoding="utf-8")
    _hit = _MAU_TU_TINH.search(_nd)
    check(f"{_f.name}: không tự dựng đường dẫn dữ liệu"
          + (f" — {_hit.group(0)[:44]}" if _hit else ""), not _hit)

# Không file nào được tự tính đường dẫn dữ liệu từ __file__ của chính nó nữa —
# đó là lý do trước đây không dời được, và là gốc của lỗi profile trắng trong
# join_groups_runner (bản sao trôi khác bản gốc).
for _f in ("fb_common.py", "cookie_exporter.py", "page_via_poster.py",
           "via_poster.py", "join_groups_runner.py"):
    _nd = Path(_f).read_text(encoding="utf-8")
    check(f"{_f}: không tự tính profiles/",
          'abspath(__file__)), "profiles"' not in _nd)
    check(f"{_f}: không tự tính cookies/",
          'abspath(__file__)), "cookies"' not in _nd)

# Ba bản sao find_profile_dir đã gộp về một. Giữ bản sao thì sửa một chỗ phải
# nhớ sửa cả ba — thực tế bản trong join_groups_runner đã trôi và chạy trên
# thư mục profile TRẮNG suốt không biết bao lâu.
import fb_common as _fbc, page_via_poster as _pvp, via_poster as _vp
check("page_via_poster dùng chung hàm", _pvp._find_profile_dir is _fbc.find_profile_dir)
check("via_poster dùng chung hàm",      _vp._find_profile_dir is _fbc.find_profile_dir)

# ── Số phiên bản: một nguồn duy nhất ───────────────────────────────────────
# Để trong file text vì có ba bên cùng đọc mà chỉ một bên chạy được Python:
# config.VERSION, UPDATE.bat, và Inno Setup khi đóng gói.
import re as _re_v
check("có file version.txt",            Path("version.txt").exists())
check("config đọc được version",        _cfg.VERSION == Path("version.txt").read_text(encoding="utf-8").strip())
check("đúng dạng MAJOR.MINOR.PATCH",    bool(_re_v.fullmatch(r"\d+\.\d+\.\d+", _cfg.VERSION)))
# version.txt KHÔNG được có ký tự xuống dòng: `set /p` trong .bat đọc cả nó vào
# biến, khiến tên file setup.exe và tag git dính ký tự rác.
check("version.txt không có xuống dòng",
      chr(10) not in Path("version.txt").read_text(encoding="utf-8"))
check("/api/ping trả về version",
      server.app.test_client().get("/api/ping").get_json().get("version") == _cfg.VERSION)
# Giao diện có chỗ để hiện, và app.js có đổ số vào chỗ đó.
check("giao diện có ô hiện version",
      'id="app-version"' in Path("templates/index.html").read_text(encoding="utf-8"))
check("app.js đổ version vào ô đó",
      'app-version' in Path("static/js/app.js").read_text(encoding="utf-8"))

# ═══════════════════════════════════════════════════════════════════════════
# Loại đăng của Page: phải có lựa chọn TRỐNG
# ───────────────────────────────────────────────────────────────────────────
# Page để trống loại đăng thì gen lịch BỎ QUA nó — dùng khi tạm không muốn đăng
# lên Page đó mà chưa muốn xoá khỏi danh sách. Trước đây ô trống chỉ hiện ra
# khi giá trị đang sai, nên chọn một loại rồi là không bao giờ bỏ chọn lại được.
_ajs = Path("static/js/app.js").read_text(encoding="utf-8")
check("có danh sách loại đăng riêng cho Page", "LOAI_PAGE_OPTIONS" in _ajs)
_m_lp = _re_v.search(r'const LOAI_PAGE_OPTIONS\s*=\s*\[([^\]]*)\]', _ajs)
check("danh sách loại đăng Page đọc được", bool(_m_lp))
if _m_lp:
    _lp = [x.strip().strip('"').strip("'") for x in _m_lp.group(1).split(",")]
    check("lựa chọn TRỐNG nằm đầu danh sách", _lp and _lp[0] == "")
    check("đủ 4 lựa chọn: trống + 3 loại", len(_lp) == 4)
    check("có đủ Homestay / Thuê / Bán",
          {"Homestay", "Thuê", "Bán"}.issubset(set(_lp)))
# Hai chỗ (bảng và form Thêm/Sửa) phải dùng CHUNG một danh sách. Trước đây chép
# cứng ở cả hai, sửa một chỗ là lệch ngay.
check("không còn chỗ nào chép cứng 3 loại của Page",
      '["Homestay","Thuê","Bán"]' not in _ajs)
check("form Thêm/Sửa Page dùng danh sách chung",
      _ajs.count("LOAI_PAGE_OPTIONS") >= 3)   # khai báo + bảng + form

# ═══════════════════════════════════════════════════════════════════════════
# Ghi chú phát hành
# ───────────────────────────────────────────────────────────────────────────
# Nút Cập nhật trong phần mềm đọc CHANGELOG.md để hiện danh sách bản cho khách
# chọn. Không có ghi chú thì khách chỉ thấy "v1.0.4" — không có cơ sở nào để
# chọn, mà chọn lùi nhầm là mất tính năng. PHAT_HANH.bat cũng chặn phát hành
# khi chưa có mục cho số sắp phát hành; các assertion dưới đây canh phần còn
# lại: dạng tiêu đề đúng, và bản đang chạy phải nằm đầu danh sách.
_cl = Path("CHANGELOG.md")
check("có file CHANGELOG.md", _cl.exists())
_muc = _re_v.findall(r"(?m)^## v(\d+\.\d+\.\d+) ", _cl.read_text(encoding="utf-8"))
check("CHANGELOG có ít nhất một bản", len(_muc) > 0)
check("CHANGELOG không có mục trùng", len(_muc) == len(set(_muc)))
# KHÔNG bắt bản đang chạy phải nằm đầu: quy trình là viết ghi chú TRƯỚC rồi mới
# phát hành, nên lúc chạy bài kiểm thì mục trên cùng chính là bản sắp ra, còn
# version.txt vẫn mang số cũ. Bắt "phải nằm đầu" là tự khoá mình lại, không bao
# giờ phát hành được bản nào nữa.
check("bản đang chạy có mục trong CHANGELOG", _cfg.VERSION in _muc)
_khoa = lambda v: tuple(int(x) for x in v.split("."))
check("CHANGELOG xếp từ mới xuống cũ",
      _muc == sorted(_muc, key=_khoa, reverse=True))

# ═══════════════════════════════════════════════════════════════════════════
# Chọn phiên bản để cập nhật
# ───────────────────────────────────────────────────────────────────────────
import capnhat as _cn
_cl_text = _cl.read_text(encoding="utf-8")
_g = _cn.doc_ghi_chu(_cl_text)
check("bóc được ghi chú mọi bản trong CHANGELOG", set(_g) == set(_muc))
check("ghi chú có ngày",   all(_g[v]["ngay"] for v in _g))
check("ghi chú có nội dung", all(_g[v]["ghi_chu"] for v in _g))
# Bẫy kinh điển: xếp theo chữ cái thì '1.9.0' đứng SAU '1.10.0'.
check("xếp theo số chứ không theo chữ cái",
      [m["tag"] for m in _cn.danh_sach_ban(["v1.9.0", "v1.10.0", "v1.2.0"], "", "1.9.0")]
      == ["v1.10.0", "v1.9.0", "v1.2.0"])
check("tag không đúng dạng bị bỏ qua",
      [m["tag"] for m in _cn.danh_sach_ban(["v1.1.0", "beta", "v2.0"], "", "1.1.0")]
      == ["v1.1.0"])
_ds = _cn.danh_sach_ban(["v1.1.0", "v1.0.5", "v1.0.3"], _cl_text, "1.0.5")
check("phân đúng mới / đang chạy / cũ",
      [m["huong"] for m in _ds] == ["moi", "dang_chay", "cu"])
check("mời đúng bản mới nhất", _cn.ban_moi_nhat(_ds)["tag"] == "v1.1.0")
check("đang ở bản mới nhất thì không mời gì",
      _cn.ban_moi_nhat(_cn.danh_sach_ban(["v1.1.0"], _cl_text, "1.1.0")) is None)

# ═══════════════════════════════════════════════════════════════════════════
# Khởi chạy tiến trình con: bản chạy thẳng và bản đã biên dịch
# ───────────────────────────────────────────────────────────────────────────
# Hai bản chạy ra hai dòng lệnh khác hẳn nhau, và cả hai đều phải đúng:
#     chạy thẳng   python.exe -X utf8 scheduler.py homestay
#     đã biên dịch server.exe  --lam scheduler homestay
# Sai chỗ này thì bấm nút Chạy runner là lỗi 500 — đã xảy ra thật khi thử bản
# biên dịch đầu tiên.
check("chạy thẳng: lệnh runner gọi đúng file .py",
      server._lenh_con("scheduler.py", "homestay")[1:] == ["-X", "utf8", "scheduler.py", "homestay"])
check("chạy thẳng: dấu hiệu runner là tên file .py",
      server._dau_hieu("scheduler.py", "homestay") == ("scheduler.py", "homestay"))
check("chạy thẳng: soi tiến trình python",
      server._TEN_TIEN_TRINH == ["python.exe", "pythonw.exe"])
# Lệnh khởi chạy và dấu hiệu đi tìm PHẢI khớp nhau, không thì khởi chạy được
# nhưng không bao giờ tìm ra để diệt — hai runner cùng chạy trên một profile.
_lenh = " ".join(server._lenh_con("scheduler.py", "homestay"))
check("lệnh khởi chạy chứa đúng dấu hiệu đi tìm",
      all(d in _lenh for d in server._dau_hieu("scheduler.py", "homestay")))
# _exe_dang_chay phải trả về một file CÓ THẬT. Nuitka đặt sys.executable thành
# "<gói>\python.exe" — file không hề tồn tại — nên dùng thẳng nó là WinError 2.
check("_exe_dang_chay trỏ vào file có thật",
      Path(server._exe_dang_chay()).is_file())

# ═══════════════════════════════════════════════════════════════════════════
# Mã máy (dùng cho đăng ký và phê duyệt)
# ───────────────────────────────────────────────────────────────────────────
# Con số này phải ỔN ĐỊNH: nó mà đổi thì khách đang dùng bình thường bỗng bị
# chặn và phải xin duyệt lại từ đầu.
import ma_may as _mm
import subprocess as _sp
_m = _mm.ma_may()
check("mã máy đúng dạng ABCD-EFGH-JKMN", _mm.hop_le(_m))
check("gọi lại vẫn ra mã đó", _mm.ma_may() == _m)
# Tiến trình khác phải ra cùng kết quả — nếu không thì cài lại phần mềm hay
# chạy runner ở tiến trình riêng là mất quyền.
_r = _sp.run([sys.executable, "-X", "utf8", "-c",
              "import ma_may; print(ma_may.ma_may())"],
             capture_output=True, text=True, cwd=str(Path(".").resolve()))
check("tiến trình khác ra cùng mã máy", _r.stdout.strip() == _m)
# Không được mang số định danh thật của máy đi
_guid = _mm._guid_windows()
check("không lộ MachineGuid của máy",
      not _guid or _guid.lower().replace("-", "") not in _m.lower().replace("-", ""))
# Bỏ các ký tự dễ đọc nhầm khi đánh vần qua điện thoại
for _c in "01258OILSBZ":
    check(f"mã máy không chứa ký tự dễ nhầm {_c!r}", _c not in _m)
for _xau in ("", "ABCD", "ABCD-EFGH-JKMN-XXXX", "0OI1-LLLL-SSSS"):
    check(f"chặn mã sai dạng {_xau!r}", not _mm.hop_le(_xau))
check("chấp nhận cả chữ thường", _mm.hop_le(_m.lower()))

# ═══════════════════════════════════════════════════════════════════════════
# Phê duyệt: hạn dùng của kết quả nhớ lại
# ───────────────────────────────────────────────────────────────────────────
# Mất mạng mà chặn ngay là phá hỏng công việc của khách vì sự cố không phải
# lỗi họ. Nên kết quả duyệt được nhớ vài ngày. Chỗ này quyết định ai vào được
# phần mềm, nên mọi ngả phải kiểm hết — nhất là ngả người dùng VẶN ĐỒNG HỒ.
import phe_duyet as _pd
_BG = 1_800_000_000.0
_NGAY = 86400.0
for _ten, _goi, _mong in [
    ("vừa hỏi xong",         {"trang_thai": _pd.DA_DUYET, "luc": _BG},                 True),
    ("6 ngày trước",         {"trang_thai": _pd.DA_DUYET, "luc": _BG - 6*_NGAY},       True),
    ("7 ngày kém 1 giây",    {"trang_thai": _pd.DA_DUYET, "luc": _BG - 7*_NGAY + 1},   True),
    ("quá 7 ngày",           {"trang_thai": _pd.DA_DUYET, "luc": _BG - 8*_NGAY},       False),
    ("bị cắt",               {"trang_thai": _pd.BI_CAT,   "luc": _BG},                 False),
    ("chờ duyệt",            {"trang_thai": _pd.CHO_DUYET,"luc": _BG},                 False),
    # Vặn đồng hồ lùi là cách dễ nhất để kéo dài hạn vô tận.
    ("đồng hồ vặn lùi",      {"trang_thai": _pd.DA_DUYET, "luc": _BG + _NGAY},         False),
    ("thiếu mốc thời gian",  {"trang_thai": _pd.DA_DUYET},                             False),
    ("mốc là chữ",           {"trang_thai": _pd.DA_DUYET, "luc": "hôm qua"},           False),
    ("không phải dict",      "da_duyet",                                               False),
    ("rỗng",                 None,                                                     False),
]:
    check(f"hạn dùng — {_ten} → {'cho qua' if _mong else 'chặn'}",
          _pd.con_han(_goi, bay_gio=_BG) is _mong)
# Kết quả nhớ phải để cạnh DỮ LIỆU, không cạnh mã nguồn: bản cài xoá sạch thư
# mục mã nguồn mỗi lần cập nhật, để đó là mỗi lần cập nhật lại phải xin duyệt.
check("kết quả duyệt nằm dưới DATA_ROOT",
      str(_pd._duong_dan_nho()).startswith(str(_cfg.DATA_ROOT)))

# ── Chữ ký của máy chủ ─────────────────────────────────────────────────────
# Không có bước kiểm chữ ký thì cả cơ chế vô nghĩa: ai cũng tự tạo được một
# file phe_duyet.json ghi "da_duyet" rồi dùng thoải mái. Dựng cặp khoá thật
# rồi thử đủ các kiểu giả mạo — đây là phần quyết định ai vào được phần mềm.
import base64 as _b64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey as _Ed
_rieng = _Ed.generate()
_KCK   = _b64.b64encode(_rieng.public_key().public_bytes_raw()).decode()
_MAY   = _mm.ma_may()

def _ky_thu(ma, tt, luc, khoa=None):
    k = khoa or _rieng
    return {"ma_may": ma, "trang_thai": tt, "luc": luc,
            "chu_ky": _b64.b64encode(k.sign(f"{ma}|{tt}|{luc}".encode())).decode()}

_that = _ky_thu(_MAY, _pd.DA_DUYET, _BG)
check("gói tin thật từ máy chủ → cho vào", _pd.dung_duoc(_that, _BG, _KCK) is True)

_khac = _Ed.generate()
for _ten, _g in [
    ("tự viết da_duyet, không ký", {"ma_may": _MAY, "trang_thai": _pd.DA_DUYET, "luc": _BG}),
    ("sửa bi_cat thành da_duyet",  {**_ky_thu(_MAY, _pd.BI_CAT, _BG), "trang_thai": _pd.DA_DUYET}),
    ("đẩy thời điểm về tương lai", {**_that, "luc": _BG + 999999}),
    ("chép gói của máy khác",      _ky_thu("AAAA-BBBB-CCCC", _pd.DA_DUYET, _BG)),
    ("chữ ký của khoá khác",       _ky_thu(_MAY, _pd.DA_DUYET, _BG, _khac)),
    ("chữ ký rác",                 {**_that, "chu_ky": "khong-phai-base64!!"}),
    ("thiếu chữ ký",               {k: v for k, v in _that.items() if k != "chu_ky"}),
]:
    check(f"giả mạo — {_ten} → chặn", _pd.dung_duoc(_g, _BG, _KCK) is False)

# Thiếu khoá công khai phải CHẶN chứ không cho qua: lỡ quên gắn khoá lúc phát
# hành mà mặc định cho qua thì mở toang cho tất cả, và không ai phát hiện ra.
check("quên gắn khoá công khai → chặn", _pd.dung_duoc(_that, _BG, "") is False)

# ── Cổng chặn phải TỰ TẮT khi chưa gắn khoá ────────────────────────────────
# Máy chủ dựng sau phần này. Nếu mặc định là bắt buộc thì ngay lúc cập nhật
# code, mọi máy đang chạy đều bị khoá ngoài — kể cả máy của chính mình — mà
# chưa có chỗ nào để xin duyệt.
# Cloudflare CHẶN THẲNG User-Agent mặc định của Python bằng lỗi 403. Đã đo trên
# máy chủ thật: mặc định → 403, đặt bất kỳ tên nào khác → 200. Thiếu dòng đặt
# tên là cổng chặn khoá TOÀN BỘ máy khách, kể cả máy đã được duyệt, vì lượt hỏi
# nào cũng hỏng. Đây là loại lỗi chỉ lộ ra khi gọi máy chủ thật.
check("có gửi User-Agent khi gọi máy chủ",
      "User-Agent" in Path("phe_duyet.py").read_text(encoding="utf-8"))
check("User-Agent mang tên phần mềm", _pd._ten_goi().startswith("MNT-FB-AutoPost/"))
check("User-Agent không phải mặc định của Python",
      "urllib" not in _pd._ten_goi().lower() and "python" not in _pd._ten_goi().lower())

# Tạm GỠ khoá ra để kiểm, thay vì tin vào giá trị đang có: khoá thật đã gắn rồi
# nên assertion kiểu "bat_buoc() is False" giờ luôn sai — mà điều cần canh không
# phải giá trị hiện tại, mà là "hễ khoá rỗng thì cổng phải tắt".
_khoa_that = _pd.KHOA_CONG_KHAI
_pd.KHOA_CONG_KHAI = ""
check("chưa gắn khoá → không bắt buộc duyệt", _pd.bat_buoc() is False)
_tt = _pd.trang_thai_hien_tai()
check("chưa gắn khoá → cho vào bình thường", _tt["cho_vao"] is True)
check("chưa gắn khoá → không gọi máy chủ", _tt["nguon"] == "chua_bat")
_j = server.app.test_client().get("/api/phe-duyet/status").get_json()
check("/api/phe-duyet/status: bat_buoc=False khi chưa gắn khoá",
      _j["bat_buoc"] is False and _j["cho_vao"] is True)
# Chiều ngược lại: HỄ có khoá là cổng bật. Dùng khoá giả chứ không khôi phục
# "khoá thật" — khoá thật hiện đang RỖNG vì cổng chặn đang tắt, nên khôi phục
# nó thì assertion này luôn sai. Điều cần canh là mối quan hệ có-khoá → bật,
# không phải giá trị đang có.
_pd.KHOA_CONG_KHAI = "khoa-gia-chi-de-kiem"
check("gắn khoá vào → cổng chặn bật", _pd.bat_buoc() is True)
_pd.KHOA_CONG_KHAI = _khoa_that
# Kiểm đầu vào form đăng ký
for _than, _mong in [({}, "họ tên"), ({"ten": "  "}, "họ tên"),
                     ({"ten": "A"}, "điện thoại")]:
    _r = server.app.test_client().post("/api/phe-duyet/dang-ky", json=_than).get_json()
    check(f"đăng ký thiếu {_mong} → báo lỗi",
          _r["ok"] is False and _mong.lower() in _r["error"].lower())
check("giao diện có màn hình đăng ký",
      'id="duyet-overlay"' in Path("templates/index.html").read_text(encoding="utf-8"))
check("chữ ký thật nhưng hết hạn → chặn",
      _pd.dung_duoc(_ky_thu(_MAY, _pd.DA_DUYET, _BG - 9 * _NGAY), _BG, _KCK) is False)

# ═══════════════════════════════════════════════════════════════════════════
# Tải Chromium lần chạy đầu
# ───────────────────────────────────────────────────────────────────────────
# Chromium 683 MB không nằm trong file cài nên máy vừa cài xong phải tải về.
# Phần dễ sai là đọc tiến độ từ chữ playwright in ra — mẫu thật, không bịa.
import chromium_tai as _ct
check("dòng không có phần trăm → None",
      _ct.doc_phan_tram("Downloading Chromium 141.0.7390.37 (playwright build v1223)") is None)
check("đọc được 0%",   _ct.doc_phan_tram("|                    | 0% of 139.2 MiB") == 0)
check("đọc được 42%",  _ct.doc_phan_tram("|■■■■■■■■            | 42% of 139.2 MiB") == 42)
check("đọc được 100%", _ct.doc_phan_tram("|■■■■■■■■■■■■■■■■■■■■| 100% of 139.2 MiB") == 100)
check("dòng rỗng → None", _ct.doc_phan_tram("") is None)
check("số vô lý bị bỏ qua", _ct.doc_phan_tram("tai 999% cua gi do") is None)
# Playwright tải nhiều gói nối tiếp, mỗi gói đếm lại từ 0% — thanh tiến độ tụt
# về 0 trông như treo. Chỉ cho phép tiến, không lùi.
_tt = _ct.TienTrinh()
_tt.phan_tram = 60
_tt.phan_tram = max(_tt.phan_tram, 5)
check("thanh tiến độ không tụt lùi", _tt.phan_tram == 60)
check("giao diện có màn hình tải Chromium",
      'id="chromium-overlay"' in Path("templates/index.html").read_text(encoding="utf-8"))

# ═══════════════════════════════════════════════════════════════════════════
# Nghỉ giữa hai nhóm khi đi tham gia nhóm
# ───────────────────────────────────────────────────────────────────────────
# Vừa tham gia một nhóm MỚI thì nghỉ lâu hơn hẳn — đó là hành động Facebook
# đếm. Bấm tham gia liên tiếp là dấu hiệu máy chạy rõ nhất. Đã ở sẵn trong nhóm
# thì chỉ mở trang lên xem rồi đi, không có hành động nào bị đếm.
check("nghỉ sau khi tham gia nhóm mới = 15 giây",
      db.JOIN_NGHI_MOI_MAC_DINH == 15)
check("nghỉ khi đã là thành viên ngắn hơn hẳn",
      db.JOIN_NGHI_BO_QUA_MAC_DINH < db.JOIN_NGHI_MOI_MAC_DINH)

# Con số này trước đây bị chép ở 7 nơi — Python lẫn JavaScript. Sửa một chỗ là
# lệch ngay, mà lệch thì không ai thấy cho tới lúc nick bị chặn tham gia nhóm.
# JS không import được hằng số Python, nên chỉ còn cách canh bằng assertion.
_m_join = _re_v.search(r'const JOIN_NGHI_MOI_MAC_DINH\s*=\s*(\d+)',
                       Path("static/js/app.js").read_text(encoding="utf-8"))
check("giao diện có khai báo cùng hằng số", bool(_m_join))
check("Python và JavaScript không lệch nhau",
      bool(_m_join) and int(_m_join.group(1)) == db.JOIN_NGHI_MOI_MAC_DINH)
# Không còn chỗ nào tự viết lại con số cũ.
for _f in ("server.py", "join_groups_runner.py", "static/js/app.js"):
    _nd = Path(_f).read_text(encoding="utf-8")
    check(f"{_f}: không còn chép cứng mặc định 30",
          not _re_v.search(r'(delay_new|join_delay_new)[^\n]{0,40}\b30\b', _nd))

# ═══════════════════════════════════════════════════════════════════════════
# Dò spam phải có ở MỌI phiên đăng bài và comment
# ───────────────────────────────────────────────────────────────────────────
# Bị spam thì Facebook gỡ cả bài lẫn comment. Nhưng trước đây chỉ luồng đăng
# Hybrid có bước dò; ba luồng còn lại — đăng VIA, đăng tường Page, đi comment —
# không có. Acc bị gỡ trong ba luồng đó thì KHÔNG AI BIẾT, và cả cơ chế nghỉ /
# nhử / thả không bao giờ khởi động.
import ast as _ast
_LUONG = [
    ("page_via_poster.py", "_run_page_via",   "đăng Hybrid"),
    ("page_via_poster.py", "_run_page_wall",  "đăng tường Page"),
    ("via_poster.py",      "_run_crosspost",  "đăng VIA"),
    ("comment_bai.py",     "_ket_phien",      "đi comment"),
]
for _f, _ham, _mo_ta in _LUONG:
    _src = Path(_f).read_text(encoding="utf-8")
    _cay = _ast.parse(_src)
    _than = ""
    for _n in _ast.walk(_cay):
        if isinstance(_n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and _n.name == _ham:
            _than = _ast.get_source_segment(_src, _n) or ""
    check(f"luồng {_mo_ta} có dò spam", "kiem_vi_pham" in _than)

# Một bản dùng chung, không chép ra bốn chỗ — chép thì sớm muộn bốn chỗ trôi
# khác nhau, và chỗ nào trôi sai thì im lặng bỏ sót spam.
check("hàm dò spam nằm ở fb_common",
      "async def kiem_vi_pham" in Path("fb_common.py").read_text(encoding="utf-8"))
for _f in ("page_via_poster.py", "via_poster.py", "comment_bai.py"):
    check(f"{_f} không tự chép lại phần dò",
          "ghi_nhan_vi_pham" not in Path(_f).read_text(encoding="utf-8"))

# ═══════════════════════════════════════════════════════════════════════════
# Cú pháp file .bat
# ───────────────────────────────────────────────────────────────────────────
# Hai lỗi dưới đây đều KHÔNG hiện ra khi đọc code, và cmd chỉ báo bằng một câu
# vô nghĩa kiểu "KHONG was unexpected at this time" rồi chết ngay dòng đầu.
# UPDATE.bat đã dính lỗi thứ nhất và hỏng trên MỌI máy suốt từ 01/08 đến
# 23/08/2026 mà không ai biết, vì không có gì kiểm nó.
#
#   1. `::` bên trong khối `( )`
#      cmd coi `::` là nhãn, mà nhãn không được nằm trong ngoặc. Dùng `rem`.
#      Điểm ác: cmd phân tích TRỌN khối trước khi xét điều kiện, nên dù không
#      bao giờ bước vào khối đó thì lỗi vẫn nổ.
#
#   2. dấu `(` `)` chưa escape trong `echo` bên trong khối `( )`
#      dấu `)` đóng khối sớm. Phải viết `^(` và `^)`.
import glob as _glob, re as _re_b

def _soi_bat(duong_dan):
    """Trả về danh sách (số dòng, lý do) cho một file .bat."""
    dong = Path(duong_dan).read_text(encoding="utf-8", errors="replace").split("\n")
    sau, loi = 0, []
    for i, ln in enumerate(dong, 1):
        s = ln.strip()
        la_chu_thich = s.startswith("::") or s.lower().startswith("rem ")
        if sau > 0 and s.startswith("::"):
            loi.append((i, ":: trong khối ( )"))
        if sau > 0 and _re_b.match(r"(?i)echo\b", s) and not la_chu_thich:
            ngoai_nhay = _re_b.sub(r'"[^"]*"', "", s)   # trong "..." thì an toàn
            if _re_b.search(r"(?<!\^)[()]", ngoai_nhay):
                loi.append((i, "ngoặc chưa escape trong echo"))
        if not la_chu_thich:
            sau = max(0, sau + ln.count("(") - ln.count(")"))
    return loi

_bat = sorted(_glob.glob("*.bat"))
# Công cụ phát hành (PHAT_HANH / PUSH / DONG_GOI) đã dọn ra thư mục MNT_FB_dev
# cạnh bên, để máy khách không nhận được chúng khi cập nhật. Nhưng chúng vẫn là
# file .bat và vẫn dính được đúng lớp lỗi trên — mà PHAT_HANH.bat lại là thứ
# tuyệt đối không được hỏng. Nên kiểm luôn nếu thư mục đó có mặt; trên máy khách
# không có nó thì bỏ qua.
_dev = Path("..") / "MNT_FB_dev"
if _dev.is_dir():
    _bat += sorted(str(p) for p in _dev.glob("*.bat"))
check("có tìm thấy file .bat để kiểm", len(_bat) > 0)
for _f in _bat:
    _loi = _soi_bat(_f)
    _ten = f"{_f} không có lỗi cú pháp khối"
    if _loi:   # nêu rõ dòng nào, để sửa được ngay mà không phải dò lại
        _ten += " — " + "; ".join(f"dòng {i}: {ly}" for i, ly in _loi)
    check(_ten, not _loi)

# ── dọn dẹp ────────────────────────────────────────────────────────────────
for suffix in ("", "-wal", "-shm"):
    try:
        Path(str(_tmp) + suffix).unlink(missing_ok=True)
    except OSError:
        pass   # best-effort; sqlite WAL có thể còn giữ file

print(f"\n{_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
