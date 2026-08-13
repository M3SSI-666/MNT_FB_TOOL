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

# ── Loại đăng: 7 lựa chọn, C_ = chỉ đi comment ─────────────────────────────
check("có đúng 10 lựa chọn",          len(db.LOAI_DANG_OPTIONS) == 10)
check("nhận diện loại hỗn hợp X_",
      all(db.la_loai_hon_hop(v) for v in ("X_Home", "X_Thuê", "X_Bán")))
check("X_ KHÔNG phải chỉ-comment",
      not any(db.la_loai_comment(v) for v in ("X_Home", "X_Thuê", "X_Bán")))
check("C_ KHÔNG phải hỗn hợp",
      not any(db.la_loai_hon_hop(v) for v in ("C_Home", "C_Thuê", "C_Bán")))
check("X_Home -> lịch homestay",      db.khop_loai_lich("X_Home", "homestay"))
check("X_Thuê KHÔNG lọt lịch bán",    not db.khop_loai_lich("X_Thuê", "ban"))
check("nhận diện loại chỉ comment",
      all(db.la_loai_comment(v) for v in ("C_Home", "C_Thuê", "C_Bán")))
check("loại đăng bài KHÔNG phải comment",
      not any(db.la_loai_comment(v) for v in ("", "Homestay", "Thuê", "Bán")))

# Khớp lịch phải CHÍNH XÁC: "C_Thuê" chứa chuỗi con "Thuê", "C_Bán" chứa "Bán".
check("Homestay -> lịch homestay",    db.khop_loai_lich("Homestay", "homestay"))
check("C_Home  -> lịch homestay",     db.khop_loai_lich("C_Home", "homestay"))
check("C_Thuê KHÔNG lọt vào lịch bán", not db.khop_loai_lich("C_Thuê", "ban"))
check("C_Thuê -> đúng lịch thuê",     db.khop_loai_lich("C_Thuê", "thue"))
check("C_Bán  -> đúng lịch bán",      db.khop_loai_lich("C_Bán", "ban"))
check("Thuê KHÔNG lọt vào lịch homestay", not db.khop_loai_lich("Thuê", "homestay"))
check("để trống -> không vào lịch nào",
      not any(db.khop_loai_lich("", l) for l in ("homestay", "thue", "ban")))

for _v in db.LOAI_DANG_OPTIONS:
    db.update_account_field(_acc_id, "loai_dang", _v)
check("lưu được cả 7 giá trị hợp lệ",
      db.get_account_by_id(_acc_id)["loai_dang"] == db.LOAI_DANG_OPTIONS[-1])
for _xau in ("C_home", "homestay", "Comment", "C_Nha", "Homestay,Thuê"):
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
check("lọc theo Page 1 -> 2 bài",
      len(db.boc_bai_de_comment("ban", 9, page="PAGE_1")) == 2)
check("lọc theo Page 2 -> 2 bài",
      len(db.boc_bai_de_comment("ban", 9, page="PAGE_2")) == 2)
check("không lọc -> lấy cả 4",         len(db.boc_bai_de_comment("ban", 9)) == 4)
check("Page lạ -> không bài nào",      db.boc_bai_de_comment("ban", 9, page="PAGE_9") == [])
check("bài lấy ra đúng Page yêu cầu",
      all(r["page"] == "PAGE_1" for r in db.boc_bai_de_comment("ban", 9, page="PAGE_1")))
# Link cũ chưa gắn Page phải bị loại khi có lọc — thà bốc ít còn hơn comment
# nhầm vào bài của Page khác.
db.them_comment_posts("ban", [_lk("gE", 5)])
check("link chưa gắn Page bị loại khi lọc",
      len(db.boc_bai_de_comment("ban", 9, page="PAGE_1")) == 2)
check("không lọc thì vẫn lấy link đó", len(db.boc_bai_de_comment("ban", 9)) == 5)

# Page chưa có bài nào trong kho -> phiên KHÔNG được bỏ, mà lùi về dùng chung
# kho. Bỏ phiên là phí nguyên một slot, trong khi bài của Page anh em cũng là
# bài của mình, comment vào vẫn đẩy lên được.
check("Page lạ: lọc riêng -> rỗng",
      db.boc_bai_de_comment("ban", 9, page="PAGE_MOI") == [])
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

# Cửa sổ chưa đầy thì KHÔNG được kết luận chết: 5 lỗi đầu đời của một acc mới
# cũng ra tỉ lệ 100%, mà 5 phiên chưa phân biệt được chặn tạm với chết hẳn.
check("5/5 hỏng chưa đủ để tắt",        _sk.danh_gia("x" * 5)[0] == "nghi")
check("20/20 hỏng -> tắt",              _sk.danh_gia("x" * 20)[0] == "tat")
check("16/20 hỏng -> tắt",              _sk.danh_gia("x" * 16 + "o" * 4)[0] == "tat")
check("15/20 hỏng -> chưa tắt",         _sk.danh_gia("x" * 15 + "o" * 5)[0] != "tat")
check("cửa sổ giữ đúng 20 phiên",       _sk.them_ket_qua("o" * 25, False).count("o") == 19)

# Dấu ngắt: cắt chuỗi lỗi nhưng KHÔNG xoá cửa sổ. Bản đầu xoá sạch lịch sử lúc
# cho nghỉ, hậu quả là cửa sổ không bao giờ tích đủ 20 và tầng "tắt hẳn" vĩnh
# viễn không nổ — acc chết cứ nghỉ-hỏng-nghỉ mãi mà không ai bị tắt.
_sau = _sk.danh_dau_nghi("x" * 5)
check("dấu ngắt cắt chuỗi lỗi",         _sk.chuoi_loi(_sau) == 0)
check("dấu ngắt giữ lại các lỗi cũ",    _sau.count("x") == 5)
check("dấu ngắt không tính là phiên",   _sk.ti_le_hong(_sau) == 1.0)
check("nghỉ dậy được thử lại đủ lượt",  _sk.danh_gia(_sk.them_ket_qua(_sau, False))[0] == "")

# Acc chết vẫn phải tới được "tắt" dù đã nghỉ nhiều lần giữa chừng.
_ls = ""
for _ in range(30):
    _ls = _sk.them_ket_qua(_ls, False)
    _hd, _ = _sk.danh_gia(_ls)
    if _hd == "nghi":
        _ls = _sk.danh_dau_nghi(_ls)
    elif _hd == "tat":
        break
check("hỏng liên tục rồi cũng bị tắt",  _hd == "tat")

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
    if _hd == "tat":
        break
check("hỏng đủ lâu -> tắt hẳn",         _hd == "tat")
check("bị tắt thì không chạy",          db.acc_duoc_chay("SK Test")[0] is False)
# Tắt hẳn chặn tất, kể cả nuôi: trang_thai='Hỏng' làm get_account_by_name không
# tìm ra acc nữa, cho phiên nuôi chạy tiếp chỉ đổ lỗi vô nghĩa vào log.
check("bị tắt thì nuôi cũng dừng",      db.acc_duoc_chay("SK Test", "nuoi_nick")[0] is False)
check("tắt = trang_thai Hỏng",          db.get_account_by_name("SK Test") is None)
check("cảnh báo tắt ở mức error",       any(c["muc"] == "error"
                                            for c in db.lay_canh_bao()))

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
from datetime import datetime as _dt
_gio_sau = f"{min(23, _dt.now().hour + 1):02d}:00"
_gio_truoc = "00:01"
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

_n_slot = db.danh_dau_spam("SPAM Test", "3 bài mới bị gỡ")
check("chuyển trạng thái sang Spam",
      db.get_accounts()[0] is not None and any(
          a["ten_acc"] == "SPAM Test" and a["trang_thai"] == db.TRANG_THAI_SPAM
          for a in db.get_accounts()))
check("dừng slot đăng bài còn lại",     _n_slot == 1)
with db._conn() as _c:
    _rows = {(r["hoat_dong"], r["gio_dang"]): r["trang_thai"] for r in _c.execute(
        "SELECT hoat_dong,gio_dang,trang_thai FROM schedules WHERE ten_acc='SPAM Test'")}
check("slot đăng sắp tới -> Nghỉ Spam", _rows[("dang_bai", _gio_sau)] == db.TT_LICH_NGHI_SPAM)
check("slot đăng đã qua giờ -> để yên", _rows[("dang_bai", _gio_truoc)] == "Chờ")
# Acc dính spam VẪN comment được — đó là cả tiền đề của tính năng đi comment.
check("slot comment KHÔNG bị dừng",     _rows[("comment", _gio_sau)] == "Chờ")
check("slot nuôi KHÔNG bị dừng",        _rows[("nuoi_nick", _gio_sau)] == "Chờ")

check("spam chặn ĐĂNG BÀI",             db.acc_duoc_chay("SPAM Test", "dang_bai")[0] is False)
check("spam VẪN cho comment",           db.acc_duoc_chay("SPAM Test", "comment")[0] is True)
check("spam VẪN cho nuôi nick",         db.acc_duoc_chay("SPAM Test", "nuoi_nick")[0] is True)
# get_account_by_name lọc cứng 'Active' thì phiên comment/nuôi không lấy được
# cookie và chết theo — trong khi việc chặn đăng đã do acc_duoc_chay lo rồi.
check("vẫn tra được acc để lấy cookie", db.get_account_by_name("SPAM Test") is not None)
check("có sinh cảnh báo mức error",     any(c["ten_acc"] == "SPAM Test" and c["muc"] == "error"
                                            for c in db.lay_canh_bao()))

db.update_account_field(_sid, "trang_thai", "Active")
check("bật lại -> đăng bài được",       db.acc_duoc_chay("SPAM Test", "dang_bai")[0] is True)
with db._conn() as _c:
    _sv = _c.execute("SELECT so_vi_pham FROM accounts WHERE id=?", (_sid,)).fetchone()[0]
# Số vụ phải GIỮ: xoá về -1 thì lần dính kế tiếp bị bỏ lỡ vì coi như chưa đo.
check("bật lại vẫn giữ số vụ đã đo",    _sv == 15)
with db._conn() as _c:
    _c.execute("DELETE FROM schedules WHERE ten_acc='SPAM Test'")
db.delete_account(_sid)
db.xoa_canh_bao()

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

# ── dọn dẹp ────────────────────────────────────────────────────────────────
for suffix in ("", "-wal", "-shm"):
    try:
        Path(str(_tmp) + suffix).unlink(missing_ok=True)
    except OSError:
        pass   # best-effort; sqlite WAL có thể còn giữ file

print(f"\n{_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
