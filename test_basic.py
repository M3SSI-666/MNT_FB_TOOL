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

# Báo chế độ test: route xuất Excel sẽ ghi vào thư mục tạm chứ KHÔNG đổ file
# rác vào Downloads thật, và KHÔNG bật cửa sổ Explorer mỗi lần chạy bài kiểm.
os.environ["MNT_TEST"] = "1"

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

# ── Lỗi máy/mạng KHÔNG được tính vào sức khoẻ acc ──────────────────────────
# Ngày 17/09 máy hết RAM hai đợt: 51 phiên hỏng trong chưa tới 5 giây vì
# Chromium không khởi động nổi. Mọi acc hỏng cùng lúc, hết đợt thì mọi acc chạy
# lại 9/9 nhóm — nhưng 41 lượt "cho acc nghỉ" đã kịp phát ra. Hai chỗ hỏng:
#
#   1. poster nuốt lỗi thật thành `return False`, nơi gọi ném lại
#      Exception("Hybrid thất bại") → classify_error chỉ còn 'other' → không
#      thử lại, và bị cộng vào lịch sử hỏng của acc.
#   2. scheduler cộng cả lỗi 'transient' vào sức khoẻ acc.
check("'Connection closed' -> transient",
      classify_error(Exception("Connection closed while reading from the driver"))[0]
      == "transient")

def _gia_run(coro):
    """Thay asyncio.run: đóng coroutine rồi ném đúng lỗi máy chết."""
    try:
        coro.close()
    except Exception:
        pass
    raise RuntimeError("Connection closed while reading from the driver")

import page_via_poster as _pvp
import via_poster as _vp

def _co_nem(mod, goi):
    that = mod.asyncio.run
    mod.asyncio.run = _gia_run
    try:
        goi()
        return False
    except RuntimeError:
        return True
    except Exception:
        return False
    finally:
        mod.asyncio.run = that

check("post_page_via ném lỗi thật lên, không nuốt thành False",
      _co_nem(_pvp, lambda: _pvp.post_page_via(
          acc_name="T", page_uid="1", first_group_uid="2",
          search_kw="k", message="m")))
check("post_page_wall ném lỗi thật lên",
      _co_nem(_pvp, lambda: _pvp.post_page_wall(
          acc_name="T", page_uid="1", message="m")))
check("post_via_crosspost ném lỗi thật lên",
      _co_nem(_vp, lambda: _vp.post_via_crosspost(
          acc_name="T", search_kw="k", message="m", first_group_uid="2")))

_src_sch = Path("scheduler.py").read_text(encoding="utf-8")
_i_tran  = _src_sch.find('if cat == "transient":\n                logger.warning')
_i_suc   = _src_sch.find("_bao_suc_khoe(stt, acc_name,")
check("scheduler thoát sớm khi lỗi transient, trước khi ghi sức khoẻ",
      _i_tran != -1 and _i_suc != -1 and _i_tran < _i_suc)

# ── Chốt "một loại lịch — một runner" ──────────────────────────────────────
# Bộ quét runner mồ côi dò bằng dòng lệnh, mà WMI trả CommandLine = null cho
# tiến trình do Task Scheduler khởi chạy: đo lúc 19:50 ngày 17/09, máy có 18
# tiến trình pythonw và bộ quét tìm ra đúng 0. Mỗi lần mở lại phần mềm là thêm
# 4 runner nữa, tới 16 runner × ~1,1 GB Chrome thì RAM cạn.
import subprocess as _sp
import khoa_runner as _kr

_LOAI_THU = "_test_khoa"
try:
    os.unlink(_kr.duong_dan(_LOAI_THU))
except OSError:
    pass

check("giành được khoá khi chưa ai giữ", _kr.giu_khoa(_LOAI_THU) is True)
check("gọi lại trong cùng tiến trình vẫn OK", _kr.giu_khoa(_LOAI_THU) is True)
check("đọc được pid người đang giữ", _kr.pid_dang_giu(_LOAI_THU) == os.getpid())

# Tiến trình KHÁC phải bị chặn — đây mới là điều duy nhất đáng kiểm.
_ma = (f"import sys; sys.path.insert(0, {os.getcwd()!r}); "
       f"import khoa_runner; "
       f"sys.exit(0 if khoa_runner.giu_khoa({_LOAI_THU!r}) else 7)")
_kq = _sp.run([sys.executable, "-c", _ma], capture_output=True, timeout=60)
check("tiến trình thứ hai KHÔNG giành được khoá", _kq.returncode == 7)

# Nhả ra thì người sau phải vào được, nếu không thì mỗi lần khởi động lại máy
# là runner thật bị chặn oan.
_fd = _kr._DANG_GIU.pop(_LOAI_THU)
os.close(_fd)
_kq2 = _sp.run([sys.executable, "-c", _ma], capture_output=True, timeout=60)
check("nhả khoá rồi thì tiến trình sau vào được", _kq2.returncode == 0)
check("chủ khoá đã thoát -> pid_dang_giu trả None",
      _kr.pid_dang_giu(_LOAI_THU) is None)
try:
    os.unlink(_kr.duong_dan(_LOAI_THU))
except OSError:
    pass

# File khoá CŨ còn nguyên nhưng chẳng ai giữ → phải coi là KHÔNG chạy.
# Đây là cái bẫy đã làm lịch Thuê chết im gần 4 tiếng đêm 18/09: file
# `.runner_thue.lock` giữ PID 1244 đã chết, phần mềm đọc PID rồi hỏi "PID này
# còn sống không". Windows dùng lại số PID, nên câu hỏi đó không bao giờ đáng
# tin — hỏi KHOÁ mới đúng, vì hệ điều hành chỉ nhả khoá khi chủ nó chết.
_LOAI_MA = "_test_khoa_ma"
with open(_kr.duong_dan(_LOAI_MA), "wb") as _f:
    _f.write(b"#999999\n")           # pid không thể tồn tại
check("file khoá mồ côi → dang_giu = False", _kr.dang_giu(_LOAI_MA) is False)
check("file khoá mồ côi → pid_dang_giu = None", _kr.pid_dang_giu(_LOAI_MA) is None)
check("file khoá mồ côi KHÔNG chặn runner thật", _kr.giu_khoa(_LOAI_MA) is True)
check("giành xong thì dang_giu = True", _kr.dang_giu(_LOAI_MA) is True)
os.close(_kr._DANG_GIU.pop(_LOAI_MA))
check("nhả rồi thì dang_giu = False", _kr.dang_giu(_LOAI_MA) is False)
# `dang_giu` giành khoá trong tích tắc rồi nhả — tuyệt đối không được để lại
# dấu vết, nếu không thì mỗi lần giao diện hỏi trạng thái là một lần phá khoá.
_kr.giu_khoa(_LOAI_MA)
_ma_kq = (_kr.dang_giu(_LOAI_MA), _kr.dang_giu(_LOAI_MA), _kr.pid_dang_giu(_LOAI_MA))
check("hỏi trạng thái nhiều lần không làm mất khoá của chủ",
      _ma_kq == (True, True, os.getpid()))
os.close(_kr._DANG_GIU.pop(_LOAI_MA))
try:
    os.unlink(_kr.duong_dan(_LOAI_MA))
except OSError:
    pass

_src_srv = Path("server.py").read_text(encoding="utf-8")
check("server dò runner sống bằng khoá, không chỉ bằng file pid",
      "dang_giu(loai)" in _src_srv)
# Phải hỏi KHOÁ chứ không hỏi PID: Windows dùng lại số PID, file khoá cũ trỏ
# vào PID đã được cấp cho tiến trình khác thì hỏi PID trả lời "còn chạy" mãi
# mãi. Lịch Thuê chết im gần 4 tiếng đêm 18/09 vì đúng chuyện này.
check("server KHÔNG còn hỏi PID để biết runner sống",
      "pid_dang_giu(loai) is not None" not in _src_srv)
check("tắt phần mềm có diệt runner theo khoá",
      _src_srv.find("kr.pid_dang_giu(loai)") != -1)
check("runner trùng loại thì tự thoát",
      "khoa_runner.giu_khoa(LOAI)" in Path("scheduler.py").read_text(encoding="utf-8"))

# ── Phiên hỏng phải nói rõ HỎNG Ở BƯỚC NÀO ─────────────────────────────────
# Trước đây mọi bước hỏng chỉ `return False`, nơi gọi ném Exception("Hybrid
# thất bại"). Bảng lịch ghi "Hybrid thất bại", Telegram ghi "5 lỗi liên tiếp" —
# không chỗ nào nói hỏng ở đâu. Lý do thật chỉ nằm trong file log, lẫn giữa
# hàng nghìn dòng, nên người quản trị không biết phải sửa cái gì.
from utils import LoiBuoc as _LoiBuoc

_cat_b, _nhan_b = classify_error(_LoiBuoc("Không mở được ô soạn bài (nhóm 4349)"))
check("LoiBuoc -> loại 'buoc'", _cat_b == "buoc")
check("LoiBuoc giữ nguyên tên bước",
      _nhan_b == "Không mở được ô soạn bài (nhóm 4349)")
# Nhãn là câu tiếng Việt do mình viết; rơi vào bộ dò từ khoá thì "Không tìm
# thấy nút Đăng" sẽ bị gán nhãn chung chung, mất sạch chi tiết vừa ghi.
check("LoiBuoc không bị bộ dò từ khoá nuốt mất",
      classify_error(_LoiBuoc("Không thấy nút Đăng"))[1] == "Không thấy nút Đăng")
check("LoiBuoc KHÔNG được thử lại (không phải lỗi mạng)",
      scheduler._should_retry("buoc", 1) is False)

for _f in ("page_via_poster.py", "via_poster.py"):
    _s = Path(_f).read_text(encoding="utf-8")
    check(f"{_f}: không còn `return False` nuốt lý do", "return False" not in _s)
    check(f"{_f}: mỗi bước hỏng có tên riêng", _s.count("raise LoiBuoc(") >= 6)
check("không còn ném 'Hybrid thất bại' trống rỗng",
      'raise Exception("Hybrid thất bại")' not in Path("scheduler.py").read_text(encoding="utf-8"))
check("scheduler truyền nhãn lỗi xuống DB",
      "ly_do_loi=label" in Path("scheduler.py").read_text(encoding="utf-8"))

_ten_tl = "__TestBaoLoi__"
_id_tl  = db.upsert_account({"ten_acc": _ten_tl, "trang_thai": "Active"})
try:
    _ly_tl = "Không mở được ô soạn bài (nhóm 4349)"
    _hd_tl, _ = db.ghi_nhan_phien_dang(_ten_tl, False, ly_do_loi=_ly_tl)
    _r_tl = db.get_account_by_name(_ten_tl)
    check("lỗi ĐẦU TIÊN đã ghi lại, không đợi đủ 5",
          _ly_tl in (_r_tl.get("loi_gan_nhat") or "") and _hd_tl == "")
    # Ghi cả NGÀY: chỉ có "20:51" thì lỗi hôm trước nhìn y hệt lỗi vừa nãy —
    # 'Sa Tran Anh' ngày 19/09 treo ghi chú "20:51 · Page crashed" thực ra là
    # của 20:51 HÔM 18/09, người dùng tưởng nick đang hỏng.
    check("ghi chú lỗi có cả ngày, không chỉ giờ",
          __import__("re").match(r"^\d{2}/\d{2} \d{2}:\d{2} · ",
                                 _r_tl.get("loi_gan_nhat") or ""))
    # Hỏng MỘT lần rồi chạy lại được thì phải xoá ghi chú, dù chưa hề bị cho
    # nghỉ. Bản cũ chỉ xoá khi acc từng nghỉ, nên acc hỏng đúng một lần mang
    # ghi chú đó suốt đời: 'Sa Tran Anh' chạy 20/20 phiên tốt mà vẫn treo lỗi.
    db.ghi_nhan_phien_dang(_ten_tl, True)
    _r_tl = db.get_account_by_name(_ten_tl)
    check("hỏng 1 lần rồi chạy lại được → xoá ghi chú (dù chưa từng nghỉ)",
          not (_r_tl.get("loi_gan_nhat") or ""))
    _hd_tl, _ = db.ghi_nhan_phien_dang(_ten_tl, False, ly_do_loi=_ly_tl)
    for _ in range(4):
        _hd_tl, _lydo_tl = db.ghi_nhan_phien_dang(_ten_tl, False, ly_do_loi=_ly_tl)
    _r_tl = db.get_account_by_name(_ten_tl)
    check("đủ 5 lỗi thì nghỉ", _hd_tl == "nghi")
    check("lý do nghỉ có CẢ số lần LẪN tên bước",
          "5 lỗi liên tiếp" in _lydo_tl and _ly_tl in _lydo_tl)
    check("lý do ra tới cột Trạng thái + Telegram",
          _ly_tl in (_r_tl.get("ly_do_nghi") or ""))
    db.ghi_nhan_phien_dang(_ten_tl, True)
    _r_tl = db.get_account_by_name(_ten_tl)
    check("chạy lại được thì xoá sạch lý do cũ",
          not (_r_tl.get("ly_do_nghi") or "") and not (_r_tl.get("loi_gan_nhat") or ""))
finally:
    db.delete_account(_id_tl)

_app_js = Path("static/js/app.js").read_text(encoding="utf-8")
# Lý do phải nằm ở cột GHI CHÚ, KHÔNG nhét vào ô Trạng thái. Cột Trạng thái hẹp
# nên câu dài bị bẻ thành một cột chữ dọc và kéo cao cả hàng — nhìn bảng còn khó
# hơn lúc chưa có lý do.
_i_nghi = _app_js.index("😴 Nghỉ tới")
check("ô Trạng thái chỉ ghi giờ, không chèn lý do dài",
      "ly_do_nghi" not in _app_js[_i_nghi:_i_nghi + 320])

# ── Mọi hàng trong bảng Tài khoản phải cao BẰNG NHAU ───────────────────────
# Ô Trạng thái của nick dính Spam từng xuống BA dòng ("🚫 Spam", "· dò từ",
# "23:51") vì cột hẹp, làm hàng đó cao gấp đôi hàng bên cạnh. "Cookie hết hạn"
# cũng bị bẻ làm hai dòng. Đo trên giao diện thật sau khi sửa: 45–46px cho cả
# 17 hàng, thay vì 45–53px.
check("ô Trạng thái Spam CHỈ ghi 'Spam'", 'nhan:"🚫 Spam"' in _app_js)
check("giờ thăm dò chuyển sang cột Ghi chú qua `phu`",
      "phu:(ly?ly" in _app_js and "dò từ ${gio}" in _app_js)
check("ô Trạng thái không bao giờ xuống dòng",
      "color:${t.mau};white-space:nowrap" in _app_js)
_i_gc2 = _app_js.index('f.key==="ghi_chu"')
_o_gc2 = _app_js[_i_gc2:_i_gc2 + 1400]
check("ô Ghi chú gộp về ĐÚNG MỘT dòng",
      "white-space:nowrap" in _o_gc2 and _o_gc2.count("display:block") == 1)
check("ô Ghi chú lấy `phu` của Trạng thái", "_trangThaiAcc(r)" in _o_gc2)
check("cột Ghi chú hiện lý do nghỉ / lỗi gần nhất",
      'f.key==="ghi_chu"' in _app_js
      and "r.loi_gan_nhat" in _app_js and "(t.phu" in _app_js)
# Ghi chú là ô SỬA ĐƯỢC. Dòng cảnh báo chỉ để nhìn — `data-val` phải giữ ghi chú
# thật, không thì bấm vào sửa là nuốt mất chữ người dùng tự viết.
_i_gc = _app_js.index('f.key==="ghi_chu"')
_o_gc = _app_js[_i_gc:_i_gc + 1800]
check("sửa Ghi chú không nuốt mất chữ người dùng tự viết",
      'data-val="${esc}"' in _o_gc and "startAccEdit(this)" in _o_gc)
check("mỗi dòng trong ô Ghi chú bị cắt gọn, không kéo cao hàng",
      "text-overflow:ellipsis;white-space:nowrap" in _o_gc)

# Lỗi Playwright kèm cả khối "Call log:" nhiều dòng — để nguyên thì ô Ghi chú
# bị kéo cao mấy dòng trống.
_ten_gd = "__TestGopDong__"
_id_gd  = db.upsert_account({"ten_acc": _ten_gd, "trang_thai": "Active"})
try:
    db.ghi_nhan_phien_dang(_ten_gd, False,
                           ly_do_loi="Page crashed\nCall log:\n  - navigating to x")
    _r_gd = db.get_account_by_name(_ten_gd)
    check("lý do lỗi được gộp về MỘT dòng",
          "\n" not in (_r_gd.get("loi_gan_nhat") or "")
          and "Call log: - navigating to x" in (_r_gd.get("loi_gan_nhat") or ""))
finally:
    db.delete_account(_id_gd)

# ── Hộp xin phép cookie của Facebook ───────────────────────────────────────
# Nhìn tận mắt lúc 23:09 ngày 17/09 trên nick 'Xuan Khoa': hộp "Cho phép sử
# dụng cookie của Facebook trên trình duyệt này?" đè lên trang Page. Nó là lớp
# phủ MODAL — ô "Bạn viết gì đi..." vẫn nằm trong DOM và vẫn tính là visible,
# nhưng mọi cú bấm đều bị nuốt. Đó là lỗi "❌ Không mở được composer!".
#
# Số liệu khớp: 2078 lượt mở composer, lượt XONG trung bình 4s (chậm nhất 15s),
# lượt HỎNG nhanh nhất 18s (trung bình 41s). Không có vùng giữa → không phải
# trang tải chậm, mà là dò hết 6 kiểu nút rồi mới chịu thua.
_src_fbc = Path("fb_common.py").read_text(encoding="utf-8")
check("có hàm đóng hộp cookie", hasattr(_fbc_mod := __import__("fb_common"), "dong_hop_cookie"))
check("bấm 'Cho phép tất cả cookie'",
      "cho phép tất cả cookie" in _src_fbc and "allow all cookies" in _src_fbc)
check("chỉ đụng dialog có chữ 'cookie'", "includes('cookie')" in _src_fbc)
check("bấm bằng Playwright, không bấm bằng JS", "await nut.click(timeout=4000)" in _src_fbc)
check("chỉ báo thành công khi hộp đã biến mất",
      "return not await _con_hop_cookie(page)" in _src_fbc
      and _src_fbc.count("_con_hop_cookie(page)") >= 4)
check("có lối thoát: bấm phần tử sâu nhất", "hop[hop.length - 1].click()" in _src_fbc)
check("vòng canh nền cũng dọn hộp cookie",
      _src_fbc.find("await dong_hop_cookie(page)") < _src_fbc.find("dlg, text = await _tim_dialog_canh_bao(page)\n\n            if dlg is None:\n                continue")
      or "Đã đóng hộp xin phép cookie (vòng canh)" in _src_fbc)

for _f in ("page_via_poster.py", "via_poster.py"):
    _s = Path(_f).read_text(encoding="utf-8")
    check(f"{_f}: dọn hộp cookie trước khi dò ô soạn bài",
          "await dong_hop_cookie(page)\n            for sel in [" in _s)
    check(f"{_f}: chưa mở được thì dọn lớp phủ rồi thử lại",
          "da_don = await dong_hop_cookie(page)" in _s)
    check(f"{_f}: dọn ngay sau khi login", "🍪 Đã đóng hộp xin phép cookie" in _s)
check("page_via_poster: dọn trước khi bấm nút Chuyển",
      "[Switch] 🍪" in Path("page_via_poster.py").read_text(encoding="utf-8"))

# ── Cờ Chromium: một bản duy nhất, và phải bớt RAM ─────────────────────────
import fb_common as _fbc

for _co in ("BackForwardCache", "--disable-background-networking",
            "--disable-component-update", "--disable-breakpad",
            "--mute-audio", "--disk-cache-size"):
    check(f"cờ bớt RAM có '{_co}'", any(_co in a for a in _fbc.ARGS_CHUNG))
# Cờ này đã làm sập renderer một lần rồi — đừng để ai thêm lại.
check("KHÔNG có --disable-software-rasterizer",
      not any("software-rasterizer" in a for a in _fbc.ARGS_CHUNG))
check("vẫn giữ --disable-gpu (vẽ bằng phần mềm)",
      "--disable-gpu" in _fbc.ARGS_CHUNG)

# Ba file poster từng mỗi chỗ chép một bản args giống hệt, nên sửa một chỗ là
# quên hai chỗ kia. Giờ tất cả phải gọi chung một hàm.
for _f in ("page_via_poster.py", "via_poster.py", "comment_bai.py", "nuoi_nick.py"):
    _s = Path(_f).read_text(encoding="utf-8")
    check(f"{_f} dùng cờ chung", "browser_launch_kwargs(" in _s)
    check(f"{_f} không còn tự liệt kê cờ",
          "--disable-blink-features=AutomationControlled" not in _s)

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
check("thêm 15 link",          db.them_comment_posts("homestay", _urls, page="PG") == 15)
check("thêm lại -> bỏ trùng",  db.them_comment_posts("homestay", _urls, page="PG") == 0)
check("nhóm được lưu sẵn",
      {r["nhom"] for r in db.get_comment_posts("homestay")} == {"g1", "g2", "g3"})

# Luật 1: DÀN TRẢI theo nhóm — vòng 1 lấy một bài mỗi nhóm, hết mới sang vòng 2.
# Trùng nhóm là HẠN CHẾ chứ không CẤM (Duong chốt 05/10): Page có ít nhóm hơn
# số bài cần mà cấm cứng thì phiên hụt vĩnh viễn.
_b = db.boc_bai_de_comment("homestay", 9, page="PG")
check("xin 9 với 3 nhóm × 5 bài -> đủ 9", len(_b) == 9)
check("3 phần tử ĐẦU phủ hết 3 nhóm", len({r["nhom"] for r in _b[:3]}) == 3)
check("không lặp lại cùng một bài", len({r["id"] for r in _b}) == 9)
_b2 = db.boc_bai_de_comment("homestay", 2, page="PG")
check("xin ít hơn số nhóm -> đúng số xin, khác nhóm", len(_b2) == 2
      and len({r["nhom"] for r in _b2}) == 2)
check("xin 0 -> rỗng",         db.boc_bai_de_comment("homestay", 0, page="PG") == [])
# Không truyền Page thì không có "chính chủ" nào để so — trả rỗng, tuyệt đối không
# lấy bừa cả kho. Đi comment dưới bài của Page lạ khiến nick dính spam.
check("không truyền Page -> rỗng", db.boc_bai_de_comment("homestay", 9) == [])
# Xin nhiều hơn số bài đang có thì trả hết, không bịa thêm.
check("xin 99 -> trả hết 15 bài",
      len(db.boc_bai_de_comment("homestay", 99, page="PG")) == 15)

# Luật 2: trong mỗi nhóm, bài CŨ NHẤT (order_idx nhỏ nhất) đi trước
_idx = {r["nhom"]: r["order_idx"] for r in _b[:3]}
_min = {}
for r in db.get_comment_posts("homestay"):
    _min[r["nhom"]] = min(_min.get(r["nhom"], 10**9), r["order_idx"])
check("vòng 1 bốc đúng bài cũ nhất mỗi nhóm", _idx == _min)

# ...nhưng bài đã comment rồi phải nhường bài chưa comment, nếu không mỗi phiên
# đều dội lại đúng một bài cho tới khi nó bị đẩy khỏi cửa sổ.
db.ghi_nhan_comment(_b[0]["id"], True)
_b3 = db.boc_bai_de_comment("homestay", 3, page="PG")
_cua_nhom = [r for r in _b3 if r["nhom"] == _b[0]["nhom"]][0]
check("bài đã comment nhường bài chưa comment", _cua_nhom["id"] != _b[0]["id"])
check("vòng 1 vẫn 1 bài mỗi nhóm", len({r["nhom"] for r in _b3}) == 3)

# so_lan phải cộng ĐÚNG số câu đã gửi. Bài chính chủ nhận 2 câu một lượt; cộng 1
# mỗi lượt thì nó bị đếm thiếu một nửa và cứ được bốc lại mãi, vì so_lan chính là
# khoá xếp hạng "bài nào ít comment nhất đi trước".
_sl = lambda i: [r for r in db.get_comment_posts("homestay") if r["id"] == i][0]
_truoc = _sl(_b[0]["id"])["so_lan"]
db.ghi_nhan_comment(_b[0]["id"], True, so_cau=2)
check("so_cau=2 -> so_lan cộng 2",   _sl(_b[0]["id"])["so_lan"] == _truoc + 2)
check("gửi nhiều câu hiện ×n trên bảng", "×2" in _sl(_b[0]["id"])["trang_thai"])
db.ghi_nhan_comment(_b[0]["id"], True)
check("mặc định vẫn cộng 1",          _sl(_b[0]["id"])["so_lan"] == _truoc + 3)
check("1 câu thì không ghi ×",        "×" not in _sl(_b[0]["id"])["trang_thai"])

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
# Nới 300 → 500 ngày 03/10: mỗi hạng mục ~250 slot đăng/ngày × 10 link/phiên
# = ~2.000-2.500 link/ngày, nên 300 chỉ còn ~3 giờ đăng gần nhất. Cả ba hạng
# mục đều đứng đúng 300/300, tức hạn mức đang chặn thật.
check("giới hạn mặc định là 500", db.GIOI_HAN_LINK == 500)
# Giao diện từng ghi cứng "300" ở hai chỗ, nới hạn mức bên Python là bảng nói
# sai ngay mà không ai biết. Nay server gửi kèm, giao diện chỉ hiển thị lại.
_src_srv_gh = Path("server.py").read_text(encoding="utf-8")
_src_ajs_gh = Path("static/js/app.js").read_text(encoding="utf-8")
check("server gửi kèm hạn mức", '"gioi_han": db.GIOI_HAN_LINK' in _src_srv_gh)
check("giao diện KHÔNG ghi cứng số link",
      "/300 link" not in _src_ajs_gh and "300 link mới nhất" not in _src_ajs_gh)
check("giao diện lấy hạn mức từ server",
      "_cmtGioiHan = res.gioi_han" in _src_ajs_gh
      and _src_ajs_gh.count('class="cmt-gioi-han"') == 2)

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
# Tính theo ca TỘ6 NHẤT: mọi bài đều là bài chính chủ nên bài nào cũng nhận
# `comment_cau_chinh_chu` câu, và giữa mỗi cặp câu còn nghỉ thêm NGHI_GIUA_2_CAU.
_so_bai  = _cb.DEFAULTS["comment_so_bai"]
_so_cau  = _cb.DEFAULTS["comment_cau_chinh_chu"]
_uoc = (max(_cb.FEED_GIAY) + max(_cb.KET_GIAY)
        + _so_bai * _so_cau * 15
        + _so_bai * (_so_cau - 1) * max(_cb.NGHI_GIUA_2_CAU)
        + (_so_bai - 1) * _cb.DEFAULTS["comment_nghi_max"])
check("trần rộng hơn phiên chạy bình thường", _cb.GIOI_HAN_PHIEN_GIAY > _uoc)
check("trần không quá rộng (≤ 30 phút)",      _cb.GIOI_HAN_PHIEN_GIAY <= 1800)

# Thời lượng khởi động / kết phiên BÁM ĐÚNG luồng đăng bài Page — thêm ô chỉnh
# riêng cho chúng là tạo chỗ để hai luồng lệch nhau. Chỉ số LƯỢNG (bao nhiêu bài,
# bao nhiêu câu, nghỉ bao lâu) mới được cấu hình.
check("không thêm ô chỉnh thời lượng phiên",
      set(_cb.DEFAULTS) == {"comment_so_bai", "comment_nghi_min", "comment_nghi_max",
                            "comment_cau_chinh_chu"})
# So THẲNG với luồng đăng bài thay vì khoá cứng con số: sửa một bên mà quên bên
# kia thì hỏng test ngay, chứ không âm thầm để hai luồng hành xử khác nhau.
import re as _re_tl
_src_pvp_t = Path("page_via_poster.py").read_text(encoding="utf-8")
_m_feed = _re_tl.search(r"scroll_sec = random\.randint\((\d+), (\d+)\)", _src_pvp_t)
check("thời lượng newsfeed khớp luồng đăng bài",
      _cb.FEED_GIAY == (int(_m_feed.group(1)), int(_m_feed.group(2))))
# Luồng ĐĂNG BÀI không còn bước kết phiên riêng — việc lướt + like đã gộp vào
# khoảng chờ thông báo đăng chéo. Luồng COMMENT thì vẫn giữ, vì nó không có
# khoảng chờ nào để gộp vào.
check("luồng đăng bài không còn bước kết phiên riêng",
      "cooldown_sec = random.randint" not in _src_pvp_t)
check("luồng comment vẫn kết phiên, thời lượng hợp lý",
      5 <= min(_cb.KET_GIAY) and max(_cb.KET_GIAY) <= 30)
# Lướt feed và hạ nhiệt là hai bước "làm người thật". Hạ xuống dưới 5 giây thì
# gần như không còn tác dụng mà vẫn tốn một lượt tải trang.
check("thời lượng còn đủ dài để có nghĩa",
      min(_cb.FEED_GIAY) >= 5 and min(_cb.KET_GIAY) >= 5)

# ── Ba tối ưu phiên đăng bài (đo ngày 02/10, phiên 188 giây) ───────────────
_src_pvp2 = Path("page_via_poster.py").read_text(encoding="utf-8")
_src_fbc2 = Path("fb_common.py").read_text(encoding="utf-8")

# 1. Lướt feed + like làm TRONG lúc chờ thông báo, không thành bước riêng.
#    Trình duyệt đứng im 60 giây ngay sau khi đăng tự nó đã là dấu hiệu lạ.
check("bỏ bước hạ nhiệt riêng", "cooldown_sec = random.randint" not in _src_pvp2)

# ── Thu link chạy SAU khi đăng, sau quãng lướt feed ────────────────────────
# Facebook đẩy thông báo đăng chéo nhỏ giọt (29s: 2/9 · 58s: 5/9 · 76s: 9/9),
# nên đọc trang thông báo ngay sau cú bấm Đăng thì không có gì mà đọc. Quãng
# lướt feed 60-70s ở trên vừa là cửa sổ dò spam vừa là chỗ chờ này.
check("KHÔNG còn thu link ở đầu phiên",
      "Thu link phiên trước" not in _src_pvp2)
check("thu link từ trang thông báo sau khi đăng",
      "[b] Trang thông báo" in _src_pvp2)
_i_sw   = _src_pvp2.index("await _switch_to_page(page, ctx, page_uid)")
_i_dang = _src_pvp2.index("Thêm nhóm → tìm")
_i_luot = _src_pvp2.index("random.randint(*CHO_SAU_DANG_GIAY)")
_i_thu  = _src_pvp2.index("[b] Trang thông báo")
# Thứ tự này LÀ cơ chế: chuyển Page → đăng → lướt feed (chờ + canh spam) → thu.
# Đảo bất kỳ cặp nào là hỏng: thu trước khi lướt thì chưa có thông báo, lướt
# trước khi đăng thì chờ nhầm chỗ.
check("chuyển Page → đăng → lướt feed → thu link",
      _i_sw < _i_dang < _i_luot < _i_thu)
# Cửa sổ 24 giờ chứ không chỉ mẻ vừa đăng: quãng chờ nằm dưới mốc 76s nên mỗi
# phiên hụt 1-3 thông báo về muộn, phiên sau đọc lại là vớt được. An toàn vì
# không Page nào phục vụ quá một loại lịch, và them_comment_posts bỏ trùng.
check("đọc cả cửa sổ 24 giờ để vớt phần hụt",
      "toi_da_phut=1440" in _src_pvp2)
# Cửa sổ rộng nhưng chỉ lấy N bài MỚI NHẤT. Đo 02/10: một lượt đọc ra 52 thông
# báo, 31 link mới — nhiều hơn mức cần. Thư viện comment là cửa sổ trượt có hạn
# mức, đổ 31 link mỗi phiên vào là thay gần hết danh sách trước khi kịp comment.
import thu_link as _tl2
check("chỉ lấy 10 bài mới nhất", _tl2.THU_LINK_MOI_NHAT == 10)
check("cắt từ ĐẦU danh sách (đáng thu nhất trước)",
      "_tb[:THU_LINK_MOI_NHAT]" in _src_pvp2)
# Nguồn (a) và (b) gộp vào MỘT danh sách rồi mới lưu: nhóm mở composer chỉ có ở
# (a), các nhóm đăng chéo chỉ có ở (b). Lưu riêng hai lượt là ghi đè hạn mức
# hai lần cho cùng một phiên.
check("gộp link hai nguồn rồi mới lưu",
      "_link_moi += [u for u in _lay if u not in _link_moi]" in _src_pvp2)

# Cắt từ đầu chỉ đúng nếu danh sách THẬT SỰ xếp đáng thu nhất trước. Bản đầu
# dựa vào thứ tự Facebook bày trên trang — tình cờ đúng, nhưng là giả định về
# giao diện người khác: hôm nào họ đổi cách xếp là hỏng ngầm, không báo lỗi,
# chỉ lặng lẽ đi comment mấy bài cũ.
_src_tl = Path("thu_link.py").read_text(encoding="utf-8")
check("hàm thu xếp lại trước khi trả về", "return xep_uu_tien(ra)" in _src_tl)
_xep = _tl2.xep_uu_tien([("u1", "3 giờ"), ("u2", "5 phút"), ("u3", "2 ngày")])
check("mới nhất lên đầu", [u for u, _ in _xep] == ["u2", "u1", "u3"])
# "Vừa xong" không có số nào đọc được. Coi là cũ nhất thì bài vừa đăng — thứ
# đáng lấy nhất — lại bị đẩy khỏi top 10.
check("đọc không ra tuổi thì coi là mới nhất",
      _tl2.xep_uu_tien([("u1", "9 phút"), ("u2", "Vừa xong")])[0][0] == "u2")
# Nhãn tuổi của Facebook chỉ đến từng phút, nên 8 nhóm cùng một đợt đăng chéo
# đều ghi "8 phút". Trong thế cân bằng đó thì vị trí trang vẫn là tiêu chí phụ
# duy nhất còn lại — sort phải ỔN ĐỊNH, không được xáo.
_deu = [(f"u{i}", "3 phút") for i in range(6)]
check("cùng hạng thì giữ nguyên thứ tự trang", _tl2.xep_uu_tien(_deu) == _deu)

# ── Ưu tiên thông báo CHƯA ĐỌC ─────────────────────────────────────────────
# Đo 03/10: Facebook dán chữ "Chưa đọc" vào đầu cả 14/14 dòng mẫu nên đọc được.
# NHƯNG dấu này KHÔNG tự xoá: mở trang hai lần trong 7 phút, 45/45 vẫn "Chưa
# đọc". Nên nó là tiêu chí yếu, tuổi mới gánh việc — giữ vì không tốn gì, đừng
# tin nó nhận ra "bài đã thu rồi".
check("đọc được dấu chưa đọc",
      _tl2.la_chua_doc("Chưa đọc Đã đăng chéo bài viết của bạn lên Homestay. 8 phút")
      and not _tl2.la_chua_doc("Đã đăng chéo bài viết của bạn lên Homestay. 1 giờ"))
# Chỉ soi 20 ký tự đầu: tên nhóm nằm giữa mô tả và có thể chứa đúng chữ đó.
check("tên nhóm chứa 'chưa đọc' KHÔNG bị nhận nhầm",
      not _tl2.la_chua_doc("Đã đăng chéo bài viết của bạn lên nhóm Sách chưa đọc. 2 giờ"))
# Chưa đọc đi trước, kể cả khi cũ hơn — vì bài đã đọc thì có thể đã nằm trong
# thư viện rồi, còn chưa đọc thì chắc chắn chưa.
_tron = [("cu_da_doc", "5 phút"), ("moi_chua_doc", "Chưa đọc ... 3 giờ")]
check("chưa đọc đi trước dù cũ hơn",
      [u for u, _ in _tl2.xep_uu_tien(_tron)] == ["moi_chua_doc", "cu_da_doc"])
# XẾP chứ không LỌC: phiên hỏng giữa đường sau khi đã mở trang thông báo thì mớ
# đó thành "đã đọc" mà chưa vào thư viện — lọc là mất hẳn, xếp thì tự bù.
check("vẫn giữ bài đã đọc để bù khi thiếu",
      len(_tl2.xep_uu_tien(_tron)) == 2)

# ── KHÔNG kiểm sống/chết lúc thu ───────────────────────────────────────────
# Đã viết bộ lọc rồi bỏ, đo 03/10: mở trang thật 1,6s/link kể cả khi mở 4 tab
# cùng lúc (cách rẻ `ctx.request.get` trả HTTP 400 cho MỌI link, vô dụng) —
# tức +16s mỗi phiên, mà 21 link đo được chết đúng 0 cái. Bài bị gỡ muộn hơn
# lúc thu; phiên comment đã mở sẵn từng bài nên dọn ở đó không tốn thêm gì.
#
# Test này để chặn việc làm lại: ai thêm kiểm sống/chết vào khúc thu thì phải
# đọc ghi chú và có số đo mới, chứ không phải vì nghe có lý.
check("thu link KHÔNG kiểm sống/chết",
      "loc_link_song" not in _src_pvp2 and "loc_link_song" not in _src_tl)
check("ghi lại vì sao bỏ, kèm số đo",
      "ĐÃ THỬ kiểm link sống/chết ngay tại đây và BỎ" in _src_tl
      and "21 link, CHẾT ĐÚNG 0 CÁI" in _src_tl)
# Dọn link chết vẫn phải còn — chỉ còn MỘT nơi làm việc đó.
_src_cb2 = Path("comment_bai.py").read_text(encoding="utf-8")
check("comment_bai vẫn dọn link chết",
      "BAI_KHONG_XEM_DUOC" in _src_cb2 and "chet=True" in _src_cb2)

# ── Bốc DƯ ứng viên rồi comment tới khi đủ số bài ──────────────────────────
# Trước đây bốc đúng 10 bài: gặp link chết là hụt đúng bấy nhiêu, không gì bù.
# Nay bốc gấp đôi (20 ứng viên cho 10 bài) rồi đi lần lượt, đủ số thì dừng.
_lc = "ung_vien_test"
db.xoa_het_comment_posts(_lc)
# g1 có 4 bài, g2 có 2, g3 có 1 — để thấy rõ thứ tự theo vòng.
for _g, _n in (("g1", 4), ("g2", 2), ("g3", 1)):
    db.them_comment_posts(_lc, [f"https://www.facebook.com/groups/{_g}/posts/{i}/"
                                for i in range(1, _n + 1)], page="PAGE_A")
db.them_comment_posts(_lc, ["https://www.facebook.com/groups/gx/posts/9/"],
                      page="PAGE_LA")

# Vòng 1 lấy một bài MỖI NHÓM rồi mới sang vòng 2 — đây là cách dàn trải.
check("vòng 1 phủ hết các nhóm trước",
      [r["nhom"] for r in db.boc_bai_de_comment(_lc, 3, page="PAGE_A")]
      == ["g1", "g2", "g3"])
check("hết nhóm mới quay lại nhóm cũ",
      [r["nhom"] for r in db.boc_bai_de_comment(_lc, 5, page="PAGE_A")]
      == ["g1", "g2", "g3", "g1", "g2"])
# Xin nhiều hơn số bài đang có thì trả về hết, không lặp bài.
_tat_ca = db.boc_bai_de_comment(_lc, 20, page="PAGE_A")
check("xin dư thì trả hết, không lặp bài",
      len(_tat_ca) == 7 and len({r["id"] for r in _tat_ca}) == 7)
# TUYỆT ĐỐI không vơ sang Page khác để cho đủ số — đó là thứ từng làm dính spam.
check("không vơ bài của Page khác",
      all(r["page"] == "PAGE_A" for r in _tat_ca))
db.xoa_het_comment_posts(_lc)

_src_cb3 = Path("comment_bai.py").read_text(encoding="utf-8")
check("bốc gấp đôi số bài cần", _cb.UNG_VIEN_GAP == 2
      and "muc_tieu * UNG_VIEN_GAP" in _src_cb3)
check("đủ số bài thì DỪNG", "if ok_n >= muc_tieu or not hang_cau:" in _src_cb3)
# Trùng nhóm là HẠN CHẾ, không CẤM: Page có ít nhóm hơn số bài cần mà cấm cứng
# thì phiên hụt vĩnh viễn. Việc dàn trải do thứ tự ứng viên lo.
check("KHÔNG chặn cứng khi trùng nhóm",
      "if _khoa_nhom(b) in da_xong_nhom:" not in _src_cb3)
check("vẫn đếm và báo số lượt trùng nhóm",
      "so_trung_nhom" in _src_cb3 and "lượt trùng nhóm" in _src_cb3)
# Câu chỉ bị tiêu khi comment lên THẬT — link chết không được ăn mất một suất.
check("link chết không tiêu mất cụm câu",
      "hang_cau.pop(0)            # câu đã lên thật → mới tiêu" in _src_cb3)
_i_pop  = _src_cb3.index("hang_cau.pop(0)")
_i_chet = _src_cb3.index("except BaiDaChet")
check("pop câu nằm ở nhánh THÀNH CÔNG, không ở nhánh link chết",
      _i_pop < _i_chet)
# Báo tiến trình theo SỐ BÀI XONG trên mục tiêu, không theo số ứng viên đã
# duyệt: duyệt 20 ứng viên cho 10 bài, nhìn "14/10" thì tưởng hỏng.
check("tiến trình báo theo mục tiêu, không theo số ứng viên",
      "tien_trinh(min(ok_n, muc_tieu), muc_tieu)" in _src_cb3)
check("hụt bài thì báo rõ ra log", "Hụt {muc_tieu - ok_n} bài" in _src_cb3)

# ── Profile: TÌM thư mục đã có trước, đừng dựng thư mục trắng ──────────────
# Thư mục profile CHÍNH LÀ phiên đăng nhập Facebook. Bản cũ ghép cứng
# `{Tên}_{c_user}`, nên sửa tên nick hoặc đổi c_user là dựng một thư mục TRẮNG:
# nick phải đăng nhập lại, Facebook thấy THIẾT BỊ MỚI — đúng thứ làm tăng rủi
# ro dính spam.
#
# Đo 07/10 trên máy thật: 13 tài khoản mà có 52 thư mục profile. 'Ngân Nguyễn'
# 5 thư mục, 'Thị Sữa' 3, 'Ngan Thi' 3 với hai c_user khác nhau — di chứng của
# lỗi tên dính dấu cách thừa và lỗi nhập nhầm UID Page vào ô c_user.
import tempfile as _tf3
import fb_common as _fbc4
with _tf3.TemporaryDirectory() as _d3:
    _goc_pf = _fbc4.PROFILES_DIR
    _fbc4.PROFILES_DIR = Path(_d3)
    try:
        def _tao_pf(t):
            (Path(_d3, t) / "Default").mkdir(parents=True)
        def _thu_pf(ten, cu):
            truoc = set(os.listdir(_d3))
            r = Path(_fbc4.find_profile_dir(ten, cu)).name
            return r, bool(set(os.listdir(_d3)) - truoc)

        _tao_pf("Ngan_Thi_61593707204364")
        _r, _moi = _thu_pf("Ngan Thi Moi", "61593707204364")
        check("đổi TÊN nick -> dùng lại profile cũ, không mất đăng nhập",
              _r == "Ngan_Thi_61593707204364" and not _moi)

        _tao_pf("Thi_Sua")
        _r, _moi = _thu_pf("Thi Sua", "99999999")
        check("đổi c_user -> dùng lại profile cũ", _r == "Thi_Sua" and not _moi)

        # Tên từng dính dấu cách thừa nên thư mục có HAI gạch dưới.
        _tao_pf("Thị_Sữa__100091883813659")
        _r, _moi = _thu_pf("Thị Sữa", "100091883813659")
        check("thư mục hai gạch dưới (di chứng lỗi cũ) -> vẫn nhận ra",
              _r == "Thị_Sữa__100091883813659" and not _moi)

        _r, _moi = _thu_pf("Nguoi La", "123456789")
        check("nick thật sự mới -> tạo thư mục mới", _moi)

        # Chốt quan trọng nhất: KHÔNG được cướp profile của acc khác trùng tên.
        _tao_pf("Trung_Ten_111111111")
        _r, _moi = _thu_pf("Trung Ten", "222222222")
        check("trùng tên nhưng khác c_user -> KHÔNG cướp profile",
              _r == "Trung_Ten_222222222" and _moi)

        # Nhiều thư mục cùng bậc -> lấy cái DÙNG GẦN ĐÂY NHẤT, không lấy cái to.
        _tao_pf("Ai_Do"); _tao_pf("Ai_Do_111111111")
        _t_moi = Path(_d3, "Ai_Do_111111111")
        os.utime(_t_moi, (9e8, 9e8))            # đặt mốc CŨ
        os.utime(_t_moi / "Default", (9e8, 9e8))
        _r, _ = _thu_pf("Ai Do", "")
        check("nhiều thư mục cùng bậc -> lấy cái dùng gần nhất", _r == "Ai_Do")
    finally:
        _fbc4.PROFILES_DIR = _goc_pf

# ── Dọn thư mục profile: phân loại đúng, và KHOÁ cái đang dùng ─────────────
# Xoá nhầm một profile đang dùng = nick phải đăng nhập lại = Facebook thấy
# thiết bị mới. Nên phân loại phải chắc, và hai nhóm `đang dùng` / `phụ trợ`
# tuyệt đối không được phép xoá.
with _tf3.TemporaryDirectory() as _d4:
    _goc_pf2 = _fbc4.PROFILES_DIR
    _fbc4.PROFILES_DIR = Path(_d4)
    try:
        for _t in ("Nick_A_111111111", "Nick_A", "Nick_B_222222222",
                   "Da_Xoa_999999999", "_quet_market_Nick_A"):
            (Path(_d4, _t) / "Default").mkdir(parents=True)
        _accs = [{"ten_acc": "Nick A", "c_user": "111111111"},
                 {"ten_acc": "Nick B", "c_user": "222222222"}]
        _pl = {x["ten"]: x for x in _fbc4.phan_loai_profile(_accs)}
        check("profile đang dùng -> nhóm 'dang_dung'",
              _pl["Nick_A_111111111"]["nhom"] == "dang_dung"
              and _pl["Nick_B_222222222"]["nhom"] == "dang_dung")
        check("bản cũ của cùng nick -> nhóm 'trung'",
              _pl["Nick_A"]["nhom"] == "trung" and _pl["Nick_A"]["cua_nick"] == "Nick A")
        check("nick đã xoá -> nhóm 'mo_coi'", _pl["Da_Xoa_999999999"]["nhom"] == "mo_coi")
        # Thư mục "_" là của tính năng quét nhóm. Luật "13 acc = 13 thư mục"
        # ngây thơ sẽ xoá oan chúng.
        check("thư mục phụ trợ -> nhóm 'phu_tro', KHÔNG xoá",
              _pl["_quet_market_Nick_A"]["nhom"] == "phu_tro"
              and not _pl["_quet_market_Nick_A"]["xoa_duoc"])
        check("CHỈ 'trung' và 'mo_coi' mới được xoá",
              {t for t, x in _pl.items() if x["xoa_duoc"]}
              == {"Nick_A", "Da_Xoa_999999999"})
    finally:
        _fbc4.PROFILES_DIR = _goc_pf2

# ── Nhịp đập: bắt cơ chế chết lặng ─────────────────────────────────────────
# Lỗi nguy hiểm nhất của phần mềm này không phải lỗi làm nó dừng, mà lỗi làm
# một CƠ CHẾ AN TOÀN chết lặng trong khi mọi thứ khác vẫn chạy. Bốn ca đã xảy
# ra trong tuần 03-07/10, ca nặng nhất im 13 ngày: biến `kq` không tồn tại
# trong hàm kết phiên comment, nằm trong except rộng nên bước dò cảnh báo gỡ
# bài của phiên comment KHÔNG HỀ CHẠY — 178/184 phiên, không ai biết.
import nhip_dap as _nd
db.init_db()
with db._conn() as _c:
    _c.execute("DELETE FROM nhip_dap")
for _ in range(5):
    _nd.ghi("dang_hybrid")
_n = _nd.doc()
check("ghi nhịp rồi đọc lại được", _n.get("dang_hybrid", {}).get("so_lan") == 5)
check("nhịp mới ghi thì giờ im gần 0",
      0 <= (_n["dang_hybrid"]["gio_im"] or 99) < 0.1)

# Cặp đôi đứt gãy — đây là phần giá trị nhất, nó không cần biết hỏng vì lý do
# gì, chỉ cần biết hai thứ đáng ra đi cùng nhau mà nay một cái biến mất.
_nd.ghi("comment")
_vd = dict((c, m) for m, c in _nd.soi())
check("đăng bài chạy mà KHÔNG dò spam -> báo đỏ",
      any("KHÔNG dò cảnh báo" in c and "Đăng bài" in c for c in _vd))
check("comment chạy mà KHÔNG dò spam -> báo đỏ (đúng ca lỗi 13 ngày)",
      any("KHÔNG dò cảnh báo" in c and "comment" in c for c in _vd))
check("đăng bài chạy mà KHÔNG thu link -> báo đỏ",
      any("KHÔNG thu link" in c for c in _vd))
check("cặp đôi đứt gãy ở mức ĐỎ, không phải vàng",
      all(m == "do" for m, _ in _nd.soi() if "KHÔNG" in _))

# Đủ cặp thì im — báo nhầm vài lần là người ta thôi đọc báo cáo.
for _ in range(5):
    _nd.ghi("do_spam_dang"); _nd.ghi("thu_link")
_nd.ghi("do_spam_comment")
check("đủ cặp thì KHÔNG báo gì", _nd.soi() == [])
check("báo cáo liệt kê số lần từng chức năng",
      "Đăng bài (Page): 5 lần" in _nd.bao_cao())

# Cơ chế CHƯA TỪNG chạy thì không báo: máy không bật phiên comment thì
# "comment im lặng" là bình thường. Báo nhầm làm người đọc quen với cảnh báo
# giả rồi bỏ qua cả cảnh báo thật.
with db._conn() as _c:
    _c.execute("DELETE FROM nhip_dap")
_nd.ghi("dang_hybrid"); _nd.ghi("do_spam_dang"); _nd.ghi("thu_link")
check("cơ chế chưa từng chạy -> không báo lỗi", _nd.soi() == [])
check("và cũng không hiện trong báo cáo", "Đi comment" not in _nd.bao_cao())

# Ghi nhịp TUYỆT ĐỐI không được làm hỏng việc chính — mất một nhịp chỉ sai một
# dòng báo cáo, còn ném lỗi ra là hỏng cả phiên đăng.
#
# Kiểm bằng HÀNH VI chứ không dò chữ "try:" trong file như bản trước. Bản trước
# bắt mọi chỗ gọi phải tự bọc try/except, nhưng `ghi()` vốn đã tự nuốt rồi: lớp
# bọc ngoài chỉ che mất dòng cảnh báo của nó chứ không bảo vệ thêm gì. Tệ hơn,
# phép kiểm dò chữ ấy lại ÉP người sau phải giữ lớp bọc thừa đó.
_nd.ghi(None)
check("tên nhịp sai kiểu -> nuốt, không ném ra ngoài", True)


def _ghi_voi_db_hong():
    """Gọi ghi() khi DB hỏng hoàn toàn. Không được ném gì ra ngoài."""
    import sqlite3 as _sq
    that = db._conn

    def _no(*a, **k):
        raise _sq.OperationalError("database is locked")
    db._conn = _no
    try:
        _nd.ghi("dang_hybrid")
        return True
    except Exception:
        return False
    finally:
        db._conn = that


check("DB hỏng thì ghi nhịp vẫn nuốt, không kéo sập phiên", _ghi_voi_db_hong())

# Nuốt thì được, nhưng phải KÊU LÊN. Cả module này sinh ra để phát hiện chức
# năng chết câm; chính nó chết câm thì báo cáo đếm thiếu mà không ai biết.
check("ghi nhịp hỏng thì ghi log mức WARNING, không phải DEBUG",
      "logger.warning" in Path("nhip_dap.py").read_text(encoding="utf-8")
      .split("def ghi(")[1].split("def ")[0])

# Và bên gọi KHÔNG được bọc thêm try/except — bọc là che mất cảnh báo trên.
for _f in ("fb_common.py", "page_via_poster.py", "comment_bai.py", "via_poster.py"):
    _s = Path(_f).read_text(encoding="utf-8").splitlines()
    for _i, _l in enumerate(_s):
        if "nhip_dap.ghi(" in _l:
            _truoc = "\n".join(_s[max(0, _i - 3):_i])
            check(f"{_f}:{_i+1} nhịp KHÔNG bị bọc try thừa", "try:" not in _truoc)
# Bốn luồng đều phải có nhịp — thiếu một luồng là luồng đó mù.
check("cả 4 luồng đều ghi nhịp",
      'nhip_dap.ghi("dang_hybrid")' in Path("page_via_poster.py").read_text(encoding="utf-8")
      and 'nhip_dap.ghi("dang_tuong_page")' in Path("page_via_poster.py").read_text(encoding="utf-8")
      and 'nhip_dap.ghi("comment")' in Path("comment_bai.py").read_text(encoding="utf-8")
      and 'nhip_dap.ghi("dang_hybrid")' in Path("via_poster.py").read_text(encoding="utf-8"))
check("dò spam phân biệt phiên đăng với phiên comment",
      'nhip_dap.ghi("do_spam_comment" if "comment" in (sau_viec or "")'
      in Path("fb_common.py").read_text(encoding="utf-8"))
# Và phải lọt vào bản tin Telegram cuối ngày, nếu không thì không ai đọc.
check("báo cáo nhịp nằm trong bản tổng kết Telegram",
      "nhip_dap.bao_cao()" in Path("thong_bao.py").read_text(encoding="utf-8"))
with db._conn() as _c:
    _c.execute("DELETE FROM nhip_dap")

# ── Dọn TỰ ĐỘNG: bốn lớp chặn, không hỏi người dùng ────────────────────────
# Không đưa việc này lên giao diện: người dùng không cần biết thư mục profile
# là gì, thêm một bảng nữa chỉ làm họ rối. Nhưng chạy ngầm thì phải đủ bốn lớp
# chặn, thiếu một lớp là không được phép chạy.
import time as _tm3
with _tf3.TemporaryDirectory() as _d5:
    _goc_pf3 = _fbc4.PROFILES_DIR
    _fbc4.PROFILES_DIR = Path(_d5)
    try:
        _cu = _tm3.time() - 30 * 86400      # 30 ngày trước
        _moi = _tm3.time() - 1 * 86400      # hôm qua
        def _tao2(t, moc):
            d = Path(_d5, t); (d / "Default").mkdir(parents=True)
            os.utime(d, (moc, moc)); os.utime(d / "Default", (moc, moc))
        _tao2("Nick_A_111111111", _cu)      # đang dùng, nhưng CŨ
        _tao2("Nick_A", _cu)                # trùng, cũ      -> xoá
        _tao2("Nick_A_cu_moi", _cu)         # mồ côi, cũ     -> xoá
        _tao2("Da_Xoa_999999999", _moi)     # mồ côi nhưng MỚI -> giữ
        _tao2("_quet_market_X", _cu)        # phụ trợ, cũ    -> giữ
        _acc2 = [{"ten_acc": "Nick A", "c_user": "111111111"}]

        _r = _fbc4.don_profile_rac(_acc2, ngay_cho=14, that=False)
        check("lớp 1+2: KHÔNG đụng thư mục đang dùng",
              "Nick_A_111111111" not in _r["xoa"])
        check("lớp 1: KHÔNG đụng thư mục phụ trợ", "_quet_market_X" not in _r["xoa"])
        check("lớp 3: thư mục còn MỚI thì giữ, dù là mồ côi",
              "Da_Xoa_999999999" not in _r["xoa"] and _r["bo_qua_vi_moi"] == 1)
        check("xoá đúng thứ cần xoá", set(_r["xoa"]) == {"Nick_A", "Nick_A_cu_moi"})
        check("that=False thì KHÔNG xoá thật", Path(_d5, "Nick_A").exists())

        _r2 = _fbc4.don_profile_rac(_acc2, ngay_cho=14, that=True)
        check("that=True thì xoá thật", not Path(_d5, "Nick_A").exists()
              and Path(_d5, "Nick_A_111111111").exists()
              and Path(_d5, "_quet_market_X").exists()
              and Path(_d5, "Da_Xoa_999999999").exists())
        # Chạy lại lần nữa phải KHÔNG còn gì — không được xoá lặp hay báo nhầm.
        check("chạy lại lần nữa thì không còn gì để xoá",
              _fbc4.don_profile_rac(_acc2, ngay_cho=14, that=True)["xoa"] == [])

        # Ngưỡng ngày phải ĐỦ RỘNG. Acc nghỉ vì dính spam lâu nhất cũng chỉ vài
        # ngày; đặt ngưỡng ngắn là xoá mất profile của nick đang nghỉ.
        check("ngưỡng coi là rác ít nhất 7 ngày", _fbc4.NGAY_COI_LA_RAC >= 7)
    finally:
        _fbc4.PROFILES_DIR = _goc_pf3

# Phân loại chỉ được HỎI, không được tạo thư mục — nếu không thì mỗi lượt quét
# lại đẻ một thư mục rỗng cho nick chưa chạy phiên nào, tức tự sinh rác cho
# chính mình dọn.
with _tf3.TemporaryDirectory() as _d6:
    _goc_pf4 = _fbc4.PROFILES_DIR
    _fbc4.PROFILES_DIR = Path(_d6)
    try:
        _fbc4.phan_loai_profile([{"ten_acc": "Chua Chay", "c_user": "123456789"}])
        check("phân loại KHÔNG tạo thư mục rỗng", os.listdir(_d6) == [])
        check("find_profile_dir(tao_moi=False) trả rỗng khi chưa có",
              _fbc4.find_profile_dir("Chua Chay", "123456789", tao_moi=False) == "")
    finally:
        _fbc4.PROFILES_DIR = _goc_pf4

# Chạy ngầm trong scheduler, và CHỈ MỘT runner làm — năm runner cùng quét là
# năm lượt đọc đĩa trùng nhau, lại giẫm chân nhau lúc xoá.
_src_sch_pf = Path("scheduler.py").read_text(encoding="utf-8")
check("scheduler có gọi dọn profile", "don_profile_rac(get_accounts())" in _src_sch_pf)
check("chỉ MỘT runner quét (mảng bật đầu tiên), không phải cả năm",
      "if LOAI == _runner_don:" in _src_sch_pf)
# Và KHÔNG đưa lên giao diện.
check("không có bảng dọn profile trong giao diện",
      "api/profiles" not in Path("server.py").read_text(encoding="utf-8")
      and "pfXoa" not in Path("static/js/app.js").read_text(encoding="utf-8"))

# ── Bản CÀI ĐẶT phải cập nhật được ─────────────────────────────────────────
# Lỗi gặp trên máy vệ tinh mới 07/10: cài xong, bấm vào số phiên bản thì hiện
# "Thư mục này chưa phải kho code git" — tức KHÔNG BAO GIỜ cập nhật được.
#
# Hai nguyên nhân chồng nhau, cả hai đều chỉ xảy ra với bản cài:
#   1. Bộ cài lấy mã nguồn bằng `git archive` nên chỉ có FILE, không có `.git`.
#   2. Máy mới không có git trong PATH; bộ cài gói MinGit vào `<app>\git\`,
#      mà `_git` lại gọi bare "git" nên trượt hết.
#
# `UPDATE.bat` vốn tự dựng kho khi chạy, nhưng nút Cập nhật chết ngay từ bước
# LIỆT KÊ nên không ai tới được chỗ đó.
_src_srv_cn = Path("server.py").read_text(encoding="utf-8")
check("link kho khớp giữa server.py và UPDATE.bat",
      'REPO_URL = "https://github.com/M3SSI-666/MNT_FB_TOOL.git"' in _src_srv_cn
      and "M3SSI-666/MNT_FB_TOOL.git" in Path("UPDATE.bat").read_text(encoding="utf-8",
                                                                     errors="ignore"))
check("ưu tiên git KÈM THEO bản cài trước git của máy",
      'kem = BASE_DIR / "git" / "cmd" / "git.exe"' in _src_srv_cn
      and 'return str(kem) if kem.exists() else "git"' in _src_srv_cn)
check("mọi lệnh git đều đi qua _tim_git", "[_tim_git(), *args]" in _src_srv_cn
      and '["git", *args]' not in _src_srv_cn)
check("thiếu .git thì tự dựng kho", "def _dung_kho_neu_thieu" in _src_srv_cn
      and '_git("remote", "add", "origin", REPO_URL)' in _src_srv_cn)
# Phải dựng kho TRƯỚC khi fetch, nếu không thì fetch trượt rồi tag cũng trượt.
_i_dung = _src_srv_cn.index("_dung_kho_neu_thieu()")
_i_fetch = _src_srv_cn.index('_git("fetch", "--tags"')
check("dựng kho TRƯỚC khi fetch", _i_dung < _i_fetch)
# Hai nguyên nhân phải báo khác nhau — gộp một câu thì người dùng sửa nhầm thứ.
check("phân biệt 'không có git' với 'chưa phải kho'",
      "Không chạy được git trên máy này." in _src_srv_cn
      and "Thư mục này chưa phải kho code git." in _src_srv_cn)

# ── File .bat: không ngủ bằng ping.exe, và phải giữ CRLF ───────────────────
# Lỗi gặp trên máy thật 06/10: chạy cập nhật thì bật hộp thoại
#   "PING.EXE - Application Error (0xc0000142)"
# Hộp thoại đó CHẶN, phải bấm OK mới đi tiếp, nên bản cập nhật đứng hẳn.
# 0xc0000142 = tiến trình không khởi tạo được; lúc cập nhật máy đang có hàng
# trăm tiến trình Chromium nên tạo thêm exe nào cũng có thể trượt. ping.exe ở
# đó chỉ để ĐẾM GIỜ — một việc vặt mà làm hỏng cả bản cập nhật.
_bat = sorted(Path(".").glob("*.bat"))
check("có đủ file .bat để kiểm", len(_bat) >= 5)
# Chỉ soi dòng LỆNH, bỏ qua dòng chú thích: chú thích có nhắc tới ping là
# chuyện bình thường, chính chỗ sửa cũng phải giải thích vì sao bỏ nó.
_ping = []
for _f in _bat:
    for _l in _f.read_text(encoding="utf-8", errors="ignore").splitlines():
        _t = _l.strip().lower()
        if _t.startswith("::") or _t.startswith("rem "):
            continue
        if "ping -n" in _t:
            _ping.append(f"{_f.name}: {_l.strip()[:50]}")
check("không file .bat nào ngủ bằng ping.exe", not _ping)

# CRLF: file .bat dùng LF thì `call :nhãn` KHÔNG TÌM THẤY NHÃN — cmd báo
# "The system cannot find the batch label specified". Tự dẫm phải khi sửa lỗi
# này: ghi lại file bằng Python làm mất CRLF, và mọi `call :cho` hỏng im lìm.
#
# `.gitattributes` đã có `*.bat text eol=crlf` nên máy clone về luôn nhận CRLF.
# Phép kiểm này canh chỗ khác: file bị CÔNG CỤ ghi đè ngay trong thư mục làm
# việc — đúng thứ vừa xảy ra — mà git thì chuẩn hoá lúc commit nên không lộ ra
# ở diff, chạy thử tại chỗ mới thấy.
_lf = []
for f in _bat:
    b = f.read_bytes()
    if b.count(b"\n") - b.count(b"\r\n") > 0:
        _lf.append(f.name)
check("mọi file .bat đều dùng CRLF", not _lf)

# Đường chờ thay thế phải CÓ THẬT và có đường lui.
for _f in ("UPDATE.bat", "RESTART.bat"):
    _s = Path(_f).read_text(encoding="utf-8", errors="ignore")
    check(f"{_f} có nhãn :cho", "\n:cho\r" in _s or "\n:cho\n" in _s)
    check(f"{_f} gọi :cho thay cho ping", "call :cho " in _s)
    # `timeout` KHÔNG dùng được làm đường lui: nó thoát ngay khi stdin bị
    # chuyển hướng — đo thật: bảo chờ 1 giây mà chỉ tốn 0,02 giây.
    check(f"{_f} đường lui dùng PowerShell, không dùng timeout",
          "Start-Sleep -Seconds %1" in _s and "timeout /t %1" not in _s)

# ── Không mở được composer thì CHUYỂN VAI LẠI, đừng bỏ cuộc ────────────────
# Đo trên log 876 phiên ngày 05-06/10:
#     bấm được nút "Chuyển ngay" -> hỏng composer   3/833 = 0,4%
#     KHÔNG bấm được             -> hỏng composer   9/52  = 17,3%  (gấp 43 lần)
# Chỉ tiêm cookie i_user mà không bấm nút là chuyển vai không trọn vẹn, vào
# nhóm thì ô soạn bài của Page không dựng ra. Mở đúng nhóm ấy bằng tay — cả vai
# cá nhân lẫn vai Page — thì composer hiện bình thường, tức nhóm và acc không
# sao. Mỗi nick chỉ dùng MỘT nhóm làm cửa vào nên bỏ cuộc ở đây là chết cả nick.
_src_pvp4 = Path("page_via_poster.py").read_text(encoding="utf-8")
check("tìm nút 'Chuyển ngay' thử 2 lượt",
      "for _lan in range(2):" in _src_pvp4
      and "Không thấy nút 'Chuyển ngay' sau 2 lượt" in _src_pvp4)
check("không mở được composer thì chuyển vai lại rồi thử tiếp",
      "chuyển vai Page lại rồi thử lần nữa" in _src_pvp4
      and "Mở được composer sau khi chuyển vai lại" in _src_pvp4)
# Lần thử lại phải ĐỨNG TRƯỚC chỗ ném lỗi, nếu không thì vô nghĩa.
_i_thu_lai = _src_pvp4.index("chuyển vai Page lại rồi thử lần nữa")
_i_nem     = _src_pvp4.index('raise LoiBuoc(f"Không mở được ô soạn bài')
check("thử lại TRƯỚC khi bỏ cuộc", _i_thu_lai < _i_nem)
# Và phải chuyển vai thật, không chỉ tải lại trang — chính cú chuyển vai mới là
# thứ còn thiếu.
_doan = _src_pvp4[_i_thu_lai:_i_nem]
check("lần thử lại có gọi _switch_to_page",
      "await _switch_to_page(page, ctx, page_uid)" in _doan)

# ── Thấy popup giữa phiên đăng thì DỪNG NGAY ───────────────────────────────
# Duong chốt 05/10: sau khi chui vào Page mà thấy popup gỡ bài / gỡ bình luận /
# spam thì gán cờ cho acc đang chạy phiên và dừng luôn, không đăng tiếp.
# Khác hẳn cách cũ: cũ chỉ tổng kết ở CUỐI phiên, tức vẫn đăng xong rồi mới biết.
import suc_khoe_acc as _skd
_MAU_SU_VIEC = ("Sự việc 5 tháng 10, 2026 Chúng tôi đã gỡ một số nội dung "
                "hoặc tin nhắn Spam Đã gỡ bài viết")
check("popup gỡ bài -> dừng phiên",
      _skd.ly_do_dung_phien(_MAU_SU_VIEC) == "gỡ bài viết")
# Gỡ BÌNH LUẬN: `doc_vi_pham` cố tình bỏ qua vì nó đếm số vụ gỡ BÀI. Ở đây thì
# tính — đang đăng mà bị gỡ bình luận cũng là Facebook vừa ra tay với acc này.
check("popup gỡ bình luận -> cũng dừng phiên",
      _skd.ly_do_dung_phien("Sự việc Chúng tôi đã gỡ bình luận của bạn")
      == "gỡ bình luận")
check("doc_vi_pham vẫn KHÔNG tính gỡ bình luận là vụ gỡ bài",
      _skd.doc_vi_pham("Sự việc Chúng tôi đã gỡ bình luận của bạn") is None)
check("popup chỉ có chữ spam -> vẫn dừng",
      _skd.ly_do_dung_phien("Sự việc Chúng tôi đã gỡ nội dung Spam") == "spam")
# Chữ "spam" một mình quá rộng để tự nó là bằng chứng — thiếu chốt "sự việc"
# thì mọi trang trợ giúp nhắc tới spam đều làm dừng phiên.
check("trang thường có chữ 'spam' -> KHÔNG dừng",
      _skd.ly_do_dung_phien("Cách báo cáo spam trên Facebook - Trung tâm trợ giúp")
      == "")
check("chuỗi rỗng -> không dừng", _skd.ly_do_dung_phien("") == "")

# Mốc "đã vào Page" phải TÁCH khỏi mốc "đã đăng": hộp Sự việc dính dai, thường
# bật sẵn ngay lúc đăng nhập — đó là chuyện của phiên trước, không được tính.
import fb_common as _fbc3
class _TrangGia2:
    pass
_tg3 = _TrangGia2()
_fbc3._nho_canh_bao(_tg3, "cảnh báo CŨ, thấy lúc đăng nhập")
_fbc3.danh_dau_vao_page(_tg3)
check("cảnh báo TRƯỚC khi vào Page -> không tính",
      _fbc3.canh_bao_sau_khi_vao_page(_tg3) == "")
_fbc3._nho_canh_bao(_tg3, _MAU_SU_VIEC)
check("cảnh báo SAU khi vào Page -> tính",
      _fbc3.canh_bao_sau_khi_vao_page(_tg3) == _MAU_SU_VIEC)
_fbc3._quen_canh_bao(_tg3)
check("quên cảnh báo thì xoá cả mốc vào Page",
      _fbc3.canh_bao_sau_khi_vao_page(_tg3) == "")

_src_pvp3 = Path("page_via_poster.py").read_text(encoding="utf-8")
check("đánh mốc ngay sau khi chuyển sang Page",
      "danh_dau_vao_page(page)" in _src_pvp3)
# Dò ở NHIỀU chặng, trong đó chặng quan trọng nhất là NGAY TRƯỚC khi bấm Đăng —
# sau cú bấm thì bài đã lên, dừng cũng không rút lại được.
check("dò ít nhất 3 chặng trong phiên đăng",
      _src_pvp3.count("await dung_neu_dinh_spam(") >= 3)
check("có dò ngay trước khi bấm Đăng",
      'dung_neu_dinh_spam(page, acc_name, "ngay trước khi bấm Đăng"' in _src_pvp3)
_i_do_cuoi = _src_pvp3.index('"ngay trước khi bấm Đăng"')
_i_bam     = _src_pvp3.index('# Click "Đăng"')
check("dò ĐỨNG TRƯỚC cú bấm Đăng", _i_do_cuoi < _i_bam)
# Phải đi đúng đường Spam, không rơi vào nhánh lỗi chung — ở đó nó bị ghi
# "lỗi [other]" rồi cộng vào lịch sử hỏng, sai hẳn bản chất.
_src_sch = Path("scheduler.py").read_text(encoding="utf-8")
check("scheduler bắt riêng DinhSpamGiuaPhien",
      "except DinhSpamGiuaPhien as e:" in _src_sch)
_i_spam = _src_sch.index("except DinhSpamGiuaPhien")
_i_chung = _src_sch.index("except Exception as e:", _i_spam)
check("bắt TRƯỚC nhánh lỗi chung", _i_spam < _i_chung)
check("là lỗi riêng, không phải Exception trống",
      "class DinhSpamGiuaPhien(PostError):" in
      Path("utils.py").read_text(encoding="utf-8"))

# ── Không được đọc tên biến không tồn tại ──────────────────────────────────
# Ngày 22/09, commit "Sửa: quy kết spam cho sai nick" để lại trong
# `comment_bai._ket_phien` một dòng đọc biến `kq` vốn không có ở đó. Dòng ấy
# nằm trong try/except Exception nên NameError bị nuốt thành log hiền lành
# "Kết phiên không trọn vẹn", và bước DÒ SPAM của phiên comment không hề chạy
# suốt 13 ngày — 178 lần hỏng trên 184 phiên mà bảng vẫn báo bình thường.
#
# Python không bắt được loại này lúc nạp module. Chỗ nguy hiểm nhất lại chính
# là nhánh hiếm chạy, bọc trong except rộng — đúng chỗ mắt người khó soi nhất.
from kiem_ten_bien import quet as _quet_ten
_ten_loi = _quet_ten(".")
if _ten_loi:
    # In ra ngay chỗ hỏng, đừng để người đọc phải tự đi dò lại cả dự án.
    for _f, _l, _h, _t in _ten_loi[:8]:
        print(f"        → {_f}:{_l} trong {_h}() đọc '{_t}' mà không có")
check("không file nào đọc tên biến không tồn tại", not _ten_loi)
# Máy quét phải thật sự bắt được — dựng lại đúng lỗi 22/09 để kiểm chứng.
import tempfile as _tf2
with _tf2.TemporaryDirectory() as _d2:
    Path(_d2, "gia.py").write_text(
        "async def f(page):\n    try:\n        if kq.get('x'):\n"
        "            pass\n    except Exception:\n        pass\n", encoding="utf-8")
    check("máy quét bắt được đúng lỗi 22/09",
          any(t == "kq" for *_, t in _quet_ten(_d2)))
# Và bước dò spam của phiên comment phải thật sự gọi được tới.
# KHÔNG so vị trí trong file: `_ket_phien` được ĐỊNH NGHĨA phía trên vòng lặp
# comment nhưng CHẠY sau nó. So thứ tự dòng ở đây là so nhầm thứ.
check("đánh mốc ngay khi câu comment ĐẦU TIÊN lên",
      "if ok_n == 1:" in _src_cb2 and "danh_dau_da_dang(page)" in _src_cb2)
# Mốc phải nằm trong vòng lặp comment, không phải trong hàm kết phiên — đánh ở
# kết phiên là muộn, cảnh báo vòng canh bắt giữa phiên sẽ nằm trước mốc.
_i_ket  = _src_cb2.index("async def _ket_phien")
_i_chay = _src_cb2.index("async def _chay_phien")
_i_moc  = _src_cb2.index("danh_dau_da_dang(page)")
check("mốc nằm trong vòng lặp comment, không nằm ở hàm kết phiên",
      _i_moc > _i_chay and not (_i_ket < _i_moc < _i_chay))
check("hàm kết phiên KHÔNG còn tự đánh mốc",
      "danh_dau_da_dang" not in _src_cb2[_i_ket:_i_chay])
check("chỉ một nơi giữ dấu hiệu bài chết",
      "BAI_KHONG_XEM_DUOC" not in _src_tl)
# Đăng xong thì ra FEED của Page, không ngồi lại nhóm vừa đăng.
check("đăng xong ra feed Page lướt + thả tim",
      'await page.goto("https://www.facebook.com/",' in _src_pvp2
      and "Lướt feed Page" in _src_pvp2
      and "max_likes=1" in _src_pvp2)

# ── Cửa sổ dò spam phải đủ dài ─────────────────────────────────────────────
# Lỗi đã mắc ở v2.33.0: bỏ 85 giây chờ thông báo đăng chéo để rút ngắn phiên,
# mà KHÔNG nhận ra bước dò cảnh báo gỡ bài đang ăn nhờ chính quãng chờ đó.
# Cửa sổ tụt từ ~100-115s còn ~17-28s. `kiem_vi_pham` nói rõ trong docstring là
# "phải chờ vài chục giây SAU khi đăng, dò sớm quá chỉ thấy vụ của hôm trước".
#
# Hai test dưới chốt sự phụ thuộc đó lại: bước lướt feed sau khi đăng KHÔNG
# được rút ngắn mà không sửa luôn bước dò spam.
import fb_common as _fbc2
check("quãng chờ sau khi đăng quanh 75 giây",
      _fbc2.CHO_SAU_DANG_GIAY == (72, 78))
# Phải bám mốc 76s — dưới mốc đó là chắc chắn hụt link mỗi phiên. Trên mốc thì
# vẫn có thể hụt (phiên A đo 02/10 mới được 7/9 ở giây 76), nhưng ít hơn hẳn.
check("quãng chờ chạm được mốc 76 giây",
      max(_fbc2.CHO_SAU_DANG_GIAY) >= 76)
check("Page lướt feed đúng bằng cửa sổ dò spam",
      "random.randint(*CHO_SAU_DANG_GIAY)" in _src_pvp2)
# Lướt feed phải ĐỨNG TRƯỚC dò spam, nếu không thì cửa sổ bằng 0.
_i_luot = _src_pvp2.index("random.randint(*CHO_SAU_DANG_GIAY)")
_i_dospam = _src_pvp2.index('kiem_vi_pham(page, acc_name, "phiên đăng Page"')
check("lướt feed trước, dò spam sau", _i_luot < _i_dospam)
# Con số sống ở MỘT nơi, cạnh chính hàm phụ thuộc vào nó.
check("không ghi cứng lại con số ở poster",
      "randint(55, 65)" not in _src_pvp2)
# Nguồn (a) phải giữ: nhóm mở composer KHÔNG sinh thông báo đăng chéo nào, bỏ
# đi là mất đúng một link mỗi lần đăng.
check("vẫn giữ nguồn bắt link từ phản hồi mạng",
      "[a] Phản hồi mạng" in _src_pvp2)
check("Page còn 5 bước", "[5/5]" in _src_pvp2 and "[6/6]" not in _src_pvp2)

# ── Mỗi phiên tự ghi thời lượng ────────────────────────────────────────────
# Trước đây muốn biết một phiên tốn bao lâu phải chạy script đo riêng, nên
# không ai biết phiên thật tốn bao nhiêu cho tới khi đi đo. Nay tự ghi.
check("phiên Page tự ghi thời lượng",
      "Phiên Page [{acc_name}]" in _src_pvp2 and "_t0 = time.time()" in _src_pvp2)
# Phải nằm trong `finally`: phiên HỎNG mà mất 400 giây là chuyện khác hẳn phiên
# hỏng sau 20 giây, mà nhìn log lỗi thì không phân biệt được.
_i_try  = _src_pvp2.index("        ok = asyncio.run(_run_page_via(")
_i_fin  = _src_pvp2.index("    finally:", _i_try)
_i_ghi  = _src_pvp2.index("⏱️  Phiên Page")
check("ghi thời lượng cả khi phiên hỏng", _i_ghi > _i_fin)
# Đo từ trước bước tải ảnh, không phải từ lúc mở Chrome — tải ảnh cũng là một
# phần của phiên. Neo trong THÂN `post_page_via`: dòng tải ảnh có ở cả hàm đăng
# tường Page phía trên, tìm từ đầu file là bắt nhầm hàm kia.
_i_pvia = _src_pvp2.index("def post_page_via(")
check("tính cả thời gian tải ảnh",
      _src_pvp2.index("_t0 = time.time()", _i_pvia)
      < _src_pvp2.index("📥 Download ảnh", _i_pvia))

# 2. Tìm nút bằng MỘT lần hỏi DOM thay cho chuỗi wait_for_selector. Đo 02/10:
#    riêng bước tìm nút "Chuyển" tiêu 8 giây để rồi không tìm thấy gì.
check("chuyển Page tìm nút trong một lần hỏi",
      "_JS_TIM_NUT" in _src_pvp2 and "async def _bam_nut" in _src_pvp2)
check("bỏ chuỗi wait_for_selector khi chuyển Page",
      'wait_for_selector(\n            \'div[role="button"]:has-text("Chuyển ngay")\''
      not in _src_pvp2)
check("chỉ bấm nút đang nhìn thấy", "elementFromPoint" in _src_pvp2)

# 3. Soạn bài DÁN bằng clipboard, KHÔNG gõ từng ký tự.
#    Đo ngày 02/10: gõ 702 ký tự mất 29 giây, dán mất ~1 giây. Mỗi phím là một
#    vòng gọi sang trình duyệt, chi phí thật ~40ms/ký tự — đắt gấp 29 lần dán.
check("soạn bài bằng clipboard",
      "await _clipboard_paste(page, ctx, message)" in _src_pvp2)
check("không còn hàm gõ từng ký tự",
      "go_noi_dung" not in _src_pvp2 and "go_noi_dung" not in _src_fbc2)

check("kết phiên like đúng 1 bài",            _cb.KET_LIKE == 1)

# ── Xem story CHỈ còn ở phiên nuôi nick ────────────────────────────────────
# Duong bỏ bước lướt story khỏi mọi phiên đăng bài và comment, chỉ giữ ở nuôi
# nick. Giữ được bao lâu là nhờ test này: thêm lại một dòng `view_stories` vào
# poster thì phiên dài thêm ~20 giây mỗi lượt mà không ai để ý.
_F_KHONG_STORY = ("via_poster.py", "page_via_poster.py", "comment_bai.py")
for _f in _F_KHONG_STORY:
    _s = Path(_f).read_text(encoding="utf-8")
    check(f"{_f} KHÔNG xem story", "view_stories(" not in _s)
check("nuôi nick VẪN xem story",
      "view_stories(page" in Path("nuoi_nick.py").read_text(encoding="utf-8"))
check("fb_common vẫn giữ hàm view_stories cho nuôi nick",
      "async def view_stories" in Path("fb_common.py").read_text(encoding="utf-8"))

# Bỏ một bước thì phải đánh số lại, nếu không log ghi "[2/7]" mà phiên chỉ có 6
# bước — đọc log để lần lỗi sẽ tưởng mất bước.
import re as _re_buoc
for _f, _tong in (("via_poster.py", 5), ("page_via_poster.py", 5)):
    _s = Path(_f).read_text(encoding="utf-8")
    _b = _re_buoc.findall(r"\[(\d)/(\d)\]", _s)
    _b = [(int(a), int(t)) for a, t in _b if int(t) == _tong]
    # So theo TẬP chứ không theo danh sách: page_via_poster có hai luồng (đăng
    # chéo nhóm và đăng tường Page), nay cả hai đều 5 bước nên mỗi số xuất hiện
    # hai lần. Điều cần canh là không hụt số nào, không phải số lần xuất hiện.
    check(f"{_f}: số bước liền mạch 1..{_tong}",
          sorted({a for a, _ in _b}) == list(range(1, _tong + 1)))

# Lý do bỏ qua
check("danh sách trống -> báo trống", _cb.ly_do_bo_qua([]) == "danh sách trống")
check("còn link -> không bỏ qua",     _cb.ly_do_bo_qua([{"url": "x"}]) == "")

# Chia câu theo chủ sở hữu bài: bài của chính Page mình được nhiều câu hơn.
_UID = "P1"
_BAI = [{"id": 1, "url": "u1", "page": "P1"},      # chính chủ
        {"id": 2, "url": "u2", "page": "P9"},      # Page khác
        {"id": 3, "url": "u3", "page": "P1"}]      # chính chủ
_POOL = [f"c{i}" for i in range(12)]

check("nhận ra bài chính chủ",    _cb.la_chinh_chu(_BAI[0], _UID))
check("bài Page khác không phải chính chủ", not _cb.la_chinh_chu(_BAI[1], _UID))
check("không có Page -> không ai là chính chủ", not _cb.la_chinh_chu(_BAI[0], ""))

_b, _c = _cb.chia_cau_cho_bai(_BAI, _POOL, 3, _UID)
check("chỉ giữ bài CHÍNH CHỦ",     [b["id"] for b in _b] == [1, 3])
check("bài Page khác bị loại hẳn", all(_cb.la_chinh_chu(b, _UID) for b in _b))
check("mỗi bài nhận đúng 3 câu",   all(len(x) == 3 for x in _c))
check("tổng câu = 2 bài × 3",      sum(len(x) for x in _c) == 6)

# Hai câu trên CÙNG một bài mà giống hệt nhau thì lộ ngay. pick_messages đảm bảo
# không trùng liền kề, và vì cắt từ MỘT dãy chung nên ràng buộc đó xuyên qua cả
# ranh giới giữa hai bài — bài này không kết thúc bằng đúng câu bài sau mở đầu.
_phang = [x for cum in _c for x in cum]
check("không câu nào trùng câu liền trước",
      all(_phang[i] != _phang[i - 1] for i in range(1, len(_phang))))

# Không có bài chính chủ nào -> phiên rỗng, TUYỆT ĐỐI không lấp bằng bài Page
# khác. Đi comment dưới bài của Page lạ khiến nick dính spam.
_b0, _c0 = _cb.chia_cau_cho_bai([_BAI[1]], _POOL, 3, _UID)
check("không có bài chính chủ -> rỗng", _b0 == [] and _c0 == [])

_b1, _c1 = _cb.chia_cau_cho_bai(_BAI, _POOL, 0, _UID)
check("số câu = 0 -> không còn bài nào", _b1 == [] and _c1 == [])

# Không truyền Page thì không có "chính chủ" nào -> cũng rỗng
_b2, _c2 = _cb.chia_cau_cho_bai(_BAI, _POOL, 3, "")
check("không có Page -> rỗng", _b2 == [] and _c2 == [])

# Thư viện ít câu hơn nhu cầu vẫn phải chạy được, không ném lỗi
_b3, _c3 = _cb.chia_cau_cho_bai(_BAI, ["x", "y"], 3, _UID)
check("thư viện 2 câu vẫn đủ chia 6 lượt", sum(len(x) for x in _c3) == 6)

# Hai comment dưới CÙNG một bài phải giãn hơn hai comment ở hai bài khác nhau —
# cùng một Page gõ liền hai câu dưới một bài là thứ dễ thấy nhất.
#
# Từng đòi cận DƯỚI phải lớn hơn cận trên của nghỉ-giữa-2-bài (20 > 15). Phải
# nới điều kiện vì khoảng 20–45s kéo phiên comment từ 5,3 lên 11,9 phút, gây ra
# sự cố cạn RAM ngày 13/09/2026. Nay giữ đúng phần cốt lõi: không ngắn hơn, và
# vươn xa hơn ở cận trên.
check("nghỉ giữa 2 câu không ngắn hơn nghỉ giữa 2 bài",
      _cb.NGHI_GIUA_2_CAU[0] >= _cb.DEFAULTS["comment_nghi_min"])
check("nghỉ giữa 2 câu vươn xa hơn ở cận trên",
      _cb.NGHI_GIUA_2_CAU[1] > _cb.DEFAULTS["comment_nghi_max"])

# Mọi quãng nghỉ đều phải là KHOẢNG, không được là số cố định: comment đều tăm
# tắp đúng một nhịp là dấu hiệu máy — chính thứ utils.jitter_ms sinh ra để tránh.
check("nghỉ giữa 2 câu là một khoảng",  _cb.NGHI_GIUA_2_CAU[1] > _cb.NGHI_GIUA_2_CAU[0])
check("nghỉ giữa 2 bài là một khoảng",
      _cb.DEFAULTS["comment_nghi_max"] > _cb.DEFAULTS["comment_nghi_min"])

# Dán thay vì gõ từng ký tự (theo yêu cầu rút gọn phiên). Khoá lại bằng test vì
# đây là thay đổi CÓ ĐÁNH ĐỔI — gõ từng ký tự giống người hơn — nên nếu ai đó
# đổi ngược lại thì phải là quyết định có ý thức, không phải vô tình.
import inspect as _insp
_src_gui = _insp.getsource(_cb._gui_mot_cau)
check("comment DÁN, không gõ từng ký tự", "keyboard.type" not in _src_gui)
check("có ghi clipboard trước khi dán",   "ghi_clipboard" in _src_gui)
# Ghi clipboard PHẢI đứng trước cú bấm vào ô: nhánh dự phòng tạo <textarea> ẩn
# rồi focus vào nó, làm ngược lại thì ô bình luận mất con trỏ, Ctrl+V rơi ra ngoài.
check("ghi clipboard trước khi bấm vào ô",
      _src_gui.index("ghi_clipboard") < _src_gui.index("box.click()"))
check("dán bằng Ctrl+V",                  "Control+v" in _src_gui)

# ctx phải đi xuyên tới _gui_mot_cau — thiếu nó thì không xin được quyền
# clipboard và luôn rơi vào nhánh dự phòng.
check("ctx truyền được tới hàm dán",
      "ctx" in str(_insp.signature(_cb._gui_mot_cau))
      and "ctx" in str(_insp.signature(_cb._comment_mot_bai)))

# Thư viện câu
check("tách câu bỏ dòng trống/trùng",
      _cb.tach_cau("a\n\n b \na\nc") == ["a", "b", "c"])
check("thư viện rỗng -> []",          _cb.tach_cau("   \n\n") == [])
_pick = nuoi_nick.pick_messages(_cb.tach_cau("c1\nc2\nc3"), 9)
check("bốc đủ câu cho 9 bài",         len(_pick) == 9)
check("KHÔNG lặp câu ở 2 bài liền nhau",
      all(_pick[i] != _pick[i+1] for i in range(len(_pick) - 1)))
db.xoa_het_comment_posts("homestay")

# ── Thu link: đọc từ trang thông báo ──────────────────────────────
import thu_link as _tl
import asyncio as _aio2


# ── Hộp thoại 'Anonymous post': dò MỘT lần thay vì 5 lần tuần tự ───────────
# Dò lần lượt thì mỗi mẫu chờ trọn wait_ms, nên lúc không có hộp thoại phải trả
# đủ 5 × 3s = 15s. Đếm trên log thật: 350 lượt gọi, 0 lượt thấy hộp thoại.
check("gộp đủ 5 mẫu vào một selector", _fc.ANON_GOP.count(",") >= len(_fc.ANON_SELECTORS) - 1)
check("mọi mẫu đều có trong selector gộp",
      all(m in _fc.ANON_GOP for m in _fc.ANON_SELECTORS))


class _TrangDem:
    """Đếm số lần wait_for_selector — phải đúng 1, không phải 5."""
    def __init__(self): self.lan = 0
    async def wait_for_selector(self, sel, timeout=None, state=None):
        self.lan += 1
        from playwright.async_api import TimeoutError as PWT
        raise PWT("khong co")
    async def query_selector(self, sel): return None


_t2 = _TrangDem()
check("không có hộp thoại -> chỉ chờ MỘT lần",
      _aio2.run(_fc.dismiss_anon_dialog(_t2, wait_ms=3000)) is False and _t2.lan == 1)


# ── Thu link bài vừa đăng: đọc từ trang thông báo ──────────────────────────

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

# Cửa sổ lọc thông báo. TRƯỚC ĐÂY phải ≤10 phút vì thu link ngay sau khi đăng:
# rộng quá là vơ luôn thông báo của lần đăng TRƯỚC bằng cùng Page, mà nếu lần đó
# thuộc loại lịch khác thì link lưu nhầm hạng mục (đã xảy ra: 7 link Homestay
# lọt vào Thuê).
#
# NAY thu link ở ĐẦU phiên sau nên phải nới rộng — chính thông báo của phiên
# trước mới là thứ cần lấy. Nới được là nhờ hai điều kiện đã kiểm trên dữ liệu
# thật ngày 02/10:
#   - Không Page nào phục vụ quá một loại lịch (0/12) → không gán nhầm hạng mục.
#   - `them_comment_posts` bỏ trùng theo URL → không sinh link lặp.
import re as _re
_src = Path("page_via_poster.py").read_text(encoding="utf-8")
_m = _re.search(r"thu_tu_thong_bao\(page,\s*toi_da_phut=(\d+)\)", _src)
check("cửa sổ lọc đủ rộng để lấy phiên trước",
      _m is not None and int(_m.group(1)) >= 120)
# Điều kiện khiến việc nới rộng an toàn — hỏng là phải biết ngay.
check("không Page nào phục vụ quá một loại lịch",
      max((len({db.loai_content_cua_acc(a["loai_dang"])
                for a in db.get_accounts()
                if (a.get("ten_page") or "").strip() == p})
           for p in {(a.get("ten_page") or "").strip() for a in db.get_accounts()}
           if p), default=1) <= 1)
check("lưu link có bỏ trùng theo URL",
      "BỎ QUA url đã có" in Path("db.py").read_text(encoding="utf-8"))


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

# ── Loại đăng: 4 lựa chọn (bỏ X_ — comment/mkt nay là cột % riêng) ─────────
# loai_dang nay chỉ quyết định mảng content. "% comment" / "% Marketplace" tách
# sang hai cột số comment_pct / marketplace_pct — mỗi acc một tỉ lệ trên tổng
# phiên của chính nó, độc lập với loại content.
check("có đúng 4 lựa chọn",           len(db.loai_dang_options()) == 4)
check("không còn lựa chọn C_ / X_ nào",
      not any(str(v).startswith(("C_", "X_")) for v in db.loai_dang_options()))

# % đọc từ cột số; >0 nghĩa là có chạy tính năng đó.
check("comment_pct 25 -> acc_comment_pct 25", db.acc_comment_pct({"comment_pct": 25}) == 25)
check("comment_pct 25 -> acc_co_comment",     db.acc_co_comment({"comment_pct": 25}))
check("comment_pct 0 -> KHÔNG comment",       not db.acc_co_comment({"comment_pct": 0}))
check("thiếu cột -> 0, KHÔNG comment",        db.acc_comment_pct({}) == 0 and not db.acc_co_comment({}))
check("marketplace_pct 15 -> acc_marketplace_pct 15", db.acc_marketplace_pct({"marketplace_pct": 15}) == 15)
check("marketplace_pct 0 -> KHÔNG marketplace", not db.acc_co_marketplace({"marketplace_pct": 0}))
check("% rác -> 0",                           db.acc_comment_pct({"comment_pct": "abc"}) == 0)
check("% âm/quá 100 bị kẹp",
      db.acc_comment_pct({"comment_pct": -5}) == 0 and db.acc_comment_pct({"comment_pct": 150}) == 100)
check("hai cột độc lập nhau",
      db.acc_comment_pct({"comment_pct": 25, "marketplace_pct": 0}) == 25
      and db.acc_marketplace_pct({"comment_pct": 25, "marketplace_pct": 0}) == 0)

# "Chỉ comment" (acc dính spam) nay đọc từ trạng thái acc.
check("acc Spam -> chỉ comment",      db.acc_dang_spam({"trang_thai": db.TRANG_THAI_SPAM}))
check("acc Active -> KHÔNG chỉ comment", not db.acc_dang_spam({"trang_thai": "Active"}))
check("acc thiếu trạng thái -> không", not db.acc_dang_spam({}))

# Khớp lịch theo KHOÁ mảng (loai_dang nay lưu khoá, không lưu nhãn).
check("khoá homestay -> lịch homestay", db.khop_loai_lich("homestay", "homestay"))
check("khoá ban -> đúng lịch bán",      db.khop_loai_lich("ban", "ban"))
check("khoá thue KHÔNG lọt lịch homestay", not db.khop_loai_lich("thue", "homestay"))
check("để trống -> không vào lịch nào",
      not any(db.khop_loai_lich("", l) for l in ("homestay", "thue", "ban")))
# Nhãn (Homestay) KHÔNG còn là loai_dang hợp lệ — đã chuyển sang khoá.
check("nhãn 'Homestay' không khớp lịch", not db.khop_loai_lich("Homestay", "homestay"))
check("X_Home cũ không còn khớp lịch",
      not any(db.khop_loai_lich("X_Home", l) for l in ("homestay", "thue", "ban")))

for _v in db.loai_dang_options():
    db.update_account_field(_acc_id, "loai_dang", _v)
check("lưu được cả giá trị hợp lệ (khoá)",
      db.get_account_by_id(_acc_id)["loai_dang"] == db.loai_dang_options()[-1])
# Nhãn và giá trị lạ đều bị chặn — chỉ nhận khoá đang bật hoặc ''.
for _xau in ("Homestay", "Bán", "C_Home", "Comment", "loai4", "homestay,thue"):
    try:
        db.update_account_field(_acc_id, "loai_dang", _xau)
        check(f"chặn loại đăng sai '{_xau}'", False)
    except ValueError:
        check(f"chặn loại đăng sai '{_xau}'", True)
db.update_account_field(_acc_id, "loai_dang", "  homestay  ")
check("khoảng trắng thừa được cắt bỏ",
      db.get_account_by_id(_acc_id)["loai_dang"] == "homestay")

# ── Mode: tập đóng Page/Via (trước là Hybrid) ──────────────────────────────
check("Mode có đúng 2 lựa chọn",      db.MODE_OPTIONS == ("Page", "Via"))
db.update_account_field(_acc_id, "mode", "Via")
check("đổi Mode sang Via được",       db.get_account_by_id(_acc_id)["mode"] == "Via")
for _m in ("Marketplace", "hybrid", "Hybrid", "page", "VIA", "Linh tinh"):
    try:
        db.update_account_field(_acc_id, "mode", _m)
        check(f"chặn Mode sai '{_m}'", False)
    except ValueError:
        check(f"chặn Mode sai '{_m}'", True)
db.update_account_field(_acc_id, "mode", "Page")
check("đổi Mode sang Page được",      db.get_account_by_id(_acc_id)["mode"] == "Page")

# ── Di trú mode "Hybrid" → "Page" (18/10) ──────────────────────────────────
# Đổi cho CẢ accounts lẫn schedules; gộp luôn alias cũ "PageVia". Idempotent.
with db._conn() as _c:
    _c.execute("INSERT INTO accounts (ten_acc, mode) VALUES ('HybAcc','Hybrid')")
    _c.execute("INSERT INTO accounts (ten_acc, mode) VALUES ('PvAcc','PageVia')")
    _c.execute("INSERT INTO schedules (loai, ten_acc, mode) VALUES ('homestay','HybAcc','Hybrid')")
db.init_db()
with db._conn() as _c:
    _m_acc = {r["ten_acc"]: r["mode"] for r in
              _c.execute("SELECT ten_acc, mode FROM accounts WHERE ten_acc IN ('HybAcc','PvAcc')")}
    _m_sch = _c.execute("SELECT mode FROM schedules WHERE ten_acc='HybAcc'").fetchone()["mode"]
check("di trú acc Hybrid → Page", _m_acc.get("HybAcc") == "Page")
check("di trú alias PageVia → Page", _m_acc.get("PvAcc") == "Page")
check("di trú dòng lịch Hybrid → Page", _m_sch == "Page")
# Scheduler vẫn NHẬN alias cũ (HYBRID/PAGEVIA) để dòng lịch chưa gen lại không gãy.
_src_sch_mode = Path("scheduler.py").read_text(encoding="utf-8")
check("scheduler nhận mode Page + alias cũ",
      'if mode in ("PAGE", "HYBRID", "PAGEVIA"):' in _src_sch_mode)

# ── Di trú X_Thuê → thue (khoá) + comment_pct=25 ───────────────────────────
# Acc cũ mang X_Thuê đi qua HAI bước di trú trong init_db: X_Thuê → "Thuê"
# (nhãn) → "thue" (khoá). Comment giữ y hành vi. Mô phỏng cả hai bước.
with db._conn() as _c:
    _c.execute("INSERT INTO accounts (ten_acc, loai_dang, comment_pct) "
               "VALUES ('MIGR_X', 'X_Thuê', 0)")
    for _x, _sach in (("X_Home", "Homestay"), ("X_Thuê", "Thuê"), ("X_Bán", "Bán")):
        _c.execute("UPDATE accounts SET loai_dang=?, comment_pct=? WHERE loai_dang=?",
                   (_sach, db.TI_LE_COMMENT_MAC_DINH, _x))
    for _nhan, _key in (("Homestay", "homestay"), ("Thuê", "thue"), ("Bán", "ban")):
        _c.execute("UPDATE accounts SET loai_dang=? WHERE loai_dang=?", (_key, _nhan))
    _migr = _c.execute("SELECT loai_dang, comment_pct FROM accounts "
                       "WHERE ten_acc='MIGR_X'").fetchone()
    _c.execute("DELETE FROM accounts WHERE ten_acc='MIGR_X'")
check("di trú X_Thuê -> loai_dang='thue' (khoá)", _migr["loai_dang"] == "thue")
check("di trú X_Thuê -> comment_pct=25",   _migr["comment_pct"] == db.TI_LE_COMMENT_MAC_DINH)

# Cột % lưu và đọc lại được; chặn tổng comment+mkt > 100.
db.update_account_field(_acc_id, "comment_pct", 30)
db.update_account_field(_acc_id, "marketplace_pct", 20)
check("lưu được comment_pct/marketplace_pct",
      db.acc_comment_pct(db.get_account_by_id(_acc_id)) == 30
      and db.acc_marketplace_pct(db.get_account_by_id(_acc_id)) == 20)
try:
    db.update_account_field(_acc_id, "marketplace_pct", 80)  # 30+80 > 100
    check("chặn comment%+mkt% > 100", False)
except ValueError:
    check("chặn comment%+mkt% > 100", True)
db.update_account_field(_acc_id, "comment_pct", 0)
db.update_account_field(_acc_id, "marketplace_pct", 0)
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

# ── Chuyển slot sang MARKETPLACE (cùng hàm, khác hoat_dong) ────────────────
# Marketplace dùng lại chuyen_slot_theo_ti_le với hoat_dong="marketplace",
# không có hàm riêng — cùng một cơ chế thì chỉ một đường code để sửa.
_smk = [{"ten_acc": "M1", "gio_dang": "05:00"} for _ in range(100)]
_nmk = _xl.chuyen_slot_theo_ti_le(_smk, {"M1"}, 25, hoat_dong="marketplace")
check("25% -> 25 slot marketplace", _nmk == 25)
check("slot đổi mang đúng hoat_dong 'marketplace'",
      sum(1 for r in _smk if r.get("hoat_dong") == "marketplace") == 25)
check("không lẫn sang comment",
      not any(r.get("hoat_dong") == "comment" for r in _smk))

# Acc tick CẢ comment LẪN marketplace: chuyển comment trước rồi marketplace,
# mỗi bước chỉ lấy từ slot còn 'dang_bai'. Nên marketplace lấy 25% của phần CÒN
# LẠI (75), không phải của 100 — đúng thiết kế, hai bước không giẫm nhau.
_sc = [{"ten_acc": "B1", "gio_dang": "05:00"} for _ in range(100)]
_xl.chuyen_slot_theo_ti_le(_sc, {"B1"}, 25, hoat_dong="comment")
_xl.chuyen_slot_theo_ti_le(_sc, {"B1"}, 25, hoat_dong="marketplace")
_dem_hd = lambda hd: sum(1 for r in _sc if (r.get("hoat_dong") or "dang_bai") == hd)
check("comment giữ nguyên 25 sau khi chuyển marketplace", _dem_hd("comment") == 25)
check("marketplace chỉ lấy từ 75 slot còn lại (25% của 75 ≈ 19)",
      _dem_hd("marketplace") == 19)
check("không slot nào mang hai hoat_dong, tổng bảo toàn",
      _dem_hd("comment") + _dem_hd("marketplace") + _dem_hd("dang_bai") == 100)

# ── Chỉ comment vào bài CHÍNH CHỦ ──────────────────────────────────────────
db.xoa_het_comment_posts("ban")
db.them_comment_posts("ban", [_lk("gA", 1), _lk("gB", 2)], page="PAGE_1")
db.them_comment_posts("ban", [_lk("gC", 3), _lk("gD", 4)], page="PAGE_2")
check("lưu được Page của từng link",
      {r["page"] for r in db.get_comment_posts("ban")} == {"PAGE_1", "PAGE_2"})
# `page` là BỘ LỌC CỨNG, không phải thứ tự ưu tiên. Hết bài chính chủ thì phiên
# bỏ trống, tuyệt đối không lấp bằng bài của Page khác — đi comment dưới bài của
# Page lạ khiến nick dính spam. (Từng làm ngược lại, đã bỏ theo yêu cầu.)
_b1 = db.boc_bai_de_comment("ban", 9, page="PAGE_1")
check("chỉ lấy bài của Page mình",      len(_b1) == 2)
check("mọi bài đều đúng Page",          {r["page"] for r in _b1} == {"PAGE_1"})
check("KHÔNG lấp bằng bài Page khác",   all(r["page"] != "PAGE_2" for r in _b1))

# Page lạ: không có bài nào của nó -> phiên rỗng, KHÔNG lùi về chung kho.
check("Page lạ -> rỗng, không lùi về chung kho",
      db.boc_bai_de_comment("ban", 9, page="PAGE_9") == [])
check("không truyền Page -> rỗng",
      db.boc_bai_de_comment("ban", 9) == [])

# Acc yếu (chỉ đăng chéo được 1 nhóm) nay chỉ comment 1 bài mỗi phiên thay vì
# được lấp cho đủ. ĐÁNH ĐỔI CÓ Ý THỨC: mất công suất còn hơn mất quyền comment.
db.xoa_het_comment_posts("ban")
db.them_comment_posts("ban", [_lk("gYeu", 1)], page="PAGE_YEU")
db.them_comment_posts("ban", [_lk("gX", i) for i in range(9)], page="PAGE_KHAC")
_by = db.boc_bai_de_comment("ban", 10, page="PAGE_YEU")
check("acc yếu 1 link -> đúng 1 bài",   len(_by) == 1)
check("acc yếu: không vơ bài Page khác", _by[0]["page"] == "PAGE_YEU")

# Link cũ chưa gắn Page (lưu từ bản trước) không thuộc Page nào -> không bốc.
db.xoa_het_comment_posts("ban")
db.them_comment_posts("ban", [_lk("gCu", 1)])          # page rỗng
db.them_comment_posts("ban", [_lk("gMoi", 2)], page="PAGE_1")
_bc = db.boc_bai_de_comment("ban", 9, page="PAGE_1")
check("link chưa gắn Page bị bỏ qua",
      len(_bc) == 1 and _bc[0]["nhom"] == "gMoi")
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

# ── Biến thể ảnh ĐÃ GỠ BỎ: mọi ảnh đăng THUẦN ẢNH GỐC ──────────────────────
# 20/10: bỏ hẳn engine biến thể (đổi sáng/tương phản + dán mã/huy hiệu số ĐT +
# xoá EXIF). Ảnh local lên Facebook đúng y file gốc, không sao chép, không sửa;
# chỉ ảnh từ URL mới tải về temp.
import shutil, tempfile as _tf
import storage as _st

check("đã xoá file anh_bien_the.py",
      not Path("anh_bien_the.py").exists())
_src_st = Path("storage.py").read_text(encoding="utf-8")
check("storage.py không còn dính biến thể ảnh",
      "anh_bien_the" not in _src_st and "bien_the" not in _src_st
      and "seed_key" not in _src_st and "sdt" not in _src_st)
check("prepare_images_for_post chỉ còn 1 tham số image_urls",
      "def prepare_images_for_post(image_urls: str)" in _src_st)
# UI: nút 🎲 Biến thể ảnh CŨ (ở tab Content) + hàm JS của nó đã gỡ. (Marketplace
# có ô "biến thể ảnh" RIÊNG của nó — xem phần test Marketplace.)
check("bỏ nút '🎲 Biến thể ảnh' cũ ở tab Content",
      "openBienTheSettings" not in Path("static/js/app.js").read_text(encoding="utf-8")
      and "saveBienTheSettings" not in Path("static/js/app.js").read_text(encoding="utf-8")
      and "🎲 Biến thể ảnh" not in Path("templates/index.html").read_text(encoding="utf-8"))
# Cài đặt số ĐT dán ảnh của Marketplace cũng bỏ.
check("bỏ cài đặt mkt_sdt_anh",
      "mkt_sdt_anh" not in Path("db.py").read_text(encoding="utf-8")
      and "mkt_sdt_anh" not in db.doc_cai_dat_mkt())

# prepare_images_for_post: dùng THẲNG ảnh gốc, giữ đúng thứ tự, không sửa file.
_md = Path(_tf.mkdtemp(prefix="test_img_"))
_goc = _md / "goc.jpg"; _goc.write_bytes(b"anh-goc-1")
_b   = _md / "b.jpg";   _b.write_bytes(b"anh-goc-2")
_byte_goc = _goc.read_bytes()
_mp = _st.MEDIA_DIR
try:
    _st.MEDIA_DIR = _md / "x"          # để MEDIA_DIR.parent == _md
    _p, _t = _st.prepare_images_for_post("/goc.jpg")
    check("ảnh local dùng THẲNG, không tạo temp", _p == [str(_goc)] and _t is None)
    check("ẢNH GỐC KHÔNG BỊ SỬA",      _goc.read_bytes() == _byte_goc)
    # Thứ tự ảnh = thứ tự trong ô ảnh của content, KHÔNG sort theo tên file.
    _p, _ = _st.prepare_images_for_post("/b.jpg,/goc.jpg")
    check("giữ đúng thứ tự đầu vào",   _p == [str(_b), str(_goc)])
    _p, _ = _st.prepare_images_for_post("/goc.jpg,/b.jpg")
    check("đảo đầu vào -> đảo đầu ra", _p == [str(_goc), str(_b)])
    # File thiếu thì bỏ qua, không ném lỗi làm chết lượt đăng.
    _p, _ = _st.prepare_images_for_post("/khong-co.jpg")
    check("file thiếu -> bỏ qua",      _p == [])
    check("rỗng -> trả ([], None)",    _st.prepare_images_for_post("") == ([], None))
finally:
    _st.MEDIA_DIR = _mp
    shutil.rmtree(_md, ignore_errors=True)

# ── server: KHÔNG rò rỉ credential qua /api/accounts ───────────────────────
import server

_client = server.app.test_client()
_res    = _client.get("/api/accounts")
_rows   = _res.get_json()["data"]
_row    = next((r for r in _rows if r["id"] == _acc_id), None)

check("/api/accounts trả về acc",      _row is not None)

# Xuất Excel UID nhóm: trình duyệt gắn Content-Type: application/json cho MỌI
# request kể cả GET body rỗng. _ma_nhom_yc() từng gọi request.json (không im
# lặng) nên ma_nhom='' (tab UID Nhóm) ném HTTP 400. Nút Xuất hỏng im cho tới
# khi thử tay. Giả lập ĐÚNG request của trình duyệt.
_hdr_json = {"Content-Type": "application/json"}
_ex1 = _client.get("/api/uid-groups/export-excel", headers=_hdr_json)
check("xuất UID Nhóm (ma='') không 400", _ex1.status_code == 200)
_ex2 = _client.get("/api/uid-groups/export-excel?ma_nhom=MARKET", headers=_hdr_json)
check("xuất UID Marketplace không 400",  _ex2.status_code == 200)
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

# Nút "Cập nhật xs tất cả" — chạy ở NỀN cho mọi acc Active, trả {dang_chay, tong}
# ngay; giao diện poll /refresh-status. Môi trường test không có profile nên chỉ
# đọc rỗng (giữ nguyên xs), KHÔNG mở trình duyệt.
_res = _client.post("/api/accounts/refresh-now").get_json()
check("endpoint cập nhật xs tất cả trả dang_chay + tong",
      _res.get("ok") is True and "tong" in _res)
_st_xs = _client.get("/api/accounts/refresh-status").get_json()
check("endpoint refresh-status trả tiến trình",
      _st_xs.get("ok") is True and "dang_chay" in _st_xs and "cap_nhat" in _st_xs
      and "giu_nguyen" in _st_xs)

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
                          "loai_dang": "homestay"})
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

check("đọc được số vụ từ 'Xem tất cả'",
      _sk.doc_vi_pham(_DLG_SPAM)["so"] == 12 and _sk.doc_vi_pham(_DLG_SPAM)["spam"] is True)
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

# ── Vụ mang NGÀY HÔM NAY: đường phát hiện CHÍNH ────────────────────────────
# Chỉ so số với lần đo trước là không đủ, vì con số đó TỤT XUỐNG ĐƯỢC. Đo thật
# trên nick 'Nguyen Ngan': 10 → 4 → 10 trong một ngày (Facebook cho vụ cũ rụng
# khỏi danh sách; và khi chưa kịp hiện "Xem tất cả (N)" thì phần đếm dự phòng
# chỉ đếm được mấy dòng đang nhìn thấy).
#
# Hậu quả của luật cũ: mốc lưu 10, mọi lần đo sau ra 4 đều bị coi là "không có
# gì mới" → nick MIỄN NHIỄM VĨNH VIỄN, cứ đăng tiếp trong khi Facebook gỡ bài
# liên tục. Đúng thứ người dùng báo ngày 22/09.
from datetime import datetime as _dt_vp
_HN = f"{_dt_vp.now().day} tháng {_dt_vp.now().month}, {_dt_vp.now().year}"
_DLG_HOM_NAY = (f"Sự việc {_HN} Chúng tôi đã gỡ một số nội dung hoặc tin nhắn "
                + f"Spam Đã gỡ bài viết {_HN} " * 4 + "Xem tất cả (4)")
_DLG_CU_HET  = _DLG_HOM_NAY.replace(_HN, "15 tháng 8, 2026")

check("đếm được vụ mang ngày hôm nay", _sk.co_vu_hom_nay(_DLG_HOM_NAY) >= 4)
check("dialog toàn vụ cũ -> 0 vụ hôm nay", _sk.co_vu_hom_nay(_DLG_CU_HET) == 0)
check("doc_vi_pham trả kèm 'hom_nay'",
      _sk.doc_vi_pham(_DLG_HOM_NAY)["hom_nay"] >= 4)

# Đây là ca THẬT đã bỏ lọt: mốc lưu 10, Facebook báo 4 — nhưng cả 4 là của
# HÔM NAY.
check("mốc 10 / đo 4 / hôm nay có -> PHẢI gắn cờ",
      _sk.co_vu_moi(10, 4, _sk.doc_vi_pham(_DLG_HOM_NAY)["hom_nay"]) is True)
check("mốc 10 / đo 4 / toàn vụ cũ -> KHÔNG gắn cờ oan",
      _sk.co_vu_moi(10, 4, _sk.doc_vi_pham(_DLG_CU_HET)["hom_nay"]) is False)
check("lần đo ĐẦU vẫn chỉ ghi mốc, dù có vụ hôm nay",
      _sk.co_vu_moi(-1, 4, 4) is False)

# ── Không được báo LẠI đúng một sự việc suốt cả ngày ───────────────────────
# Hộp cảnh báo giữ nguyên vụ của hôm nay tới hết ngày, nên mọi phiên sau đều
# đọc ra y hệt. Nick 'Nguyen Ngan' ngày 22/09 bị đánh spam 12 LẦN cho đúng MỘT
# sự việc — log cho thấy `hom_nay=6` ở cả 12 lần đo, không đổi một đơn vị.
_nid = db.upsert_account({"ten_acc": "NGAYSPAM Test", "trang_thai": "Active"})
with db._conn() as _c:
    _c.execute("UPDATE accounts SET so_vi_pham=10 WHERE id=?", (_nid,))
# Tín hiệu "có vụ đề ngày hôm nay" KHÔNG còn là đường gắn cờ. Hộp thoại dính
# dai: hễ trong ngày có một vụ là nó mang ngày hôm nay suốt cả ngày, nên mọi
# phiên sau đều đọc ra y hệt — log cho thấy `hom_nay=6` ở cả 12 lần đo của
# 'Nguyen Ngan' ngày 22/09, không đổi một đơn vị. Thay bằng phép phân biệt
# "cảnh báo MỚI hiện sau khi đăng", vừa không đọc lại vừa không bỏ sót vụ thứ
# hai trong cùng ngày.
_m1, _ = db.ghi_nhan_vi_pham("NGAYSPAM Test", 4, True, hom_nay=6, chac_chan=True)
_m2, _ = db.ghi_nhan_vi_pham("NGAYSPAM Test", 4, True, hom_nay=6, chac_chan=True)
check("chưa đăng gì, dù mang ngày hôm nay -> KHÔNG gắn cờ",
      _m1 is False and _m2 is False)

# Con số ĐẾM MÒ không được ghi đè mốc đã lưu.
# 12 lần đo cùng ngày cho 13,19,6,19,20,20,20,15,8,17,10,20 trong khi số vụ
# thật không đổi — ghi đè bằng con số đó là xoá mất mốc tốt bằng một số rác.
with db._conn() as _c:
    _c.execute("UPDATE accounts SET so_vi_pham=13, vi_pham_ngay='' WHERE id=?", (_nid,))
db.ghi_nhan_vi_pham("NGAYSPAM Test", 19, True, hom_nay=0, chac_chan=False)
check("đếm mò KHÔNG ghi đè mốc",
      db.get_account_by_name("NGAYSPAM Test")["so_vi_pham"] == 13)
# Con số KHÔNG còn tham gia quyết định — chỉ `da_dang` quyết.
_m4, _ = db.ghi_nhan_vi_pham("NGAYSPAM Test", 19, True, hom_nay=0, chac_chan=False)
check("chưa đăng gì + đếm mò -> KHÔNG gắn cờ", _m4 is False)
_m5, _ = db.ghi_nhan_vi_pham("NGAYSPAM Test", 19, True, hom_nay=0, chac_chan=True)
check("chưa đăng gì + số chắc chắn -> vẫn KHÔNG gắn cờ", _m5 is False)
_m6, _ = db.ghi_nhan_vi_pham("NGAYSPAM Test", 19, True, 0, True, da_dang=True)
check("đã đăng + thấy cảnh báo -> gắn cờ, khỏi cần so số", _m6 is True)
db.delete_account(_nid)

check("log ghi rõ số là chắc chắn hay đếm mò",
      "ĐẾM MÒ" in Path("fb_common.py").read_text(encoding="utf-8"))

# ── Vòng canh KHÔNG được nuốt mất bằng chứng ───────────────────────────────
# Vòng canh nền quét mỗi 5 giây và ĐÓNG dialog ngay khi thấy. `kiem_vi_pham`
# chạy cuối phiên, mở facebook.com rồi chờ 4–6 giây mới dò — quãng đó vòng canh
# đã kịp đóng mất. Đếm trên log tới 22/09: vòng canh thấy 252 lần,
# `kiem_vi_pham` chỉ đọc được 65 lần; riêng nick 'Nguyen Ngan' đúng 3 lần trong
# khi Facebook gỡ bài của nó liên tục. Log vì thế đầy dòng
# "✅ Không thấy cảnh báo gỡ bài" trong đúng những phiên vừa bị gỡ bài.
import fb_common as _fbc_vp


class _TrangGia:
    pass


_tg = _TrangGia()
_fbc_vp._nho_canh_bao(_tg, "Spam Đã gỡ bài viết")
check("vòng canh ghi lại được chữ cảnh báo",
      any(t == "Spam Đã gỡ bài viết"
          for _ts, t in _fbc_vp._CANH_BAO_DA_THAY.get(id(_tg), [])))
_fbc_vp._nho_canh_bao(_tg, "ngắn")
_fbc_vp.danh_dau_da_dang(_tg)
_fbc_vp._nho_canh_bao(_tg, "Spam Đã gỡ bài viết — bản DÀI hơn sau khi đăng")
check("lấy bản DÀI nhất trong số thấy sau khi đăng",
      "bản DÀI hơn" in _fbc_vp._canh_bao_sau_khi_dang(_tg))
_fbc_vp._MOC_DA_DANG.pop(id(_tg), None)

# ── Cảnh báo thấy TRƯỚC khi đăng KHÔNG phải của phiên này ─────────────────
# Đếm trên toàn bộ log: 512 lần hộp cảnh báo bật lên, thì 276 lần (54%) rơi vào
# lúc đăng nhập / xem story / lướt newsfeed / chuyển sang Page — tức phiên CHƯA
# đăng gì cả. Quy cho phiên đó là đổ oan cho nick đang chạy phiên, trong khi vụ
# gỡ bài có thể do nick khác gây ra (nhiều nick dùng chung một Page).
check("chưa đánh mốc đăng -> KHÔNG dùng cảnh báo cũ",
      _fbc_vp._canh_bao_sau_khi_dang(_tg) == "")
check("thấy cảnh báo khi CHƯA đăng -> tính là 'đã mở sẵn'",
      _fbc_vp.da_thay_truoc_khi_dang(_tg) is True)
_fbc_vp.danh_dau_da_dang(_tg)          # phiên vừa đăng xong
check("cảnh báo thấy TRƯỚC khi đăng -> vẫn bỏ qua",
      _fbc_vp._canh_bao_sau_khi_dang(_tg) == "")
_fbc_vp._nho_canh_bao(_tg, "Spam Đã gỡ bài viết — vụ MỚI sau khi đăng")
check("cảnh báo thấy SAU khi đăng -> mới dùng",
      "vụ MỚI sau khi đăng" in _fbc_vp._canh_bao_sau_khi_dang(_tg))
# Hộp thoại đã mở TRƯỚC khi đăng thì vẫn phải nhớ là "mở sẵn", dù sau đó có
# thấy lại nữa — đó là hộp cũ dính dai, không phải vụ mới.
check("mở sẵn từ trước -> vẫn là 'đã mở sẵn'",
      _fbc_vp.da_thay_truoc_khi_dang(_tg) is True)

_tg2 = _TrangGia()
_fbc_vp.danh_dau_da_dang(_tg2)
_fbc_vp._nho_canh_bao(_tg2, "Spam Đã gỡ bài viết — chỉ hiện SAU khi đăng")
check("chỉ hiện sau khi đăng -> KHÔNG phải 'mở sẵn'",
      _fbc_vp.da_thay_truoc_khi_dang(_tg2) is False)
_fbc_vp._quen_canh_bao(_tg2)

# ── LUẬT (Duong chốt 04/10): thấy cảnh báo sau khi đăng là gắn cờ ─────────
# Chốt duy nhất còn lại là "phiên này có đăng thật không". Bỏ điều kiện cũ
# "trước khi đăng không có hộp nào mở sẵn": đo 2 ngày 03-04/10, nó chặn 28/49
# lần thấy cảnh báo gỡ bài, mà cả 28 lần đều rơi vào đúng 3 nick vốn đã bị gắn
# cờ ở phiên khác — không cứu được nick khoẻ nào, chỉ làm chậm việc.
_vid = db.upsert_account({"ten_acc": "VIPHAM Test", "trang_thai": "Active"})
with db._conn() as _c:
    _c.execute("UPDATE accounts SET so_vi_pham=20 WHERE id=?", (_vid,))
_v1, _ = db.ghi_nhan_vi_pham("VIPHAM Test", 20, True, 6, True, da_dang=True)
check("đã đăng + thấy cảnh báo -> gắn cờ NGAY", _v1 is True)
_v2, _ = db.ghi_nhan_vi_pham("VIPHAM Test", 20, True, 6, True, da_dang=True)
check("bị gỡ lần nữa trong ngày -> vẫn gắn cờ (không giới hạn 1 lần/ngày)",
      _v2 is True)
# Đây là cái MỚI so với luật cũ: hộp mở sẵn từ trước KHÔNG còn là lý do tha.
_v3, _ = db.ghi_nhan_vi_pham("VIPHAM Test", 20, True, 6, True, da_dang=True)
check("hộp cũ mở sẵn cũng KHÔNG tha nữa", _v3 is True)
# Con số là nhiễu nên không được ảnh hưởng tới quyết định, dù tăng hay giảm.
_v4, _ = db.ghi_nhan_vi_pham("VIPHAM Test", 2, True, 0, True, da_dang=True)
check("số vụ GIẢM vẫn gắn cờ (con số là nhiễu)", _v4 is True)
_v5, _ = db.ghi_nhan_vi_pham("VIPHAM Test", 99, True, 6, False, da_dang=True)
check("số đếm mò vẫn gắn cờ", _v5 is True)
# Chốt phải giữ: phiên hỏng giữa chừng, chưa đăng gì thì KHÔNG gán cờ — hộp
# cảnh báo trông thấy khi đó là chuyện của phiên trước, gán là đổ oan thật.
_v6, _ = db.ghi_nhan_vi_pham("VIPHAM Test", 20, True, 6, True, da_dang=False)
check("chưa đăng gì -> KHÔNG gắn cờ", _v6 is False)
db.delete_account(_vid)

_src_fbc_vp = Path("fb_common.py").read_text(encoding="utf-8")
check("gắn cờ theo 'phiên này có đăng', không theo hộp cũ/mới",
      "vua_dinh = bool(la_spam and da_dang)" in Path("db.py").read_text(encoding="utf-8")
      and "da_dang = da_dang_trong_phien(page)" in _src_fbc_vp)
# Vẫn log cả hai mặt để còn đọc lại được, dù chỉ một mặt dùng để quyết định.
check("log ghi rõ phiên có đăng chưa và hộp cũ hay mới",
      "phiên này CÓ đăng" in _src_fbc_vp
      and "hộp cũ đã mở sẵn từ trước" in _src_fbc_vp)

_fbc_vp._quen_canh_bao(_tg)
check("đóng trang thì xoá, không rò sang phiên sau",
      id(_tg) not in _fbc_vp._CANH_BAO_DA_THAY
      and id(_tg) not in _fbc_vp._MOC_DA_DANG)

# Mọi luồng đưa nội dung lên đều phải đánh mốc, không thì cảnh báo của vòng
# canh vĩnh viễn không được dùng tới.
for _f_md in ("page_via_poster.py", "via_poster.py", "comment_bai.py"):
    check(f"{_f_md}: có đánh mốc sau khi đăng/comment",
          "danh_dau_da_dang(page)" in Path(_f_md).read_text(encoding="utf-8"))

_src_fb = Path("fb_common.py").read_text(encoding="utf-8")
check("CẢ HAI đường đóng dialog đều ghi lại trước khi đóng",
      _src_fb.count("_nho_canh_bao(page") >= 2)
_i_vc = _src_fb.index("async def _vong_canh(")
_than_vc = _src_fb[_i_vc:_src_fb.index(chr(10) + "def ", _i_vc + 10)]
check("vòng canh ghi lại TRƯỚC khi bấm đóng",
      _than_vc.index("_nho_canh_bao(page") < _than_vc.index("btn.click("))
check("kiem_vi_pham dùng lại chữ vòng canh đã thấy",
      "_CANH_BAO_DA_THAY.get(id(page)" in _src_fb
      and "Dùng lại cảnh báo vòng canh" in _src_fb)
check("truyền 'hom_nay' xuống tận db", 'vp.get("hom_nay", 0)' in _src_fb)

# ── Spam: tầng DB ──────────────────────────────────────────────────────────
_sid = db.upsert_account({"ten_acc": "SPAM Test", "trang_thai": "Active",
                          "loai_dang": "homestay", "ten_page": "P"})
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

# Luật DUY NHẤT: phiên đã đăng thật + thấy cảnh báo gỡ bài = gắn cờ nick đó.
# Không còn "lần đo đầu chỉ ghi mốc" — luật cũ cần nó để khỏi đánh spam hàng
# loạt lúc mới bật tính năng, nhưng luật mới vốn đã là tín hiệu theo TỪNG PHIÊN
# nên không thể nổ vì dữ liệu cũ.
_moi1, _cu1 = db.ghi_nhan_vi_pham("SPAM Test", 12, True, da_dang=True)
check("đã đăng + thấy cảnh báo -> dính spam ngay",
      _moi1 is True and _cu1 == -1)
_moi2, _cu2 = db.ghi_nhan_vi_pham("SPAM Test", 12, True, da_dang=False)
check("chưa đăng gì -> không kết luận",  _moi2 is False and _cu2 == 12)
_moi3, _cu3 = db.ghi_nhan_vi_pham("SPAM Test", 15, True, da_dang=True)
check("đã đăng, số vụ tăng -> vẫn gắn cờ (số không tham gia quyết định)",
      _moi3 is True and _cu3 == 12)

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

# ── Phiên VỪA bị đánh Spam không được tự thả chính mình ────────────────────
# `kiem_vi_pham` chạy ở CUỐI phiên, trước khi phiên báo thành công. Nên thứ tự
# thật là: đăng xong 9 nhóm → phát hiện bị gỡ bài → đánh Spam → phiên báo
# thành công → `ghi_nhan_phien_dang(ok=True)`. Nếu nhánh Spam coi đó là "thăm
# dò thành công" thì nick vừa bị phạt tự thả mình ra ngay.
#
# Thấy thật lúc 01:51 ngày 22/09 trên nick 'Nguyen Ngan':
#     01:51:04  🚫 DÍNH SPAM — nhử lại lúc 02:51
#     01:51:26  ✅ STT 312 hoàn thành (9 nhóm)   → Spam → Active
# Telegram bắn hai tin cùng một phút: "Active → Spam" rồi "Spam → Active".
# Nghỉ một tiếng thành nghỉ hai mươi giây.
_tid = db.upsert_account({"ten_acc": "THAMDO Test", "trang_thai": "Active"})
db.danh_dau_spam("THAMDO Test", "vừa bị gỡ bài")      # nghỉ tới +60 phút
_hd_vua, _ = db.ghi_nhan_phien_dang("THAMDO Test", True)
_a_vua = db.get_account_by_name("THAMDO Test")
check("vừa đánh Spam + phiên OK -> KHÔNG thả",
      _hd_vua == "" and _a_vua["trang_thai"] == db.TRANG_THAI_SPAM)
check("… và mốc nghỉ giữ nguyên", (_a_vua["nghi_den"] or "") != "")

# Hết giờ nghỉ thì mới thật sự là phiên thăm dò.
with db._conn() as _c:
    _c.execute("UPDATE accounts SET nghi_den=? WHERE id=?",
               ((_dt.now() - _td(minutes=5)).isoformat(timespec="seconds"), _tid))
_hd_that, _ = db.ghi_nhan_phien_dang("THAMDO Test", True)
check("hết giờ nghỉ + phiên OK -> mới thả",
      _hd_that == "het_spam"
      and db.get_account_by_name("THAMDO Test")["trang_thai"] == "Active")

# Và thăm dò thật mà hỏng thì nghỉ thêm một lượt.
db.danh_dau_spam("THAMDO Test", "lại hỏng")
with db._conn() as _c:
    _c.execute("UPDATE accounts SET nghi_den=? WHERE id=?",
               ((_dt.now() - _td(minutes=5)).isoformat(timespec="seconds"), _tid))
_hd_hong, _ = db.ghi_nhan_phien_dang("THAMDO Test", False)
check("hết giờ nghỉ + phiên hỏng -> nghỉ thêm", _hd_hong == "tham_do_hong")
db.delete_account(_tid)

# ── Phiên thăm dò chạy ở SLOT KẾ TIẾP, không phải đúng mốc hết nghỉ ────────
# Ngày 22/09 nick 'Ngân Nấm' hết nghỉ lúc 20:10, nhưng slot gần nhất của nó là
# 20:18 — nên tới 20:18 phiên thăm dò mới chạy, 20:22 mới được thả. Người dùng
# nhìn ô "dò lúc 20:10" rồi đợi tới 20:15 không thấy gì, tưởng hỏng.
#
# Chữ cũ hứa một mốc chính xác rồi không giữ lời. Phải nói "dò TỪ".
_ajs_td = Path("static/js/app.js").read_text(encoding="utf-8")
check("ô Trạng thái ghi 'dò từ', không hứa 'dò lúc'",
      "dò từ" in _ajs_td and "dò lúc" not in _ajs_td)
check("chú thích nói rõ phải đợi slot kế tiếp",
      "SLOT KẾ TIẾP của nick chạy thử" in _ajs_td)

# `mo_duong_tham_do` trả acc kể cả khi mở 0 slot (acc không còn dòng 'Nghỉ
# Spam' nào), mà scheduler quét mỗi 60 giây × 5 runner. Riêng câu log ấy đã ghi
# 3649 dòng trong ngày 22/09, lấp mất những dòng thật sự cần đọc.
_src_sch_td = Path("scheduler.py").read_text(encoding="utf-8")
check("chỉ ghi log khi THẬT SỰ mở được slot",
      'if _hs["so_slot"]:' in _src_sch_td)

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
db.update_account_field(_sid, "loai_dang", "homestay")
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
# Đăng tường Page tích hợp phiên: acc nối Page theo UID, tab Page bỏ 2 cột
# ───────────────────────────────────────────────────────────────────────────
# Runner Page riêng + cột 'Loại đăng' / 'Acc quản lý' của Page đã bỏ (15/10):
# acc nào quản page thì chính nó đăng (ô Tên Page = chọn page THEO UID ở tab Tài
# khoản), content lấy theo Loại đăng của acc. Đăng page thành phiên 'dang_page'
# lồng trong lịch mảng.
_ajs = Path("static/js/app.js").read_text(encoding="utf-8")
check("đã bỏ danh sách loại đăng riêng của Page", "LOAI_PAGE_OPTIONS" not in _ajs)
check("đã bỏ ô vẽ 'Loại đăng' ở tab Page (pageLoaiCell)", "pageLoaiCell" not in _ajs)
check("tab Page không còn cột loai_page / acc_quan_ly", "loai_page" not in _ajs and "acc_quan_ly" not in _ajs)
# Ô 'Tên Page' ở bảng Tài khoản nay nối theo page_uid (dropdown), không gõ tay tên.
check("cột Tên Page ở Tài khoản dùng page_uid", '{key:"page_uid",label:"Tên Page"}' in _ajs)
check("có dropdown chọn Page theo UID (CHON_SAN.page_uid)", "page_uid:" in _ajs and "_pagesDS" in _ajs)
# Cột Loại đăng: nới rộng + không xuống dòng để tên mảng gói trong 1 dòng.
_ô_loai = _ajs[_ajs.index('if(f.key==="loai_dang"){'):]
_ô_loai = _ô_loai[:_ô_loai.index('if(f.key==="page_uid"){')]
check("ô Loại đăng không xuống dòng (white-space:nowrap + min-width)",
      "white-space:nowrap" in _ô_loai and "min-width:96px" in _ô_loai)
# Server: cột xuất Excel của Page cũng bỏ 2 cột đó.
_srv = Path("server.py").read_text(encoding="utf-8")
check("EXPORT_PAGE_COLUMNS bỏ acc_quan_ly + loai_page",
      "acc_quan_ly" not in _srv.split("EXPORT_PAGE_COLUMNS")[1].split("]")[0]
      and "loai_page" not in _srv.split("EXPORT_PAGE_COLUMNS")[1].split("]")[0])
# db: có cột page_uid cho acc + helper tra page theo UID.
check("accounts có cột page_uid (nối acc→page)", 'page_uid TEXT' in Path("db.py").read_text(encoding="utf-8"))
check("db có get_page_by_uid", "def get_page_by_uid" in Path("db.py").read_text(encoding="utf-8"))

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
# Cột Trạng thái phải nói VÌ SAO acc đang nghỉ
# ───────────────────────────────────────────────────────────────────────────
# Không có lý do thì mọi kiểu nghỉ nhìn giống hệt nhau ("Nghỉ tới 23:57"), mà
# "Lỗi Composer" và "lỗi liên tiếp" cần xử lý khác hẳn nhau.
_aid_ld = db.upsert_account({"ten_acc": "LYDO Test", "trang_thai": "Active",
                             "loai_dang": "homestay"})
db.danh_dau_spam("LYDO Test", "hộp thoại đăng bài rỗng", ly_do="Lỗi Composer")
_r_ld = next(a for a in db.get_accounts() if a["ten_acc"] == "LYDO Test")
check("đánh dấu spam lưu được lý do", _r_ld.get("ly_do_nghi") == "Lỗi Composer")
check("vẫn vào trạng thái Spam như thường", _r_ld["trang_thai"] == db.TRANG_THAI_SPAM)
# Nhử thành công thì phải XOÁ lý do — không thì acc đã chạy lại bình thường mà
# cột Trạng thái vẫn treo chữ "Lỗi Composer".
db.het_spam("LYDO Test")
_r_ld = next(a for a in db.get_accounts() if a["ten_acc"] == "LYDO Test")
check("nhử thành công thì xoá lý do", (_r_ld.get("ly_do_nghi") or "") == "")
# Không truyền lý do thì để trống, cột hiện "Spam" như cũ.
db.danh_dau_spam("LYDO Test", "3 bài mới bị gỡ")
_r_ld = next(a for a in db.get_accounts() if a["ten_acc"] == "LYDO Test")
check("không truyền lý do → để trống", (_r_ld.get("ly_do_nghi") or "") == "")
with db._conn() as _c:
    _c.execute("DELETE FROM accounts WHERE ten_acc='LYDO Test'")

check("scheduler ghi lý do 'Lỗi Composer'",
      'ly_do="Lỗi Composer"' in Path("scheduler.py").read_text(encoding="utf-8"))
check("giao diện hiện lý do rồi xuống dòng giờ nghỉ",
      _re_v.search(r"ly_do_nghi[\s\S]{0,400}Nghỉ tới", _ajs2) is not None
      if (_ajs2 := Path("static/js/app.js").read_text(encoding="utf-8")) else False)

# ═══════════════════════════════════════════════════════════════════════════
# Acc bị chặn đăng: slot chuyển sang nuôi nick THEO NHỊP, không phải mọi slot
# ───────────────────────────────────────────────────────────────────────────
# Bản đầu đổi MỌI slot còn lại thành phiên nuôi. Sai hai chuyện:
#   - acc KHÔNG tick Nuôi cũng bị nuôi, trong khi người dùng cố ý không muốn
#   - acc CÓ tick thì bị nuôi mỗi slot: acc 110 slot thành 110 phiên nuôi/ngày,
#     trong khi nhịp cài đặt 150 phút chỉ ra ~10 phiên
_aid_kt = db.upsert_account({"ten_acc": "NUOI KhongTick", "trang_thai": "Active",
                             "loai_dang": "homestay", "nuoi_nick": 0, "nuoi_interval": 150})
_aid_ct = db.upsert_account({"ten_acc": "NUOI CoTick", "trang_thai": "Active",
                             "loai_dang": "homestay", "nuoi_nick": 1, "nuoi_interval": 150})

# Trường hợp 1: không tick Nuôi → KHÔNG nuôi, slot nghỉ hẳn.
check("không tick Nuôi → không có phiên nuôi nào",
      db.den_gio_nuoi("NUOI KhongTick") is False)

# Trường hợp 2: có tick → giữ đúng nhịp nuoi_interval, y như lúc chạy bình thường.
check("có tick, chưa nuôi lần nào → nuôi ngay",
      db.den_gio_nuoi("NUOI CoTick") is True)
db.ghi_nhan_nuoi("NUOI CoTick")
check("vừa nuôi xong → chưa tới nhịp, slot nghỉ",
      db.den_gio_nuoi("NUOI CoTick") is False)
_bg = _dt.now()
check("60 phút sau → vẫn chưa tới nhịp",
      db.den_gio_nuoi("NUOI CoTick", bay_gio=_bg + _td(minutes=60)) is False)
check("149 phút sau → vẫn chưa tới",
      db.den_gio_nuoi("NUOI CoTick", bay_gio=_bg + _td(minutes=149)) is False)
check("150 phút sau → tới nhịp, được nuôi",
      db.den_gio_nuoi("NUOI CoTick", bay_gio=_bg + _td(minutes=150)) is True)
# Đồng hồ vặn lùi cho ra khoảng âm — phải cho qua, không thì acc kẹt vĩnh viễn
# không bao giờ nuôi nữa.
check("đồng hồ vặn lùi → vẫn cho nuôi, không kẹt",
      db.den_gio_nuoi("NUOI CoTick", bay_gio=_bg - _td(minutes=60)) is True)

# Phiên nuôi phải ĐÁNH MỐC, cho cả hai đường: slot nuôi vốn có và slot thay cho
# phiên bị chặn. Không thì hai đường đếm nhịp riêng và acc bị nuôi dày gấp đôi.
check("chạy xong phiên nuôi thì đánh mốc",
      "db.ghi_nhan_nuoi(acc_name" in Path("scheduler.py").read_text(encoding="utf-8"))
check("scheduler hỏi nhịp trước khi đổi sang nuôi",
      "db.den_gio_nuoi(item[\"ten_acc\"]" in Path("scheduler.py").read_text(encoding="utf-8"))

# ═══════════════════════════════════════════════════════════════════════════
# Chặn Composer: hộp thoại đăng bài mở ra nhưng rỗng
# ───────────────────────────────────────────────────────────────────────────
# Facebook chặn acc đăng bằng cách trả về hộp thoại trống — 0 nút, 0 ô soạn
# thảo, đúng 12 ký tự tiêu đề, KHÔNG lỗi console, KHÔNG request hỏng.
#
# Đã đo bằng ba phép thử tách biến trên acc 'Ngân Nấm' ngày 27/08:
#   acc đó + nhóm khác              → rỗng
#   acc KHOẺ + đúng nhóm đó         → mở bình thường, 12 nút
#   acc đó + PROFILE SẠCH hoàn toàn → vẫn rỗng
# Nên không phải do nhóm, không phải cache, không phải profile — mà do chính
# tài khoản bị chặn.
from fb_common import composer_bi_chan as _cbc

class _TrangComposer:
    def __init__(self, day):
        self.day, self.i = list(day), 0
    async def evaluate(self, _js):
        r = self.day[min(self.i, len(self.day) - 1)]
        self.i += 1
        return r

def _thu_composer(day):
    return _aio.run(_cbc(_TrangComposer(day), giay_cho=4))

check("composer tải được → không phải bị chặn",
      _thu_composer([{"nut": 12, "o": 1}]) is False)
# Composer chạy được LUÔN có hàng chục nút, nên "0 nút" là dấu hiệu sạch. Nhưng
# vẫn phải chờ, không kết luận ngay: máy chậm thì vài giây đầu cũng 0 nút.
check("tải chậm rồi có nút → không phải bị chặn",
      _thu_composer([{"nut": 0, "o": 0}, {"nut": 12, "o": 1}]) is False)
check("rỗng suốt → kết luận BỊ CHẶN",
      _thu_composer([{"nut": 0, "o": 0}]) is True)
# Chưa có dialog là chuyện khác hẳn (chưa bấm mở được) — đừng gán nhầm thành bị
# chặn, không thì mọi lỗi mở composer đều bị đẩy vào đường Spam.
check("chưa có dialog → KHÔNG kết luận bị chặn",
      _thu_composer([None]) is False)

# Bị chặn phải đi đúng ĐƯỜNG SPAM, không rơi vào nhánh lỗi kỹ thuật chung.
_sch = Path("scheduler.py").read_text(encoding="utf-8")
check("scheduler bắt riêng ComposerBiChan", "except ComposerBiChan:" in _sch)
check("bị chặn thì đánh dấu Spam",
      _re_v.search(r"except ComposerBiChan:[\s\S]{0,900}danh_dau_spam", _sch) is not None)
check("cột trạng thái ghi 'Chặn Composer'", "Chặn Composer" in _sch)
# Phải bắt TRƯỚC `except Exception` — Python xét theo thứ tự, đặt sau là không
# bao giờ chạy tới.
check("bắt ComposerBiChan trước Exception chung",
      _sch.index("except ComposerBiChan:") < _sch.index("except Exception as e:\n            cat, label"))
_pvp = Path("page_via_poster.py").read_text(encoding="utf-8")
check("cả hai luồng đăng đều dò chặn composer",
      _pvp.count("composer_bi_chan(page)") == 2)

# ═══════════════════════════════════════════════════════════════════════════
# Kết luận "cookie hết hạn" phải hỏi lại lần nữa
# ───────────────────────────────────────────────────────────────────────────
# Lịch tham gia nhóm mở tới 5 Chromium cùng lúc. Trang tải chậm, dò ngay thì
# thấy giống hệt trang chưa đăng nhập. Log ngày 25/08 có 8 dòng "Cookie hết
# hạn" trong khi CẢ 14 acc đều còn cookie đủ trường, và cùng những acc đó chạy
# phiên khác thì xong bình thường.
import asyncio as _aio
from fb_common import chua_dang_nhap as _cdn

class _TrangGia:
    def __init__(self, ket_qua):
        self.ket_qua, self.lan, self.reload_n = list(ket_qua), 0, 0
        self.url = "https://www.facebook.com/"
    async def evaluate(self, _js):
        r = self.ket_qua[min(self.lan, len(self.ket_qua) - 1)]
        self.lan += 1
        return r
    async def reload(self, **kw):
        self.reload_n += 1

def _thu_dang_nhap(ket_qua):
    t = _TrangGia(ket_qua)
    return _aio.run(_cdn(t)), t

_r, _t = _thu_dang_nhap([False])
check("đăng nhập bình thường → kết luận ngay", _r is False and _t.lan == 1)
check("trường hợp bình thường KHÔNG tốn thêm lần tải", _t.reload_n == 0)
_r, _t = _thu_dang_nhap([True, True])
check("cookie chết thật → vẫn kết luận là chết", _r is True and _t.reload_n == 1)
_r, _t = _thu_dang_nhap([True, False])
check("lần đầu nhầm, hỏi lại thì ổn → KHÔNG báo chết", _r is False)

# Log của phiên tham gia nhóm phải gắn tên acc: 5 tiến trình cùng ghi một file,
# không gắn tên thì các dòng trộn vào nhau và không biết dòng lỗi của acc nào.
_jgr = Path("join_groups_runner.py").read_text(encoding="utf-8")
check("phiên tham gia nhóm có hàm log gắn tên acc", "def _log(" in _jgr)
check("không còn gọi logger trực tiếp trong phiên",
      not _re_v.search(r"logger\.(info|warning|error)\(", _jgr))
# Hết cookie phải đánh dấu CẢ TÀI KHOẢN, không chỉ dòng lịch — dòng lịch bị ghi
# đè ở lần chạy sau, nên nhìn tab Tài khoản không thấy gì.
check("hết cookie thì đánh dấu tài khoản",
      "UPDATE accounts SET trang_thai='Cookie hết hạn'" in _jgr)

# Gặp dialog hạn chế ("hoạt động bất thường") khi tham gia nhóm → acc bị chặn
# nhóm: DỪNG tham gia nhóm cho acc đó, chuỗi sang acc kế tiếp.
import join_groups_runner as _jgr_mod
check("join: nhận diện dialog FB hạn chế → True",
      _jgr_mod._la_bi_han_che([{"chu": "Mở Facebook trên thiết bị di động để xác "
          "nhận danh tính của bạn. Một số hành động đã bị hạn chế do có hoạt động "
          "bất thường", "nut": ["Đóng", "OK"]}]) is True)
check("join: dialog thường (không hạn chế) → False",
      _jgr_mod._la_bi_han_che([{"chu": "Bạn có chắc muốn rời nhóm?",
                                "nut": ["Hủy", "Rời"]}]) is False
      and _jgr_mod._la_bi_han_che([]) is False)
check("join: gặp chặn nhóm thì DỪNG acc (break) + đánh status 'Bị chặn nhóm'",
      'return "chan_nhom"' in _jgr and 'if result == "chan_nhom":' in _jgr
      and "bi_chan_nhom = True" in _jgr and "Bị chặn nhóm" in _jgr
      and "_la_bi_han_che" in _jgr)

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
    ("page_via_poster.py", "_run_page_via",   "đăng Page"),
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

# ── VIA thu link như Page (18/10), nhưng KHÔNG like trong cooldown ─────────
# Đăng VIA xong cũng bắt link (phản hồi mạng + trang thông báo) rồi lưu danh
# sách comment. Khác Page ở chỗ KHÔNG like (VIA ở trang cá nhân).
_src_via = Path("via_poster.py").read_text(encoding="utf-8")
check("VIA bắt link từ phản hồi mạng (BoBatLink)", "BoBatLink" in _src_via)
check("VIA thu link từ trang thông báo", "thu_tu_thong_bao" in _src_via)
check("VIA lưu link vào danh sách comment", "them_comment_posts" in _src_via)
check("post_via_crosspost nhận loai_comment + page_uid",
      "loai_comment:    str" in _src_via and "page_uid:        str" in _src_via)
check("VIA dùng cửa sổ chờ thông báo như Page", "random.randint(*CHO_SAU_DANG_GIAY)" in _src_via)
check("VIA KHÔNG like trong cooldown (max_likes=0, không có max_likes=1)",
      "max_likes=1" not in _src_via and "max_likes=0" in _src_via)
_i_via = _src_sch_mode.index('if mode == "VIA":')
_than_via = _src_sch_mode[_i_via:_src_sch_mode.index("MODE không hỗ trợ", _i_via)]
check("scheduler VIA truyền loai_comment=LOAI + page_uid của acc",
      "loai_comment=LOAI" in _than_via and 'get("page_uid"' in _than_via)

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

# ═══════════════════════════════════════════════════════════════════════════
# Báo Telegram — luật là NÓ HỎNG THÌ CHỈ MÌNH NÓ HỎNG
# ═══════════════════════════════════════════════════════════════════════════
# Mọi bài kiểm dưới đây bảo vệ đúng một điều: việc báo cáo không bao giờ được
# chặn hay làm chậm phiên đăng bài. Bản v2.0.0 từng biến một máy chủ ngoài thành
# thứ bắt buộc và làm mọi máy đứng hình; đừng đi lại đường đó bằng cửa sau.
import time as _time
import thong_bao as _tb

_tb_cu = {k: db.get_setting(k, "") for k in
          ("tg_bat", "tg_token", "tg_chat_id", "tg_ten_may", "tg_gio_tom_tat")}
try:
    # ── Chưa bật: im lặng tuyệt đối ─────────────────────────────────────────
    db.set_setting("tg_bat", "0")
    check("chưa bật thì san_sang() = False", _tb.san_sang() is False)

    _t0 = _time.time()
    _tb.gui("không được gửi gì cả")
    _tb.bao_doi_trang_thai("Acc Không Có Thật", "Spam",
                           trang_thai_cu="Active", ly_do="Lỗi Composer")
    _tat = _time.time() - _t0
    check(f"tắt Telegram thì báo cáo tốn < 50ms (đo được {_tat*1000:.0f}ms)", _tat < 0.05)

    # ── Bật nhưng token sai: vẫn không được chặn ────────────────────────────
    # Đây là bài kiểm quan trọng nhất cả file. Token sai là chuyện sẽ xảy ra
    # thật — gõ nhầm một ký tự là ra. Lúc đó phần mềm phải đăng bài như thường.
    db.set_setting("tg_bat", "1")
    db.set_setting("tg_token", "111111:TOKEN_GIA_DUNG_CHO_BAI_KIEM")
    db.set_setting("tg_chat_id", "999999999")
    db.set_setting("tg_ten_may", "Máy Kiểm Thử")

    check("bật + đủ thông tin thì san_sang() = True", _tb.san_sang() is True)

    # Phải là lần chuyển THẬT (Active → Cookie hết hạn), không thì hàm trả về
    # ngay ở nhánh "không có gì để báo" và bài kiểm này đo một cái vỏ rỗng.
    _t0 = _time.time()
    _tb.bao_doi_trang_thai("Acc Không Có Thật 2", "Cookie hết hạn",
                           trang_thai_cu="Active")
    _cho = _time.time() - _t0
    check(f"token sai vẫn không chặn phiên đăng bài (đo được {_cho*1000:.0f}ms)",
          _cho < 0.5)

    # ── Chống báo lặp ───────────────────────────────────────────────────────
    # Lưới an toàn cho hai tiến trình cùng đọc trạng thái cũ rồi cùng ghi.
    _k = "Acc Lặp Kiểm Thử"
    check("lần đầu báo thì cho qua",
          _tb._da_bao_gan_day(_k, "Active→Spam") is False)
    check("đúng lần chuyển đó lặp lại thì bị chặn",
          _tb._da_bao_gan_day(_k, "Active→Spam") is True)
    check("lần chuyển khác của cùng acc thì vẫn báo",
          _tb._da_bao_gan_day(_k, "Spam→Active") is False)

    # ── thu() phải nói rõ hỏng ở đâu ────────────────────────────────────────
    # Ô để trống nghĩa là "dùng cấu hình đã lưu", nên phải xoá cấu hình đã lưu
    # thì mới dựng được đúng cảnh người dùng chưa điền gì.
    db.set_setting("tg_token", "")
    db.set_setting("tg_chat_id", "")
    check("thu() thiếu token → báo thiếu token",
          "token" in _tb.thu("", "")[1].lower())
    check("thu() thiếu chat id → báo thiếu chat id",
          "chat id" in _tb.thu("abc", "")[1].lower())
    db.set_setting("tg_token", "111111:TOKEN_GIA_DUNG_CHO_BAI_KIEM")
    db.set_setting("tg_chat_id", "999999999")

    # ── Bản tổng kết ────────────────────────────────────────────────────────
    _tt = _tb.tom_tat()
    check("tổng kết có tên máy", "Máy Kiểm Thử" in _tt)
    check("tổng kết có số acc Active", "Active" in _tt)
finally:
    for _k2, _v2 in _tb_cu.items():
        db.set_setting(_k2, _v2)
    try:
        with db._conn() as _c:
            _c.execute("DELETE FROM tb_da_gui WHERE khoa LIKE 'Acc %Kiểm Thử%' "
                       "OR khoa LIKE 'Acc Không Có Thật%'")
    except Exception:
        pass

check("đã trả cấu hình Telegram về như cũ",
      db.get_setting("tg_bat", "") == _tb_cu["tg_bat"])

# ═══════════════════════════════════════════════════════════════════════════
# Quét tin nhắn Marketplace — nhịp, mốc "tin mới", kênh Telegram riêng, khoá acc
# ───────────────────────────────────────────────────────────────────────────
# Nick marketplace tự ghé hộp thư định kỳ (3–5'), có khách nhắn MỚI thì báo vào
# MỘT kênh Telegram RIÊNG. Bốn chốt phải giữ đúng:
#   - chỉ acc marketplace% > 0 mới được quét;
#   - nhịp quét lấy từ mkt_scan_min/max, chưa quét lần nào → quét ngay;
#   - "tin mới" = chữ ký chưa đọc lần này TRỪ các chữ ký đã thấy lần trước;
#   - kênh Market tách hẳn kênh báo trạng thái (token/chat_id riêng), tắt là im.
import market_inbox as _mi
from datetime import datetime as _dt, timedelta as _td

_mkt_cu = {k: db.get_setting(k, "") for k in
           ("tg_mkt_bat", "tg_mkt_token", "tg_mkt_chat_id",
            "mkt_scan_min", "mkt_scan_max")}
try:
    # Nhịp cố định 200s để bài kiểm khỏi phụ thuộc random.
    db.set_setting("mkt_scan_min", "200")
    db.set_setting("mkt_scan_max", "200")

    _aid_mz = db.upsert_account({"ten_acc": "MKT Zero", "c_user": "mkt000",
                                 "trang_thai": "Active", "loai_dang": "homestay",
                                 "marketplace_pct": 0})
    _aid_mt = db.upsert_account({"ten_acc": "MKT Test", "c_user": "mkt001",
                                 "trang_thai": "Active", "loai_dang": "homestay",
                                 "marketplace_pct": 20})

    # 1) Chỉ acc marketplace% > 0 — acc 0% không bao giờ bị quét.
    check("acc marketplace% = 0 → không quét",
          db.den_gio_quet_mkt("MKT Zero", c_user="mkt000") is False)
    check("acc marketplace% > 0, chưa quét lần nào → quét ngay",
          db.den_gio_quet_mkt("MKT Test", c_user="mkt001") is True)

    # 2) Nhịp quét: vừa quét xong thì nghỉ, đủ nhịp mới quét lại.
    db.ghi_nhan_quet_mkt("MKT Test", c_user="mkt001")
    _bgm = _dt.now()
    check("vừa quét xong → chưa tới nhịp",
          db.den_gio_quet_mkt("MKT Test", c_user="mkt001", bay_gio=_bgm) is False)
    check("120s sau → vẫn chưa tới nhịp (200s)",
          db.den_gio_quet_mkt("MKT Test", c_user="mkt001",
                              bay_gio=_bgm + _td(seconds=120)) is False)
    check("360s sau → tới nhịp, quét lại",
          db.den_gio_quet_mkt("MKT Test", c_user="mkt001",
                              bay_gio=_bgm + _td(seconds=360)) is True)
    check("đồng hồ vặn lùi → vẫn cho quét, không kẹt",
          db.den_gio_quet_mkt("MKT Test", c_user="mkt001",
                              bay_gio=_bgm - _td(seconds=120)) is True)

    # 3) Mốc "tin mới": chữ ký lần này TRỪ chữ ký đã thấy lần trước. Y HỆT phép
    #    so trong scheduler._scan_mkt_worker.
    def _moi(chua_doc, acc, cu):
        hien = {_mi.chu_ky(h): h for h in chua_doc}
        da_thay = db.doc_tin_moc_mkt(acc, c_user=cu)
        moi = [hien[k] for k in hien if k not in da_thay]
        db.ghi_tin_moc_mkt(acc, set(hien.keys()), c_user=cu)
        return moi

    check("mốc ban đầu rỗng",
          db.doc_tin_moc_mkt("MKT Test", c_user="mkt001") == set())
    _A = {"name": "An Nguyen",  "preview": "còn hàng không shop"}
    _B = {"name": "Binh Tran",  "preview": "ship về Huế bao nhiêu"}
    _C = {"name": "Cuong Le",   "preview": "cho xem thêm ảnh với"}
    check("lần quét đầu → cả 2 hội thoại chưa đọc đều là tin mới",
          len(_moi([_A, _B], "MKT Test", "mkt001")) == 2)
    # Lần sau: A còn chưa đọc (cũ, không báo lại), C mới xuất hiện → chỉ C mới.
    _m2 = _moi([_A, _C], "MKT Test", "mkt001")
    check("lần quét sau → chỉ hội thoại MỚI được báo, tin cũ im",
          len(_m2) == 1 and _m2[0]["name"] == "Cuong Le")
    # A đã rụng khỏi mốc (giờ mốc = {A,C}); nếu A quay lại chưa đọc vẫn không coi
    # là mới vì nó vẫn nằm trong mốc.
    check("hội thoại cũ vẫn chưa đọc ở lần kế → không báo lại",
          len(_moi([_A, _C], "MKT Test", "mkt001")) == 0)

    # 3b) Tin do CHÍNH MÌNH vừa trả lời (preview "Bạn:…") KHÔNG phải tin khách →
    #     loại ra, không báo. Bằng không: mình rep xong lại tự báo tin cho mình.
    check("preview mở đầu 'Bạn:' → không tính là tin khách",
          _mi.la_tin_khach({"name": "An", "preview": "Bạn: còn hàng nhé", "unread": True}) is False)
    check("preview mở đầu 'You:' → không tính là tin khách",
          _mi.la_tin_khach({"name": "An", "preview": "You: still available", "unread": True}) is False)
    check("preview là lời khách, CHƯA ĐỌC → tính là tin khách",
          _mi.la_tin_khach({"name": "An", "preview": "còn hàng không shop", "unread": True}) is True)
    # 20/10, nick Dang Xuan Duy: card KHÔNG ghi người gửi — tin mình nhắn khách
    # ("Chị có dùng zalo k ạ?…") hiện y như tin khách, không có "Bạn:", nên
    # Telegram báo cả tin mình gửi. Tin mình gửi thì luôn ĐÃ ĐỌC → chỉ báo chưa đọc.
    check("tin mình nhắn khách (card đã đọc, không có 'Bạn:') → KHÔNG báo",
          _mi.la_tin_khach({"name": "Hong Nhung", "bai": "Liên hệ/ Zalo: 0333 194 822",
                            "preview": "Chị có dùng zalo k ạ? Em xin phép kết nối",
                            "unread": False}) is False)
    check("không rõ đọc/chưa đọc (thiếu cờ) → KHÔNG báo",
          _mi.la_tin_khach({"name": "An", "preview": "còn hàng không shop"}) is False)
    check("tin hệ thống 'Cảnh giác với các hành vi lừa đảo…' → KHÔNG báo",
          _mi.la_tin_khach({"name": "Hong Nhung", "unread": True, "preview":
              "Cảnh giác với các hành vi lừa đảo thường gặp thông qua ứng dụng thanh toán"})
          is False)
    check("khách nhắc chữ 'lừa đảo' giữa câu vẫn được báo (lọc hệ thống khớp đầu câu)",
          _mi.la_tin_khach({"name": "An", "unread": True,
                            "preview": "Bên em có lừa đảo không vậy"}) is True)
    check("khách hỏi 'Mặt hàng này vẫn còn chứ?' (chưa đọc) → báo",
          _mi.la_tin_khach({"name": "Hong Nhung", "unread": True,
                            "preview": "Mặt hàng này vẫn còn chứ?"}) is True)
    # chu_ky đổi khi khách nhắn tin mới (preview đổi) → báo; đứng yên → im.
    check("khách nhắn tin mới (preview đổi) → chữ ký đổi",
          _mi.chu_ky({"name": "An", "preview": "còn không"}) !=
          _mi.chu_ky({"name": "An", "preview": "ship bao nhiêu"}))
    # chu_ky phân biệt theo BÀI: cùng người + cùng câu nhưng khác bài → khác tin.
    check("cùng người cùng câu nhưng khác bài → chữ ký khác",
          _mi.chu_ky({"name": "An", "bai": "Ghế", "preview": "còn không"}) !=
          _mi.chu_ky({"name": "An", "bai": "Bàn", "preview": "còn không"}))

    # 3c) Soạn tin Telegram — Kiểu 1: • Người — bài "Tên bài": nội dung.
    _tin = _tb.soan_tin_mkt("Máy Nhà", "Sa Tran Anh",
            [{"nguoi_gui": "Tùng", "bai": "Test", "trich": "còn hàng không shop"}])
    check("soạn tin có tên máy + acc + số tin",
          "Máy Nhà" in _tin and "Sa Tran Anh" in _tin and "1 tin Marketplace mới" in _tin)
    check("soạn tin tách tên bài theo Kiểu 1",
          '• <b>Tùng</b> — bài "Test": còn hàng không shop' in _tin)
    # Không có tên bài thì không ép ra chữ "bài" rỗng.
    _tin2 = _tb.soan_tin_mkt("Máy Nhà", "Acc X",
            [{"nguoi_gui": "Lan", "trich": "ib giá"}])
    check("không có tên bài → chỉ • Người: nội dung",
          "• <b>Lan</b>: ib giá" in _tin2 and "bài" not in _tin2)

    # 4) Kênh Telegram Market: tách hẳn, tắt là im; token/chat_id riêng.
    db.set_setting("tg_mkt_bat", "0")
    check("kênh Market tắt → san_sang_mkt() = False", _tb.san_sang_mkt() is False)
    check("kênh Market tắt → bao_tin_mkt trả False, không gửi gì",
          _tb.bao_tin_mkt("MKT Test", [{"nguoi_gui": "An", "trich": "test"}]) is False)
    db.set_setting("tg_mkt_bat", "1")
    db.set_setting("tg_mkt_token", "222222:TOKEN_MKT_GIA")
    db.set_setting("tg_mkt_chat_id", "-100888")
    _cfm = _tb.cau_hinh_mkt()
    check("cau_hinh_mkt đọc đúng token/chat_id riêng của kênh Market",
          _cfm["token"] == "222222:TOKEN_MKT_GIA" and _cfm["chat_id"] == "-100888")
    check("kênh Market dùng CHUNG tên máy với kênh trạng thái",
          _cfm["ten_may"] == _tb.cau_hinh()["ten_may"])
    check("bật + đủ thông tin → san_sang_mkt() = True", _tb.san_sang_mkt() is True)
    # Danh sách rỗng thì không có gì để báo, dù kênh đang bật.
    check("không có tin mới → bao_tin_mkt trả False",
          _tb.bao_tin_mkt("MKT Test", []) is False)

    # 5) Bước 4 — nhịp DỌN (tự xóa) bài niêm yết: den_gio_xoa_mkt / ghi_nhan.
    db.set_setting("mkt_xoa_bat", "0")
    check("tự xóa TẮT → den_gio_xoa_mkt luôn False (kể cả acc marketplace%>0)",
          db.den_gio_xoa_mkt("MKT Test", c_user="mkt001") is False)
    db.set_setting("mkt_xoa_bat", "1")
    check("bật tự xóa + acc marketplace%=0 → không dọn",
          db.den_gio_xoa_mkt("MKT Zero", c_user="mkt000") is False)
    check("bật + marketplace%>0 + chưa dọn lần nào → tới giờ",
          db.den_gio_xoa_mkt("MKT Test", c_user="mkt001") is True)
    db.ghi_nhan_xoa_mkt("MKT Test", c_user="mkt001")
    _bgx = _dt.now()
    check("vừa dọn xong → chưa tới nhịp (mặc định 24h)",
          db.den_gio_xoa_mkt("MKT Test", c_user="mkt001", bay_gio=_bgx) is False)
    check("25 giờ sau → tới nhịp dọn lại",
          db.den_gio_xoa_mkt("MKT Test", c_user="mkt001",
                             bay_gio=_bgx + _td(hours=25)) is True)
    db.set_setting("mkt_xoa_bat", "0")
finally:
    for _k3, _v3 in _mkt_cu.items():
        db.set_setting(_k3, _v3)
    try:
        with db._conn() as _c:
            _c.execute("DELETE FROM accounts WHERE ten_acc IN ('MKT Test','MKT Zero')")
    except Exception:
        pass

# Khoá theo acc + lồng quét vào runner mảng — chốt bằng mã nguồn scheduler.
_src_sch_mkt = Path("scheduler.py").read_text(encoding="utf-8")
check("scheduler có set running_accs khoá theo acc",
      "running_accs" in _src_sch_mkt)
check("worker đăng bỏ qua acc đang quét inbox Market",
      "if _ak in running_accs:" in _src_sch_mkt)
check("scheduler có worker quét Market riêng",
      "def _scan_mkt_worker" in _src_sch_mkt)
check("dispatch quét chỉ chạy ở runner mảng content",
      "loai_content_bat()" in _src_sch_mkt and "den_gio_quet_mkt" in _src_sch_mkt)
# ── Bước 4: tự xóa bài niêm yết Marketplace quá X ngày ──────────────────────
import market_cleanup as _mc
check("đọc tuổi: '5 ngày trước' → 5", _mc.doc_tuoi_ngay("Đã đăng 5 ngày trước") == 5)
check("đọc tuổi: 'hôm qua' → 1", _mc.doc_tuoi_ngay("Đăng hôm qua") == 1)
check("đọc tuổi: '2 tuần trước' → 14", _mc.doc_tuoi_ngay("2 tuần trước") == 14)
check("đọc tuổi: '3 giờ trước' → 0 (cùng ngày)", _mc.doc_tuoi_ngay("3 giờ trước") == 0)
check("đọc tuổi: 'vừa xong' → 0", _mc.doc_tuoi_ngay("Vừa xong") == 0)
check("đọc tuổi: '1 tháng trước' → 30", _mc.doc_tuoi_ngay("1 tháng trước") == 30)
check("đọc tuổi: chữ không có mốc → None (an toàn)", _mc.doc_tuoi_ngay("Ghế gỗ đẹp") is None)
check("tìm tuổi trong card: bỏ tiêu đề có số ('3 tháng sử dụng'), lấy dòng '4 ngày trước'",
      _mc._tim_tuoi(["Ghế sofa 3 tháng sử dụng", "2.000.000 đ", "4 ngày trước"]) == 4)
check("tìm tuổi: card không có dòng mốc nào → None",
      _mc._tim_tuoi(["Bàn ăn 6 ghế", "1.500.000 đ"]) is None)
# Ngày niêm yết tuyệt đối "DD/MM" (đo thật trên trang /you/selling).
_hn = _dt(2026, 10, 21).date()
check("ngày niêm yết '19/10' (hôm nay 21/10) → 2 ngày",
      _mc.doc_ngay_niem_yet("Còn hàng · Ngày niêm yết: 19/10", _hn) == 2)
check("ngày niêm yết '8/10' → 13 ngày",
      _mc.doc_ngay_niem_yet("Ngày niêm yết: 8/10", _hn) == 13)
check("ngày niêm yết qua năm '30/12' (hôm nay 2/1/2026) → 3 ngày (lùi năm)",
      _mc.doc_ngay_niem_yet("Ngày niêm yết: 30/12", _dt(2026, 1, 2).date()) == 3)
check("ngày niêm yết: không khớp → None", _mc.doc_ngay_niem_yet("Còn hàng") is None)
_bai_mau = [{"tieu_de": "a", "tuoi": 5}, {"tieu_de": "b", "tuoi": 2},
            {"tieu_de": "c", "tuoi": None}]
check("lọc quá hạn: chỉ bài tuổi > ngưỡng, BỎ bài tuổi None",
      [b["tieu_de"] for b in _mc.loc_qua_han(_bai_mau, 3)] == ["a"])
check("DOM luồng Xóa ĐÃ đo thật → _XOA_DA_DO_DOM = True",
      _mc._XOA_DA_DO_DOM is True)
_mc_quet_goc, _mc_xoa_goc = _mc.quet_bai_niem_yet, _mc._xoa
try:
    _mc.quet_bai_niem_yet = lambda *a, **k: list(_bai_mau)
    # Chạy thử: liệt kê quá hạn, KHÔNG xóa (không mở trình duyệt).
    _kq_thu = _mc.xoa_bai_cu("AccX", "cu", so_ngay=3, chay_thu=True)
    check("xoa_bai_cu (chạy thử): liệt kê quá hạn, da_xoa=0",
          _kq_thu["da_xoa"] == 0 and _kq_thu["chay_thu"] is True
          and len(_kq_thu["qua_han"]) == 1 and _kq_thu["qua_han"][0]["tieu_de"] == "a")

    # Xóa thật: gọi _xoa (thay bằng hàm giả để khỏi mở trình duyệt).
    async def _fake_xoa(*a, **k):
        return 1
    _mc._xoa = _fake_xoa
    _kq_that = _mc.xoa_bai_cu("AccX", "cu", so_ngay=3, chay_thu=False)
    check("xoa_bai_cu (xóa thật): gọi _xoa, da_xoa = số bài đã xóa",
          _kq_that["chay_thu"] is False and _kq_that["da_xoa"] == 1)
finally:
    _mc.quet_bai_niem_yet = _mc_quet_goc
    _mc._xoa = _mc_xoa_goc
# Sau khi xóa, FB hỏi 'Bạn đã bán...?' → chọn NGẪU NHIÊN 1 trong 4 lý do + Tiếp.
check("có đúng 4 lý do xóa để chọn ngẫu nhiên",
      len(_mc.LY_DO_XOA) == 4 and all(isinstance(x, str) and x for x in _mc.LY_DO_XOA))
_src_mc = Path("market_cleanup.py").read_text(encoding="utf-8")
check("market_cleanup chọn NGẪU NHIÊN lý do + bấm Tiếp (không chặn việc xóa)",
      "random.choice(LY_DO_XOA)" in _src_mc and "def _tra_loi_khao_sat" in _src_mc
      and 'name="Tiếp"' in _src_mc)
# 26/10: mỗi phiên chỉ xóa 1 bài ("xóa 1/10 bài quá 2 ngày") — sau khi xóa thì
# tải lại trang mà KHÔNG cuộn, bài cũ nằm dưới cùng chưa được FB nạp → tưởng hết.
_than_xoa_mc = _src_mc[_src_mc.index("async def _xoa("):_src_mc.index("def xoa_bai_cu(")]
check("dọn Market: tải lại sau mỗi lần xóa PHẢI cuộn nạp đủ danh sách",
      "await _tai_selling(page)" in _than_xoa_mc
      and "page.goto(SELLING_URL" not in _than_xoa_mc
      and "await _cuon_tai_het(page)" in _src_mc[_src_mc.index("async def _tai_selling"):])
check("dọn Market: chưa thấy bài quá hạn thì cuộn thêm 1 lượt rồi mới dừng",
      _than_xoa_mc.count("await _tim_muc_tieu()") == 2
      and "await _cuon_tai_het(page)" in _than_xoa_mc)


class _TrangGia:
    """Giả trang selling: mỗi lần cuộn đáy FB nạp thêm 5 dòng, tối đa `tong`."""
    def __init__(self, tong):
        self.tong, self.da_nap, self.cuon = tong, 5, 0

    async def evaluate(self, js, *a):
        if "scrollHeight" in js:
            self.cuon += 1
            self.da_nap = min(self.tong, self.da_nap + 5)
        elif "Ngày niêm yết" in js:
            return self.da_nap

    async def wait_for_timeout(self, ms):
        pass


_tg_mc = _TrangGia(23)
_aio.run(_mc._cuon_tai_het(_tg_mc))
check("cuộn nạp tới khi danh sách thôi dài thêm (23 bài → nạp đủ 23, không cuộn vô hạn)",
      _tg_mc.da_nap == 23 and _tg_mc.cuon <= 8)


class _TrangCham(_TrangGia):
    """FB nạp CHẬM: cứ 3 lượt cuộn mới thêm 5 dòng (27/10 Mai Trung Thao: 43 bài)."""
    async def evaluate(self, js, *a):
        if "scrollHeight" in js:
            self.cuon += 1
            if self.cuon % 3 == 0:
                self.da_nap = min(self.tong, self.da_nap + 5)
        elif "Ngày niêm yết" in js:
            return self.da_nap


_tc_mc = _TrangCham(43)
_aio.run(_mc._cuon_tai_het(_tc_mc))
check("cuộn kiên nhẫn: FB nạp chậm (3 lượt mới thêm bài) vẫn nạp đủ 43 bài",
      _tc_mc.da_nap == 43)
check("dọn Market: 1 bài hỏng không bỏ cả phiên — thử tiếp, chỉ dừng khi hỏng 3 lần liền",
      "loi_lien >= 3" in _than_xoa_mc and "await _tai_selling(page)" in _than_xoa_mc
      and "continue" in _than_xoa_mc)
check("dọn Market: lỗi giữa chừng vẫn trả số bài ĐÃ xóa (không mất tổng kết)",
      _than_xoa_mc.rstrip().endswith("return da_xoa"))
check("dọn Market: dừng mà còn bài quá hạn thì ghi log số dòng / số nút để chẩn đoán",
      "dừng mà còn" in _than_xoa_mc)
check("scheduler ghi tổng kết dọn cả khi xóa được 0 bài",
      'kq.get("da_xoa") or kq.get("qua_han")' in Path("scheduler.py").read_text(encoding="utf-8"))
# Dọn chạy im: KHÔNG báo Telegram, KHÔNG còn chế độ chạy thử ở runner.
check("gỡ hẳn báo Telegram cho dọn (soan_xoa_mkt/bao_xoa_mkt)",
      not hasattr(_tb, "soan_xoa_mkt") and not hasattr(_tb, "bao_xoa_mkt"))
check("worker dọn KHÔNG gọi báo Telegram + luôn xóa thật (chay_thu=False)",
      "bao_xoa_mkt" not in _src_sch_mkt and "chay_thu=False" in _src_sch_mkt
      and "mkt_xoa_chay_thu" not in _src_sch_mkt)
# Scheduler nối dọn + cài đặt mặc định + UI.
check("scheduler có worker dọn Market + dispatch den_gio_xoa_mkt + đánh nhịp",
      "def _xoa_mkt_worker" in _src_sch_mkt and "den_gio_xoa_mkt" in _src_sch_mkt
      and "ghi_nhan_xoa_mkt" in _src_sch_mkt)
_cd_mkt = db.doc_cai_dat_mkt()
check("MKT mặc định có mkt_xoa_bat=0 / sau_ngay=3 (KHÔNG còn chay_thu)",
      _cd_mkt.get("mkt_xoa_bat") == "0" and _cd_mkt.get("mkt_xoa_sau_ngay") == "3"
      and "mkt_xoa_chay_thu" not in _cd_mkt)
_html_mkt4 = Path("templates/index.html").read_text(encoding="utf-8")
_ajs_mkt4 = Path("static/js/app.js").read_text(encoding="utf-8")
check("UI Marketplace tự xóa chỉ còn ô bật + số ngày (đã bỏ Chạy thử)",
      'id="mkt-xoa-bat"' in _html_mkt4 and 'id="mkt-xoa-sau-ngay"' in _html_mkt4
      and 'id="mkt-xoa-chay-thu"' not in _html_mkt4)
check("app.js nạp + lưu cài đặt tự xóa (không còn mkt-xoa-chay-thu)",
      "mkt_xoa_bat:" in _ajs_mkt4 and "mkt-xoa-sau-ngay" in _ajs_mkt4
      and "mkt-xoa-chay-thu" not in _ajs_mkt4)

_src_mi = Path("market_inbox.py").read_text(encoding="utf-8")
check("market_inbox CHỈ đọc danh sách, KHÔNG gọi click lên hội thoại",
      ".click(" not in _src_mi and "click()" not in _src_mi)
# Chốt sửa lỗi 19/10: CHỈ quét panel Marketplace ([role=main]), KHÔNG vơ cả
# Messenger thường (các /messages/e2ee/t/… nằm ngoài main nhưng vẫn ở trong DOM).
check("market_inbox chỉ quét trong [role=main] (panel Marketplace)",
      '[role="main"]' in _src_mi)
check("danh sách hội thoại lấy TỪ main, không phải cả document",
      "main.querySelectorAll(" in _src_mi
      and "document.querySelectorAll('a" not in _src_mi)
check("market_inbox loại tin mình vừa trả lời (la_tin_khach)",
      "def la_tin_khach" in _src_mi and "quet_inbox_market" in _src_mi)
check("market_inbox đo chưa đọc theo nét chữ của CHÍNH phần tử (không lấy khối cha)",
      "unread: fw >= 600" in _src_mi and "nodeType === 3" in _src_mi)
check("market_inbox chỉ trả tin khách đã qua la_tin_khach",
      "khach = [d for d in ds if la_tin_khach(d)]" in _src_mi)

# ── Mọi chỗ ghi trạng thái đều phải báo, và báo ĐÚNG MỘT LẦN ────────────────
# `update_account_field` là cửa chung: cả giao diện lẫn scheduler đổi Trạng thái
# qua đó, nên nó tự so cũ với mới rồi báo. Hai hàm còn lại ghi thẳng bằng SQL
# nên phải tự gọi. Thêm chỗ ghi thứ tư mà quên báo thì sự cố sẽ âm thầm.
_src_db = Path("db.py").read_text(encoding="utf-8")
check("db.py báo ở đúng 3 chỗ (cửa chung + danh_dau_spam + het_spam)",
      _src_db.count("bao_doi_trang_thai(") == 3)
check("cửa chung update_account_field có đọc trạng thái cũ trước khi ghi",
      "SELECT ten_acc, trang_thai, c_user FROM accounts WHERE id=?" in _src_db)
check("join_groups_runner.py tự báo (nó ghi thẳng bằng SQL)",
      Path("join_groups_runner.py").read_text(encoding="utf-8")
          .count("bao_doi_trang_thai(") == 1)

# scheduler đổi Trạng thái QUA update_account_field. Gọi thêm bao_doi_trang_thai
# ở đó là mỗi sự cố nhắn hai lần vào nhóm chung — kiểu lỗi không ai coi là lỗi
# nên không ai đi sửa, chỉ làm người ta dần bỏ qua thông báo.
check("scheduler.py KHÔNG tự báo (tránh nhắn hai lần)",
      "bao_doi_trang_thai(" not in Path("scheduler.py").read_text(encoding="utf-8"))

# Quên truyền trạng thái cũ thì hàm im lặng — mất cảnh báo mà không có lỗi nào
# hiện ra. Mọi lời gọi thật đều phải nêu rõ nó.
for _f3 in ("db.py", "join_groups_runner.py"):
    _s3 = Path(_f3).read_text(encoding="utf-8")
    check(f"{_f3}: mọi lời gọi đều truyền trạng thái cũ",
          _s3.count("bao_doi_trang_thai(") == _s3.count("trang_thai_cu="))

# ── Mẹo offset ÂM không được sửa thành xác nhận ─────────────────────────────
# Telegram giao mỗi lệnh cho ĐÚNG MỘT bên hỏi rồi xoá. Ba máy cùng một bot mà
# máy nào cũng xác nhận đã đọc, thì /tinhtrang chỉ một máy trả lời — hỏng đúng
# cái tính năng này sinh ra để làm. Ai sửa thành offset=update_id+1 sẽ vướng đây.
_src_tb = Path("thong_bao.py").read_text(encoding="utf-8")
import re as _re
_m_off = _re.search(r'"getUpdates",\s*\{"offset":\s*"(-?\d+)"', _src_tb)
check("nghe lệnh có truyền offset", _m_off is not None)
check("offset phải ÂM — số dương là xác nhận đã đọc, máy khác sẽ mất lệnh",
      _m_off is not None and int(_m_off.group(1)) < 0)
check("không có chỗ nào xác nhận update_id + 1",
      "update_id\"] + 1" not in _src_tb and "uid + 1" not in _src_tb)

# ── Chỉ báo khi VƯỢT ranh giới chạy / không chạy ────────────────────────────
# Báo theo LẦN GHI thì một acc kẹt spam cả tuần sẽ nhắn 168 lần giống hệt nhau,
# vì phiên thăm dò ghi đè 'Spam' lên 'Spam' mỗi tiếng. Người ta sẽ tắt bot đi,
# rồi bỏ lỡ cảnh báo thật sự tiếp theo. Nên phải so trạng thái CŨ với MỚI.
for _cu, _moi, _mong in [
    ("Active",         "Spam",           "hong"),
    ("Active",         "Cookie hết hạn", "hong"),
    ("Spam",           "Active",         "hoi_phuc"),
    ("Cookie hết hạn", "Active",         "hoi_phuc"),
    # Ghi đè cùng trạng thái — chính là phiên thăm dò mỗi tiếng.
    ("Spam",           "Spam",           ""),
    ("Cookie hết hạn", "Cookie hết hạn", ""),
    # 'Dừng' là bạn tự tay cho nick nghỉ, không phải sự cố.
    ("Active",         "Dừng",           ""),
    ("Dừng",           "Active",         ""),
    ("Dừng",           "Spam",           ""),
    # Hỏng kiểu này sang hỏng kiểu khác: vẫn đang ngừng, không có gì mới.
    ("Spam",           "Cookie hết hạn", ""),
    # Không biết trạng thái cũ thì im, còn hơn báo bừa mỗi lần ghi.
    ("",               "Spam",           ""),
]:
    _ten = f"{_cu or '(không rõ)'} → {_moi}"
    check(f"{_ten}: {_mong or 'im lặng'}", _tb._huong_doi(_cu, _moi) == _mong)

# Khoá chống trùng phải gồm CẢ HAI đầu của lần chuyển. Chỉ lấy trạng thái mới
# thì acc được thả khỏi Spam lúc 10:00, rồi 10:03 nạp lại cookie xong — tin thứ
# hai bị nuốt, đúng cái tin đang chờ. Lỗi này đã xảy ra thật khi chạy thử.
check("hai lần chuyển khác nhau cùng đích thì KHÔNG nuốt nhau",
      _tb._da_bao_gan_day("Acc Kiểm Thử", "Spam→Active") is False
      and _tb._da_bao_gan_day("Acc Kiểm Thử", "Cookie hết hạn→Active") is False)
check("đúng lần chuyển đó lặp lại thì bị chặn",
      _tb._da_bao_gan_day("Acc Kiểm Thử", "Spam→Active") is True)

# ── Báo vào NHÓM chung ──────────────────────────────────────────────────────
# Nhiều máy cùng báo vào một nhóm để mấy quản trị viên cùng xem. Nhóm có hai
# ràng buộc mà chat riêng không có, và cả hai đều âm thầm.
check("có giãn cách giữa hai tin", hasattr(_tb, "GIAN_CACH_GIAY"))
# Telegram cho khoảng 20 tin/phút vào cùng một nhóm. Vượt thì nó NUỐT tin chứ
# không báo gì — mất cảnh báo mà không ai biết là đã mất.
check("giãn cách đủ thưa để không vượt ~20 tin/phút của nhóm",
      _tb.GIAN_CACH_GIAY >= 3.0)
check("giãn cách không thưa quá đến mức cảnh báo tới muộn",
      _tb.GIAN_CACH_GIAY <= 10)

check("tim_chat thiếu token → báo thiếu token",
      "token" in _tb.tim_chat("")[1].lower())

# Quên mã lệnh cũ để không phình bộ nhớ, nhưng KHÔNG được quên sạch: mỗi lần
# hỏi, Telegram trả lại đúng mấy lệnh gần nhất — quên sạch là trả lời lại từng
# ấy lệnh cũ thêm một lần nữa, vào nhóm chung, trước mặt mọi người.
_src_tb2 = Path("thong_bao.py").read_text(encoding="utf-8")
check("có dọn bớt mã lệnh đã xử lý", "_da_xu_ly" in _src_tb2 and "discard" in _src_tb2)
check("KHÔNG xoá sạch mã lệnh đã xử lý", "_da_xu_ly.clear()" not in _src_tb2)

# Trong KÊNH, bài đăng đến dưới dạng channel_post chứ không phải message. Chỉ
# nghe 'message' thì cảnh báo vẫn tới kênh còn /tinhtrang im lặng vĩnh viễn —
# hỏng mà không có lấy một dòng lỗi nào để lần ra. Nút 'Lấy hộ' lại có thể hiện
# ra kênh, nên người dùng hoàn toàn có thể đi thẳng vào cái bẫy đó.
check("nghe lệnh nhận cả channel_post (kênh)", "channel_post" in _src_tb2)
check("xin Telegram gửi cả channel_post",
      '"message","channel_post"' in _src_tb2)

# ── Tổng kết hằng ngày chỉ được gửi MỘT lần ─────────────────────────────────
# Mốc "đã gửi hôm nay" phải nằm trong cơ sở dữ liệu. Giữ trong biến thì tắt app
# mở lại là quên sạch, và mỗi lần khởi động lại sau giờ tổng kết sẽ gửi thêm
# một bản nữa — ngày chạy RUN_APP bốn lần là bốn tin giống hệt nhau.
# Đặt mốc giờ cố định thay vì so với đồng hồ thật: bài kiểm so đồng hồ thật sẽ
# đúng hay sai tuỳ lúc chạy — chạy gần nửa đêm là vỡ.
_luc = _dt(2026, 8, 28, 14, 30)          # 14:30 ngày 28/08
check("chưa gửi hôm nay + đã qua giờ → gửi",
      _tb._den_gio("08:00", "", _luc) is True)
check("đã gửi hôm nay rồi → không gửi lại",
      _tb._den_gio("08:00", "2026-08-28", _luc) is False)
check("chưa tới giờ → chưa gửi",
      _tb._den_gio("23:00", "", _luc) is False)
check("đúng phút đặt → gửi",
      _tb._den_gio("14:30", "", _luc) is True)
check("mốc hôm qua → sang ngày mới thì gửi",
      _tb._den_gio("08:00", "2026-08-27", _luc) is True)
check("giờ ghi sai định dạng → không gửi bừa",
      _tb._den_gio("tầm bậy", "", _luc) is False)
_src_vn = Path("thong_bao.py").read_text(encoding="utf-8")
check("mốc tổng kết ghi xuống cơ sở dữ liệu, không giữ trong biến",
      'set_setting("tg_tomtat_ngay"' in _src_vn
      and 'get_setting("tg_tomtat_ngay"' in _src_vn)

# ── Nút ẩn/hiện bảng Telegram ───────────────────────────────────────────────
# Bảng này là phần cài một lần rồi thôi, nên thu lại cho trang Hành động gọn.
# Đổi tên id ở một bên mà quên bên kia thì nút bấm không ăn, mà không có lỗi nào
# hiện ra — kiểu hỏng chỉ phát hiện khi có người thử bấm.
_html = Path("templates/index.html").read_text(encoding="utf-8")
_ajs3 = Path("static/js/app.js").read_text(encoding="utf-8")
for _id in ("tg-bang", "tg-mui-ten", "tg-nhan"):
    check(f"'{_id}' có trong cả giao diện lẫn mã",
          f'id="{_id}"' in _html and _id in _ajs3)
check("thanh tiêu đề gọi được tgGap()", 'onclick="tgGap()"' in _html)
check("có hàm tgGap", "function tgGap(" in _ajs3)
# Thu bảng lại thì vẫn phải biết đang bật hay tắt, nên nhãn trạng thái nằm ở
# thanh tiêu đề chứ không nằm trong phần bị ẩn.
check("nhãn trạng thái được cập nhật cả khi nạp lẫn khi lưu",
      _ajs3.count("_tgNhan(") >= 3)

# ── Không được thêm thư viện mới ────────────────────────────────────────────
# Cả file chỉ dùng thư viện chuẩn của Python. Thêm 'requests' vào đây là bắt
# mọi máy khách phải cài thêm, mà bản cài đã đóng gói sẵn thư viện từ trước.
check("thong_bao.py không dùng requests", "import requests" not in _src_tb)
check("thong_bao.py không dùng thư viện ngoài nào",
      "cryptography" not in _src_tb and "httpx" not in _src_tb)

# ── Kênh Telegram chết thì PHẢI KÊU LÊN ─────────────────────────────────────
# Đây là lối ra duy nhất của mọi cảnh báo. Trước đây cả ba đường hỏng đều im:
# `_goi_api` trả None và ghi log mức debug; `_luong_chay` thấy kq=None thì
# điều kiện `if kq and not kq.get("ok")` là False nên không làm gì; Telegram
# từ chối mà không kèm retry_after cũng rơi vào đúng nhánh đó. Kết quả: token
# hết hạn là ngừng nhận cảnh báo mà log sạch bong, và im lặng bị hiểu thành
# "hôm nay không có vấn đề gì" — đúng cơ chế đã gây ra lỗi câm 13 ngày.
_src_tb2 = Path("thong_bao.py").read_text(encoding="utf-8")
check("gọi API Telegram hỏng -> log WARNING, không phải DEBUG",
      'logger.warning(f"⚠️  Telegram {method} hỏng' in _src_tb2)
check("luồng gửi có đếm số lần hỏng LIÊN TIẾP", "_ghi_ket_qua(kq, hong)" in _src_tb2)
check("hỏng quá ngưỡng thì báo MẤT KÊNH ở mức ERROR",
      "MẤT KÊNH TELEGRAM" in _src_tb2 and "logger.error" in _src_tb2)
check("gửi lại được thì báo đã hồi phục",
      "gửi lại được sau" in _src_tb2)

# `kq` sau nhánh retry_after phải được GÁN LẠI, không thì lần gửi lại thành
# công vẫn bị đếm là hỏng.
check("gửi lại sau retry_after thì cập nhật lại kq",
      "kq = _goi_api(\"sendMessage\"" in _src_tb2)

_dem = []
for _kq, _hong in ((None, 0), ({"ok": False, "description": "bad token"}, 1),
                   ({"ok": True}, 2)):
    _dem.append(_tb._ghi_ket_qua(_kq, _hong))
check("không gọi được API -> tăng số lần hỏng", _dem[0] == 1)
check("Telegram từ chối -> tăng số lần hỏng",   _dem[1] == 2)
check("gửi được -> đếm lại từ 0",               _dem[2] == 0)

# ═══════════════════════════════════════════════════════════════════════════
# Sao lưu — bản sao chỉ có giá trị nếu MỞ ĐƯỢC
# ═══════════════════════════════════════════════════════════════════════════
# Bốn bản sao lưu đầu tiên của phần mềm này đều trông như thành công — `copy`
# chạy xong, không lỗi, UPDATE.bat in "[OK] Da sao luu" — mà cả bốn đều là file
# hỏng, SQLite mở lên báo "file is not a database". Dữ liệu 716 KB, bản sao 4 KB.
#
# Hai nguyên nhân, và bài kiểm dưới đây khoá cả hai lại.
import sao_luu as _sl
import sqlite3 as _sq3
import config as _cfg

_src_up = Path("UPDATE.bat").read_text(encoding="utf-8", errors="replace")

# 1. Chế độ WAL: những gì vừa ghi nằm trong app.db-wal, chưa gộp vào app.db.
#    `copy app.db` là chép thiếu. VACUUM INTO thì SQLite tự gộp.
check("sao lưu dùng VACUUM INTO chứ không phải copy",
      "VACUUM INTO" in Path("sao_luu.py").read_text(encoding="utf-8"))
check("UPDATE.bat KHÔNG còn copy thẳng app.db",
      "copy /y \"data\\app.db\"" not in _src_up)
check("UPDATE.bat gọi sao_luu.py", "sao_luu.py" in _src_up)
check("sao lưu thất bại thì UPDATE.bat DỪNG, không cập nhật tiếp",
      "if errorlevel 1" in _src_up and "DUNG LAI de khong lam mat gi" in _src_up)

# 2. Đường dẫn bị đoán: bản CÀI ĐẶT để dữ liệu ở %LOCALAPPDATA%, nên khối cũ
#    tìm "data\app.db" cạnh mã nguồn không thấy gì và bỏ qua sao lưu — máy vệ
#    tinh chưa từng được sao lưu lần nào.
check("nơi để bản sao lưu bám theo nơi dữ liệu thật, không phải mã nguồn",
      Path(_sl.thu_muc_dich()).parent == Path(_cfg.DB_PATH).parent.parent)

# Tạo thật một bản rồi MỞ LẠI đếm — không tin vào "lệnh chạy xong không báo lỗi".
# `sao_luu.tao()` đọc THẲNG config.DB_PATH làm nguồn. Trỏ tạm sang DB tạm CHỈ
# trong khối này (restore ở finally) — không đặt ở đầu file vì bài kiểm cấu trúc
# "DB nằm dưới DATA_ROOT" cần config.DB_PATH ở giá trị mặc định. Không trỏ thì
# bài kiểm đòi data/app.db THẬT — máy dev có, CI (checkout sạch) không → fail.
_cfg_db_goc = _cfg.DB_PATH
_cfg.DB_PATH = _tmp
_tm_sl = Path(_tmp).parent / "kiem_sao_luu"
try:
    _ban = _sl.tao(_tm_sl)
    check("bản sao lưu tạo ra có thật", _ban.exists())
    with _sq3.connect(f"file:{_ban}?mode=ro", uri=True) as _c_sl:
        _n_ban = _c_sl.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        _n_that = _sq3.connect(str(_cfg.DB_PATH)).execute(
            "SELECT COUNT(*) FROM accounts").fetchone()[0]
    check(f"bản sao MỞ ĐƯỢC và đủ tài khoản ({_n_ban}/{_n_that})", _n_ban == _n_that)
    check("bản sao không phải cái vỏ vài KB", _ban.stat().st_size > 50 * 1024)

    # Giữ 14 bản gần nhất. Không dọn thì ổ đĩa đầy dần rồi một ngày sao lưu hỏng
    # vì hết chỗ — đúng lúc cần nó nhất.
    check("có dọn bớt bản cũ", _sl.GIU_LAI == 14)

    # ── Mã hoá: file rời khỏi máy KHÔNG được để lộ gì ───────────────────────
    # File sao lưu chứa mật khẩu Facebook, cookie xs, mã 2FA của MỌI tài khoản.
    # Ai cầm được nó là đăng nhập được vào tất cả.
    _MK = "mat khau dung cho bai kiem"
    _enc = _sl.ma_hoa(_ban, _MK, _tm_sl / "kiem.enc")
    _tho = _enc.read_bytes()

    check("file mã hoá có nhãn nhận dạng", _tho.startswith(_sl.DAU_FILE))
    try:
        _sq3.connect(f"file:{_enc}?mode=ro", uri=True).execute("SELECT 1 FROM accounts")
        check("file mã hoá KHÔNG còn mở được bằng SQLite", False)
    except Exception:
        check("file mã hoá KHÔNG còn mở được bằng SQLite", True)

    # Bài kiểm quan trọng nhất của cả phần này: soi từng mật khẩu thật xem có
    # byte nào lọt nguyên văn ra file đã mã hoá không.
    _mk_that = [(a.get("password") or "") for a in db.get_accounts()
                if (a.get("password") or "").strip()]
    _lo = [m for m in _mk_that if m.encode() in _tho]
    check(f"không mật khẩu Facebook nào lọt ra file mã hoá ({len(_mk_that)} cái soi)",
          not _lo)
    _ck_that = [(a.get("xs") or "") for a in db.get_accounts() if (a.get("xs") or "").strip()]
    check(f"không cookie nào lọt ra file mã hoá ({len(_ck_that)} cái soi)",
          not [c for c in _ck_that if c.encode() in _tho])

    # Hai lần mã hoá cùng dữ liệu phải ra hai file khác hẳn — nếu giống nhau thì
    # người ngoài nhìn vào là biết hôm nay dữ liệu có đổi hay không.
    _enc2 = _sl.ma_hoa(_ban, _MK, _tm_sl / "kiem2.enc")
    check("mỗi lần mã hoá ra một file khác nhau",
          _enc2.read_bytes() != _tho)

    # ── Giải mã và các đường hỏng ──────────────────────────────────────────
    _ra = _sl.giai_ma(_enc, _MK, _tm_sl / "giai.db")
    check("giải mã đúng mật khẩu → về đủ tài khoản", _sl.dem_acc(_ra) == _n_that)

    for _mo_ta, _ham in (
        ("sai mật khẩu bị từ chối",
         lambda: _sl.giai_ma(_enc, "sai bet", _tm_sl / "x1.db")),
        ("file không phải của phần mềm này bị từ chối",
         lambda: _sl.giai_ma(_ban, _MK, _tm_sl / "x3.db")),
    ):
        try:
            _ham(); check(_mo_ta, False)
        except Exception:
            check(_mo_ta, True)

    # Sửa một byte trong ruột file — Fernet phải phát hiện. Không có bước này
    # thì file hỏng trên đường truyền sẽ giải mã ra rác mà vẫn coi là thành công.
    _sua = _tm_sl / "sua.enc"
    _b = bytearray(_tho); _b[-5] ^= 0xFF; _sua.write_bytes(bytes(_b))
    try:
        _sl.giai_ma(_sua, _MK, _tm_sl / "x2.db")
        check("file bị sửa một byte bị phát hiện", False)
    except Exception:
        check("file bị sửa một byte bị phát hiện", True)

    # ── Đường khôi phục phải luôn còn ──────────────────────────────────────
    # Bản sao lưu chưa khôi phục thử thì chưa phải bản sao lưu.
    check("có hàm khôi phục", callable(getattr(_sl, "khoi_phuc", None)))
    check("có KHOI_PHUC_DU_LIEU.bat cho người dùng",
          Path("KHOI_PHUC_DU_LIEU.bat").exists())
    _bat_kp = Path("KHOI_PHUC_DU_LIEU.bat").read_text(encoding="utf-8", errors="replace")
    check("file khôi phục tắt phần mềm trước khi thay dữ liệu", "taskkill" in _bat_kp)
    _src_sl = Path("sao_luu.py").read_text(encoding="utf-8")
    check("khôi phục cất bản đang dùng sang một bên trước",
          "truoc_khi_khoi_phuc" in _src_sl)
    check("khôi phục xoá WAL cũ để SQLite không gộp nhầm dữ liệu cũ",
          '"-wal", "-shm"' in _src_sl)

    # `with sqlite3.connect(...)` chỉ commit chứ KHÔNG đóng kết nối. Trên Windows
    # file vẫn bị giữ, nên khôi phục ném PermissionError — lỗi này đã xảy ra thật
    # và chỉ lộ ra khi diễn tập khôi phục.
    check("mọi kết nối SQLite trong sao_luu.py đều được đóng thật",
          "with sqlite3.connect" not in _src_sl
          and _src_sl.count("contextlib.closing") >= 4)

    # ── Bản sao lưu KHÔNG được rơi vào nhóm quản trị ───────────────────────
    # Quản trị viên cần biết acc nào hỏng, không cần mật khẩu của acc đó.
    # Nơi gửi lấy thẳng từ tab Báo về Telegram — chủ dự án chọn vậy để khỏi
    # điền hai chỗ, và để thêm một trạm mới chỉ là điền đúng một bộ thông số.
    check("nơi gửi lấy từ cấu hình Telegram, không có ô riêng",
          'db.get_setting("tg_chat_id"' in _src_sl and "sl_chat_id" not in _src_sl)
    check("chưa cấu hình Telegram thì không gửi bừa",
          "Chưa cấu hình Telegram" in _src_sl)
    check("chưa đặt mật khẩu thì không gửi file trần",
          "Chưa đặt mật khẩu mã hoá" in _src_sl)

    # ── Máy bật liên tục vẫn phải sao lưu mỗi ngày ─────────────────────────
    # Trước đây dùng một biến bật/tắt đặt một lần cho cả đời tiến trình, nên máy
    # để chạy suốt sẽ sao lưu ĐÚNG MỘT LẦN rồi thôi vĩnh viễn — hôm sau, tuần
    # sau đều không chạy, mà không có dấu hiệu gì. Máy trạm bật cả ngày là
    # trường hợp thường gặp nhất, nên đó là chỗ hỏng nặng nhất.
    _src_tn = Path("thong_bao.py").read_text(encoding="utf-8")
    check("có khoảng thời gian hỏi lại việc sao lưu", hasattr(_tb, "THU_SAO_LUU_PHUT"))
    check("hỏi lại đủ dày để sang ngày mới không trễ quá một tiếng",
          _tb.THU_SAO_LUU_PHUT <= 60)
    check("hỏi lại không quá dày, khỏi phí công",
          _tb.THU_SAO_LUU_PHUT >= 10)
    check("đo bằng thời điểm, KHÔNG bằng biến bật/tắt một lần",
          "lan_thu_sao_luu" in _src_tn and "da_thu_sao_luu" not in _src_tn)
    # Mốc khởi tạo phải là 0 để lần hỏi đầu nổ ngay khi mở phần mềm, chứ không
    # bắt người dùng chờ hết một chu kỳ.
    check("mở phần mềm là sao lưu ngay, không chờ hết chu kỳ",
          "lan_thu_sao_luu = 0.0" in _src_tn)

    # Đẩy đi hỏng thì KHÔNG được ghi nhận "hôm nay xong" — để hôm sau còn thử lại.
    _i_gui = _src_sl.index("if not ok:")
    _i_ghi = _src_sl.index('db.set_setting("sl_ngay"')
    check("đẩy đi hỏng thì không đánh dấu là đã xong", _i_gui < _i_ghi)
except Exception as _e_sl:
    check(f"tạo được bản sao lưu (lỗi: {_e_sl})", False)
finally:
    _cfg.DB_PATH = _cfg_db_goc   # trả config.DB_PATH về mặc định
    import shutil as _sh
    _sh.rmtree(_tm_sl, ignore_errors=True)

# ═══════════════════════════════════════════════════════════════════════════
# Lấy lại phiên cho acc hết xs
# ═══════════════════════════════════════════════════════════════════════════
# `xs` trong DB và cookie trong profile Chrome là HAI KHO RIÊNG. Cái trong DB là
# ảnh chụp lúc nhập tay; cái trong profile do Chrome giữ và Facebook làm mới mỗi
# lần acc hoạt động. Đo trên máy thật: 12/12 acc đọc được đều có `xs` ở profile
# KHÁC hẳn `xs` trong DB — không một cái nào còn trùng.
import cookie_exporter as _ce
import khoi_phuc_phien as _kp

_src_ce = Path("cookie_exporter.py").read_text(encoding="utf-8")
_src_sch = Path("scheduler.py").read_text(encoding="utf-8")
_src_kp = Path("khoi_phuc_phien.py").read_text(encoding="utf-8")

# ── Tầng 0: giữ xs khỏi cũ đi ──────────────────────────────────────────────
check("có hàm đồng bộ xs sau phiên", callable(getattr(_ce, "dong_bo_xs", None)))
check("scheduler gọi nó sau mỗi phiên", "dong_bo_xs" in _src_sch)
# Đặt trong _don_cache_sau_phien vì đó là lúc DUY NHẤT chắc chắn trình duyệt đã
# đóng — profile còn mở thì Chrome khoá file cookie và đọc không ra.
_i_don = _src_sch.index("def _don_cache_sau_phien")
_i_sync = _src_sch.index("dong_bo_xs")
check("đồng bộ xs đặt trong hàm chạy sau khi trình duyệt đã đóng",
      _i_don < _i_sync < _src_sch.index("def _cuu_phien_het_han"))

# `get_account_by_name` CHỈ trả acc Active/Spam. Dùng nó ở đây thì acc đang
# 'Dừng' hay 'Cookie hết hạn' tra ra rỗng — đúng những acc cần giữ xs nhất.
_i_ds = _src_ce.index("def dong_bo_xs")
# Bỏ dòng chú thích trước khi soi: chính chú thích trong hàm đó giải thích VÌ SAO
# không dùng `get_account_by_name`, nên soi cả chú thích là bắt nhầm.
_than_ds = "\n".join(l for l in _src_ce[_i_ds:_src_ce.index("def _find_profile_dir")].splitlines()
                     if not l.lstrip().startswith("#"))
check("đồng bộ xs KHÔNG gọi get_account_by_name (hàm đó lọc mất acc Dừng)",
      "get_account_by_name" not in _than_ds)

check("acc không có thật thì trả rỗng, không nổ", _ce.dong_bo_xs("Acc Không Có Thật") == "")
check("tên rỗng thì trả rỗng, không nổ", _ce.dong_bo_xs("") == "")

# ── Tầng 1: cứu từ profile ─────────────────────────────────────────────────
check("có hàm quét cứu phiên", callable(getattr(_kp, "quet", None)))
check("scheduler gọi quét cứu phiên", "_cuu_phien_het_han" in _src_sch)

# Bốn tiến trình scheduler chạy song song. Để cả bốn cùng quét thì một acc bị
# bốn trình duyệt mở lên cùng lúc.
check("chỉ MỘT loại scheduler chạy quét cứu, tránh mở bốn trình duyệt cùng lúc",
      'if LOAI != "homestay"' in _src_sch)

# Chỉ trả acc về Active khi Facebook ĐÃ XÁC NHẬN phiên còn sống. Dựa vào "đọc
# được cookie" thôi thì chưa đủ: file cookie vẫn còn nguyên sau khi phiên bị thu
# hồi, nên acc sẽ về Active rồi hỏng lại ngay, mỗi vòng bắn một cặp tin Telegram.
check("phải hỏi Facebook trước khi trả acc về Active",
      "chua_dang_nhap" in _src_kp)
_i_hoi = _src_kp.index("if await chua_dang_nhap(page)")
_i_active = _src_kp.index('update_account_field(acc["id"], "trang_thai", "Active")')
check("hỏi Facebook TRƯỚC rồi mới đổi trạng thái", _i_hoi < _i_active)

# Đổi qua update_account_field để nó tự so cũ/mới rồi bắn '🟢 HOẠT ĐỘNG TRỞ LẠI'.
check("đổi trạng thái qua cửa chung, để tin Telegram tự bắn",
      "update_account_field" in _src_kp
      and "UPDATE accounts SET trang_thai" not in _src_kp)

# Profile đang mở nghĩa là acc đó đang chạy phiên — đụng vào là hỏng cả hai.
check("bỏ qua acc có profile đang mở", "_profile_dang_mo" in _src_kp)
# Profile đăng nhập sang nick khác thì ghi bừa sẽ gán cookie nhầm nick.
check("từ chối khi profile đang là nick khác", "profile đang là nick khác" in _src_kp)

check("có giãn cách giữa hai lần thử cứu cùng một acc", _kp.NGHI_PHUT >= 30)
check("mỗi lượt chỉ cứu vài acc, khỏi mở cả loạt trình duyệt", 1 <= _kp.MOI_LUOT <= 5)
# Vòng lặp scheduler gọi hàm này; một profile hỏng treo vô hạn là đứng luôn
# việc đăng bài.
check("có chặn trên thời gian cho mỗi acc", 30 <= _kp.CHO_GIAY <= 180)
check("chặn trùng ghi xuống cơ sở dữ liệu (bốn tiến trình không thấy nhau)",
      "kp_da_thu" in _src_kp)

# Việc KIỂM và việc GHI DẤU phải tách rời. Gộp lại rồi gọi trong bộ lọc thì mọi
# acc hết hạn đều bị ghi dấu "vừa thử", trong khi chỉ MOI_LUOT acc đầu được thử
# thật — 10 acc hỏng thì 7 acc bị khoá 90 phút mà chưa hề được đụng tới.
check("kiểm và ghi dấu là hai hàm riêng",
      callable(getattr(_kp, "_con_nghi", None))
      and callable(getattr(_kp, "_danh_dau_da_thu", None)))
# rindex chu khong index: docstring cua ham co chep lai doan ma CU de
# giai thich loi, nen index() bat nham vao vi du do.
_loc = _src_kp[_src_kp.rindex("cho = ["):_src_kp.rindex("][:MOI_LUOT]")]
check("bộ lọc chỉ ĐỌC, không ghi dấu",
      "_con_nghi(" in _loc and "_danh_dau_da_thu" not in _loc)
check("ghi dấu ngay trước khi thử thật",
      _src_kp.index("_danh_dau_da_thu(_khoa(a))") < _src_kp.index("cuu_mot_acc(a)"))
# Bộ đếm "đã thử" theo c_user, không theo tên — hai nick trùng tên không được
# chặn lượt cứu của nhau.
check("đếm 'đã thử' theo c_user",
      _kp._khoa({"ten_acc": "Tuấn Ngọc", "c_user": "111"}) == "111"
      and _kp._khoa({"ten_acc": "Tuấn Ngọc", "c_user": ""}) == "Tuấn Ngọc")

# ═══════════════════════════════════════════════════════════════════════════
# Lịch của máy — sáng tự chạy, khuya tự nghỉ
# ═══════════════════════════════════════════════════════════════════════════
import lich_may as _lm

# ── Giờ BẬT runner: "đã qua giờ chưa" ──────────────────────────────────────
# Bật muộn là vô hại, thậm chí mong muốn: mở phần mềm lúc 9h sáng thì vẫn nên
# bật runner lên chạy.
for _h, _mong in ((6, False), (7, True), (9, True), (15, True)):
    check(f"bật runner lúc {_h:02d}:00 (mốc 07:00) → {_mong}",
          _lm._qua_gio("07:00", _dt(2026, 9, 8, _h, 0)) is _mong)

# ── Giờ CHO MÁY NGHỈ: phải dùng CỬA SỔ ─────────────────────────────────────
# Đây là chỗ suýt hỏng nặng. Dùng "đã qua giờ chưa" như lúc bật thì: đêm qua
# máy tắt, 9h sáng mở phần mềm lên — mốc 01:00 vẫn tính là "đã qua mà hôm nay
# chưa chạy", và máy NGỦ ĐÔNG NGAY LÚC 9H SÁNG, cắt ngang mọi thứ.
for _h, _p, _mong in ((0, 59, False), (1, 0, True), (1, 29, True),
                      (1, 30, False), (9, 0, False), (23, 0, False)):
    check(f"cho máy nghỉ lúc {_h:02d}:{_p:02d} (mốc 01:00) → {_mong}",
          _lm._trong_cua_so("01:00", _dt(2026, 9, 8, _h, _p)) is _mong)
check("MỞ PHẦN MỀM LÚC 9H SÁNG KHÔNG làm máy ngủ đông",
      _lm._trong_cua_so("01:00", _dt(2026, 9, 8, 9, 0)) is False)

# Cửa sổ phải cộng vòng qua nửa đêm: mốc 23:50 thì chạy tới 00:20 hôm sau.
check("cửa sổ cộng vòng qua nửa đêm",
      _lm._trong_cua_so("23:50", _dt(2026, 9, 8, 0, 10)) is True
      and _lm._trong_cua_so("23:50", _dt(2026, 9, 8, 0, 20)) is False)

# ── Chạy qua nhiều ngày: mỗi ngày đúng một lần bật, một lần nghỉ ───────────
_lm_cu = {k: db.get_setting(k, "") for k in
          ("lm_bat", "lm_gio_bat", "lm_gio_tat", "lm_runner", "lm_hanh_dong",
           "lm_ngay_bat", "lm_ngay_tat")}
_that_bat, _that_tat, _that_nghi = _lm.bat_runner, _lm.tat_runner, _lm._cho_may_nghi
_dem = {"bat": 0, "tat": 0, "nghi": []}
try:
    _lm.bat_runner    = lambda: (_dem.__setitem__("bat", _dem["bat"] + 1), 2)[1]
    _lm.tat_runner    = lambda: (_dem.__setitem__("tat", _dem["tat"] + 1), 3)[1]
    _lm._cho_may_nghi = lambda hd: _dem["nghi"].append(hd)
    for _k, _v in (("lm_bat", "1"), ("lm_gio_bat", "07:00"), ("lm_gio_tat", "01:00"),
                   ("lm_runner", "homestay,nuoi"), ("lm_hanh_dong", "ngu_dong"),
                   ("lm_ngay_bat", ""), ("lm_ngay_tat", "")):
        db.set_setting(_k, _v)

    _t = _dt(2026, 9, 8, 5, 0)
    for _ in range(3 * 24 * 3):          # 3 ngày, kiểm mỗi 20 phút
        _lm.kiem_tra(_t)
        _t += _td(minutes=20)
    check(f"3 ngày → đúng 3 lần bật (đếm được {_dem['bat']})", _dem["bat"] == 3)
    check(f"3 ngày → đúng 3 lần nghỉ (đếm được {len(_dem['nghi'])})",
          len(_dem["nghi"]) == 3)
    check("cho máy nghỉ đúng kiểu đã chọn",
          set(_dem["nghi"]) == {"ngu_dong"})

    # Tắt lịch thì tuyệt đối không đụng gì tới máy.
    _dem["nghi"].clear()
    db.set_setting("lm_bat", "0")
    db.set_setting("lm_ngay_tat", "")
    check("tắt lịch thì không làm gì", _lm.kiem_tra(_dt(2026, 9, 9, 1, 0)) == "")
    check("tắt lịch thì tuyệt đối không cho máy nghỉ", not _dem["nghi"])
finally:
    _lm.bat_runner, _lm.tat_runner, _lm._cho_may_nghi = _that_bat, _that_tat, _that_nghi
    for _k, _v in _lm_cu.items():
        db.set_setting(_k, _v)

check("đã trả cấu hình lịch máy về như cũ",
      db.get_setting("lm_bat", "") == _lm_cu["lm_bat"])

# ── Mở phần mềm giữa giờ làm việc thì dựng runner dậy ──────────────────────
# Lịch hằng ngày chỉ nổ MỘT lần mỗi ngày và có ghi dấu "hôm nay chạy rồi", nên
# tình huống này lọt lưới: 07:00 chạy → 12:00 tắt máy đi ăn → 14:00 bật lại thì
# phần mềm thấy "hôm nay chạy rồi" và NẰM IM. Mất trắng buổi chiều, không dấu hiệu.
_lm_cu2 = {k: db.get_setting(k, "") for k in
           ("lm_bat", "lm_gio_bat", "lm_gio_tat", "lm_runner", "lm_ngay_bat", "lm_ngay_tat")}
_that_bat2 = _lm.bat_runner
_dem2 = {"n": 0}
try:
    _lm.bat_runner = lambda: (_dem2.__setitem__("n", _dem2["n"] + 1), 2)[1]
    for _k, _v in (("lm_bat", "1"), ("lm_gio_bat", "07:00"), ("lm_gio_tat", "02:00"),
                   ("lm_runner", "homestay,thue")):
        db.set_setting(_k, _v)

    # Giờ làm vắt qua nửa đêm: 07:00 → 02:00.
    for _h, _mong in ((6, False), (7, True), (12, True), (23, True),
                      (1, True), (2, False), (4, False)):
        check(f"{_h:02d}:00 trong giờ làm việc (07:00→02:00) → {_mong}",
              _lm.trong_gio_lam_viec(_dt(2026, 9, 7, _h, 0)) is _mong)

    # Sáng đã chạy rồi, trưa tắt máy, chiều bật lại.
    db.set_setting("lm_ngay_bat", "2026-09-07")
    _lm._da_dung_lai = False
    _dem2["n"] = 0
    check("mở phần mềm lúc 14:00 (sáng đã chạy) → vẫn dựng runner dậy",
          bool(_lm.dung_lai_neu_can(_dt(2026, 9, 7, 14, 0))) and _dem2["n"] == 1)

    # Nhưng chỉ MỘT lần mỗi lần mở phần mềm. Làm liên tục thì người dùng vừa bấm
    # Dừng một runner là 20 giây sau nó tự bật lại.
    _dem2["n"] = 0
    for _ in range(3):
        _lm.dung_lai_neu_can(_dt(2026, 9, 7, 14, 1))
    check("các vòng sau KHÔNG bật lại, để người dùng bấm Dừng được", _dem2["n"] == 0)

    # Ngoài giờ làm thì tuyệt đối không bật.
    _lm._da_dung_lai = False
    _dem2["n"] = 0
    _lm.dung_lai_neu_can(_dt(2026, 9, 7, 4, 0))
    check("mở phần mềm lúc 04:00 (ngoài giờ làm) → không bật gì", _dem2["n"] == 0)

    # Lịch tắt thì không đụng gì.
    _lm._da_dung_lai = False
    db.set_setting("lm_bat", "0")
    _dem2["n"] = 0
    _lm.dung_lai_neu_can(_dt(2026, 9, 7, 14, 0))
    check("lịch tắt → không dựng runner", _dem2["n"] == 0)
finally:
    _lm.bat_runner = _that_bat2
    _lm._da_dung_lai = False
    for _k, _v in _lm_cu2.items():
        db.set_setting(_k, _v)

# Cờ "đã dựng lại" phải nằm trong bộ nhớ, KHÔNG ghi xuống cơ sở dữ liệu: nó phải
# quên đi mỗi lần mở lại phần mềm — đó chính là điều nó dùng để nhận ra.
_src_lm0 = Path("lich_may.py").read_text(encoding="utf-8")
# LÀM XONG RỒI MỚI ĐÁNH DẤU. Đánh dấu trước rồi mới làm thì chỉ cần bước sau
# hỏng — hoặc phần mềm bị tắt đúng khoảnh khắc giữa hai dòng — là mốc còn đó mà
# việc chưa làm, và CẢ ĐÊM ĐÓ máy không bao giờ ngủ. Đã xảy ra thật 07/09.
_i_nghi   = _src_lm0.index('_cho_may_nghi(c["hanh_dong"])')
_i_dau_tat = _src_lm0.index('set_setting("lm_ngay_tat", hom)')
check("cho máy nghỉ TRƯỚC, đánh dấu SAU", _i_nghi < _i_dau_tat)
_i_bat     = _src_lm0.index("n = bat_runner()", _src_lm0.index('_qua_gio(c["gio_bat"]'))
_i_dau_bat = _src_lm0.index('set_setting("lm_ngay_bat", hom)')
check("bật runner TRƯỚC, đánh dấu SAU", _i_bat < _i_dau_bat)

check("cờ đã-dựng-lại không ghi xuống cơ sở dữ liệu",
      "_da_dung_lai" in _src_lm0 and 'set_setting("lm_da_dung_lai' not in _src_lm0)

# ── Máy tắt hẳn thì phần mềm KHÔNG đánh thức được ──────────────────────────
# Sự thật kỹ thuật này phải hiện ra trong giao diện, không thì người dùng chọn
# "Tắt hẳn" rồi sáng hôm sau ngồi chờ một cái máy nằm im.
_html_lm = Path("templates/index.html").read_text(encoding="utf-8")
_src_lm  = Path("lich_may.py").read_text(encoding="utf-8")
_ajs_lm = Path("static/js/app.js").read_text(encoding="utf-8")
check("giao diện có cảnh báo cho lựa chọn Tắt hẳn", "_lmCanhBao" in _ajs_lm)
check("cảnh báo nói rõ phải vào BIOS", "BIOS" in _ajs_lm or "RTC Alarm" in _ajs_lm)
check("có file cài lịch đánh thức", Path("CAI_LICH_MAY.bat").exists())
_bat_lm = Path("CAI_LICH_MAY.bat").read_text(encoding="utf-8", errors="replace")
# schtasks KHÔNG có cờ "đánh thức máy để chạy" — mà đó là thứ duy nhất cần ở đây.
check("dùng PowerShell -WakeToRun chứ không phải schtasks", "-WakeToRun" in _bat_lm)
# Windows mặc định TẮT hẹn giờ đánh thức trên laptop; tắt thì tác vụ vô dụng.
check("có bật 'cho phép hẹn giờ đánh thức'", "RTCWAKE" in _bat_lm)
check("có bật chế độ ngủ đông", "hibernate on" in _bat_lm)
# Giờ đánh thức đọc từ chính cơ sở dữ liệu, khỏi phải điền hai nơi rồi lệch nhau.
check("giờ đánh thức lấy từ cấu hình trong phần mềm", "lm_gio_bat" in _bat_lm)

# ── Hai nơi giữ giờ sáng, phần mềm phải tự đối chiếu ───────────────────────
# Giờ sáng nằm ở phần mềm VÀ ở tác vụ đánh thức của Windows. Đổi trong phần mềm
# mà quên chạy lại CAI_LICH_MAY.bat thì máy vẫn thức — nhưng theo giờ CŨ. Nhìn
# như chạy được, chỉ là muộn mấy tiếng, và không một dòng lỗi nào.
check("đọc được giờ Windows đang hẹn", callable(getattr(_lm, "gio_danh_thuc", None)))
check("có hàm đối chiếu hai bên", callable(getattr(_lm, "tinh_trang_danh_thuc", None)))
_tt_dt = _lm.tinh_trang_danh_thuc()
for _k in ("gio_phan_mem", "gio_windows", "da_cai", "khop"):
    check(f"kết quả đối chiếu có '{_k}'", _k in _tt_dt)

# Đọc XML chứ không đọc bản in /FO LIST: bản in ra theo ngôn ngữ và định dạng
# giờ của máy ("7:00:00 AM"), nên phân tích nó sẽ hỏng trên máy đặt ngôn ngữ khác.
check("đọc giờ từ XML, không phụ thuộc ngôn ngữ máy",
      "StartBoundary" in _src_lm and "/XML" in _src_lm)

# Bấm nút sửa thì phải chạy có quyền quản trị, không thì tác vụ không ghi được.
check("nút sửa chạy CAI_LICH_MAY.bat có quyền quản trị",
      "-Verb RunAs" in _src_lm and "CAI_LICH_MAY.bat" in _src_lm)
check("giao diện có nút sửa khi lệch giờ", "lmCaiDanhThuc" in _ajs_lm)


# ═══════════════════════════════════════════════════════════════════════════
# Tắt phần mềm phải THẬT SỰ tắt
# ═══════════════════════════════════════════════════════════════════════════
# Bấm "Tắt phần mềm" thì runner chết hết nhưng SERVER VẪN SỐNG — đo được: 21
# phút sau vẫn phục vụ bình thường. Người dùng tưởng đã tắt, thực ra chưa.
#
# Nguyên nhân: `subprocess.run(..., capture_output=True)` KHÔNG có hạn chờ. Nó
# đợi tới khi ống dữ liệu đóng, mà tiến trình con của Chrome giữ ống đó — nên
# treo vĩnh viễn, và `os._exit(0)` phía sau không bao giờ chạy.
_src_sv = Path("server.py").read_text(encoding="utf-8")

# Tắt phải THẬT SỰ tắt, và phải nhanh. Đo tận tay lúc 02:3x ngày 19/09 trên
# chính runner Bán (PID 6212):
#     taskkill /F /T /PID 6212  -> treo >20 giây, chạy HAI lần, tiến trình VẪN SỐNG
#     TerminateProcess(6212)    -> chết trong 0,00 giây
# `taskkill /T` phải tự duyệt cây tiến trình của cả máy; máy này lúc tải nặng có
# hơn hai trăm tiến trình nên nó nghẽn ở đó.
check("KHÔNG còn gọi taskkill ở đâu nữa", '["taskkill"' not in _src_sv)

# Việc xử lý tiến trình nay nằm ở `tien_trinh.py`, dùng chung giữa server và
# `dung_het.py` (RESTART.bat gọi file đó, không nên nạp cả Flask chỉ để tắt một
# tiến trình). Trước đây mỗi nơi giữ một bản chép của bốn hàm này.
import tien_trinh as _tt

def _chi_ma(src: str) -> str:
    """Bỏ docstring và dòng chú thích — chính chỗ đó GHI LẠI vì sao không dùng
    WMI/taskkill nữa, nên soi cả file thì phép kiểm đọc trúng lời giải thích."""
    import re as _r
    src = _r.sub(r'"""[\s\S]*?"""', "", src)
    return chr(10).join(l for l in src.splitlines()
                        if not l.strip().startswith("#"))

_src_tt = Path("tien_trinh.py").read_text(encoding="utf-8")
check("tien_trinh: giết bằng TerminateProcess", "TerminateProcess" in _src_tt)
check("tien_trinh: dựng cây bằng Toolhelp32, không WMI",
      "CreateToolhelp32Snapshot" in _src_tt and "CimInstance" not in _chi_ma(_src_tt))
check("tien_trinh: lọc PID trùng trước khi bắn", "dict.fromkeys(pids)" in _src_tt)
check("tien_trinh: chờ có hạn rồi hỏi lại HĐH",
      "time.time() < han" in _src_tt and "KHÔNG diệt được PID" in _src_tt)
check("tien_trinh: xếp con TRƯỚC cha (đừng để Chromium mồ côi)",
      "ra.reverse()" in _src_tt)
# Runner LÀ con của server. Chặn nhầm con cháu thì nút Dừng không diệt được gì.
_ban_tt = _tt.ban_do_cha_con()
check("to_tien trả tổ tiên, KHÔNG trả con cháu",
      os.getpid() in _tt.to_tien(ban=_ban_tt)
      and not (set(_ban_tt.get(os.getpid(), [])) & _tt.to_tien(ban=_ban_tt)))
check("server + dung_het dùng chung, không ai chép lại",
      "tien_trinh.diet_cay" in _src_sv
      and "tien_trinh.diet_cay" in Path("dung_het.py").read_text(encoding="utf-8")
      and "TerminateProcess" not in _chi_ma(_src_sv))

# Lúc tắt: chỉ được quét PowerShell MỘT lần rồi diệt MỘT lượt.
_i_sd    = _src_sv.index("def _shutdown_all(")
_than_sd = _src_sv[_i_sd:_src_sv.index(chr(10) + "def ", _i_sd + 10)]
check("tắt app: chỉ quét tiến trình một lần", _than_sd.count("_quet_python()") == 1)
check("tắt app: gom runner + join worker rồi diệt một lượt",
      _than_sd.count("_kill_pids(") == 1 and "join_groups_worker" in _than_sd)

# Mở app KHÔNG được cắt ngang phiên đang chạy. Khoá đã bảo đảm một loại một
# runner, nên runner còn giữ khoá là runner lành — để yên.
_i_dr    = _src_sv.index("def _don_runner_la(")
_than_dr = _src_sv[_i_dr:_src_sv.index(chr(10) + "def ", _i_dr + 10)]
check("mở app: giữ nguyên runner đang giữ khoá",
      "pid not in giu" in _than_dr and "Giữ nguyên runner đang chạy" in _than_dr)
check("mở app: vá lại file pid cho runner lành",
      'RUNNER_CFG[loai]["pid_file"]).write_text(str(pid))' in _than_dr)
_i_main = _src_sv.index('if "--lam" in sys.argv:')
check("khởi động gọi _don_runner_la, KHÔNG diệt sạch",
      "_don_runner_la()" in _src_sv[_i_main:]
      and "_kill_all_runners()" not in _src_sv[_i_main:])

# Nút "Dừng" của TỪNG runner phải tìm theo KHOÁ, không chỉ theo file pid. Đo
# lúc 02:2x ngày 19/09: `.runner_ban.pid` đã biến mất trong khi runner Bán thật
# vẫn sống ở PID 6212 và đang giữ khoá. Nút Dừng hồi đó không có pid để diệt,
# còn bước quét dòng lệnh thì vừa mù vừa quá hạn — nên bấm mãi không ăn.
_i_st    = _src_sv.index("def run_stop(")
_than_st = _src_sv[_i_st:_src_sv.index(chr(10) + "@app.route", _i_st + 10)]
check("nút Dừng tìm runner theo khoá", "kr.pid_dang_giu(loai)" in _than_st)
check("nút Dừng vẫn tra file pid", "_runner_pid(loai)" in _than_st)
# Nút này người ta vừa bấm và đang ngồi nhìn, nên KHÔNG được quét WMI. Đo lúc
# 21:2x ngày 19/09 trên máy thật: Get-CimInstance Win32_Process quá 120 GIÂY
# chưa xong, còn chụp ảnh tiến trình bằng Toolhelp32 mất 0,006 giây cho cả 270
# tiến trình. Bỏ được vì từ v2.18.0 runner nào cũng giữ khoá.
check("nút Dừng KHÔNG quét WMI/PowerShell", "_find_python_pids(" not in _than_st)

# HAI server cùng nghe một cổng là chuyện có thật: Flask bật SO_REUSEADDR nên
# trên Windows bản mới bind đè được lên bản cũ mà không ai báo lỗi. Đo lúc
# 21:4x ngày 19/09, netstat thấy hai dòng LISTENING trên 8080 — PID 13680 từ
# 15:07 và PID 21480 từ 21:34. Giao diện hỏi trúng cái CŨ nên cập nhật xong vẫn
# hiện số hiệu bản cũ, người dùng tưởng bản vá không ăn.
_i_sc    = _src_sv.index("def _don_server_cu(")
_than_sc = _src_sv[_i_sc:_src_sv.index(chr(10) + "def ", _i_sc + 10)]
check("khởi động: dọn server cũ trước khi bind cổng",
      "_pid_nghe_cong(PORT)" in _than_sc and "_kill_pids(cu" in _than_sc)
check("dọn xong còn sót thì báo lỗi rõ", "Vẫn còn server cũ" in _than_sc)
_i_main2 = _src_sv.index('if "--lam" in sys.argv:')
check("gọi _don_server_cu TRƯỚC khi mở server",
      _src_sv.index("_don_server_cu()", _i_main2) < _src_sv.index("_don_runner_la()", _i_main2))
check("tìm PID theo cổng bằng netstat, không dùng WMI",
      'subprocess.run(["netstat", "-ano"]' in _src_sv)

# RESTART.bat phải gom HẾT pid nghe cổng 8080, không chỉ dòng cuối — dòng cuối
# thường là server VỪA bật, diệt nó thì cái cũ sống tiếp.
for _b2 in ("RESTART.bat", "UPDATE.bat"):
    _s_b2 = Path(_b2).read_text(encoding="utf-8", errors="replace")
    check(f"{_b2}: gom hết PID cổng 8080",
          "call set SV_PID=%%SV_PID%% %%a" in _s_b2)
check("lưới vét WMI có hạn chờ ngắn", "timeout=5," in _src_sv)
check("nút Dừng báo THẤT BẠI khi runner vẫn còn giữ khoá",
      "kr.dang_giu(loai)" in _than_st and '"ok": False' in _than_st)
check("giao diện đọc kết quả thật của nút Dừng",
      "const r=await API.runStop(loai)" in _app_js and "if(r.ok)" in _app_js)

# Runner sống mà mất file pid là chuyện có thật — phải vá lại, không thì mỗi
# vòng hỏi trạng thái lại bỏ lỡ một lần vá và nút Dừng mãi không tìm ra nó.
_i_rr    = _src_sv.index("def _runner_running(")
_than_rr = _src_sv[_i_rr:_src_sv.index(chr(10) + "def ", _i_rr + 10)]
check("hỏi trạng thái thì vá lại file pid từ khoá",
      'RUNNER_CFG[loai]["pid_file"]).write_text(str(con))' in _than_rr)

# RESTART.bat / UPDATE.bat cũng phải bỏ taskkill. Đo trên máy thật 19/09: cửa
# sổ cmd đứng im ở dòng "Kill Flask server PID 13680" — `taskkill /F /PID` treo,
# và `Get-CimInstance` lọc theo CommandLine thì 30 giây chưa xong lúc máy tải
# nặng. Người dùng tưởng máy treo.
import dung_het as _dh

for _b in ("RESTART.bat", "UPDATE.bat"):
    _s_b = Path(_b).read_text(encoding="utf-8", errors="replace")
    # Bỏ dòng chú thích: chính chỗ này GHI LẠI vì sao không dùng taskkill nữa,
    # nên soi cả file thì phép kiểm tự báo động vì đọc trúng lời giải thích.
    _lenh_b = "\n".join(l for l in _s_b.splitlines()
                        if not l.strip().startswith("::")
                        and not l.strip().lower().startswith("rem "))
    check(f"{_b}: không còn taskkill", "taskkill" not in _lenh_b)
    check(f"{_b}: không quét Get-CimInstance nữa", "Get-CimInstance" not in _lenh_b)
    check(f"{_b}: gọi dung_het.py", "dung_het.py" in _lenh_b)

# ── UPDATE.bat: sau khi tự chép sang %TEMP% thì %~dp0 ĐỔI NGHĨA ──────────
# File đó tự chép mình sang %TEMP% rồi chạy bản sao (để `git reset --hard` ở
# bước 4 không ghi đè chính nó giữa chừng). Từ lúc ấy `%~dp0` trỏ vào %TEMP%
# chứ không phải thư mục cài đặt — mọi thứ phải dùng `%MNT_UPDATE_DIR%`.
#
# Bản v2.23.0 lỡ dùng `%~dp0` ở bước dừng app: `call` tìm _TIM_PYTHON.bat
# trong %TEMP% -> không thấy -> errorlevel 1 -> `exit /b 1` -> LỆNH CẬP NHẬT
# DỪNG NGAY Ở BƯỚC 2/6 mà không báo gì rõ ràng. Máy vệ tinh bấm update mãi
# không lên bản mới. Đo lại: %~dp0 ra thư mục Temp, errorlevel = 1.
_ub = Path("UPDATE.bat").read_text(encoding="utf-8", errors="replace").splitlines()
_i_chep = next(i for i, l in enumerate(_ub) if 'cd /d "%MNT_UPDATE_DIR%"' in l)
_pham = [f"dòng {i+1}"
         for i, l in enumerate(_ub[_i_chep:], start=_i_chep)
         if ("%~dp0" in l or "%~f0" in l)
         and not l.strip().startswith("::")
         and not l.strip().lower().startswith("rem ")]
check("UPDATE.bat: sau khi chép sang TEMP thì KHÔNG còn dùng %~dp0"
      + (f" — còn {_pham}" if _pham else ""), not _pham)

# Và mọi file nó gọi tới phải có thật.
import re as _re_ub
_thieu = sorted({m.group(1)
                 for l in _ub
                 if not l.strip().startswith("::")
                 and not l.strip().lower().startswith("rem ")
                 for m in _re_ub.finditer(r"%MNT_UPDATE_DIR%([A-Za-z0-9_.]+)", l)
                 if not Path(m.group(1)).exists()})
check("UPDATE.bat: mọi file nó gọi đều tồn tại"
      + (f" — thiếu {_thieu}" if _thieu else ""), not _thieu)

check("dung_het: tìm runner qua khoá, không chỉ file pid",
      hasattr(_dh, "pid_giu_khoa") and hasattr(_dh, "pid_tu_file"))
# dung_het KHÔNG được chép lại phần xử lý tiến trình — dùng chung `tien_trinh`.
check("dung_het dùng chung tien_trinh, không tự chép",
      "tien_trinh.diet_cay" in Path("dung_het.py").read_text(encoding="utf-8"))

# Giết thật một cây tiến trình rồi đo — đây là điều duy nhất đáng tin.
_cay = _sp.Popen(["cmd", "/c", "start /b timeout /t 90 >nul & timeout /t 90 >nul"],
                 stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                 creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0)) if sys.platform == "win32" else None
if _cay:
    _time.sleep(1.0)
    _n_cay = len(_tt.ca_cay([_cay.pid]))
    _t0 = _time.time()
    for _p in _tt.ca_cay([_cay.pid]):
        _tt.diet_mot(_p)
    _mat = _time.time() - _t0
    _time.sleep(0.4)
    check(f"tien_trinh giết sạch cây {_n_cay} tiến trình", not _tt.con_song(_cay.pid))
    check(f"… và nhanh ({_mat:.2f}s, taskkill từng treo >20s)", _mat < 2.0)

check("tắt phần mềm: dọn dẹp chạy trong luồng riêng có hạn chờ",
      "don.join(timeout=" in _src_sv)
# Bỏ "chạy ẩn" + nút/endpoint "Tắt phần mềm" (19/10): lối tắt DUY NHẤT là nút X.
# Không cần os._exit nữa — server chạy ở DAEMON thread, nên đóng cửa sổ
# (webview.start trả về) là tiến trình tự thoát, server không còn sống lẻ loi.
check("server chạy ở daemon thread → đóng cửa sổ là thoát sạch",
      "threading.Thread(target=_serve, daemon=True)" in _src_sv)
check("đã bỏ endpoint /api/app/shutdown + nút Tắt phần mềm",
      '@app.route("/api/app/shutdown"' not in _src_sv
      and "shutdownApp" not in Path("static/js/app.js").read_text(encoding="utf-8"))
check("đã bỏ chế độ chạy ẩn (--no-browser) và mở trình duyệt (--browser)",
      '"--no-browser" in sys.argv' not in _src_sv
      and '"--browser" in sys.argv' not in _src_sv)

# Nút X cũng gọi cùng hàm dọn đó, nên cũng phải chờ có hạn — không thì bấm X
# mấy lần cửa sổ cũng không nhúc nhích.
check("nút X cũng chờ có hạn, không gọi thẳng _shutdown_all",
      "win.events.closing += _dong_cua_so" in _src_sv)

# ── Xoá sạch bảng lịch ─────────────────────────────────────────────────────
# Đổi cột "Loại đăng" của một acc KHÔNG tự dọn lịch cũ — acc vẫn nằm trong bảng
# lịch loại cũ và vẫn tới giờ chạy, nên một nick có thể bị HAI loại lịch gọi,
# mở hai Chrome trên cùng một thư mục profile.
def _dong_lich(loai, stt, gio="08:00", acc="AccXoa"):
    """replace_schedules đọc theo TÊN KHOÁ nên thiếu một khoá là SQLite ném lỗi."""
    return {"loai": loai, "stt": stt, "ma_content": "C1", "ten_acc": acc,
            "ten_page": "P", "gio_dang": gio, "ma_nhom": "TIME1",
            "tu_khoa": "k", "mode": "Page", "trang_thai": "Chờ"}


db.replace_schedules("ban", [_dong_lich("ban", i) for i in range(1, 6)])
check("dựng được 5 dòng lịch ban", len(db.get_schedules("ban")) == 5)

# Xoá SẠCH khác hẳn "Dừng → X": kia đổi trạng thái, dòng vẫn còn.
db.bulk_set_schedule_status("ban", "Chờ", "X")
check("Dừng→X: dòng VẪN CÒN", len(db.get_schedules("ban")) == 5)

check("xoá sạch trả về số dòng đã xoá", db.xoa_het_lich("ban") == 5)
check("xoá sạch: bảng trống hẳn",       db.get_schedules("ban") == [])
check("xoá bảng đã trống -> 0, không nổ", db.xoa_het_lich("ban") == 0)

# Chỉ đụng ĐÚNG loại được chỉ định — xoá nhầm loại khác là mất cả ngày công gen.
db.replace_schedules("ban",  [_dong_lich("ban", 1)])
db.replace_schedules("thue", [_dong_lich("thue", 1, "09:00")])
db.xoa_het_lich("ban")
check("không đụng loại lịch khác", len(db.get_schedules("thue")) == 1
      and db.get_schedules("ban") == [])

# Xoá sạch lịch THAM GIA NHÓM — Page ('') và Market ('MARKET') riêng biệt.
with db._conn() as _c_j:
    _c_j.execute("DELETE FROM join_schedules")
    _c_j.execute("INSERT INTO join_schedules (ten_acc,nguon) VALUES ('JA','')")
    _c_j.execute("INSERT INTO join_schedules (ten_acc,nguon) VALUES ('JB','')")
    _c_j.execute("INSERT INTO join_schedules (ten_acc,nguon) VALUES ('JC','MARKET')")
def _dem_join(ng):
    with db._conn() as _c:
        return _c.execute("SELECT COUNT(*) FROM join_schedules WHERE COALESCE(nguon,'')=?",
                          (ng,)).fetchone()[0]
check("xoa_het_join('') xoá lịch Page, GIỮ Market",
      db.xoa_het_join("") == 2 and _dem_join("") == 0 and _dem_join("MARKET") == 1)
check("xoa_het_join('MARKET') xoá lịch Market",
      db.xoa_het_join("MARKET") == 1 and _dem_join("MARKET") == 0)
with db._conn() as _c_j2:
    _c_j2.execute("INSERT INTO join_schedules (ten_acc,nguon) VALUES ('JX','')")
_rjx = _client.post("/api/join/xoa-het", json={"nguon": ""}).get_json()
check("endpoint /api/join/xoa-het xoá lịch Page",
      _rjx.get("ok") is True and _rjx.get("deleted") == 1)
check("nút 'Xoá lịch' cho cả 2 tab tham gia nhóm + hàm + API",
      "joinXoaHet('')" in Path("templates/index.html").read_text(encoding="utf-8")
      and "joinXoaHet('MARKET')" in Path("templates/index.html").read_text(encoding="utf-8")
      and "async function joinXoaHet" in Path("static/js/app.js").read_text(encoding="utf-8")
      and "joinXoaHet:" in Path("static/js/api.js").read_text(encoding="utf-8"))
with db._conn() as _c_j3:
    _c_j3.execute("DELETE FROM join_schedules")

# Endpoint: route nhận chuỗi tự do mà đây là lệnh XOÁ, nên loại lạ phải bị chặn
# TRƯỚC khi chạm vào bảng.
_r = _client.post("/api/schedule/khong_co_loai_nay/xoa-het").get_json()
check("loại lạ -> từ chối", _r.get("ok") is False and "hợp lệ" in (_r.get("error") or ""))
check("loại lạ -> không xoá gì", len(db.get_schedules("thue")) == 1)

# Runner đang chạy mà rút bảng lịch dưới chân nó thì phiên đang chạy ghi trạng
# thái vào dòng vừa biến mất — im lặng, không lỗi, và người dùng tưởng đã xoá
# xong trong khi Chrome vẫn đang đăng bài.
_that_rr = server._runner_running
try:
    server._runner_running = lambda l: True
    _r = _client.post("/api/schedule/thue/xoa-het").get_json()
    check("runner đang chạy -> từ chối xoá", _r.get("ok") is False
          and "đang chạy" in (_r.get("error") or ""))
    check("runner đang chạy -> dòng còn nguyên", len(db.get_schedules("thue")) == 1)

    server._runner_running = lambda l: False
    _r = _client.post("/api/schedule/thue/xoa-het").get_json()
    check("runner đã dừng -> xoá được", _r.get("ok") is True and _r.get("deleted") == 1)
finally:
    server._runner_running = _that_rr


# ── Thử cookie ─────────────────────────────────────────────────────────────
import inspect as _ins2
_src_thu = _ins2.getsource(_ce.thu_cookie)

# PHẢI mở trên thư mục TẠM. Dùng profile thật thì nó đã có sẵn phiên đăng nhập
# cũ, nên vào được kể cả khi xs vừa dán đã chết — tức luôn báo "OK" và vô dụng.
# Đây là điểm khiến cả tính năng có nghĩa hay không, nên khoá lại bằng test.
check("thử cookie dùng thư mục tạm",      "mkdtemp" in _src_thu)
check("KHÔNG đụng profile thật của acc",  "find_profile_dir" not in _src_thu)
check("dọn thư mục tạm sau khi xong",     "rmtree" in _src_thu)
# Dò ô mật khẩu trên DOM, không so chuỗi trong URL — xem chú thích chua_dang_nhap.
check("dùng chua_dang_nhap để nhận biết", "chua_dang_nhap" in _src_thu)
check("có chặn trên thời gian",           "wait_for" in _src_thu)

check("thiếu c_user/xs -> báo lỗi, không mở trình duyệt",
      _ce.thu_cookie("KhongCoAccNay", "", "") == (False, "Thiếu c_user hoặc xs"))

# Đối chiếu UID Facebook trả về với c_user đang lưu — bắt ca c_user cũ / gõ nhầm
# một chữ số mà xs vẫn đúng phiên.
check("có đọc UID thật từ mã trang", '"USER_ID"' in _src_thu)
check("có so UID với c_user đang lưu", "uid != c_user" in _src_thu)

# ── c_user KHÔNG được là UID một Page ──────────────────────────────────────
# Gặp thật 03/10: 'Alex Tường' mang c_user = UID Page 'Long Sơn' suốt 3 ngày,
# Facebook từ chối cookie nên mọi phiên báo "Cookie hết hạn" dù xs vẫn tốt.
_pid_cu = db.upsert_page({"ten_page": "Page Chan CU", "page_uid": "61599999999002"})
_aid_cu = db.upsert_account({"ten_acc": "Acc Chan CU", "c_user": "100000000000001",
                             "trang_thai": "Active"})
check("nhận ra c_user trùng UID Page", db.page_trung_c_user(" 61599999999002 ") == "Page Chan CU")
check("c_user nick thường không bị coi là Page", db.page_trung_c_user("100000000000001") == "")
try:
    db.update_account_field(_aid_cu, "c_user", "61599999999002")
    _chan_o = False
except ValueError as _e_cu:
    _chan_o = "Page Chan CU" in str(_e_cu)
check("sửa ô c_user thành UID Page bị CHẶN, báo tên Page", _chan_o)
check("bị chặn thì c_user cũ giữ nguyên",
      (db.get_account_by_id(_aid_cu) or {}).get("c_user") == "100000000000001")
try:
    db.upsert_account({"id": _aid_cu, "ten_acc": "Acc Chan CU", "c_user": "61599999999002"})
    _chan_form = False
except ValueError:
    _chan_form = True
check("form Thêm/Sửa với c_user = UID Page bị CHẶN", _chan_form)
db.update_account_field(_aid_cu, "c_user", "100000000000002")
check("sửa c_user sang ID nick khác vẫn được",
      (db.get_account_by_id(_aid_cu) or {}).get("c_user") == "100000000000002")
_r_cu = _client.post(f"/api/accounts/{_aid_cu}/field",
                     json={"field": "c_user", "value": "61599999999002"}).get_json()
check("API sửa ô trả lỗi rõ ràng cho giao diện",
      _r_cu.get("ok") is False and "UID của Page" in (_r_cu.get("error") or ""))
db.delete_account(_aid_cu)
with db._conn() as _c_cu:
    _c_cu.execute("DELETE FROM pages WHERE id=?", (_pid_cu,))

# Runner tham gia nhóm: _update_status gọi KHÔNG kèm cột nào (nhánh "Cookie hết
# hạn") từng sinh "SET trang_thai=?,  WHERE" — lỗi cú pháp, che mất lỗi thật và
# chặn luôn bước đánh dấu acc + báo Telegram. Gặp thật 03/10–06/10.
_src_jr_cu = Path("join_groups_runner.py").read_text(encoding="utf-8")
check("cập nhật trạng thái lịch không kèm cột vẫn đúng cú pháp",
      'sets = "".join(f", {k}=?" for k in kwargs)' in _src_jr_cu
      and 'SET trang_thai=?{sets} WHERE id=?' in _src_jr_cu)
_re_cu = __import__("re")
check("không còn chỗ nào ghép ', {sets}' cứng sau một cột cố định",
      not _re_cu.search(r'SET \w+=\?, \{sets\}', _src_jr_cu + Path("db.py").read_text(encoding="utf-8")
                        + Path("server.py").read_text(encoding="utf-8")))

# ── Trùng c_user giữa hai dòng ─────────────────────────────────────────────
# Dán nhầm CẢ CẶP c_user + xs của nick A vào dòng nick B thì cookie hợp lệ, và
# phép đối chiếu UID ở trên cũng khớp (Facebook trả về A, ô c_user cũng ghi A).
# Dấu vết duy nhất là hai dòng cùng mang một c_user.
_a1 = db.upsert_account({"ten_acc": "TrungA", "c_user": "555", "xs": "x1",
                         "trang_thai": "Active"})
_a2 = db.upsert_account({"ten_acc": "TrungB", "c_user": "666", "xs": "x2",
                         "trang_thai": "Active"})
check("c_user khác nhau -> không báo trùng", db.acc_trung_c_user(_a1) == [])

# Từ 14/10 c_user là KHOÁ xác định nick, nên nhập trùng bị CHẶN ngay ở cửa ghi
# (kể cả thừa khoảng trắng). Cảnh báo trùng vẫn giữ cho dữ liệu cũ đã lỡ trùng
# từ trước — dựng thẳng bằng SQL để giả lập.
for _gt in ("555", " 555 "):
    try:
        db.update_account_field(_a2, "c_user", _gt)
        _chan_tr = False
    except ValueError as _e_tr:
        _chan_tr = "TrungA" in str(_e_tr)
    check(f"nhập c_user đã thuộc nick khác bị CHẶN ({_gt!r})", _chan_tr)
check("bị chặn thì c_user cũ giữ nguyên",
      db.get_account_by_id(_a2)["c_user"] == "666")
try:
    db.upsert_account({"ten_acc": "TrungC", "c_user": "555", "trang_thai": "Active"})
    _chan_form_tr = False
except ValueError:
    _chan_form_tr = True
check("form Thêm với c_user đã có bị CHẶN", _chan_form_tr)
db.upsert_account({"id": _a1, "ten_acc": "TrungA", "c_user": "555"})
check("form Sửa giữ nguyên c_user của chính nó thì KHÔNG bị chặn",
      db.get_account_by_id(_a1)["c_user"] == "555")

with db._conn() as _c_tr:                               # dữ liệu cũ đã lỡ trùng
    _c_tr.execute("UPDATE accounts SET c_user='555' WHERE id=?", (_a2,))
check("trùng -> A thấy B",  db.acc_trung_c_user(_a1) == ["TrungB"])
check("trùng -> B thấy A",  db.acc_trung_c_user(_a2) == ["TrungA"])

with db._conn() as _c_tr:                               # thừa khoảng trắng vẫn là trùng
    _c_tr.execute("UPDATE accounts SET c_user=' 555 ' WHERE id=?", (_a2,))
check("bỏ qua khoảng trắng thừa", db.acc_trung_c_user(_a1) == ["TrungB"])

db.update_account_field(_a1, "c_user", "")
check("c_user rỗng -> không coi là trùng", db.acc_trung_c_user(_a1) == [])

# Endpoint: acc không tồn tại phải báo lỗi gọn, không nổ
_r = _client.post("/api/accounts/999999/thu-cookie").get_json()
check("acc không tồn tại -> báo lỗi", _r.get("ok") is False
      and "Không tìm thấy" in (_r.get("error") or ""))

# Thử ĐƯỢC thì phải tự bật lại Active: dán xs KHÔNG tự làm việc này, nên acc đã
# từng "Cookie hết hạn" sẽ bị Gen lịch bỏ qua mãi dù cookie đã sống lại.
_id_ck = db.upsert_account({"ten_acc": "AccThuCookie", "c_user": "11101",
                            "xs": "xs1", "trang_thai": "Cookie hết hạn"})
_that_thu = _ce.thu_cookie
try:
    import cookie_exporter as _ce_mod
    _ce_mod.thu_cookie = lambda *a, **k: (True, "Cookie còn dùng được")
    _r = _client.post(f"/api/accounts/{_id_ck}/thu-cookie").get_json()
    check("cookie sống -> báo song=True", _r.get("song") is True)
    check("cookie sống -> tự bật lại Active",
          _r.get("da_bat_lai") is True
          and db.get_account_by_id(_id_ck)["trang_thai"] == "Active")

    # Đang Active sẵn thì KHÔNG báo "đã bật lại" — tránh nói thừa.
    _r = _client.post(f"/api/accounts/{_id_ck}/thu-cookie").get_json()
    check("đang Active -> không báo bật lại", _r.get("da_bat_lai") is False)

    # Cookie chết thì TUYỆT ĐỐI không được đụng vào trạng thái.
    db.update_account_field(_id_ck, "trang_thai", "Cookie hết hạn")
    _ce_mod.thu_cookie = lambda *a, **k: (False, "Facebook không nhận cookie")
    _r = _client.post(f"/api/accounts/{_id_ck}/thu-cookie").get_json()
    check("cookie chết -> song=False",  _r.get("song") is False)
    check("cookie chết -> giữ nguyên trạng thái",
          db.get_account_by_id(_id_ck)["trang_thai"] == "Cookie hết hạn")
finally:
    _ce_mod.thu_cookie = _that_thu


# ── Marketplace: cài đặt của form "Tạo bài niêm yết" ───────────────────────
# Form có 8 ô. Từ 13/10: Ảnh, Mô tả và TIÊU ĐỀ lấy từ Content (tiêu đề ở cột
# riêng `tieu_de_mkt`); Giá sinh ngẫu nhiên; Tình trạng và số nhóm cố định.
# Chỉ Loại niêm yết, Hạng mục, Vị trí, Từ khoá nhóm còn nằm ở `settings`.
#
# Tiêu đề chuyển về content vì Facebook so bài mới với bài cũ còn sống của
# chính nick đó — trùng tiêu đề + mô tả + ảnh là từ chối. Một tiêu đề dùng
# chung cho mọi bài là tự thêm một điểm trùng. Giá và vị trí thì vẫn KHÔNG có
# cột riêng ở content.
with db._conn() as _con_mkt:
    _cot_content = {r[1] for r in
                    _con_mkt.execute("PRAGMA table_info(content)").fetchall()}
check("content CÓ cột Tiêu đề Market Place", "tieu_de_mkt" in _cot_content)
check("content KHÔNG có cột giá / vị trí riêng",
      not {"gia", "vi_tri"} & _cot_content)
check("cài đặt KHÔNG còn Tiêu đề / Giá / Tình trạng / Số nhóm",
      not {"mkt_tieu_de", "mkt_gia_list", "mkt_tinh_trang", "mkt_so_nhom"}
          & set(db.MKT_MAC_DINH))
# Khoá cũ còn sót trong bảng settings của máy đã dùng bản trước thì cũng KHÔNG
# được đọc tới — không thì một Tình trạng cũ đặt tay cứ thế âm thầm áp dụng.
db.set_setting("mkt_tinh_trang", "Đã qua sử dụng - Tốt")
check("khoá cài đặt cũ còn sót không lọt vào cài đặt đọc ra",
      "mkt_tinh_trang" not in db.doc_cai_dat_mkt())
db.set_setting("mkt_tinh_trang", "")
check("Tình trạng cố định là Mới", db.MKT_TINH_TRANG == "Mới")
check("luôn tick tối đa 20 nhóm",  db.MKT_SO_NHOM == 20)

# loai_dang nay CHÍNH LÀ khoá mảng, nên loai_content_cua_acc trả về chính nó khi
# mảng đang bật, ngược lại ''.
check("khoá homestay -> content homestay", db.loai_content_cua_acc("homestay") == "homestay")
check("khoá thue -> content thue",    db.loai_content_cua_acc("thue")     == "thue")
check("khoá ban -> content ban",      db.loai_content_cua_acc("ban")      == "ban")
check("acc chưa phân công -> rỗng",   db.loai_content_cua_acc("")         == "")
check("nhãn 'Homestay' -> rỗng (không phải khoá)", db.loai_content_cua_acc("Homestay") == "")
check("mảng đang tắt (loai4) -> rỗng", db.loai_content_cua_acc("loai4")   == "")
check("giá trị lạ -> rỗng, không đoán bừa",
      db.loai_content_cua_acc("C_Home") == "")
# Hai chiều phải khớp nhau tuyệt đối, nếu không sẽ có acc Gen được lịch mà
# Marketplace lại không biết lấy content ở đâu (hoặc ngược lại).
check("khớp hai chiều với khop_loai_lich",
      all(db.khop_loai_lich(v, db.loai_content_cua_acc(v))
          for v in db.loai_dang_options() if v))

# Giá bài Marketplace nay SINH ngẫu nhiên chứ không bốc từ danh sách cố định:
# trùng giá với bài cũ còn sống là thêm một điểm giống nhau, mà Facebook so bài
# mới với chính bài cũ của nick đó rồi từ chối nếu quá giống.
_gia = [db.sinh_gia() for _ in range(400)]
check("giá sinh ra toàn số",        all(g.isdigit() for g in _gia))
check("giá đều CHẴN",               all(int(g) % 2 == 0 for g in _gia))
check("giá đều dưới 1000",          all(0 < int(g) < db.GIA_TOI_DA for g in _gia))
# 400 lần bốc trong 499 giá mà chỉ ra một hai giá trị thì hàm đã thôi ngẫu nhiên.
check("giá trải rộng, không kẹt một chỗ", len(set(_gia)) > 100)

# Chưa đặt lần nào thì phải ra đúng mặc định — người dùng mở phần mềm lần đầu
# là dùng được ngay, không phải tự đi điền sáu ô.
_cd_mkt = db.doc_cai_dat_mkt()
check("mặc định: loại niêm yết là Mặt hàng cần bán",
      _cd_mkt["mkt_loai_tin"] == "Mặt hàng cần bán")
check("mặc định: hạng mục Hộ gia đình", _cd_mkt["mkt_hang_muc"] == "Hộ gia đình")
check("mặc định: vị trí Hai Bà Trưng",  _cd_mkt["mkt_vi_tri"] == "Hai Bà Trưng")
# "Time" là chuỗi con của "Times" nên một mình nó đã vớt hết, nhưng giữ cả hai
# cho người đọc ô cài đặt hiểu ngay là bắt cả hai lối viết. Đo trên 28 nhóm thật
# của Sa Tran Anh: "Times, Time" vớt 26/28, đúng bằng bộ từ khoá dài trước đây.
check("mặc định: từ khoá nhóm bắt cả 'Times' lẫn 'Time'",
      db.tach_tu_khoa(_cd_mkt["mkt_tu_khoa"]) == ["Times", "Time"])
# Từ khoá rỗng nghĩa là tick nhóm nào cũng được — đúng cái phải tránh. Để trống
# thì lấy lại mặc định chứ không được coi là "không lọc".
db.set_setting("mkt_tu_khoa", "")
check("từ khoá để trống -> lấy lại mặc định, KHÔNG thành không lọc",
      db.doc_cai_dat_mkt()["mkt_tu_khoa"] == db.MKT_MAC_DINH["mkt_tu_khoa"])

# Xoá trắng một ô rồi lưu thì phải quay về mặc định, KHÔNG được để rỗng — ô
# Hạng mục rỗng nghĩa là lúc đăng không biết chọn gì và phiên hỏng giữa chừng.
db.set_setting("mkt_hang_muc", "   ")
check("ô để trống -> lấy lại mặc định",
      db.doc_cai_dat_mkt()["mkt_hang_muc"] == "Hộ gia đình")
db.set_setting("mkt_hang_muc", "Đồ điện tử")
check("ô có giá trị -> giữ nguyên giá trị đó",
      db.doc_cai_dat_mkt()["mkt_hang_muc"] == "Đồ điện tử")
db.set_setting("mkt_hang_muc", "")

_r_mkt = _client.get("/api/marketplace/cai-dat").get_json()
check("API trả cài đặt đã trộn mặc định",
      _r_mkt.get("ok") and _r_mkt["data"]["mkt_vi_tri"] == "Hai Bà Trưng")
check("API không còn trả danh sách giá (giá tự sinh)", "gia" not in _r_mkt)

# Mặc định chỉ được có MỘT nguồn (db.MKT_MAC_DINH). Nếu app.js tự giữ một bản
# nữa thì hai bên sẽ lệch, và người dùng thấy một đằng còn Facebook nhận một nẻo.
_ajs_mkt = Path("static/js/app.js").read_text(encoding="utf-8")
check("app.js KHÔNG chép lại bộ mặc định, phải hỏi server",
      "API.mktCaiDat()" in _ajs_mkt and "Hộ gia đình" not in _ajs_mkt)

# Trang nằm ở nhóm "Vận hành" chứ không phải một tab thứ tư của Content:
# CONTENT_CATEGORIES cố định 3 loại vì chúng khớp 1-1 với 3 scheduler.
_html_mkt = Path("templates/index.html").read_text(encoding="utf-8")
check("Content vẫn đúng 3 danh mục", len(server.CONTENT_CATEGORIES) == 3)
check("có mục Marketplace ở sidebar", 'data-page="marketplace"' in _html_mkt)
check("có trang Marketplace",         'id="page-marketplace"' in _html_mkt)
check("Marketplace nằm SAU mục Tham gia nhóm (nhóm Vận hành)",
      _html_mkt.index('data-page="marketplace"')
      > _html_mkt.index('data-page="tham-gia-nhom"'))
check("mở trang Marketplace thì nạp cài đặt",
      'page==="marketplace"' in _ajs_mkt and "mktNap()" in _ajs_mkt)
check("Marketplace có tên ở thanh tiêu đề", 'marketplace:"Marketplace"' in _ajs_mkt)
# Ảnh và Mô tả lấy từ Content nên tuyệt đối không được có ô nhập ở đây — có ô
# nhập là sinh ra nguồn thứ hai, rồi không ai biết lúc đăng lấy bản nào.
check("KHÔNG có ô nhập Ảnh / Mô tả ở trang Marketplace",
      'id="mkt-anh"' not in _html_mkt and 'id="mkt-mo-ta"' not in _html_mkt)
# Trang chỉ liệt kê những ô CẦN NHẬP, đánh số liền 1..4: Loại niêm yết, Hạng
# mục, Vị trí, Chọn nhóm (từ khoá). Tiêu đề / Giá / Tình trạng / Số nhóm đã bỏ.
import re as _re_mkt
_khoi_mkt = _html_mkt[_html_mkt.index('id="page-marketplace"'):]
_khoi_mkt = _khoi_mkt[:_khoi_mkt.index('id="page-hanh-dong"')]
check("số thứ tự đánh liền 1..6 (thêm mục 6 Tự xóa bài cũ)",
      _re_mkt.findall(r'class="mkt-so">(\d+)<', _khoi_mkt)
      == [str(i) for i in range(1, 7)])
check("KHÔNG còn ô Tiêu đề / Giá / Tình trạng / Số nhóm",
      not any(f'id="{x}"' in _khoi_mkt
              for x in ("mkt-tieu-de", "mkt-gia-list", "mkt-tinh-trang", "mkt-so-nhom")))
check("app.js không còn đọc/ghi các ô đã bỏ",
      not any(x in _ajs_mkt for x in ('"mkt-tieu-de"', '"mkt-gia-list"',
                                      '"mkt-tinh-trang"', '"mkt-so-nhom"')))
# Số nhóm ghi sẵn trên trang phải khớp hằng số mà bộ đăng dùng thật.
check("chữ '20 nhóm' trên trang khớp MKT_SO_NHOM",
      f"{db.MKT_SO_NHOM} nhóm khớp từ khoá" in _khoi_mkt)
check("từ khoá được nạp và lưu",
      'el("mkt-tu-khoa").value' in _ajs_mkt and "mkt_tu_khoa:" in _ajs_mkt)

# ── Tiêu đề Market Place theo từng content ─────────────────────────────────
_html_ct = Path("templates/index.html").read_text(encoding="utf-8")
_bang_ct = _html_ct[_html_ct.index("<th>Mã content</th>"):_html_ct.index('id="content-table"')]
check("bảng Content: thứ tự cột Ảnh < Mã thư viện < Tiêu đề Market < Sử dụng < Ghi chú",
      _bang_ct.index(">Ảnh</th>") < _bang_ct.index(">Mã thư viện</th>")
      < _bang_ct.index(">Tiêu đề Market Place</th>")
      < _bang_ct.index(">Sử dụng</th>") < _bang_ct.index(">Ghi chú</th>"))
check("bảng Content có dropdown Mã thư viện + ô sửa form",
      "contentSetThuVien" in _ajs_mkt and 'id="ce_tv"' in _ajs_mkt and "ma_thu_vien:" in _ajs_mkt)
check("bảng Content có ô sửa nhanh tiêu đề",
      'ec(r,"tieu_de_mkt"' in _ajs_mkt)
check("form Thêm/Sửa content có ô tiêu đề và gửi lên khi lưu",
      'id="ce_tdm"' in _ajs_mkt and "tieu_de_mkt:" in _ajs_mkt)
_cid_tdm = db.upsert_content({"loai": "homestay", "ma_content": "TDM1", "noi_dung": "nd"})
_r_tdm = _client.post(f"/api/content/{_cid_tdm}/field",
                      json={"field": "tieu_de_mkt", "value": "Căn hộ Times City"}).get_json()
check("API sửa ô nhận cột tieu_de_mkt", _r_tdm.get("ok") is True)
check("tiêu đề lưu vào content",
      any(r["id"] == _cid_tdm and r["tieu_de_mkt"] == "Căn hộ Times City"
          for r in db.get_content("homestay")))
# Cột 'Sử dụng' là tập ĐÓNG (Có/Không): dropdown ở giao diện + validate ở server.
# Giá trị lạ làm content âm thầm rơi khỏi Gen (chỉ lấy su_dung="Có").
check("API từ chối Sử dụng giá trị lạ",
      _client.post(f"/api/content/{_cid_tdm}/field",
                   json={"field": "su_dung", "value": "co"}).get_json().get("ok") is False)
check("API nhận Sử dụng = Không",
      _client.post(f"/api/content/{_cid_tdm}/field",
                   json={"field": "su_dung", "value": "Không"}).get_json().get("ok") is True)
_khoi_su = _ajs_mkt[_ajs_mkt.index("function startContentFieldEdit"):
                    _ajs_mkt.index("function switchContent")]
check("ô Sử dụng ở bảng Content dùng dropdown Có/Không, không gõ tay",
      'field==="su_dung"' in _khoi_su and 'createElement("select")' in _khoi_su
      and '["Có","Không"]' in _khoi_su)
_cot_xuat = [k for k, _ in server.EXPORT_CONTENT_COLUMNS]
check("xuất Excel content có cột tiêu đề, giữa Sử dụng và Ghi chú",
      _cot_xuat.index("su_dung") + 1 == _cot_xuat.index("tieu_de_mkt")
      == _cot_xuat.index("ghi_chu") - 1)
db.import_content([{"ma_content": "TDM2", "noi_dung": "x",
                    "tieu_de_mkt": "  Tiêu đề nhập  "}], "homestay")
check("nhập Excel content giữ tiêu đề",
      any(r["ma_content"] == "TDM2" and r["tieu_de_mkt"] == "Tiêu đề nhập"
          for r in db.get_content("homestay")))
with db._conn() as _c_tdm:
    _c_tdm.execute("DELETE FROM content WHERE ma_content IN ('TDM1','TDM2')")

# Bộ đăng: tiêu đề lấy từ content, KHÔNG từ cài đặt; thiếu thì dừng TRƯỚC khi
# tải ảnh / mở trình duyệt.
_src_mp = Path("market_poster.py").read_text(encoding="utf-8")
check("bộ đăng không còn đọc tiêu đề / giá / tình trạng / số nhóm từ cài đặt",
      not any(x in _src_mp for x in ('cd["mkt_tieu_de"]', 'cd["mkt_gia_list"]',
                                     'cd["mkt_tinh_trang"]', 'cd["mkt_so_nhom"]')))
check("bộ đăng dùng Tình trạng và số nhóm cố định",
      '("Tình trạng", db.MKT_TINH_TRANG)' in _src_mp and "so_nhom = db.MKT_SO_NHOM" in _src_mp)

# ── Biến thể ảnh RIÊNG cho Marketplace: dán SỐ ĐIỆN THOẠI vào góc ─────────────
# Marketplace đánh mạnh trùng bộ ảnh, nên mỗi ảnh dán số ĐT vào 1 trong 4 góc
# (trong VÙNG AN TOÀN — hình vuông giữa ảnh — để FB cắt thumbnail không mất số).
# CHỈ Marketplace, CHỈ khi bật + có nhập số. Không còn hệ thống icon.
import mkt_anh as _mia
check("mặc định Marketplace có mkt_bien_the_bat/sdt",
      "mkt_bien_the_bat" in db.MKT_MAC_DINH and "mkt_bien_the_sdt" in db.MKT_MAC_DINH)
check("biến thể ảnh Marketplace mặc định TẮT",
      db.doc_cai_dat_mkt()["mkt_bien_the_bat"] == "0")
check("tab Marketplace có ô tick + số điện thoại (mục 5)",
      'id="mkt-bien-the"' in _khoi_mkt and 'id="mkt-bien-the-sdt"' in _khoi_mkt)
check("UI nạp + lưu ô biến thể ảnh Marketplace",
      'el("mkt-bien-the")' in _ajs_mkt and "mkt_bien_the_bat:" in _ajs_mkt
      and "mkt_bien_the_sdt:" in _ajs_mkt)
check("ĐÃ BỎ hệ thống icon (không còn thư viện icon / _ds_icon)",
      not Path("assets/icon_lienhe").exists()
      and "_ds_icon" not in Path("mkt_anh.py").read_text(encoding="utf-8"))
check("market_poster gọi biến thể liên hệ, khoá theo bật + có số ĐT",
      "mkt_anh.bien_the_lien_he" in _src_mp
      and 'cd.get("mkt_bien_the_bat") == "1"' in _src_mp)

if _mia.CO_PILLOW:
    from PIL import Image as _ImM
    _mdm = Path(tempfile.mkdtemp(prefix="test_mkt_bt_"))
    _g1 = _mdm / "a.jpg"; _g2 = _mdm / "b.jpg"
    _ImM.new("RGB", (800, 600), (180, 180, 190)).save(_g1, "JPEG")
    _ImM.new("RGB", (640, 640), (150, 170, 160)).save(_g2, "JPEG")
    _b1 = _g1.read_bytes()
    _out = _mia.bien_the_lien_he([str(_g1), str(_g2)], str(_mdm / "ra"),
                                 "0333 194 822", seed=3)
    check("biến thể ra đủ số ảnh, đúng thứ tự",
          len(_out) == 2 and [Path(p).stem for p in _out] == ["1", "2"])
    check("ảnh biến thể là file MỚI, KHÔNG đụng ảnh gốc",
          all(str(_mdm / "ra") in p for p in _out) and _g1.read_bytes() == _b1)
    check("ảnh biến thể mở được + giữ kích thước ảnh gốc",
          _ImM.open(_out[0]).size == (800, 600))
    check("không có số điện thoại → trả NGUYÊN ảnh gốc",
          _mia.bien_the_lien_he([str(_g1)], str(_mdm / "x"), "  ") == [str(_g1)])
    _xx = _mdm / "xau.jpg"; _xx.write_bytes(b"khong phai anh")
    check("ảnh hỏng → giữ nguyên đường dẫn gốc, không ném lỗi",
          _mia.bien_the_lien_he([str(_xx)], str(_mdm / "y"), "0909")[0] == str(_xx))
    # VÙNG AN TOÀN: ảnh DỌC 400×800 → huy hiệu phải nằm trong vuông giữa [200,600],
    # KHÔNG chạm dải trên/dưới (để FB cắt thumbnail vuông không mất số).
    _port = _mdm / "port.jpg"
    _ImM.new("RGB", (400, 800), (120, 130, 140)).save(_port, "JPEG")
    _po = _mia.bien_the_lien_he([str(_port)], str(_mdm / "sz"), "0333 194 822", seed=1)[0]
    _pim = _ImM.open(_po).convert("RGB")
    def _lech_max(vung):
        return max(abs(r - 120) + abs(g - 130) + abs(b - 140)
                   for r, g, b in vung.getdata())
    _dai_tren = _pim.crop((0, 0, 400, 150))
    _dai_duoi = _pim.crop((0, 650, 400, 800))
    check("huy hiệu nằm TRONG vùng an toàn (dải trên/dưới ảnh dọc KHÔNG bị đụng)",
          _lech_max(_dai_tren) < 45 and _lech_max(_dai_duoi) < 45)
    shutil.rmtree(_mdm, ignore_errors=True)
else:
    check("BỎ QUA test biến thể Marketplace (chưa cài Pillow)", True)
# Vị trí: ô ở tab Marketplace có từ v2.30.0 mà bộ đăng chưa từng đọc tới —
# bài mang vị trí Facebook tự điền, mỗi nick một khác. Nay chọn theo cài đặt.
_than_dien = _src_mp[_src_mp.index("async def _dien_thong_tin"):]
_than_dien = _than_dien[:_than_dien.index("\nasync def ")]
check("điền thông tin có bước chọn vị trí theo cài đặt, TRƯỚC khi bấm Tiếp",
      'await _chon_vi_tri(page, cd["mkt_vi_tri"])' in _than_dien
      and _than_dien.index("_chon_vi_tri(") < _than_dien.index('_bam_dung_chu(page, "Tiếp")'))
_than_vt = _src_mp[_src_mp.index("async def _chon_vi_tri"):]
_than_vt = _than_vt[:_than_vt.index("\nasync def ")]
check("chọn vị trí xong phải ĐỌC LẠI ô, sai thì dừng",
      "sau = await o.input_value()" in _than_vt and "raise LoiBuoc" in _than_vt)
check("chọn gợi ý KHỚP chữ đã gõ, không bấm mù dòng đầu",
      "_JS_GOI_Y_VI_TRI" in _than_vt and ".includes(can)" in _src_mp)
# Ảnh: bản đầu cắt cứng anh[:3] — content 6 ảnh lên Marketplace chỉ còn 3.
check("Marketplace tải đủ ảnh (tối đa 10), không cắt cứng 3",
      'set_input_files("input[type=file]", anh[:3])' not in _src_mp
      and 'set_input_files("input[type=file]", can)' in _src_mp
      and "ANH_TOI_DA = 10" in _src_mp
      and "await _tai_anh(page, anh)" in _than_dien)
_than_anh = _src_mp[_src_mp.index("async def _tai_anh"):]
_than_anh = _than_anh[:_than_anh.index("\nasync def ")]
check("tải ảnh xong chờ bộ đếm của Facebook báo đủ, không chờ cố định",
      "_JS_DEM_ANH" in _than_anh and "if da >= len(can):" in _than_anh)
import market_poster as _mp_tdm
check("so khớp vị trí bỏ dấu, không phân biệt hoa thường",
      _mp_tdm._khong_dau("Hai Bà Trưng") in _mp_tdm._khong_dau("Quận Hai Bà Trưng, Hanoi"))
check("so khớp vị trí: chữ đ", _mp_tdm._khong_dau("Đống Đa") == "dong da")
check("so khớp vị trí: nơi khác KHÔNG khớp",
      _mp_tdm._khong_dau("Hai Bà Trưng") not in _mp_tdm._khong_dau("Trịnh Châu Tỉnh/Thành phố"))
try:
    _mp_tdm.post_marketplace("Ai Do", "mô tả", image_url="http://x/a.jpg", tieu_de="   ")
    _mp_loi = ""
except Exception as _e_tdm:
    _mp_loi = str(_e_tdm)
check("thiếu tiêu đề -> báo lỗi ngay, không mở trình duyệt",
      "chưa có Tiêu đề Market Place" in _mp_loi)
# Scheduler: thiếu tiêu đề là lỗi DỮ LIỆU — báo ở slot rồi bỏ qua, KHÔNG tính
# vào sức khoẻ acc (5 slot như vậy là nick bị cho nghỉ oan).
_src_sc = Path("scheduler.py").read_text(encoding="utf-8")
_than_mkt_sc = _src_sc[_src_sc.index("def _run_marketplace_slot"):]
_than_mkt_sc = _than_mkt_sc[:_than_mkt_sc.index("\ndef ", 10)]
_i_thieu = _than_mkt_sc.index("if not tieu_de:")
check("scheduler bỏ qua slot thiếu tiêu đề mà không ghi sức khoẻ acc",
      "return" in _than_mkt_sc[_i_thieu:_i_thieu + 400]
      and "ghi_nhan_phien_dang" not in _than_mkt_sc[_i_thieu:_i_thieu + 400]
      and _i_thieu < _than_mkt_sc.index("post_marketplace("))
check("scheduler truyền tiêu đề của content cho bộ đăng",
      'ct.get("tieu_de_mkt")' in _than_mkt_sc and "tieu_de=tieu_de" in _than_mkt_sc)

# ── Tham gia nhóm Market ───────────────────────────────────────────────────
# Dùng chung bộ máy với "Tham gia nhóm", khác hai chỗ: nguồn nhóm và KHÔNG
# switch sang Page. Marketplace chỉ đăng được dưới nick cá nhân, nên cho Page
# vào nhóm là tốn một lượt xin duyệt mà nick vẫn không đăng được vào đó.
_src_jr = Path("join_groups_runner.py").read_text(encoding="utf-8")
check("runner nhận tham số nguồn nhóm",
      'def _run_join(schedule_id: int, acc_name: str, page_uid: str, nguon: str = "")' in _src_jr)
check("nguồn MARKET đọc nhóm ma_nhom='MARKET'",
      'WHERE ma_nhom=\'MARKET\'' in _src_jr)
_i_mkt  = _src_jr.index('if nguon == "MARKET":\n            _log("info", "👤')
_i_swi  = _src_jr.index("await _switch_to_page(page, ctx, page_uid)", _i_mkt)
check("nhóm MARKET KHÔNG switch sang Page",
      "else:" in _src_jr[_i_mkt:_i_swi])
_src_jw = Path("join_groups_worker.py").read_text(encoding="utf-8")
check("worker đọc JOIN_NGUON", 'JOIN_NGUON' in _src_jw)

# Nhóm đã tham gia được lọc TRƯỚC khi duyệt, không mở trang — đo thật lúc làm
# tối ưu này: phiên cũ mở 30 trang nhóm trong 10 phút chỉ để biết cả 30 đều đã
# là thành viên. Chỉ nhóm lọt qua bộ lọc mới rơi vào đường dự phòng 5 giây.
check("lọc nhóm đã tham gia trước khi duyệt",
      "_lay_nhom_da_vao" in _src_jr and "con_lai" in _src_jr)
# groups/joins trả nhóm của CHỦ THỂ ĐANG HOẠT ĐỘNG. Lịch Market không switch
# Page nên nó ra nhóm của nick cá nhân — đúng thứ cần, nhưng log phải nói đúng.
check("log gọi đúng chủ thể, không nói 'Page' khi chạy Market",
      'chu_the = "Nick" if nguon == "MARKET" else "Page"' in _src_jr
      and "f\"📋 {chu_the} đã tham gia" in _src_jr)
check("MARKET không bắt buộc Page UID",
      'if NGUON != "MARKET" and not PAGE_UID' in _src_jw)

# Hai tab phải TÁCH danh sách: lịch Market không được lẫn vào tab cũ và ngược
# lại, nếu không thì bấm Run ở tab này lại chạy nhóm của tab kia.
_src_srv_j = Path("server.py").read_text(encoding="utf-8")
check("API lọc lịch theo nguồn",
      "WHERE COALESCE(nguon,'')=?" in _src_srv_j)
check("tạo nhanh Market không đòi Page",
      "gen-quick-market" in _src_srv_j and "get_uid_groups_market" in _src_srv_j)
check("tạo nhanh UID Nhóm bỏ qua lịch Market",
      "WHERE COALESCE(nguon,'')=''" in _src_srv_j)

# ── Tạo lịch nhanh = DỰNG LẠI theo phân công hiện tại ──────────────────────
# Trước đây nút này chỉ THÊM nên bảng phình ra: đo 01/10, 16 dòng trong khi
# phân công thật chỉ có 12, và hai nick có hai dòng — bấm "Chạy lần lượt" là
# chúng chạy hai lượt, lượt đầu cho Page CŨ đi xin vào 58 nhóm.
with db._conn() as _c_gq:
    _c_gq.execute("DELETE FROM join_schedules")
    _c_gq.execute("DELETE FROM accounts")
    _c_gq.execute("DELETE FROM pages")
for _n, _p in (("A1", "P1"), ("A2", "P2"), ("A3", "")):
    db.upsert_account({"ten_acc": _n, "ten_page": _p, "trang_thai": "Active",
                       "c_user": f"c{_n}", "xs": "x"})
db.upsert_account({"ten_acc": "A4", "ten_page": "P1", "trang_thai": "Dừng",
                   "c_user": "cA4", "xs": "x"})
for _p, _u in (("P1", "111"), ("P2", "222"), ("P_cu", "999")):
    db.upsert_page({"ten_page": _p, "page_uid": _u})
# Ba dòng rác: acc không tồn tại, acc đổi Page, acc không còn Active.
with db._conn() as _c_gq:
    for _a, _p in (("A_da_xoa", "P1"), ("A1", "P_cu"), ("A4", "P1")):
        _c_gq.execute("INSERT INTO join_schedules(ten_acc,ten_page,nguon) VALUES(?,?,'')",
                      (_a, _p))
    _c_gq.execute("INSERT INTO join_schedules(ten_acc,ten_page,nguon) "
                  "VALUES('A1','P1','MARKET')")

_r_gq = _client.post("/api/join/gen-quick", json={}).get_json()
_sau = [(r["ten_acc"], r["ten_page"]) for r in
        _client.get("/api/join/schedules").get_json()["data"]]
check("chỉ còn acc Active CÓ gán Page", sorted(_sau) == [("A1", "P1"), ("A2", "P2")])
check("xoá đúng 3 dòng không còn khớp", _r_gq.get("xoa") == 3)
check("acc chưa gán Page không được tạo lịch", ("A3", "") not in _sau)
check("acc Dừng không được tạo lịch", not [x for x in _sau if x[0] == "A4"])
# Lịch Marketplace là bảng khác, tuyệt đối không được dọn lây.
check("KHÔNG đụng vào lịch Marketplace",
      len(_client.get("/api/join/schedules?nguon=MARKET").get_json()["data"]) == 1)
# Bấm lại lần nữa thì không được tạo thêm — nếu không, mỗi lần bấm là một
# dòng trùng và nick đó chạy thêm một lượt.
_r_gq2 = _client.post("/api/join/gen-quick", json={}).get_json()
check("bấm lại không tạo thêm dòng trùng",
      _r_gq2.get("created") == 0 and _r_gq2.get("xoa") == 0
      and len(_client.get("/api/join/schedules").get_json()["data"]) == 2)
with db._conn() as _c_gq:
    _c_gq.execute("DELETE FROM join_schedules")
check("truyền JOIN_NGUON khi Run", '"JOIN_NGUON":' in _src_srv_j)

_html_jm = Path("templates/index.html").read_text(encoding="utf-8")
_ajs_jm  = Path("static/js/app.js").read_text(encoding="utf-8")

# ── Làm sạch nhóm ──────────────────────────────────────────────────────────
# Rời mọi nhóm KHÔNG có trong UID Marketplace, để nick chỉ còn nhóm mục tiêu.
# Rời nhóm khó quay lại nên mặc định TẮT và phải tự tay tích từng nick.
check("cột lam_sach mặc định TẮT",
      '_add_col("join_schedules", "lam_sach", "lam_sach INTEGER DEFAULT 0")'
      in Path("db.py").read_text(encoding="utf-8"))
# Làm sạch bật được cho CẢ lịch Page (02/10). Lịch Page thì Page rời nhóm ngoài
# UID Nhóm — runner chỉ làm khi Facebook xác nhận đang dùng Page.
with db._conn() as _c_ls:
    _c_ls.execute("INSERT INTO join_schedules(ten_acc,ten_page,page_uid,nguon) "
                  "VALUES('LS_PAGE','P','123','')")
    _id_ls = _c_ls.execute("SELECT id FROM join_schedules WHERE ten_acc='LS_PAGE'").fetchone()[0]
_r_ls = _client.post(f"/api/join/{_id_ls}/lam-sach", json={"bat": True}).get_json()
with db._conn() as _c_ls:
    _v_ls = _c_ls.execute("SELECT lam_sach FROM join_schedules WHERE id=?", (_id_ls,)).fetchone()[0]
    _c_ls.execute("DELETE FROM join_schedules WHERE ten_acc='LS_PAGE'")
check("bật được làm sạch cho lịch Page", _r_ls.get("ok") is True and _v_ls == 1)
import re as _re_ls
_html_ls = Path("templates/index.html").read_text(encoding="utf-8")
_bang_page = _html_ls[_html_ls.index('id="page-tham-gia-nhom"'):_html_ls.index('id="join-table"')]
check("bảng Page có cột Làm sạch và Đã rời",
      ">Làm sạch</th>" in _bang_page and ">Đã rời</th>" in _bang_page)
check("bỏ cột Giờ chạy ở bảng Page (chạy lần lượt nên giờ chạy vô nghĩa)",
      ">Giờ chạy</th>" not in _bang_page)
_ajs_ls = Path("static/js/app.js").read_text(encoding="utf-8")
check("ô Làm sạch ở bảng Page gọi đúng nguồn Page",
      "jmLamSach(${r.id}, this.checked, '')" in _ajs_ls)
check("số cột hàng trống khớp bảng Page (10 cột)",
      len(_re_ls.findall(r"<th[\s>]", _bang_page)) == 10
      and 'colspan="10" class="empty">Chưa có lịch tham gia nhóm nào' in _ajs_ls)
# Làm sạch chạy SAU phần tham gia, và chỉ khi đã vào được ít nhất một nhóm mục
# tiêu. Bản cũ làm sạch TRƯỚC: ngày 02/10 bước tham gia báo lỗi 15/15 nhóm (đọc
# sai, xem dưới) — nick nào có nhóm cũ mà chạy tiếp là rời sạch nhóm cũ, không
# vào được nhóm mới.
_i_join = _src_jr.index("for i, g in enumerate(groups, 1):")
_i_sach = _src_jr.index("await _lam_sach_nhom(")
_i_chan = _src_jr.index('if stats["moi_join"] + stats["da_join"] == 0:')
check("làm sạch chạy SAU phần tham gia", _i_join < _i_sach)
check("chưa vào được nhóm mục tiêu nào thì BỎ QUA làm sạch", _i_join < _i_chan < _i_sach)
check("nhóm mới chờ duyệt KHÔNG tính là đã vào khi quyết định làm sạch",
      "cho_duyet" not in _src_jr[_i_chan:_i_chan + 60])
check("chỉ còn MỘT chỗ gọi làm sạch", _src_jr.count("await _lam_sach_nhom(") == 1)
check("làm sạch dùng lại danh sách vừa đọc, không cuộn đọc lại",
      "page, groups_goc, dang_o," in _src_jr[_i_sach:_i_sach + 120])
# Rời 425 nhóm mất gần 3 tiếng (Mai Tùng, 02/10) — cột "Đã rời" phải tăng dần,
# không thì bảng đứng ở 0 cả buổi, nhìn tưởng tool treo.
check("làm sạch báo tiến độ lên bảng trong lúc chạy",
      'bao=lambda n: _update_status("Đang chạy", da_roi=n)' in _src_jr
      and "bao(da_roi)" in _src_jr)
# Trạng thái phải giữ nguyên "Đang chạy": dọn lịch kẹt và nút Dừng đều tìm
# đúng chữ đó — ghi chữ khác vào là lịch kẹt mãi khi tiến trình chết.
check("báo tiến độ không đổi chữ trạng thái",
      "_update_status(f\"Đang rời" not in _src_jr)
# `groups` bị thay bằng danh sách đã lọc, nên phải giữ bản gốc để biết nhóm nào
# là mục tiêu — dùng nhầm `groups` là rời luôn nhóm đã tham gia từ trước.
check("làm sạch dùng danh sách mục tiêu GỐC", "groups_goc = list(groups)" in _src_jr)
check("làm sạch theo cờ của lịch, cả Page lẫn Market",
      "lam_sach_nay = lam_sach" in _src_jr)
# Lịch Page: switch hỏng mà vẫn làm sạch là NICK rời sạch nhóm của nó, kể cả
# nhóm Marketplace. Phải hỏi Facebook trước, hỏng thì bỏ qua làm sạch.
_i_hoi_page = _src_jr.index("not await _dang_dung_page(page, page_uid)")
check("lịch Page hỏi Facebook đang dùng Page TRƯỚC khi làm sạch",
      _i_join < _i_hoi_page < _i_sach
      and "lam_sach_nay = False" in _src_jr[_i_hoi_page:_i_hoi_page + 300])
check("lịch Market không phải hỏi Page",
      'nguon != "MARKET" and not await _dang_dung_page' in _src_jr)
check("switch hỏng KHÔNG dừng phần tham gia (logic Page giữ như cũ)",
      "_dang_dung_page" not in _src_jr[_src_jr.index("await _switch_to_page(page, ctx, page_uid)"):_i_join])

import asyncio as _aio_ls
import join_groups_runner as _jr_ls

class _TrangGia:
    """Trang giả: goto không làm gì, `url` là chỗ /me trỏ tới."""
    def __init__(self, url): self.url = url
    async def goto(self, *a, **k): pass
    async def wait_for_timeout(self, *a): pass

def _hoi(url, uid):
    return _aio_ls.run(_jr_ls._dang_dung_page(_TrangGia(url), uid))

check("/me ra id Page -> đang dùng Page",
      _hoi("https://www.facebook.com/profile.php?id=615", "615"))
check("/me ra id nick -> KHÔNG phải Page",
      not _hoi("https://www.facebook.com/profile.php?id=100019346433861", "615"))
check("id dài hơn mà trùng đầu KHÔNG được nhận nhầm",
      not _hoi("https://www.facebook.com/profile.php?id=6150", "615"))
check("thiếu Page UID -> KHÔNG phải Page", not _hoi("https://www.facebook.com/profile.php?id=", ""))
with db._conn() as _c_ls:
    _c_ls.execute("INSERT INTO pages(ten_page,page_uid,link_page) "
                  "VALUES('LS','61599999999001','https://www.facebook.com/TenRutGon/')")
check("Page có tên rút gọn: khớp link Page đã lưu",
      _hoi("https://www.facebook.com/tenrutgon", "61599999999001"))
check("tên rút gọn khác -> KHÔNG phải Page",
      not _hoi("https://www.facebook.com/nickcanhan", "61599999999001"))
with db._conn() as _c_ls:
    _c_ls.execute("DELETE FROM pages WHERE page_uid='61599999999001'")
# Đọc lại danh sách nhóm sau phiên: nhóm ghi lỗi mà thật ra đã vào thì sửa lại.
check("đối chiếu lại nhóm ghi lỗi với danh sách nhóm đã vào",
      'r["result"] = "moi_join"' in _src_jr and 'stats["loi"]      -= len(sua)' in _src_jr)
# Đếm KẾT QUẢ, không đếm số lần bấm — đúng lỗi đã mắc ở bước tick nhóm
# Marketplace: log báo tick 20 mà thực tế chỉ 16.
check("xác minh đã rời bằng cách đọc lại nút",
      "con_o = await page.evaluate(_JS_NUT_HIEN" in _src_jr
      and 'return "da_roi"' in _src_jr)
# Rời xong Facebook tự điều hướng đi, page.reload() lúc đó ném
# `ERR_ABORTED; maybe frame was detached` — gặp thật 01/10 ở nhóm
# 719961823676435: đã rời được nhưng bị ghi thành lỗi.
check("vào lại bằng goto chứ không reload",
      "await page.reload(" not in _src_jr)
# "Không đọc được trạng thái" KHÔNG được coi là "đã là thành viên": suy đoán đó
# làm phiên 01/10 báo "đã là thành viên: 16" trong khi 17/25 nhóm chưa hề vào.
check("không đoán 'đã là thành viên' khi không đọc được",
      "Không đọc được trạng thái thành viên" in _src_jr
      and "coi như đã là thành viên" not in _src_jr)
# Bộ dò phải khớp CHÍNH XÁC cả chuỗi trên nút ĐANG NHÌN THẤY. Bản cũ hỏi
# textContent có CHỨA "đã tham gia" nên trúng cả "N người bạn đã tham gia".
check("dò trạng thái khớp chính xác, chỉ nút nhìn thấy",
      "elementFromPoint" in _src_jr
      and "/^(đã tham gia|joined)$/" in _src_jr
      and "includes('đã tham gia')" not in _src_jr)
check("bấm Tham gia xong phải xác minh",
      'sau = await _cho_trang_thai(page' in _src_jr
      and 'Bấm Tham gia rồi mà vẫn chưa vào' in _src_jr)
# goto lại ĐÚNG URL đang mở ngay sau khi bấm thì Chromium trả bản trang cũ, nút
# vẫn "Tham gia nhóm". Đo 02/10: 15/15 nhóm vào thật bị ghi thành lỗi.
_than_join = _src_jr[_src_jr.index("async def _join_one_group"):
                     _src_jr.index("# ─── Main flow")]
_sau_bam = _than_join[_than_join.index("# XÁC MINH sau khi bấm"):]
check("xác minh đọc trên trang TRƯỚC khi vào lại",
      _sau_bam.index("_cho_trang_thai(page, 6)") < _sau_bam.index("page.goto("))
check("vào lại sau khi bấm Tham gia dùng URL chống cache",
      "page.goto(url," not in _sau_bam and "page.goto(_url_chong_cache(url)" in _sau_bam)
_than_roi = _src_jr[_src_jr.index("async def _roi_mot_nhom"):
                    _src_jr.index("async def _lam_sach_nhom")]
check("xác minh đã rời cũng dùng URL chống cache",
      _than_roi.count("page.goto(url,") == 1
      and "page.goto(_url_chong_cache(url)" in _than_roi)
import join_groups_runner as _jr_cc
check("URL chống cache thêm tham số đúng cách",
      _jr_cc._url_chong_cache("https://x/groups/1/").startswith("https://x/groups/1/?_t=")
      and _jr_cc._url_chong_cache("https://x/groups/1/?ref=a").startswith("https://x/groups/1/?ref=a&_t="))
# Lỗi thật thì ghi lại Facebook đang hiện gì — chụp TRƯỚC khi vào lại trang,
# vì vào lại là hộp thoại (nếu có) mất.
check("lỗi tham gia có ghi chẩn đoán (hộp thoại + ảnh)",
      "await _ghi_chan_doan(page, ten_nhom, hop, anh)" in _sau_bam
      and _sau_bam.index("anh = await page.screenshot()")
          < _sau_bam.index("page.goto(_url_chong_cache(url)"))
check("ảnh lỗi có giới hạn, không đầy ổ đĩa",
      "_SO_ANH_LOI >= 5" in _src_jr and "[:-_GIU_ANH_LOI]" in _src_jr)

# Nút Dừng chuỗi: diet_cay nhận DANH SÁCH pid. Truyền một số đơn lẻ thì nó ném
# TypeError → lỗi 500, chuỗi chạy tiếp như chưa bấm (gặp thật 02/10).
check("Dừng chuỗi truyền danh sách pid", "diet_cay(int(" not in _src_srv_j)
_p_dung = _sp.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
_pf_dung = Path(".join_chain_TEST_DUNG.pid")
_pf_dung.write_text(str(_p_dung.pid))
_r_dung = _client.post("/api/join/stop-chain", json={"nguon": "TEST_DUNG"})
try:
    _p_dung.wait(timeout=10)
except _sp.TimeoutExpired:
    _p_dung.kill()
check("API Dừng chuỗi trả về bình thường", _r_dung.status_code == 200
      and (_r_dung.get_json() or {}).get("ok") is True)
check("API Dừng chuỗi diệt được tiến trình chuỗi",
      _p_dung.returncode is not None and _r_dung.get_json()["da_diet"] == [_p_dung.pid])
check("API Dừng chuỗi xoá file pid", not _pf_dung.exists())
_pf_dung.unlink(missing_ok=True)
check("gửi yêu cầu thì tính chờ duyệt, không tính đã vào",
      'return "cho_duyet"' in _src_jr and "Đã gửi yêu cầu, chờ duyệt" in _src_jr)
# Danh sách groups/joins nạp rất chậm; bản cũ dừng sau 3 lượt im nên đọc thiếu.
check("đọc danh sách nhóm kiên nhẫn hơn",
      "for _ in range(45)" in _src_jr and "yen >= 6" in _src_jr
      and "window.scrollBy(0, 2200)" in _src_jr)

# ── Tên tài khoản không được có dấu cách thừa ──────────────────────────────
# Tên acc là khoá tham chiếu của 4 bảng khác; lệch một dấu cách là mọi tra cứu
# theo tên trượt sạch — đã vấp thật: get_account_by_name('Thị Sữa') trả None.
_id_sp = db.upsert_account({"ten_acc": "  Acc Thua Dau Cach  ", "trang_thai": "Active"})
check("cắt dấu cách ngay lúc lưu",
      db.get_account_by_id(_id_sp)["ten_acc"] == "Acc Thua Dau Cach")
check("tra theo tên đã cắt là thấy",
      db.get_account_by_name("Acc Thua Dau Cach") is not None)
# Migration phải sửa ĐỒNG LOẠT, nếu không lịch trỏ vào tên cũ thành mồ côi.
_src_db_sp = Path("db.py").read_text(encoding="utf-8")
check("migration sửa cả 5 bảng tham chiếu",
      all(x in _src_db_sp for x in
          ('("accounts", "ten_acc")', '("schedules", "ten_acc")',
           '("join_schedules", "ten_acc")', '("comment_posts", "acc")',
           '("pages", "acc_quan_ly")')))
check("migration bỏ qua khi cắt xong bị trùng tên khác",
      'SELECT COUNT(*) FROM accounts WHERE ten_acc=?' in _src_db_sp
      and "if _da_co:" in _src_db_sp)
# Hộp xác nhận: chỉ bấm nút NẰM TRONG dialog. Bấm bừa chữ "Rời nhóm" ở ngoài
# là bấm lại chính cái menu vừa đóng.
check("chỉ bấm nút trong hộp thoại",
      'div[role="dialog"] div[role="button"]:has-text("Rời nhóm")' in _src_jr)
# Nút "Đã tham gia" có HAI cái trên trang; bấm nhầm cái bị che thì menu không
# mở — đo thật 01/10, bấm cái đầu theo thứ tự DOM ra menu rỗng.
check("chỉ bấm nút đang NHÌN THẤY",
      "elementFromPoint" in _src_jr and "_JS_NUT_HIEN" in _src_jr)
check("da_roi về 0 khi bắt đầu lượt mới", "tong_nhom=total, da_roi=0" in _src_jr)
check("bảng có cột Làm sạch và Đã rời",
      ">Làm sạch</th>" in _html_jm and ">Đã rời</th>" in _html_jm)
check("bỏ cột Giờ chạy ở tab Market",
      _html_jm[_html_jm.index('id="page-tham-gia-nhom-market"'):
               _html_jm.index('id="jm-table"')].count("Giờ chạy") == 0)
check("hỏi lại trước khi BẬT làm sạch",
      "if(bat && !confirm(" in _ajs_jm)
check("có mục Tham gia nhóm Market", 'data-page="tham-gia-nhom-market"' in _html_jm)
check("nằm ngay dưới Tham gia nhóm",
      0 < _html_jm.index('data-page="tham-gia-nhom-market"')
          - _html_jm.index('data-page="tham-gia-nhom"') < 200)
check("mở trang thì nạp lịch Market",
      'page==="tham-gia-nhom-market"' in _ajs_jm and "loadJoinMarket()" in _ajs_jm)
# Chạy LẦN LƯỢT: một nút thay cho một nút mỗi hàng. Không song song — mỗi phiên
# là một Chromium ~1,1 GB, máy đã 11,6/15,9 GB với 5 runner.
_src_jc = Path("join_chain_worker.py").read_text(encoding="utf-8")
check("chuỗi chạy theo đúng thứ tự bảng (id giảm dần)",
      "ORDER BY id DESC" in _src_jc)
check("chuỗi chạy tuần tự, không song song",
      "for r in rows:" in _src_jc and "Popen" not in _src_jc)
check("chuỗi ghi file pid của lịch đang chạy để đèn từng hàng vẫn đúng",
      "pid_file(sid).write_text" in _src_jc and "pid_file(sid).unlink" in _src_jc)
check("một nick hỏng KHÔNG làm đứt cả chuỗi",
      "except Exception as e:" in _src_jc and "finally:" in _src_jc)
check("chuỗi sập thì báo ra", 'bao(xong=True' in _src_jc and "loi=" in _src_jc)
check("dừng chuỗi diệt CẢ CÂY tiến trình",
      "tien_trinh.diet_cay" in _src_srv_j)
check("cả hai tab đều có nút Chạy lần lượt",
      'id="join-nut-chay"' in _html_jm and 'id="jm-nut-chay"' in _html_jm)
# Bỏ nút Run từng hàng — nếu còn thì người dùng có hai đường chạy song song
# nhau, và chuỗi sẽ giành trình duyệt với phiên bấm tay.
check("KHÔNG còn nút Run từng hàng",
      "runJoin(" not in _ajs_jm and "jmChay(" not in _ajs_jm)

# Vòng lặp nạp bảng ↔ trạng thái chuỗi (v2.30.0–v2.32.0): loadJoinMarket gọi
# jcTrangThai, jcTrangThai lại gọi loadJoinMarket, không có nhịp chờ nào ở giữa.
# Đo 02/10: ~250 yêu cầu/giây, chạy mãi kể cả khi đã sang tab khác, cạn 16.384
# cổng mạng của Windows — bấm xoá lịch phải chờ rất lâu. Chỉ nhịp 5 giây
# (setInterval) được nạp lại bảng.
import re as _re_lap

def _than_ham(src, ten):
    i = src.index(f"function {ten}(")
    m = _re_lap.search(r"\n(?:async )?function ", src[i + 1:])
    return src[i: i + 1 + m.start()] if m else src[i:]

for _ten in ("loadJoinMarket", "loadJoinSchedules", "jcTheoDoi"):
    _goi = _re_lap.findall(r"(?<!=>)jcTrangThai\(([^)]*)\)", _than_ham(_ajs_jm, _ten))
    check(f"{_ten} gọi jcTrangThai mà KHÔNG nạp lại bảng",
          _goi and all(g.replace(" ", "").endswith(",false") for g in _goi))
_tt_lap = _than_ham(_ajs_jm, "jcTrangThai")
check("jcTrangThai mặc định nạp lại bảng (cho nhịp 5 giây)", "napLai=true" in _tt_lap)
check("napLai=false thì thoát TRƯỚC mọi lần nạp lại bảng",
      _tt_lap.index("if(!napLai)") < _tt_lap.index("c.nap()"))
check("nhịp 5 giây vẫn nạp lại bảng",
      "setInterval(()=>jcTrangThai(nguon), 5000)" in _than_ham(_ajs_jm, "jcTheoDoi"))

check("đổi tên tab cũ thành Tham gia nhóm Page",
      "Tham gia nhóm Page" in _html_jm
      and '"tham-gia-nhom":"Tham gia nhóm Page"' in _ajs_jm)

check("trang Market KHÔNG có cột Page",
      "jm-table" in _html_jm
      and _html_jm[_html_jm.index('id="page-tham-gia-nhom-market"'):
                   _html_jm.index('id="jm-table"')].count("<th>Page</th>") == 0)

# Lịch Market thật sự tách khỏi lịch cũ.
with db._conn() as _c_jm:
    _c_jm.execute("INSERT INTO join_schedules(ten_acc,ten_page,nguon) VALUES('A','P','')")
    _c_jm.execute("INSERT INTO join_schedules(ten_acc,ten_page,nguon) VALUES('A','','MARKET')")
_r_j1 = _client.get("/api/join/schedules").get_json()
_r_j2 = _client.get("/api/join/schedules?nguon=MARKET").get_json()
check("tab cũ không thấy lịch Market",
      all((r.get("nguon") or "") == "" for r in _r_j1["data"]))
check("tab Market chỉ thấy lịch Market",
      _r_j2["data"] and all(r["nguon"] == "MARKET" for r in _r_j2["data"]))
with db._conn() as _c_jm:
    _c_jm.execute("DELETE FROM join_schedules WHERE ten_acc='A'")


# ── UID Marketplace: danh sách nhóm đã được duyệt ──────────────────────────
# Lưu CHUNG bảng uid_groups với ma_nhom='MARKET'. Tab "UID Nhóm" vốn đã lọc
# ma_nhom==='' nên hai danh sách không lẫn nhau — phải giữ đúng như vậy.
check("mã nhóm Marketplace là MARKET", db.MA_NHOM_MARKET == "MARKET")
check("tab UID Nhóm vẫn chỉ hiện ma_nhom rỗng",
      'g.ma_nhom === ""' in _ajs_mkt)

check("tách link nhóm dạng số",
      [x["uid"] for x in db.tach_link_nhom(
          "https://www.facebook.com/groups/311375961636397/")] == ["311375961636397"])
check("tách link nhóm dạng chữ",
      [x["uid"] for x in db.tach_link_nhom(
          "facebook.com/groups/homestaytimescity")] == ["homestaytimescity"])
check("bỏ được đuôi ?ref=",
      [x["uid"] for x in db.tach_link_nhom(
          "https://www.facebook.com/groups/123456789/?ref=share")] == ["123456789"])
check("nhận UID trần",
      [x["uid"] for x in db.tach_link_nhom("987654321")] == ["987654321"])
check("đọc được tên nhóm sau dấu |",
      db.tach_link_nhom("facebook.com/groups/abc | Homestay Times City")[0]["ten_nhom"]
      == "Homestay Times City")
check("nhiều dòng, bỏ trùng, giữ thứ tự",
      [x["uid"] for x in db.tach_link_nhom(
          "facebook.com/groups/111\nfacebook.com/groups/222\nfacebook.com/groups/111")]
      == ["111", "222"])
check("dòng rác bị bỏ qua", db.tach_link_nhom("chưa có gì\n\nlinh tinh") == [])
check("tự dựng link đầy đủ từ UID trần",
      db.tach_link_nhom("555666777")[0]["link_url"]
      == "https://www.facebook.com/groups/555666777/")

_them, _bo = db.them_nhom_tu_link(db.tach_link_nhom(
    "facebook.com/groups/mkt1 | Nhóm A\nfacebook.com/groups/mkt2"), db.MA_NHOM_MARKET)
check("thêm nhóm Marketplace", (_them, _bo) == (2, 0))
_them2, _bo2 = db.them_nhom_tu_link(db.tach_link_nhom("facebook.com/groups/mkt1"),
                                    db.MA_NHOM_MARKET)
check("thêm lại thì bỏ qua trùng", (_them2, _bo2) == (0, 1))
_mkt_ds = db.get_uid_groups_market()
check("đọc lại đúng 2 nhóm", [g["uid"] for g in _mkt_ds] == ["mkt1", "mkt2"])
check("giữ tên nhóm đã nhập", _mkt_ds[0]["ten_nhom"] == "Nhóm A")
# Quan trọng: KHÔNG được lẫn vào sheet UID Nhóm của người dùng.
check("nhóm MARKET không lọt vào sheet UID Nhóm",
      not [g for g in db.get_all_uid_groups()
           if g["ma_nhom"] == "" and (g["uid"] or "").startswith("mkt")])

_r_um = _client.get("/api/uid-groups/market").get_json()
check("API trả danh sách nhóm Marketplace",
      _r_um.get("ok") and len(_r_um["data"]) == 2)
_r_um2 = _client.post("/api/uid-groups/them",
                      json={"text": "facebook.com/groups/mkt3",
                            "ma_nhom": "MARKET"}).get_json()
check("API thêm được nhóm mới", _r_um2.get("them") == 1)
_r_um3 = _client.post("/api/uid-groups/them", json={"text": "abc"}).get_json()
check("dán rác thì báo lỗi rõ, không thêm gì",
      _r_um3.get("ok") is False and "link" in (_r_um3.get("error") or "").lower())

# Quét tên nhóm: worker chạy tiến trình riêng, KHÔNG được dùng profile Chrome
# của nick — nick nào cũng có thể đang chạy phiên đăng bài, hai bên giành khoá
# thư mục profile là hỏng cả hai.
_src_quet = Path("quet_nhom.py").read_text(encoding="utf-8")
check("quét dùng profile riêng, không giành khoá với runner",
      '_quet_{MA_NHOM' in _src_quet and "find_profile_dir" not in _src_quet)
# Chỉ đọc nghĩa là KHÔNG có cú bấm nào trong worker: vào trang nhóm, đọc, đi
# tiếp. Một cú click lạc vào đây có thể là bấm Tham gia nhóm bằng nick thật.
check("quét chỉ ĐỌC — không có cú bấm nào", ".click(" not in _src_quet)
check("quét dùng lại doc_so_thanh_vien đã có",
      "doc_so_thanh_vien" in _src_quet)
# Nguồn lấy tên nhóm. Đo ngày 30/09 trên nick thật: og:title KHÔNG tồn tại,
# document.title đọc lại của trang trước (mở riêng hai nhóm, chờ 9 giây, vẫn
# cùng một title dù số thành viên khác nhau), h1 đầu trang là "Thông báo".
import quet_nhom as _qnm
check("lấy tên từ [role=main] h1", '[role="main"] h1' in _qnm.JS_TEN)
check("KHÔNG tin document.title", "document.title" not in _qnm.JS_TEN
      and "document.title" not in _qnm.JS_DOC)
check("KHÔNG tin og:title", "og:title" not in _qnm.JS_TEN
      and "og:title" not in _qnm.JS_DOC)
check("bỏ số thông báo '(8)' ở đầu tên",
      _qnm._don_ten("(8) ✅Chợ Cư Dân Times City | Facebook")
      == "✅Chợ Cư Dân Times City")
check("bỏ đuôi '| Facebook'", _qnm._don_ten("Times City Mart | Facebook")
      == "Times City Mart")
# Hai nhóm KHÁC NHAU có thể TRÙNG TÊN — 382936754082358 (16,6K) và
# 1362597001398822 (13,5K) cùng tên "✅Chợ Cư Dân Times City & Park Hill".
# Nên tuyệt đối không được thêm phép "trùng tên thì đọc lại": nó ghi đè tên
# đúng. Cũng vì vậy, muốn đối chiếu chắc chắn thì phải khớp bằng UID.
check("KHÔNG có phép đọc lại khi trùng tên", "ten_truoc" not in _src_quet)
# Nhóm lưu bằng TÊN CHỮ (7/25 nhóm của Duong) phải lấy thêm dạng SỐ, nếu không
# bộ lọc "nhóm đã tham gia" trượt và nhóm đó bị mở lại mỗi lần chạy.
check("lấy mã số từ URL dạng số",
      _qnm._ma_so_nhom("https://www.facebook.com/groups/123456789/", []) == "123456789")
check("lấy mã số từ link phụ khi URL là tên chữ",
      _qnm._ma_so_nhom("https://www.facebook.com/groups/timecity/",
                       ["/groups/987654321/members/", "/groups/987654321/media/",
                        "/groups/111222333/"]) == "987654321")
# Link /groups/<số> TRẦN không tính: trang nhóm đầy link sang nhóm khác trong
# các bài đăng, lấy bừa là ghi nhầm mã của nhóm người ta.
check("không đoán bừa khi chỉ có link nhóm khác",
      _qnm._ma_so_nhom("https://www.facebook.com/groups/timecity/",
                       ["/groups/111222333/", "/groups/444555666/"]) == "")
check("thiếu mã số thì vẫn phải quét lại", "_thieu_ma_so" in _src_quet)
# Cột thanh_vien khai là TEXT nhưng dữ liệu cũ có dòng giữ SỐ (nhập từ Excel),
# SQLite không ép kiểu. Gọi .strip() thẳng lên int làm worker sập ngay ở bước
# đọc danh sách — người bấm nút chỉ thấy nó đứng im.
check("chịu được thanh_vien là số", "_rong" in _src_quet and "str(v" in _src_quet)
# Sập thì phải BÁO RA, không được đứng im.
check("worker báo lỗi khi sập", "except Exception as e" in _src_quet
      and "bao(xong=True, loi=" in _src_quet)
check("mặc định chỉ quét dòng còn thiếu",
      "QUET_HET" in _src_quet and 'QUET_HET", "0"' in _src_quet)
_src_srv_q = Path("server.py").read_text(encoding="utf-8")
check("server chặn chạy chồng hai lượt quét",
      "_quet_dang_chay(" in _src_srv_q)
check("có nút quét và ô chọn nick",
      'id="uidm-nut-quet"' in _html_mkt and 'id="uidm-acc"' in _html_mkt)
# Quét UID luôn chạy ẩn — đã BỎ ô tích "hiện Chrome" theo yêu cầu (không ai cần
# nhìn tận mắt nó mở từng nhóm). Giữ phép kiểm ở dạng đảo để không ai thêm lại.
check("đã bỏ ô tích hiện Chrome khỏi quét UID",
      'uidm-hien-chrome' not in _html_mkt and 'uid-hien-chrome' not in _html_mkt
      and "hien_chrome:" not in _ajs_mkt)
# Sắp xếp theo số thành viên, ba trạng thái. Giữ cả "thứ tự nhập" vì đó là thứ
# tự Duong tự duyệt từng nhóm, không phải danh sách ngẫu nhiên.
check("cột Thành viên bấm được để sắp xếp",
      'onclick="uidmSapXep()"' in _html_mkt and 'id="uidm-th-tv"' in _html_mkt)
check("sắp xếp đủ ba trạng thái",
      '_uidmSap === "" ? "giam"' in _ajs_mkt and '"giam" ? "tang" : ""' in _ajs_mkt)
# thanh_vien có dòng là SỐ, có dòng là CHUỖI — phải đọc được cả hai, nếu không
# thì sắp xếp ra thứ tự lung tung mà nhìn bảng không biết sai ở đâu.
check("đọc số thành viên chịu được cả số lẫn chuỗi",
      'String(g.thanh_vien || "0").replace(/\\D/g, "")' in _ajs_mkt)

# ── Cột STT + kéo đổi thứ tự ───────────────────────────────────────────────
# Cột STT kiêm luôn tay cầm để kéo, thay cho một cột ☰ riêng: bảng Tài khoản
# đã 19 cột, thêm cột nữa chỉ để kéo là phí chỗ.
check("có kiểu cho cột STT", "td.stt {" in _html_mkt)
check("các bảng đều có đầu cột # (gồm cả Thư viện ảnh)",
      _html_mkt.count('width:40px;text-align:center">#</th>') == 5
      and 'id="uidm-table"' in _html_mkt and 'id="tv-table"' in _html_mkt)
check("KHÔNG còn cột ☰ rỗng", 'style="width:32px"></th>' not in _html_mkt)
for _b in ("rows.map((r,i)=>{", "res.data.map((p,i)=>", "res.data.map((r,i)=>{",
           "res.data.map((g,i)=>{"):
    check(f"bảng có chỉ số hàng: {_b[:22]}", _b in _ajs_mkt)
check("đủ các bảng có ô STT (gồm cả Thư viện ảnh)", _ajs_mkt.count('class="stt"') == 6)

# UID Marketplace sắp xếp được theo số thành viên. Kéo trong lúc đang sắp xếp
# thì thứ tự NHÌN THẤY bị ghi đè lên thứ tự tay — mất thứ tự Duong tự duyệt
# từng nhóm mà không có đường lấy lại.
check("Marketplace kéo được", "function uidmDrop" in _ajs_mkt
      and 'uidmDrop(event,${g.id})' in _ajs_mkt)
check("đang sắp xếp thì CHẶN kéo",
      "if(_uidmSap){" in _ajs_mkt and "_rowDrop(e, t, \"uidm-table\"" in _ajs_mkt)
_i_chan = _ajs_mkt.index("async function uidmDrop")
_i_goi  = _ajs_mkt.index('_rowDrop(e, t, "uidm-table"', _i_chan)
check("chặn ĐỨNG TRƯỚC khi gọi lưu",
      _ajs_mkt.index("if(_uidmSap){", _i_chan) < _i_goi)


# ── Hai tab UID dùng chung một bộ máy ──────────────────────────────────────
# Chỉ khác đúng `ma_nhom`. Tách làm hai bộ là tạo chỗ cho chúng lệch nhau — đã
# có tiền lệ với hai file poster từng giữ hai bản chép của cùng một hàm.
check("import Excel nhận ma_nhom",
      "def import_uid_groups(records: list[dict], ma_nhom: str = \"\")" in
      Path("db.py").read_text(encoding="utf-8"))
# Nhập Excel gửi multipart nên KHÔNG có JSON body — phải đọc được cả form.
check("đọc ma_nhom từ cả query, JSON lẫn form",
      "request.form.get(\"ma_nhom\")" in _src_srv_q
      and "request.args.get(\"ma_nhom\")" in _src_srv_q)
# Mã sheet lạ phải quy về '' chứ không được ghi thẳng: ghi nhầm mã thì dữ liệu
# lọt sang sheet không tồn tại, chẳng tab nào hiện ra mà cũng không báo lỗi.
check("mã sheet lạ quy về rỗng",
      'return "MARKET" if str(v).strip().upper() == "MARKET" else ""' in _src_srv_q)

# Nhập Excel vào sheet Marketplace KHÔNG được lẫn sang sheet UID Nhóm.
_truoc_uid = len(db.get_uid_groups(""))
db.import_uid_groups([{"uid": "xl_mkt_1", "ten_nhom": "X"}], db.MA_NHOM_MARKET)
db.import_uid_groups([{"uid": "xl_uid_1", "ten_nhom": "Y"}], "")
check("Excel vào đúng sheet Marketplace",
      "xl_mkt_1" in [g["uid"] for g in db.get_uid_groups(db.MA_NHOM_MARKET)])
check("Excel vào đúng sheet UID Nhóm",
      "xl_uid_1" in [g["uid"] for g in db.get_uid_groups("")])
check("hai sheet không lẫn nhau",
      "xl_mkt_1" not in [g["uid"] for g in db.get_uid_groups("")]
      and "xl_uid_1" not in [g["uid"] for g in db.get_uid_groups(db.MA_NHOM_MARKET)])
check("thêm trùng trong CÙNG sheet mới bị bỏ qua",
      db.import_uid_groups([{"uid": "xl_mkt_1"}], db.MA_NHOM_MARKET) == (0, 1)
      and db.import_uid_groups([{"uid": "xl_mkt_1"}], "") == (1, 0))

# Tab UID Nhóm: bỏ form nhập tay, thay bằng dán link + quét như tab Marketplace.
check("UID Nhóm có ô dán link", 'id="uid-dan"' in _html_mkt)
check("UID Nhóm có nút quét tên", 'id="uid-nut-quet"' in _html_mkt)
check("UID Nhóm BỎ form nhập tay từng ô",
      "openUidGroupForm" not in _html_mkt and "openUidGroupForm" not in _ajs_mkt)
check("cả hai tab đều có Nhập/Xuất Excel",
      "exportUidGroupsExcel('')" in _html_mkt
      and "exportUidGroupsExcel('MARKET')" in _html_mkt
      and "importUidGroupsExcel(event,'')" in _html_mkt
      and "importUidGroupsExcel(event,'MARKET')" in _html_mkt)
check("nhập Excel gửi kèm ma_nhom", 'fd.append("ma_nhom"' in _ajs_mkt)

check("có mục UID Marketplace ở sidebar", 'data-page="uid-market"' in _html_mkt)
check("có trang UID Marketplace", 'id="page-uid-market"' in _html_mkt)
check("mở trang thì nạp danh sách",
      'page==="uid-market"' in _ajs_mkt and "loadUidMarket()" in _ajs_mkt)


# ── Marketplace: lọc nhóm theo từ khoá ─────────────────────────────────────
# Bước chọn nhóm KHÔNG có ô tìm kiếm (đo trên nick Sa Tran Anh ngày 29/09: 28
# nhóm hiện thẳng thành danh sách tick), nên phần mềm phải tự đọc tên và tự lọc.
check("bỏ dấu + bỏ hoa thường + bỏ ký tự lạ",
      db.chuan_hoa("MUA BÁN NHÀ TIMES CITY-PARK HILL ✅") == "muabannhatimescityparkhill")
check("chuẩn hoá đổi đ -> d", db.chuan_hoa("Đống Đa") == "dongda")
check("chuỗi rỗng -> rỗng", db.chuan_hoa("") == "")

check("tách nhiều từ khoá theo dấu phẩy",
      db.tach_tu_khoa("Times City, Time City, làng Times")
      == ["Times City", "Time City", "làng Times"])
check("tách từ khoá: bỏ trùng sau khi chuẩn hoá",
      db.tach_tu_khoa("Times City, TIMES CITY, times  city") == ["Times City"])
check("tách từ khoá: ô rỗng -> rỗng", db.tach_tu_khoa("  ,  ") == [])

# Từ khoá rỗng KHÔNG được coi là "khớp tất cả" — như vậy là tick sạch mọi nhóm.
check("từ khoá rỗng -> không khớp gì", db.khop_tu_khoa("Times City", "") is False)
check("khớp một trong nhiều từ khoá",
      db.khop_tu_khoa("Chợ Làng Time City - Park Hill", "Times City, Time City"))
check("không khớp thì trả False",
      db.khop_tu_khoa("Phòng trọ Kim Giang - Linh Đàm", "Times City, Time City") is False)

# Facebook viết "43,5K" kiểu Việt Nam: PHẨY là dấu thập phân khi có hậu tố K,
# còn CHẤM là phân cách hàng nghìn khi không có. Lẫn hai thứ là sai nghìn lần.
check("đọc 43,5K thành viên", db.doc_so_thanh_vien("43,5K thành viên · Công khai") == 43500)
check("đọc 3,6K thành viên",  db.doc_so_thanh_vien("3,6K thành viên") == 3600)
check("đọc 1.234 thành viên", db.doc_so_thanh_vien("1.234 thành viên") == 1234)
check("đọc 950 thành viên",   db.doc_so_thanh_vien("950 thành viên") == 950)
check("không có số -> 0",     db.doc_so_thanh_vien("Công khai") == 0)

# 28 nhóm THẬT của nick Sa Tran Anh, chép nguyên từ DOM lúc 29/09.
_NHOM_THAT = [
    "Cư dân Times City & Park Hill tìm Mua Nhà & Thuê Nhà 43,5K thành viên · Công khai",
    "Hội Mua Bán Nhà & Thuê Nhà Times City 30,6K thành viên · Công khai",
    "Chợ Làng Time City - Park Hill - Premium 29,5K thành viên · Công khai",
    "TRAO ĐỔI - MUA BÁN - CHO THUÊ CĂN HỘ TIMES CITY 🔑 19,8K thành viên · Riêng tư",
    "Chợ cư dân làng Times 16,1K thành viên · Công khai",
    "CHỢ - TIME CITY - HÒA BÌNH GREEN -MINH KHAI - ONLINE 11,0K thành viên · Công khai",
    "CHỢ DỊCH VỤ CHO CƯ DÂN TIMES CITY - PARK HILL 30,7K thành viên · Công khai",
    "Homestay Times City 3,6K thành viên · Công khai",
    "Mua bán cho thuê căn hộ Times city 27,6K thành viên · Công khai",
    "MUA BÁN NHÀ TIMES CITY-PARK HILL-PARK PREMIUM✅ 14,1K thành viên · Công khai",
    "Cư dân Park Hill Times City 18,2K thành viên · Công khai",
    "Times City Mua bán cho thuê căn hộ 52,3K thành viên · Công khai",
    "Hội mua bán chung cư Times city 4,6K thành viên · Công khai",
    "Homestay Times City - Cho thuê Homestay Times City theo ngày / giờ 14,8K thành viên · Công khai",
    "TÌM PHÒNG TRỌ✅KIM GIANG✅THANH LIỆT✅ĐẠI KIM✅LINH ĐÀM✅HÀ ĐÔNG 97,0K thành viên · Công khai",
    "Chợ chung cư Times City 15,6K thành viên · Công khai",
    "Phòng trọ khu vực Bằng Liệt - Thanh Liệt - Kim Giang - Linh Đàm 36,4K thành viên · Công khai",
    "Làng Times City 37,2K thành viên · Công khai",
    "Chợ cư dân Times City-Park Hill- Park Premium 18,1K thành viên · Công khai",
    "Times City Mart 23,3K thành viên · Công khai",
    "Chung cư Times City Park Hill Premium 12,5K thành viên · Công khai",
    "Cư Dân Chợ Làng Times City ParkHill Premium 22,1K thành viên · Công khai",
    "Homestay Times City - Park Hill cho thuê theo giờ/ngày/tháng/năm 4,8K thành viên · Công khai",
    "Chợ Cư Dân Times City Minh Khai 9,6K thành viên · Công khai",
    "Times City 44,5K thành viên · Công khai",
    "BẤT ĐỘNG SẢN Times City 35,4K thành viên · Công khai",
    "Bất động sản Times City Park Hill Mua bán cho thuê 66,3K thành viên · Công khai",
    "Bất động sản KĐT Times City - Những thông tin mới nhất 6,4K thành viên · Công khai",
]
_ds = [{"ten": t} for t in _NHOM_THAT]

# Một từ khoá "Times City" bỏ oan 3 nhóm chỉ vì chính tả — đây là lý do phải
# cho nhiều từ khoá. Giữ phép đo này để sau có ai rút về một từ khoá thì biết.
_mot, _ = db.chon_nhom_marketplace(_ds, "Times City", 99)
check("một từ khoá 'Times City' chỉ vớt được 23/28", len(_mot) == 23)

_chon, _bo = db.chon_nhom_marketplace(_ds, db.MKT_MAC_DINH["mkt_tu_khoa"], 99)
check("mặc định nhiều từ khoá vớt được 26/28", len(_chon) == 26)
_ten_bo = " | ".join(n["ten"] for n in _bo)
check("chỉ còn loại 2 nhóm phòng trọ khác khu",
      len(_bo) == 2 and "KIM GIANG" in _ten_bo and "Bằng Liệt" in _ten_bo)

# Khớp nhiều hơn hạn mức thì bốc NGẪU NHIÊN, không ưu tiên nhóm đông nữa.
_chon20, _bo20 = db.chon_nhom_marketplace(_ds, db.MKT_MAC_DINH["mkt_tu_khoa"], 20)
check("đúng 20 nhóm khi hạn mức 20", len(_chon20) == 20)
check("mọi nhóm được chọn đều khớp từ khoá",
      all(db.khop_tu_khoa(n["ten"], db.MKT_MAC_DINH["mkt_tu_khoa"])
          for n in _chon20))

# Thứ tự TICK cũng phải ngẫu nhiên, không phải từ trên xuống: tick theo đúng
# thứ tự danh sách phiên nào cũng vậy là một dấu vết nhận ra máy.
_vi_tri = {t: i for i, t in enumerate(_NHOM_THAT)}
_xuoi = sum(1 for _ in range(8)
            if [_vi_tri[n["ten"]] for n in
                db.chon_nhom_marketplace(_ds, db.MKT_MAC_DINH["mkt_tu_khoa"], 20)[0]]
            == sorted(_vi_tri[n["ten"]] for n in
                      db.chon_nhom_marketplace(_ds, db.MKT_MAC_DINH["mkt_tu_khoa"], 20)[0]))
check("thứ tự tick ngẫu nhiên, không phải từ trên xuống", _xuoi == 0)
check("danh sách bỏ giữ đúng thứ tự màn hình",
      [_vi_tri[n["ten"]] for n in _bo20]
      == sorted(_vi_tri[n["ten"]] for n in _bo20))

# Bốc ngẫu nhiên thật, không phải lúc nào cũng ra một bộ. 26 nhóm khớp mà chỉ
# lấy 20 nên C(26,20) = 230.230 khả năng — năm lần ra y hệt nhau là chuyện
# gần như không xảy ra, trừ khi hàm đã thôi ngẫu nhiên.
_cac_lan = {tuple(n["ten"] for n in
                  db.chon_nhom_marketplace(_ds, db.MKT_MAC_DINH["mkt_tu_khoa"], 20)[0])
            for _ in range(5)}
check("bốc ngẫu nhiên — 5 lần không ra cùng một bộ", len(_cac_lan) > 1)
check("chọn + bỏ luôn bằng tổng số nhóm", len(_chon20) + len(_bo20) == 28)
# Hạn mức 0 thì không tick gì — không được hiểu thành "không giới hạn".
check("hạn mức 0 -> không chọn nhóm nào",
      db.chon_nhom_marketplace(_ds, "Times City", 0)[0] == [])


# ═══════════════════════════════════════════════════════════════════════════
# Giấy phép — đăng nhập Gmail, mỗi tài khoản một máy
# ═══════════════════════════════════════════════════════════════════════════
import giay_phep as _gp
from datetime import datetime as _dt, timedelta as _td

# ĐÂY LÀ PHÉP KIỂM QUAN TRỌNG NHẤT CỦA CẢ KHỐI NÀY.
# Phần mềm đang chạy việc thật trên máy Duong và trên các máy đã phát đi. Bật
# nhầm kèm một bản cập nhật là tất cả đồng loạt hiện màn hình đăng nhập trong
# khi máy chủ giấy phép còn chưa dựng xong.
_os.environ.pop("MNT_GIAY_PHEP", None)
check("GIẤY PHÉP MẶC ĐỊNH LÀ TẮT", _gp.bat() is False)
check("đang tắt thì KHÔNG chặn ai", _gp.trang_thai()["dung_duoc"] is True)
check("đang tắt thì vòng canh không chạy", _gp.bat_dau_canh() is None)

_os.environ["MNT_GIAY_PHEP"] = "1"
check("bật bằng biến môi trường thì có hiệu lực", _gp.bat() is True)
check("bật mà chưa đăng nhập -> chặn",
      _gp.trang_thai() == {"dung_duoc": False, "email": "", "han_den": "",
                           "ly_do": "Chưa đăng nhập"})

# Mã máy phải cố định giữa các lần gọi, nếu không thì mỗi lần mở app là một
# máy mới và khách bị đá khỏi chính mình.
check("mã máy cố định", _gp.may_id() == _gp.may_id())
check("mã máy đã băm, không lộ mã gốc", len(_gp.may_id()) == 32)

_gp_tep_that = _gp.TEP
_gp.TEP = Path(tempfile.mkdtemp(prefix="test_gp_")) / "gp.json"
try:
    _nay = _dt.now()

    def _dat(**k):
        _mac = {"email": "a@gmail.com", "token": "tk", "may_id": _gp.may_id(),
                "han_den": (_nay + _td(days=30)).strftime("%Y-%m-%d"),
                "kiem_cuoi": _nay.isoformat(timespec="seconds")}
        _mac.update(k)
        _gp._ghi(_mac)

    _dat()
    check("giấy phép đủ điều kiện -> dùng được", _gp.trang_thai()["dung_duoc"])

    # Chép cả thư mục data/ sang máy khác là cách chia sẻ dễ nghĩ ra nhất.
    _dat(may_id="cua-may-khac")
    check("giấy phép của máy khác -> KHÔNG dùng được",
          not _gp.trang_thai()["dung_duoc"])
    check("và nói rõ vì sao", "máy khác" in _gp.trang_thai()["ly_do"].lower())

    _dat(han_den=(_nay - _td(days=1)).strftime("%Y-%m-%d"))
    check("hết hạn -> không dùng được", not _gp.trang_thai()["dung_duoc"])

    # Ân hạn vừa là mức chịu mạng chập chờn, vừa là thời gian tối đa một máy
    # BỊ ĐÁ còn chạy được. Hai thứ đó là một, không tách ra được.
    check("ân hạn đúng 15 phút như Duong chọn", _gp.AN_HAN_PHUT == 15)
    _dat(kiem_cuoi=(_nay - _td(minutes=_gp.AN_HAN_PHUT - 3))
         .isoformat(timespec="seconds"))
    check("mất mạng trong ân hạn -> vẫn chạy", _gp.trang_thai()["dung_duoc"])
    _dat(kiem_cuoi=(_nay - _td(minutes=_gp.AN_HAN_PHUT + 3))
         .isoformat(timespec="seconds"))
    check("mất mạng quá ân hạn -> khoá", not _gp.trang_thai()["dung_duoc"])

    # Mốc thời gian hỏng không được hiểu thành "vừa kiểm xong".
    _dat(kiem_cuoi="rác")
    check("mốc kiểm hỏng -> coi như đã lâu, khoá",
          not _gp.trang_thai()["dung_duoc"])
finally:
    shutil.rmtree(_gp.TEP.parent, ignore_errors=True)
    _gp.TEP = _gp_tep_that
    _os.environ.pop("MNT_GIAY_PHEP", None)

# Phân biệt "máy chủ nói KHÔNG" với "không gọi được máy chủ" là mấu chốt: gộp
# hai thứ lại thì hoặc mất mạng cũng bị khoá, hoặc bị đá rồi vẫn chạy tiếp.
_src_gp = Path("giay_phep.py").read_text(encoding="utf-8")
check("không gọi được máy chủ thì trả None, không phải dict",
      "return None" in _src_gp.split("def _goi(")[1].split("\ndef ")[0])
check("máy chủ trả lời từ chối thì xoá giấy phép ngay",
      "xoa()" in _src_gp.split("def kiem_tra(")[1].split("\ndef ")[0])

# Bí mật của Google TUYỆT ĐỐI không được nằm trong bản phát cho khách — đó là
# lý do app đi vòng qua máy chủ chứ không tự gọi Google.
#
# Bỏ chú thích và chuỗi tài liệu trước khi kiểm: `giay_phep.py` có NHẮC TỚI
# client_secret ở phần giải thích vì sao không để nó ở đây, và đó là thứ nên
# giữ lại chứ không phải thứ phải xoá đi cho qua phép kiểm.
def _ma_khong_chu_thich(p: Path) -> str:
    import io as _io
    import tokenize as _tk
    ra = []
    try:
        for t in _tk.generate_tokens(_io.StringIO(
                p.read_text(encoding="utf-8", errors="ignore")).readline):
            if t.type not in (_tk.COMMENT, _tk.STRING, _tk.NL, _tk.NEWLINE):
                ra.append(t.string)
    except Exception:
        return p.read_text(encoding="utf-8", errors="ignore")
    return " ".join(ra).lower()


for _f in sorted(Path(".").glob("*.py")):
    if _f.name == "test_basic.py":
        continue
    check(f"{_f.name}: không nhúng bí mật Google vào mã",
          "client_secret" not in _ma_khong_chu_thich(_f))


# ── Hai nick TRÙNG TÊN, khác c_user: mọi thứ phải phân biệt bằng c_user ─────
# Gặp thật 14/10: hai nick 'Tuấn Ngọc'. Tra theo tên chọn bừa một trong hai —
# phiên comment 12:42 chạy nhầm sang nick kia, "Cookie hết hạn" đánh nhầm nick,
# hai nick thay nhau báo hết cookie; `UPDATE ... WHERE ten_acc=?` ghi đè cả hai.
_TT = "Trùng Tên"
with db._conn() as _c_tt:
    _c_tt.execute("DELETE FROM accounts WHERE ten_acc=?", (_TT,))
    _c_tt.execute("DELETE FROM schedules WHERE ten_acc=?", (_TT,))
    _c_tt.execute("DELETE FROM join_schedules WHERE ten_acc=?", (_TT,))
_tt1 = db.upsert_account({"ten_acc": _TT, "c_user": "900001", "xs": "x1",
                          "trang_thai": "Active"})                      # id nhỏ hơn, không Page
_tt2 = db.upsert_account({"ten_acc": _TT, "c_user": "900002", "xs": "x2",
                          "trang_thai": "Active", "ten_page": "P_TT2",
                          "loai_dang": "Thuê"})
_tt = lambda i: db.get_account_by_id(i)

check("tra theo c_user ra ĐÚNG nick, dù tên trùng",
      db.get_account_by_name(_TT, c_user="900002")["id"] == _tt2
      and db.get_account_by_name(_TT, c_user="900001")["id"] == _tt1)

# Trạng thái chỉ đổi đúng nick được chỉ định — nick kia giữ nguyên.
db.danh_dau_spam(_TT, "thử", c_user="900002")
check("gắn cờ Spam chỉ trúng nick được chỉ định",
      _tt(_tt2)["trang_thai"] == db.TRANG_THAI_SPAM and _tt(_tt1)["trang_thai"] == "Active")
check("nick kia vẫn được chạy bình thường",
      db.acc_duoc_chay(_TT, "dang_bai", c_user="900001") == (True, "")
      and db.acc_duoc_chay(_TT, "dang_bai", c_user="900002")[0] is False)
check("đang nghỉ spam: chỉ nick bị gắn cờ",
      db.acc_dang_spam_nghi(_TT, c_user="900002") and not db.acc_dang_spam_nghi(_TT, c_user="900001"))
db.het_spam(_TT, c_user="900002")
check("thả spam đúng nick", _tt(_tt2)["trang_thai"] == "Active" and not _tt(_tt2)["nghi_den"])
for _ in range(3):
    db.ghi_nhan_phien_dang(_TT, False, ly_do_loi="lỗi thử", c_user="900001")
check("lịch sử phiên ghi đúng nick",
      "x" in (_tt(_tt1)["lich_su_phien"] or "") and not (_tt(_tt2)["lich_su_phien"] or ""))
db.ghi_nhan_nuoi(_TT, c_user="900002")
check("mốc nuôi ghi đúng nick",
      _tt(_tt2)["nuoi_lan_cuoi"] and not _tt(_tt1)["nuoi_lan_cuoi"])
_vp = db.ghi_nhan_vi_pham(_TT, 3, True, da_dang=True, c_user="900002")
check("ghi vi phạm đúng nick", _vp[0] is True and _tt(_tt2)["so_vi_pham"] == 3
      and _tt(_tt1)["so_vi_pham"] != 3)

# Suy c_user cho dòng lịch: tên trùng → thu hẹp theo Page, rồi theo Loại đăng.
with db._conn() as _c_tt:
    check("suy c_user theo Page khi tên trùng", db.tim_c_user(_c_tt, _TT, "P_TT2") == "900002")
    check("suy c_user theo nick có Loại đăng", db.tim_c_user(_c_tt, _TT, "") == "900002")
    _c_tt.execute("INSERT INTO accounts(ten_acc,c_user,trang_thai) VALUES('Tên Riêng TT','900099','Active')")
    check("tên duy nhất → nick đó", db.tim_c_user(_c_tt, "Tên Riêng TT", "") == "900099")
    _c_tt.execute("DELETE FROM accounts WHERE ten_acc='Tên Riêng TT'")

# Dòng lịch mang c_user; đánh X chỉ dòng của đúng nick.
db.replace_schedules("tt_thu", [
    {"loai": "tt_thu", "stt": 1, "ma_content": "c", "ten_acc": _TT, "ten_page": "",
     "gio_dang": "23:58", "ma_nhom": "", "tu_khoa": "", "mode": "Page",
     "trang_thai": "Chờ", "c_user": "900001"},
    {"loai": "tt_thu", "stt": 2, "ma_content": "c", "ten_acc": _TT, "ten_page": "P_TT2",
     "gio_dang": "23:59", "ma_nhom": "", "tu_khoa": "", "mode": "Page",
     "trang_thai": "Chờ"},                                   # thiếu c_user → suy theo Page
])
with db._conn() as _c_tt:
    _dong = {r["stt"]: dict(r) for r in _c_tt.execute(
        "SELECT * FROM schedules WHERE loai='tt_thu'")}
check("dòng lịch giữ c_user được truyền", _dong[1]["c_user"] == "900001")
check("dòng lịch thiếu c_user được suy đúng nick", _dong[2]["c_user"] == "900002")
_n_x = db.danh_dau_x_con_lai_hom_nay(_TT, loai="tt_thu", c_user="900002")
with db._conn() as _c_tt:
    _dong = {r["stt"]: dict(r) for r in _c_tt.execute(
        "SELECT * FROM schedules WHERE loai='tt_thu'")}
check("đánh X chỉ dòng của đúng nick",
      _n_x == 1 and _dong[2]["trang_thai"] == db.TT_LICH_X_TU_DONG and _dong[1]["trang_thai"] == "Chờ")

# Sửa c_user: dòng lịch đi theo.
db.update_account_field(_tt1, "c_user", "900011")
with db._conn() as _c_tt:
    check("sửa c_user → dòng lịch trỏ c_user mới",
          _c_tt.execute("SELECT c_user FROM schedules WHERE loai='tt_thu' AND stt=1")
          .fetchone()[0] == "900011")

# Nâng cấp dữ liệu cũ: dòng chưa có c_user được gắn khi khởi động.
with db._conn() as _c_tt:
    _c_tt.execute("UPDATE schedules SET c_user='' WHERE loai='tt_thu' AND stt=2")
db.init_db()
with db._conn() as _c_tt:
    check("khởi động gắn c_user cho dòng lịch cũ",
          _c_tt.execute("SELECT c_user FROM schedules WHERE loai='tt_thu' AND stt=2")
          .fetchone()[0] == "900002")

# Scheduler: dòng lịch → đúng nick theo c_user, không theo tên.
check("scheduler tra nick của dòng lịch theo c_user",
      scheduler._tk({"ten_acc": _TT, "c_user": "900002", "ten_page": ""})["id"] == _tt2
      and scheduler._tk({"ten_acc": _TT, "c_user": "900011", "ten_page": ""})["id"] == _tt1)
check("scheduler mở profile / dựng cookie bằng c_user của dòng",
      scheduler._c_user_cua({"c_user": "900002"}, {"c_user": "900011"}) == "900002")
_src_sc_tt = Path("scheduler.py").read_text(encoding="utf-8")
check("scheduler không còn gọi hàm trạng thái theo tên trần",
      not _re_ls.search(r"db\.(acc_duoc_chay|acc_dang_spam_nghi|den_gio_nuoi|acc_can_tham_do)"
                        r"\(item\[\"ten_acc\"\](, hd)?\)", _src_sc_tt)
      and "_mark_cookie_dead(acc_name)" not in _src_sc_tt)

# Gen lịch: hai nick trùng tên đều được xếp slot, mỗi dòng mang c_user riêng.
_r_gen = _client.post("/api/schedule/thue/gen", json={
    "start": "08:00", "end": "11:00", "keyword_pool": ["kw"],
    "acc_settings": [
        {"ten": _TT, "c_user": "900011", "page": "P_TT1", "nghi": 30, "luc_dang": 2,
         "c_offset": 0, "first_group_url": "123", "mode": "Page", "contents": ["C1"]},
        {"ten": _TT, "c_user": "900002", "page": "P_TT2", "nghi": 30, "luc_dang": 2,
         "c_offset": 0, "first_group_url": "123", "mode": "Page", "contents": ["C1"]},
    ]}).get_json()
with db._conn() as _c_tt:
    _cu_gen = [r[0] for r in _c_tt.execute(
        "SELECT c_user FROM schedules WHERE loai='thue' AND ten_acc=?", (_TT,))]
check("Gen: hai nick trùng tên KHÔNG bị gộp — cả hai có slot",
      _r_gen.get("ok") and {"900011", "900002"} <= set(_cu_gen))
check("Gen: dòng lịch vẫn hiện tên thật", all(c in ("900011", "900002") for c in _cu_gen))

# Tham gia nhóm: tạo lịch nhanh Market tạo cho CẢ hai nick trùng tên.
with db._conn() as _c_tt:
    _c_tt.execute("DELETE FROM join_schedules WHERE ten_acc=?", (_TT,))
_client.post("/api/join/gen-quick-market", json={})
with db._conn() as _c_tt:
    _cu_join = sorted(r[0] for r in _c_tt.execute(
        "SELECT c_user FROM join_schedules WHERE ten_acc=? AND nguon='MARKET'", (_TT,)))
check("tạo lịch Market: nick thứ hai trùng tên KHÔNG bị bỏ sót",
      _cu_join == ["900002", "900011"])
import join_groups_runner as _jr_tt
_jr_tt._CU = "900002"
check("runner tham gia nhóm dùng c_user của dòng lịch, không tra theo tên",
      _jr_tt._c_user_cua(_TT) == "900002")
_jr_tt._CU = ""
check("dò spam / đồng bộ xs nhận c_user",
      'c_user: str = ""' in Path("fb_common.py").read_text(encoding="utf-8")
      and "_khoa_acc(acc_name, c_user)" in Path("cookie_exporter.py").read_text(encoding="utf-8"))

with db._conn() as _c_tt:
    _c_tt.execute("DELETE FROM accounts WHERE ten_acc=?", (_TT,))
    _c_tt.execute("DELETE FROM schedules WHERE ten_acc=? OR loai='tt_thu'", (_TT,))
    _c_tt.execute("DELETE FROM join_schedules WHERE ten_acc=?", (_TT,))

# ── Nick sống lại (về Active) → slot X😴 còn lại hôm nay tự về 'Chờ' ─────────
# Trước đây sửa xong cookie, nick về Active mà lịch vẫn nằm X😴 tới hết ngày.
_TS = "Song Lai"
with db._conn() as _c_ts:
    _c_ts.execute("DELETE FROM accounts WHERE ten_acc=?", (_TS,))
    _c_ts.execute("DELETE FROM schedules WHERE loai='ts_thu'")
_ts1 = db.upsert_account({"ten_acc": _TS, "c_user": "900201", "xs": "x",
                          "trang_thai": "Cookie hết hạn"})
_ts2 = db.upsert_account({"ten_acc": _TS, "c_user": "900202", "xs": "x",
                          "trang_thai": "Cookie hết hạn"})       # trùng tên, nick khác
_dong_ts = lambda stt, gio, tt, cu: {
    "loai": "ts_thu", "stt": stt, "ma_content": "c", "ten_acc": _TS, "ten_page": "",
    "gio_dang": gio, "ma_nhom": "", "tu_khoa": "", "mode": "Page",
    "trang_thai": tt, "c_user": cu}
db.replace_schedules("ts_thu", [
    _dong_ts(1, "23:58", db.TT_LICH_X_TU_DONG, "900201"),   # tương lai, tự đánh → về Chờ
    _dong_ts(2, "23:59", db.TT_LICH_X_TU_DONG, "900201"),   # tương lai, tự đánh → về Chờ
    _dong_ts(3, "00:00", db.TT_LICH_X_TU_DONG, "900201"),   # đã qua giờ → giữ nguyên
    _dong_ts(4, "23:57", "X",                   "900201"),   # người dùng tắt tay → giữ
    _dong_ts(5, "23:56", db.TT_LICH_X_TU_DONG, "900202"),   # nick kia → giữ
])
_n_ts = db.update_account_field(_ts1, "trang_thai", "Active")
with db._conn() as _c_ts:
    _tt_ts = {r["stt"]: r["trang_thai"] for r in _c_ts.execute(
        "SELECT stt, trang_thai FROM schedules WHERE loai='ts_thu'")}
check("về Active: slot X😴 tương lai của đúng nick về Chờ",
      _n_ts == 2 and _tt_ts[1] == "Chờ" and _tt_ts[2] == "Chờ")
check("slot đã qua giờ KHÔNG chạy bù", _tt_ts[3] == db.TT_LICH_X_TU_DONG)
check("slot người dùng tắt tay (X) giữ nguyên", _tt_ts[4] == "X")
check("nick trùng tên khác KHÔNG bị đụng", _tt_ts[5] == db.TT_LICH_X_TU_DONG)
check("Active → Active không trả gì thêm",
      db.update_account_field(_ts1, "trang_thai", "Active") == 0)

# Dán xs mới cho nick "Cookie hết hạn" → server tự thử ở nền.
import time as _time_ts
import cookie_exporter as _ce_ts
_thu_that = _ce_ts.thu_cookie
def _cho_ts(dk, giay=5):
    for _ in range(int(giay / 0.1)):
        if dk():
            return True
        _time_ts.sleep(0.1)
    return False
try:
    _ce_ts.thu_cookie = lambda *a, **k: (True, "Cookie còn dùng được")
    _r_ts = _client.post(f"/api/accounts/{_ts2}/field",
                         json={"field": "xs", "value": "xs_moi"}).get_json()
    check("dán xs cho nick hết cookie → tự thử ở nền", _r_ts.get("dang_thu") is True)
    check("thử được → nick tự về Active",
          _cho_ts(lambda: db.get_account_by_id(_ts2)["trang_thai"] == "Active"))
    with db._conn() as _c_ts:
        check("… kéo theo slot X😴 tương lai của nick đó về Chờ",
              _cho_ts(lambda: _c_ts.execute("SELECT trang_thai FROM schedules "
                                            "WHERE loai='ts_thu' AND stt=5").fetchone()[0] == "Chờ"))
    check("… và báo kết quả qua kênh cảnh báo",
          _cho_ts(lambda: "dùng được" in (db.get_account_by_id(_ts2)["canh_bao_moi"] or "")))

    db.update_account_field(_ts2, "trang_thai", "Cookie hết hạn")
    _ce_ts.thu_cookie = lambda *a, **k: (False, "Facebook không nhận cookie — cần lấy xs mới")
    _client.post(f"/api/accounts/{_ts2}/field", json={"field": "xs", "value": "xs_hong"})
    check("thử hỏng → báo lý do",
          _cho_ts(lambda: "chưa dùng được" in (db.get_account_by_id(_ts2)["canh_bao_moi"] or "")))
    check("thử hỏng → giữ nguyên Cookie hết hạn",
          db.get_account_by_id(_ts2)["trang_thai"] == "Cookie hết hạn")

    _r_ts = _client.post(f"/api/accounts/{_ts1}/field",
                         json={"field": "xs", "value": "xs_khac"}).get_json()
    check("nick đang Active thì dán xs KHÔNG tự thử", _r_ts.get("dang_thu") is False)
    _r_ts = _client.post(f"/api/accounts/{_ts2}/field",
                         json={"field": "ghi_chu", "value": "abc"}).get_json()
    check("sửa ô khác xs KHÔNG tự thử", _r_ts.get("dang_thu") is False)
finally:
    _ce_ts.thu_cookie = _thu_that
_cho_ts(lambda: not server._DANG_THU_XS)
with db._conn() as _c_ts:
    _c_ts.execute("DELETE FROM accounts WHERE ten_acc=?", (_TS,))
    _c_ts.execute("DELETE FROM schedules WHERE loai='ts_thu'")

# ── Từ khoá XEN KẼ theo thời gian, mỗi nick quay đều ─────────────────────────
# Bản cũ chia theo nick: 11 nick, 4 từ khoá → ba nick liền nhau chung một từ
# khoá, bảng lịch thành cụm 3 dòng trùng nhau (người dùng thấy 13/10).
from xep_lich import rai_tu_khoa as _rtk, phan_bo_lich as _pbl
_KW = ["Chợ cư dân", "Cộng", "Làng", "times city & park hill"]
for _so in (11, 8, 4):          # 8 nick / 4 từ khoá: ca dễ dính cố định một từ khoá
    _moc = _pbl([{"ten": f"N{i}", "nghi": 12} for i in range(_so)], 5 * 60, 25 * 60)
    _dong = [{"ten_acc": t} for _, t in _moc]
    _rtk(_dong, _KW)
    check(f"{_so} nick: hai dòng liền nhau KHÔNG trùng từ khoá",
          all(a["tu_khoa"] != b["tu_khoa"] for a, b in zip(_dong, _dong[1:])))
    _theo = {}
    for r in _dong:
        _theo.setdefault(r["ten_acc"], []).append(r["tu_khoa"])
    check(f"{_so} nick: mỗi nick quay ĐỀU đủ các từ khoá (lệch ≤ 1)",
          all(max(v.count(k) for k in _KW) - min(v.count(k) for k in _KW) <= 1
              for v in _theo.values()))
    check(f"{_so} nick: tổng mỗi từ khoá đều nhau (lệch ≤ 1)",
          max(sum(r["tu_khoa"] == k for r in _dong) for k in _KW)
          - min(sum(r["tu_khoa"] == k for r in _dong) for k in _KW) <= 1)
_dong = [{"ten_acc": "A", "mode": "Page"}, {"ten_acc": "B", "mode": "Khac"},
         {"ten_acc": "C", "mode": "Page"}]
_rtk(_dong, _KW, can=lambda r: r["mode"] in ("Via", "Page"))
check("dòng không cần từ khoá để trống, không làm lệch vòng",
      _dong[1]["tu_khoa"] == "" and _dong[0]["tu_khoa"] == "Chợ cư dân"
      and _dong[2]["tu_khoa"] == "Cộng")
_d1 = [{"ten_acc": "A"}]; _rtk(_d1, [])
check("không có từ khoá → không gán gì", "tu_khoa" not in _d1[0])
check("Gen lịch dùng cách chia mới, bỏ con trỏ theo nick",
      "rai_tu_khoa(schedule, keyword_pool" in Path("server.py").read_text(encoding="utf-8")
      and "keyword_cursor" not in Path("server.py").read_text(encoding="utf-8"))

# ── Content TRẢI ĐỀU + XEN KẼ (xep_lich.rai_content) ──────────────────────────
# Bản cũ mỗi nick một con trỏ riêng từ ô "Content đầu": lịch Bán thật (11 nick,
# 2 content) có 79% cặp dòng liền nhau trùng content, cụm dài tới 9 dòng.
import itertools as _it_ct
from xep_lich import rai_content as _rct, _hien_content as _hct, chuyen_slot_so_luong as _csl
def _lich_ct(so_nick, n_ct, seed=0):
    _m = _pbl([{"ten": f"N{i}", "nghi": (10, 12, 15)[(i + seed) % 3]} for i in range(so_nick)],
              5 * 60, 25 * 60)
    _ds = [{"ten_acc": t} for _, t in _m]
    _tg = {}
    for r in _ds: _tg[r["ten_acc"]] = _tg.get(r["ten_acc"], 0) + 1
    _csl(_ds, {k: round(v * .25) for k, v in _tg.items()}, "comment")   # chen dòng comment
    _CT = [f"C{i}" for i in range(n_ct)]
    _rct(_ds, _CT)
    _vis = [r for r in _ds if _hct(r)]
    _theo = {}
    for r in _vis: _theo.setdefault(r["ten_acc"], []).append(r["ma_content"])
    return _ds, _vis, _theo, _CT
for _so, _nct in ((11, 4), (8, 4), (5, 6), (3, 17), (11, 5)):
    _ds, _vis, _theo, _CT = _lich_ct(_so, _nct)
    check(f"{_so} nick / {_nct} content: hai dòng đăng liền nhau gần như không trùng (≤ 0,5%)",
          sum(a["ma_content"] == b["ma_content"] for a, b in zip(_vis, _vis[1:]))
          <= len(_vis) * .005)
    check(f"{_so} nick / {_nct} content: nick không đăng lại content vừa đăng",
          all(a != b for v in _theo.values() for a, b in zip(v, v[1:])))
    check(f"{_so} nick / {_nct} content: mỗi nick quay đều đủ content (lệch ≤ 2)",
          all(max(v.count(c) for c in _CT) - min(v.count(c) for c in _CT) <= 2
              for v in _theo.values()))
    check(f"{_so} nick / {_nct} content: cả bảng mỗi content đăng ngang nhau (lệch ≤ 3)",
          max(sum(r["ma_content"] == c for r in _vis) for c in _CT)
          - min(sum(r["ma_content"] == c for r in _vis) for c in _CT) <= 3)
# 2–3 content: không thể vừa xen kẽ hoàn hảo vừa để mỗi nick đổi content —
# nhưng KHÔNG nick nào được đăng một content cả ngày (lỗi của cách ưu tiên
# tuyệt đối "liền nhau khác nhau": 8 nick / 2 content → có nick lệch 76 lần).
for _so, _nct in ((11, 2), (8, 2), (5, 2), (3, 2), (8, 3), (3, 3)):
    _ds, _vis, _theo, _CT = _lich_ct(_so, _nct)
    _cum = max(len(list(g)) for _, g in _it_ct.groupby(r["ma_content"] for r in _vis))
    _tr = sum(a["ma_content"] == b["ma_content"] for a, b in zip(_vis, _vis[1:])) / len(_vis)
    check(f"{_so} nick / {_nct} content: mỗi nick vẫn đều content (lệch ≤ 2), "
          f"không lặp quá 3 lần liền",
          all(max(v.count(c) for c in _CT) - min(v.count(c) for c in _CT) <= 2
              and max(len(list(g)) for _, g in _it_ct.groupby(v)) <= 3
              for v in _theo.values()))
    check(f"{_so} nick / {_nct} content: trùng liền nhau ít (<{30 if _nct == 2 else 5}%), "
          f"cụm ≤ {5 if _nct == 2 else 3} dòng (bản cũ: 79%, cụm 9)",
          _tr < (.30 if _nct == 2 else .05) and _cum <= (5 if _nct == 2 else 3))
_ds = [{"ten_acc": "A"}, {"ten_acc": "B", "hoat_dong": "comment"},
       {"ten_acc": "B", "hoat_dong": "nuoi_nick"}, {"ten_acc": "C"}]
_rct(_ds, ["X", "Y"])
check("dòng comment/nuôi nằm giữa KHÔNG làm lệch vòng — hai dòng đăng hai bên vẫn khác nhau",
      _ds[0]["ma_content"] != _ds[3]["ma_content"])
check("dòng comment vẫn có content (để còn thành phiên nhử đăng bài)",
      _ds[1]["ma_content"] in ("X", "Y"))
_ds = [{"ten_acc": "A"}]; _rct(_ds, [])
check("không có content → không gán gì", "ma_content" not in _ds[0])
_src_gen_ct = Path("server.py").read_text(encoding="utf-8")
check("Gen lịch rải content SAU khi chuyển slot, bỏ con trỏ theo nick",
      "rai_content(schedule, contents)" in _src_gen_ct and "content_cursor" not in _src_gen_ct
      and _src_gen_ct.index("rai_content(schedule, contents)")
          > _src_gen_ct.index('chuyen_slot_so_luong(schedule, han_mkt, "marketplace")'))

# ── Đăng tường Page = phiên 'dang_page' lồng trong lịch mảng ──────────────────
# GIỮ NGUYÊN phiên nuôi; chỉ đổi slot ĐĂNG BÀI sang 'dang_page' (random, rải
# đều — dùng lại chuyen_slot_so_luong như comment/marketplace). Runner Page
# riêng đã bỏ; content của bài page lấy theo Loại đăng của chính acc.
from collections import Counter as _Cnt_dp
check("_hien_content tính 'dang_page' là dòng CÓ content (được gán ma_content)",
      _hct({"hoat_dong": "dang_page"}) is True)
_dp = ([{"ten_acc": "A", "hoat_dong": "nuoi_nick"} for _ in range(4)]
       + [{"ten_acc": "A", "hoat_dong": "dang_bai"} for _ in range(8)])
_n_dp = _csl(_dp, {"A": 3}, "dang_page")
_cc_dp = _Cnt_dp(r["hoat_dong"] for r in _dp)
check("Gen page: đổi đúng N slot đăng bài sang dang_page", _n_dp == 3 and _cc_dp["dang_page"] == 3)
check("Gen page: GIỮ NGUYÊN mọi phiên nuôi", _cc_dp["nuoi_nick"] == 4)
check("Gen page: chỉ lấy từ slot đăng bài (8 − 3 = 5 còn lại)", _cc_dp["dang_bai"] == 5)
_dp2 = ([{"ten_acc": "B", "hoat_dong": "nuoi_nick"} for _ in range(3)]
        + [{"ten_acc": "B", "hoat_dong": "dang_bai"} for _ in range(2)])
check("Gen page: thiếu slot đăng bài thì tự cắt, nuôi vẫn nguyên",
      _csl(_dp2, {"B": 5}, "dang_page") == 2
      and _Cnt_dp(r["hoat_dong"] for r in _dp2)["nuoi_nick"] == 3)
check("Gen gọi chuyển slot dang_page TRƯỚC comment/marketplace (chỉ tiêu page là số cứng)",
      'chuyen_slot_so_luong(schedule, han_page, "dang_page")' in _src_gen_ct
      and _src_gen_ct.index('han_page, "dang_page"')
          < _src_gen_ct.index('han_cmt, "comment"'))
# scheduler: dispatcher route 'dang_page' → _run_page_slot (post_page_wall + page_uid của acc).
_src_sc_dp = Path("scheduler.py").read_text(encoding="utf-8")
_than_dp = _src_sc_dp.split("def _run_page_slot")[1].split("\ndef ")[0] if "def _run_page_slot" in _src_sc_dp else ""
check("scheduler route 'dang_page' sang _run_page_slot",
      'if hd == "dang_page":' in _src_sc_dp and "_run_page_slot(item)" in _src_sc_dp)
check("_run_page_slot đăng tường bằng post_page_wall + page_uid của acc",
      "post_page_wall(" in _than_dp and 'acc_data.get("page_uid")' in _than_dp)
check("bỏ nhánh runner Page riêng (LOAI=='page') trong scheduler",
      'if LOAI == "page":' not in _src_sc_dp)
# acc nối page theo UID: chọn page_uid thì ten_page tự đồng bộ (server lo).
_pid_dp = db.upsert_page({"ten_page": "Page Z UID", "page_uid": "PZUID9", "bai_dang_toi_da": 2})
_aid_dp = db.upsert_account({"ten_acc": "AccPageUidTest", "loai_dang": "homestay"})
db.update_account_field(_aid_dp, "page_uid", "PZUID9")
_arow = [a for a in db.get_accounts() if a["id"] == _aid_dp][0]
check("chọn page_uid thì ten_page đồng bộ theo page",
      _arow["page_uid"] == "PZUID9" and _arow["ten_page"] == "Page Z UID")
db.update_account_field(_aid_dp, "page_uid", "")
_arow = [a for a in db.get_accounts() if a["id"] == _aid_dp][0]
check("bỏ page_uid thì ten_page về rỗng",
      (_arow["page_uid"] or "") == "" and (_arow["ten_page"] or "") == "")
check("get_page_by_uid trả đúng page theo UID",
      (db.get_page_by_uid("PZUID9") or {}).get("ten_page") == "Page Z UID")
check("form Gen bỏ ô \"Content đầu\" của từng acc",
      "acc-c-" not in Path("static/js/app.js").read_text(encoding="utf-8"))
_r_gct = _client.post("/api/schedule/homestay/gen", json={
    "start": "08:00", "end": "14:00", "keyword_pool": ["kw"],
    "acc_settings": [
        {"ten": f"GenCT{i}", "c_user": f"77700{i}", "page": "", "nghi": 15, "luc_dang": 4,
         "first_group_url": "123", "mode": "Page", "contents": ["H1", "H2", "H3", "H4"]}
        for i in range(3)]}).get_json()
with db._conn() as _c_gct:
    _ma_gct = [r[0] for r in _c_gct.execute(
        "SELECT ma_content FROM schedules WHERE loai='homestay' ORDER BY stt")]
check("Gen (API): content xen kẽ — hai dòng liền nhau không trùng, đủ 4 content",
      _r_gct.get("ok") and len(_ma_gct) > 8 and set(_ma_gct) == {"H1", "H2", "H3", "H4"}
      and all(a != b for a, b in zip(_ma_gct, _ma_gct[1:])))

# ── Xoá mảng content: mảng nào cũng xoá được, LUÔN CÒN ÍT NHẤT 1 ─────────────
_reg_cu = db.get_setting("loai_content_ds", "")
_ds0 = db.loai_content_ds()
_bat = lambda ds: [d["key"] for d in ds if d["bat"]]
_moi = [dict(d, bat=0) if d["key"] == "homestay" else dict(d) for d in _ds0]
check("xoá được mảng gốc (Homestay)", "homestay" not in _bat(db.luu_loai_content(_moi)))
check("mảng đã xoá không còn là Loại đăng hợp lệ", "homestay" not in db.loai_dang_options())
_tat_het = [dict(d, bat=0) for d in _ds0]
try:
    db.luu_loai_content(_tat_het); _chan_het = False
except ValueError as _e_m:
    _chan_het = "ít nhất 1" in str(_e_m)
check("xoá hết mọi mảng bị CHẶN", _chan_het)
_mot = [dict(d, bat=1 if d["key"] == "ban" else 0) for d in _ds0]
check("còn đúng 1 mảng vẫn lưu được", _bat(db.luu_loai_content(_mot)) == ["ban"])
db.set_setting("loai_content_ds", '[{"key":"homestay","bat":0},{"key":"thue","bat":0},{"key":"ban","bat":0}]')
check("registry hỏng (tắt hết) vẫn còn 1 mảng chạy được", len(db.loai_content_bat()) == 1)
for _ds_loi, _chu in (
        ([dict(d, nhan="Times City", bat=1) if d["key"] in ("thue", "ban") else dict(d) for d in _ds0], "trùng tên"),
        ([dict(d, nhan="x" * 31) if d["key"] == "thue" else dict(d) for d in _ds0], "tối đa"),
        ([dict(d, nhan="", bat=1) if d["key"] == "loai4" else dict(d) for d in _ds0], "phải đặt tên")):
    try:
        db.luu_loai_content(_ds_loi); _chan_ten = False
    except ValueError as _e_m:
        _chan_ten = _chu in str(_e_m)
    check(f"tên mảng không hợp lệ bị chặn ({_chu})", _chan_ten)
_trung_hoa = [dict(d, nhan="BÁN") if d["key"] == "thue" else dict(d) for d in _ds0]
try:
    db.luu_loai_content(_trung_hoa); _chan_hoa = False
except ValueError:
    _chan_hoa = True
check("trùng tên không phân biệt hoa thường cũng bị chặn", _chan_hoa)

db.luu_loai_content(_ds0)
_tk_m = db.thong_ke_loai_content()
check("thống kê mảng có đủ 5 slot, đếm content + nick",
      set(_tk_m) == {"homestay", "thue", "ban", "loai4", "loai5"}
      and all({"so_content", "so_acc"} <= set(v) for v in _tk_m.values()))
_r_m = _client.get("/api/loai-content").get_json()
check("API mảng trả kèm thống kê + giới hạn tên", "tk" in _r_m and _r_m.get("ten_toi_da") == 30)
_r_m = _client.post("/api/loai-content/luu", json={"ds": _tat_het})
check("API chặn xoá mảng cuối cùng, báo rõ lý do",
      _r_m.status_code == 400 and "ít nhất 1" in (_r_m.get_json() or {}).get("error", ""))
_client.post("/api/loai-content/luu", json={"ds": _moi})          # xoá Homestay
_r_m = _client.post("/api/run/homestay/start", json={}).get_json()
check("không khởi động được runner của mảng gốc đã xoá",
      _r_m.get("ok") is False and "đã bị xoá" in (_r_m.get("error") or ""))
_src_srv_m = Path("server.py").read_text(encoding="utf-8")
check("xoá mảng thì dừng runner đang chạy của nó",
      "run_stop(k)" in _src_srv_m and "truoc - {d[\"key\"] for d in moi if d[\"bat\"]}" in _src_srv_m)
import lich_may as _lm_m
check("Lịch máy dừng/bật được runner của cả 5 mảng + nuôi (không còn page)",
      {"homestay", "thue", "ban", "loai4", "loai5", "nuoi"} <= set(_lm_m.RUNNER)
      and "page" not in _lm_m.RUNNER)
_ajs_m = Path("static/js/app.js").read_text(encoding="utf-8")
# Thư viện ảnh: tới 8 ảnh một hàng — bản đầu khung 140px nên ảnh thứ 4 đã xuống dòng.
_khoi_tvb = _ajs_m[_ajs_m.index("async function tvLoadBang"):][:6000]
check("Thư viện ảnh: hiện tới 8 ảnh trên một hàng (không xuống dòng ở ảnh thứ 4)",
      "imgs.slice(0,8)" in _khoi_tvb and "max-width:324px" in _khoi_tvb
      and "imgs.slice(0,4)" not in _khoi_tvb and "+${imgs.length-8}" in _khoi_tvb)
check("tab Thư viện ảnh kéo thả được (draggable + lưu qua /api/thuvien/mang/reorder)",
      'ondrop="tvTabTha(event,${m.id})"' in _ajs_m and "/api/thuvien/mang/reorder" in _ajs_m)
check("bảng lịch tô màu bộ ảnh theo nhãn mới (không dò chữ 'Bộ ảnh' cứng)",
      '_laBo=!!_ma && _ma!=="Ảnh"' in _ajs_m and '_ma.startsWith("Bộ ảnh")' not in _ajs_m)
_khoi_mang = _ajs_m[_ajs_m.index("function renderContentTabs"):_ajs_m.index("async function _luuLoai")]
check("quản lý mảng dùng hộp thoại của app, KHÔNG dùng prompt/confirm trình duyệt",
      "Dialog.prompt(" in _khoi_mang and "Dialog.confirm(" in _khoi_mang
      and not _re_ls.search(r"(?<![.\w])(prompt|confirm)\(", _khoi_mang))
check("mảng nào cũng có nút xoá, trừ khi chỉ còn 1",
      "xoaLoai(" in _khoi_mang and "conMot" in _khoi_mang
      and '["homestay","thue","ban"].includes' not in _khoi_mang)
check("ô tick runner của Lịch máy dựng theo các mảng đang có",
      "function _lmRunner()" in _ajs_m and "LM_RUNNER" not in _ajs_m)
# Tab Log: ô log của mảng dựng theo registry — xoá mảng là mất ô, đổi tên là đổi nhãn.
_html_m = Path("templates/index.html").read_text(encoding="utf-8")
_trang_log = _html_m[_html_m.index('id="page-logs"'):]
check("tab Log không ghi cứng ô log của mảng content",
      'id="log-mang"' in _trang_log
      and not any(f'id="log-{k}"' in _trang_log for k in ("homestay", "thue", "ban", "loai4", "loai5"))
      and 'id="log-page"' not in _trang_log   # runner Page riêng đã bỏ (15/10)
      and all(f'id="log-{k}"' in _trang_log for k in ("nuoi", "join")))
_khoi_log = _ajs_m[_ajs_m.index("function renderLogMang"):_ajs_m.index("// Join log")]
check("ô log + danh sách đọc log theo các mảng đang bật",
      "_loaiBat()" in _khoi_log and '"homestay","thue","ban"' not in _khoi_log
      and "renderLogMang();" in _ajs_m[_ajs_m.index("function apDungLoai"):_ajs_m.index("let _currentContentLoai")])
for _k_log in ("loai4", "loai5", "nuoi"):
    check(f"API log đọc được runner {_k_log}",
          _client.get(f"/api/logs/{_k_log}?n=5").get_json().get("ok") is True)
# Runner 'page' riêng đã bỏ → /api/logs/page bị từ chối như loại lạ.
check("API log KHÔNG còn runner page",
      _client.get("/api/logs/page?n=5").get_json().get("ok") is False)
check("API log vẫn từ chối loại lạ",
      _client.get("/api/logs/khong-co?n=5").get_json().get("ok") is False)
# Tab Link comment: tab + thư viện câu theo mảng đang bật, không ghi cứng 3 mảng gốc.
_khoi_cmt = _ajs_m[_ajs_m.index("// ── Link comment"):_ajs_m.index("// ── Cài đặt nuôi nick")]
check("tab Link comment dựng tab theo các mảng đang bật",
      "function _cmtLoaiDS()" in _khoi_cmt and "_loaiBat()" in _khoi_cmt
      and "CMT_LOAI" not in _ajs_m and '["homestay","🏠 Homestay"]' not in _khoi_cmt
      and 'pool("homestay"' not in _khoi_cmt)
check("mảng đang chọn ở tab Link comment bị xoá thì tự về mảng đầu tiên",
      "if(!ds.some(([k])=>k===_cmtLoai)) _cmtLoai" in _khoi_cmt)
check("đổi tên tab \"Bài đi Comment\" thành \"Link comment\"",
      "Link comment</div>" in _html_m and "Bài đi Comment" not in _html_m
      and '"comment-posts":"Link comment"' in _ajs_m and "Bài đi Comment" not in _ajs_m)
import comment_bai as _cb_m
db.set_setting("loai_content_ds", '[{"key":"loai4","nhan":"Đất","bat":1}]')
db.set_setting("comment_pool_loai4", "Còn lô nào không ạ")
check("phiên comment đọc được thư viện câu của mảng thêm mới (loai4)",
      _cb_m.cai_dat().get("pool_loai4") == "Còn lô nào không ạ")
db.set_setting("comment_pool_loai4", "")
db.set_setting("loai_content_ds", _reg_cu)

# ── Dừng runner: báo đúng kết quả + dọn dòng kẹt "đang chạy" ─────────────────
# 16/10: cả 3 lần Dừng (01:00, 09:42, 10:01) đều báo "KHÔNG thành công — PID None
# vẫn chạy" dù runner đã chết — Windows nhả khoá chậm hơn lúc tiến trình chết một
# nhịp. Và lịch Bán kẹt 4 dòng "🔄 Đang chạy" + 2 dòng "🌱 Đang nuôi" cả ngày.
_TT_KET = {
    "🔄 Đang chạy 09:58":            "⏹ Dừng giữa chừng 09:58",
    "🔄 Thử lại 2/3 sau 30s":        "⏹ Dừng giữa chừng",
    "🌱 Đang nuôi 09:41 (spam)":     "⏹ Dừng giữa chừng 09:41",
    "💬 Đang comment 10:05":         "⏹ Dừng giữa chừng 10:05",
    "💬 3/9 · 10:12":                "⏹ Dừng giữa chừng 10:12",
    "🛒 Đang đăng Marketplace 10:20": "⏹ Dừng giữa chừng 10:20",
    # Trạng thái đã XONG — không được đụng vào
    "✅ 10:30 (9 nhóm)":             None,
    "💬 10:40 · 9/9 bài":            None,
    "💬 10:41 bỏ qua: danh sách trống": None,
    "🌱 10:23 (đã nuôi)":            None,
    "❌ 10:50 Cookie hết hạn":        None,
    "Chờ":                           None,
    "X😴":                           None,
}
db.replace_schedules("loai5", [
    {"loai": "loai5", "stt": i + 1, "ma_content": "C1", "ten_acc": "KetA", "ten_page": "",
     "gio_dang": "10:00", "ma_nhom": "1", "tu_khoa": "", "mode": "Page", "trang_thai": tt,
     "c_user": "880001"} for i, tt in enumerate(_TT_KET)])
def _tt_loai5():
    with db._conn() as _c:
        return [r[0] for r in _c.execute(
            "SELECT trang_thai FROM schedules WHERE loai='loai5' ORDER BY stt")]
_n_ket = db.don_dong_dang_chay("loai5")
_sau_ket = _tt_loai5()
check("dọn đúng mọi trạng thái đang làm dở → '⏹ Dừng giữa chừng HH:MM'",
      _n_ket == 6 and all(_sau_ket[i] == (moi or cu)
                          for i, (cu, moi) in enumerate(_TT_KET.items())))
check("dòng đã xong (✅/❌/💬 xong/🌱 đã nuôi/Chờ/X😴) giữ nguyên",
      all(_sau_ket[i] == cu for i, (cu, moi) in enumerate(_TT_KET.items()) if moi is None))
check("reset đầu ngày đưa '⏹ Dừng giữa chừng' về Chờ như mọi dòng khác",
      db.reset_schedules_to_wait("loai5") > 0
      and all(t in ("Chờ", "X") or t == "X😴" for t in _tt_loai5()) and
      _tt_loai5()[0] == "Chờ")

import khoa_runner as _kr_st
_goc_st = (_kr_st.dang_giu, _kr_st.pid_dang_giu, server._kill_pids,
           server._runner_pid, server._CHO_NHA_KHOA_GIAY)
_dem_hoi = {"n": 0}
def _khoa_nha_cham(loai):                 # khoá còn "giữ" 3 lần hỏi đầu rồi mới nhả
    _dem_hoi["n"] += 1
    return _dem_hoi["n"] <= 3
try:
    db.replace_schedules("loai5", [
        {"loai": "loai5", "stt": 1, "ma_content": "C1", "ten_acc": "KetA", "ten_page": "",
         "gio_dang": "10:00", "ma_nhom": "1", "tu_khoa": "", "mode": "Page",
         "trang_thai": "🔄 Đang chạy 10:00", "c_user": "880001"}])
    _kr_st.dang_giu = _khoa_nha_cham
    _kr_st.pid_dang_giu = lambda loai: 4321 if _dem_hoi["n"] < 1 else None
    server._kill_pids = lambda pids, *a, **k: list(pids)
    server._runner_pid = lambda loai: None
    server._CHO_NHA_KHOA_GIAY = 3
    _r_st = _client.post("/api/run/loai5/stop").get_json()
    check("Dừng: khoá nhả chậm vài nhịp vẫn báo THÀNH CÔNG (không còn báo sai)",
          _r_st.get("ok") is True and _dem_hoi["n"] > 3)
    check("Dừng thành công thì dòng đang chạy dở thành '⏹ Dừng giữa chừng'",
          _tt_loai5() == ["⏹ Dừng giữa chừng 10:00"])
    _kr_st.dang_giu = lambda loai: True            # khoá KHÔNG bao giờ nhả
    _kr_st.pid_dang_giu = lambda loai: 4321
    server._CHO_NHA_KHOA_GIAY = 0.3
    db.update_schedule_status(db._conn().execute(
        "SELECT id FROM schedules WHERE loai='loai5'").fetchone()[0], "🔄 Đang chạy 10:00")
    _r_st = _client.post("/api/run/loai5/stop").get_json()
    check("Dừng: runner thật sự còn sống thì vẫn báo KHÔNG dừng được",
          _r_st.get("ok") is False and "4321" in (_r_st.get("error") or ""))
    check("Dừng hỏng thì KHÔNG đụng vào dòng đang chạy (runner còn đang làm nó)",
          _tt_loai5() == ["🔄 Đang chạy 10:00"])
finally:
    (_kr_st.dang_giu, _kr_st.pid_dang_giu, server._kill_pids,
     server._runner_pid, server._CHO_NHA_KHOA_GIAY) = _goc_st
db.replace_schedules("loai5", [])
_src_sch_st = Path("scheduler.py").read_text(encoding="utf-8")
check("runner vừa giành khoá thì dọn dòng kẹt từ lần bị diệt trước (RESTART/tắt máy)",
      "db.don_dong_dang_chay(LOAI)" in _src_sch_st
      and _src_sch_st.index("khoa_runner.giu_khoa(LOAI)")
          < _src_sch_st.index("db.don_dong_dang_chay(LOAI)")
          < _src_sch_st.index("while True:", _src_sch_st.index("def main(")))
import dung_het as _dh_st
check("RESTART/UPDATE dừng đủ 6 runner — khớp server và Lịch máy",
      set(_dh_st.RUNNER) == set(server._RUNNER_KEYS) == set(_lm_m.RUNNER)
      and "page" not in _dh_st.RUNNER)   # runner Page riêng đã bỏ (15/10)

# ── Thư viện ảnh: tab "Bộ ảnh" (tv_mang) + dòng ảnh (tv_bo) ──────────────────
# Trang quản lý thư viện ảnh — na ná tab Content nhưng độc lập. Bước 1 mới chỉ
# dựng chỗ CHỨA ảnh (chưa nối vào luồng đăng).
with db._conn() as _c_tv:
    _bang_tv = {r[0] for r in _c_tv.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
check("init_db tạo bảng tv_mang + tv_bo + tv_con_tro",
      {"tv_mang", "tv_bo", "tv_con_tro"} <= _bang_tv)

# DB: tab (mang) CRUD + giữ thứ tự.
_m1 = db.tv_mang_them("3PN")
_m2 = db.tv_mang_them("Duplex")
check("thêm tab bộ ảnh, có id", isinstance(_m1, int) and _m1 > 0)
check("list tab giữ đúng thứ tự thêm",
      [m["ten"] for m in db.tv_mang_list()] == ["3PN", "Duplex"])
db.tv_mang_doi_ten(_m2, "Đập thông")
check("đổi tên tab", any(m["id"] == _m2 and m["ten"] == "Đập thông" for m in db.tv_mang_list()))

# DB: dòng ảnh (bo) CRUD, giữ đúng tab, thứ tự xuống cuối, reorder.
_b1 = db.tv_bo_upsert({"mang_id": _m1, "ma": "bo1", "link_anh": "/media/thuvien/a.jpg", "su_dung": "Có"})
_b2 = db.tv_bo_upsert({"mang_id": _m1, "ma": "bo2", "su_dung": "Có"})
db.tv_bo_upsert({"mang_id": _m2, "ma": "x", "su_dung": "Không"})
check("dòng ảnh lọc đúng theo tab",
      [b["ma"] for b in db.tv_bo_list(_m1)] == ["bo1", "bo2"]
      and [b["ma"] for b in db.tv_bo_list(_m2)] == ["x"])
db.tv_bo_reorder([_b2, _b1])
check("reorder đổi đúng thứ tự dòng ảnh",
      [b["ma"] for b in db.tv_bo_list(_m1)] == ["bo2", "bo1"])
db.tv_bo_update_field(_b1, "su_dung", "Không")
check("sửa nhanh field dòng ảnh",
      any(b["id"] == _b1 and b["su_dung"] == "Không" for b in db.tv_bo_list(_m1)))
_loi_field = False
try:
    db.tv_bo_update_field(_b1, "mang_id", 999)   # field lạ → chặn
except ValueError:
    _loi_field = True
check("sửa nhanh chặn field không hợp lệ", _loi_field)
db.tv_bo_xoa(_b1)
check("xoá dòng ảnh", all(b["id"] != _b1 for b in db.tv_bo_list(_m1)))
db.tv_mang_xoa(_m2)
check("xoá tab thì xoá luôn dòng ảnh bên trong",
      all(m["id"] != _m2 for m in db.tv_mang_list()) and db.tv_bo_list(_m2) == [])

# API: endpoint hoạt động qua test client (dùng DB tạm).
check("API thêm tab bộ ảnh",
      _client.post("/api/thuvien/mang/them", json={"ten": "2PN"}).get_json().get("ok") is True)
check("API chặn tab trùng tên",
      _client.post("/api/thuvien/mang/them", json={"ten": "2pn"}).get_json().get("ok") is False)
_js_mang = _client.get("/api/thuvien/mang").get_json()
_mid_api = [m["id"] for m in _js_mang["data"] if m["ten"] == "2PN"][0]
check("API lưu + đọc dòng ảnh",
      _client.post("/api/thuvien/bo/luu",
                   json={"mang_id": _mid_api, "ma": "api1", "link_anh": "/media/thuvien/z.jpg"}).get_json().get("ok") is True
      and any(b["ma"] == "api1" for b in _client.get(f"/api/thuvien/bo?mang_id={_mid_api}").get_json()["data"]))
check("API chặn lưu dòng ảnh thiếu tab",
      _client.post("/api/thuvien/bo/luu", json={"ma": "mo_coi"}).get_json().get("ok") is False)

# UI: nav + trang + cột bảng + hàm JS.
_html_tv = Path("templates/index.html").read_text(encoding="utf-8")
_ajs_tv = Path("static/js/app.js").read_text(encoding="utf-8")
check("sidebar có mục Thư viện ảnh, ngay dưới UID Marketplace",
      _html_tv.index('data-page="uid-market"') < _html_tv.index('data-page="thu-vien"')
      < _html_tv.index('nav-section">Lịch đăng'))
check("có trang Thư viện ảnh + đủ 6 cột bảng",
      'id="page-thu-vien"' in _html_tv and 'id="tv-table"' in _html_tv
      and ">Mã bộ ảnh<" in _html_tv)
check("app.js có hàm loadThuVien + CRUD tab/dòng ảnh",
      "function loadThuVien" in _ajs_tv and "function tvThemMang" in _ajs_tv
      and "function tvOpenEdit" in _ajs_tv)
check("mở trang thu-vien thì nạp dữ liệu",
      'page==="thu-vien"' in _ajs_tv and "loadThuVien()" in _ajs_tv)
# Ảnh thư viện tách khỏi CONTENT_MEDIA_DIRS để dọn-ảnh-mồ-côi không xoá nhầm.
check("thư mục ảnh thư viện NẰM NGOÀI CONTENT_MEDIA_DIRS",
      "thuvien" not in str(_cfg.CONTENT_MEDIA_DIRS))

# ── Chống lag lưới ảnh: thumbnail sinh khi cần + lazy-load ───────────────────
import storage as _stg_th
from PIL import Image as _PILImg
import tempfile as _tf_th, shutil as _sh_th
_tmp_md = Path(_tf_th.gettempdir()) / "mnt_thumb_test"
_sh_th.rmtree(_tmp_md, ignore_errors=True)
(_tmp_md / "thuvien").mkdir(parents=True, exist_ok=True)
_PILImg.new("RGB", (800, 600), (10, 20, 30)).save(_tmp_md / "thuvien" / "aa.png")
check("không phải ảnh thumbs → không sinh (False)",
      _stg_th.tao_thumbnail_neu_can(_tmp_md, "thuvien/aa.png") is False)
check("sinh thumbnail khi cần → file có thật + cạnh ≤ 160px",
      _stg_th.tao_thumbnail_neu_can(_tmp_md, "thuvien/thumbs/aa.png") is True
      and (_tmp_md / "thuvien" / "thumbs" / "aa.png").exists()
      and max(_PILImg.open(_tmp_md / "thuvien" / "thumbs" / "aa.png").size) <= 160)
check("thiếu ảnh gốc → False (route 404, onerror rơi về ảnh gốc)",
      _stg_th.tao_thumbnail_neu_can(_tmp_md, "thuvien/thumbs/khong_co.png") is False)
_sh_th.rmtree(_tmp_md, ignore_errors=True)
check("quét ảnh mồ côi KHÔNG đệ quy → thư mục thumbs/ không bị xóa",
      "iterdir()" in Path("storage.py").read_text(encoding="utf-8"))
_ajs_th = Path("static/js/app.js").read_text(encoding="utf-8")
check("lưới ảnh dùng thumbnail nhỏ (_thumb) + lazy-load",
      "function _thumb(" in _ajs_th and "_thumb(u)" in _ajs_th
      and 'loading="lazy"' in _ajs_th and 'decoding="async"' in _ajs_th
      and "onerror=" in _ajs_th)
check("route /media sinh thumbnail khi cần",
      "tao_thumbnail_neu_can" in Path("server.py").read_text(encoding="utf-8"))

# Content trỏ vào thư viện: cột ma_thu_vien lưu + sửa nhanh được qua API.
_cid_tv = db.upsert_content({"loai": "homestay", "ma_content": "TV1",
                             "noi_dung": "x", "ma_thu_vien": "7"})
check("content lưu được cột ma_thu_vien",
      any(r["id"] == _cid_tv and r["ma_thu_vien"] == "7" for r in db.get_content("homestay")))
check("API sửa nhanh nhận field ma_thu_vien",
      _client.post(f"/api/content/{_cid_tv}/field",
                   json={"field": "ma_thu_vien", "value": "9"}).get_json().get("ok") is True)
check("content đọc lại ma_thu_vien mới",
      any(r["id"] == _cid_tv and r["ma_thu_vien"] == "9" for r in db.get_content("homestay")))
with db._conn() as _c_tv2:
    _c_tv2.execute("DELETE FROM content WHERE ma_content='TV1'")

# ── Bước 3: roll bộ ảnh lúc đăng (anh_cho_bai / chon_bo_anh / con trỏ) ───────
# Dựng 1 thư viện 3 bộ (bo A/B/C) đều dùng được, +1 bộ "Không" để chắc chắn bị bỏ.
_mr = db.tv_mang_them("ROLL")
db.tv_bo_upsert({"mang_id": _mr, "ma": "A", "link_anh": "/media/thuvien/A.jpg", "su_dung": "Có"})
db.tv_bo_upsert({"mang_id": _mr, "ma": "B", "link_anh": "/media/thuvien/B.jpg", "su_dung": "Có"})
db.tv_bo_upsert({"mang_id": _mr, "ma": "C", "link_anh": "/media/thuvien/C.jpg", "su_dung": "Có"})
db.tv_bo_upsert({"mang_id": _mr, "ma": "D", "link_anh": "/media/thuvien/D.jpg", "su_dung": "Không"})

# Ưu tiên ảnh riêng: cột Ảnh có ảnh thì dùng chính nó, KHÔNG đụng thư viện.
check("roll: có ảnh riêng thì giữ nguyên, bỏ qua thư viện",
      db.anh_cho_bai("u1", "/media/content/rieng.jpg", str(_mr), True) == "/media/content/rieng.jpg")
# Không ảnh riêng, không thư viện → rỗng.
check("roll: không ảnh riêng + không thư viện → rỗng",
      db.anh_cho_bai("u1", "", "", True) == "" and db.anh_cho_bai("u1", "  ", None, False) == "")
# Chỉ lấy bộ su_dung='Có' + có link_anh (bộ D bị loại khỏi mọi lần bốc).
check("roll: chỉ bốc trong {A,B,C}, không bao giờ ra D",
      all(db.anh_cho_bai(f"rand{i}", "", str(_mr), False) in
          {"/media/thuvien/A.jpg", "/media/thuvien/B.jpg", "/media/thuvien/C.jpg"}
          for i in range(30)))

# Marketplace: con trỏ chạy TUẦN TỰ qua 3 bộ rồi vòng lại (bắt đầu từ chỗ nào
# cũng được — kiểm bằng cách 3 lần liên tiếp phải phủ đúng 3 bộ khác nhau).
_cu_mkt = "acc_roll_mkt"
_lan = [db.anh_cho_bai(_cu_mkt, "", str(_mr), True) for _ in range(3)]
check("roll Marketplace: 3 lần liên tiếp phủ đủ 3 bộ (tuần tự, không lặp)",
      set(_lan) == {"/media/thuvien/A.jpg", "/media/thuvien/B.jpg", "/media/thuvien/C.jpg"})
check("roll Marketplace: vòng thứ 2 lặp lại y hệt vòng 1 (con trỏ vòng tròn)",
      [db.anh_cho_bai(_cu_mkt, "", str(_mr), True) for _ in range(3)] == _lan)

# Mỗi nick một con trỏ riêng (roll độc lập).
with db._conn() as _c_ct:
    _ct_rows = _c_ct.execute(
        "SELECT c_user FROM tv_con_tro WHERE thu_vien_id=?", (_mr,)).fetchall()
check("con trỏ roll lưu riêng theo nick", any(r[0] == _cu_mkt for r in _ct_rows))

# Page/VIA (dung_con_tro=False) KHÔNG được đụng vào con trỏ Marketplace.
with db._conn() as _c_ct2:
    _vt_truoc = _c_ct2.execute(
        "SELECT vi_tri FROM tv_con_tro WHERE c_user=? AND thu_vien_id=?",
        (_cu_mkt, _mr)).fetchone()[0]
for _ in range(5):
    db.anh_cho_bai(_cu_mkt, "", str(_mr), False)   # bốc ngẫu nhiên
with db._conn() as _c_ct3:
    _vt_sau = _c_ct3.execute(
        "SELECT vi_tri FROM tv_con_tro WHERE c_user=? AND thu_vien_id=?",
        (_cu_mkt, _mr)).fetchone()[0]
check("Page/VIA bốc ngẫu nhiên KHÔNG đẩy con trỏ Marketplace", _vt_truoc == _vt_sau)

# Thư viện rỗng / toàn bộ 'Không' → rỗng (không nổ).
_mr0 = db.tv_mang_them("ROLL_RONG")
check("roll: thư viện không có bộ dùng được → rỗng",
      db.anh_cho_bai("u1", "", str(_mr0), True) == ""
      and db.anh_cho_bai("u1", "", str(_mr0), False) == "")
# ma_thu_vien rác (không phải số) → rỗng, không nổ.
check("roll: mã thư viện rác → rỗng", db.anh_cho_bai("u1", "", "abc", True) == "")

# Scheduler nối đúng: Marketplace dùng con trỏ, 3 kênh còn lại ngẫu nhiên.
_sched_src = Path("scheduler.py").read_text(encoding="utf-8")
check("scheduler: Marketplace roll theo con trỏ (dung_con_tro=True)",
      "anh_cho_bai" in _sched_src and "dung_con_tro=True" in _sched_src
      and _sched_src.count("dung_con_tro=False") == 3)

# ── Mã ảnh CHỐT lúc GEN (cột "Mã ảnh" trên bảng lịch — "nhìn sao đăng vậy") ──
with db._conn() as _c_sc:
    _cols_sc = {r[1] for r in _c_sc.execute("PRAGMA table_info(schedules)").fetchall()}
check("schedules có cột ma_anh + anh_dang", {"ma_anh", "anh_dang"} <= _cols_sc)

# db.chot_anh_cho_lich: trả (nhãn hiển thị, link đã chốt). Dùng lại thư viện _mr.
_lblO, _lnkO = db.chot_anh_cho_lich("gcu1", "/media/content/own.jpg", str(_mr), True)
check("chốt gen: có ảnh riêng → ('Ảnh', chính link đó)",
      _lblO == "Ảnh" and _lnkO == "/media/content/own.jpg")
_lblB, _lnkB = db.chot_anh_cho_lich("gcu1", "", str(_mr), True)
check("chốt gen: lấy thư viện → nhãn '<tên thư viện> - <mã>' + link CÙNG bộ",
      _lblB.startswith("ROLL - ")
      and _lnkB == f"/media/thuvien/{_lblB.split(' - ', 1)[1]}.jpg")
_lblN, _lnkN = db.chot_anh_cho_lich("gcu1", "", "", True)
check("chốt gen: không ảnh + không thư viện → ('', '')", _lblN == "" and _lnkN == "")

# replace_schedules lưu + get_schedules đọc lại ma_anh/anh_dang (round-trip).
db.replace_schedules("tt_ma_anh", [{
    "loai": "tt_ma_anh", "stt": 1, "ma_content": "C1", "ten_acc": "A",
    "ten_page": "", "gio_dang": "08:00", "ma_nhom": "", "tu_khoa": "",
    "mode": "Page", "trang_thai": "Chờ",
    "ma_anh": "Bộ ảnh-G1", "anh_dang": "/media/thuvien/g1.jpg"}])
_row_ma = db.get_schedules("tt_ma_anh")[0]
check("lịch lưu + đọc lại được ma_anh / anh_dang",
      _row_ma["ma_anh"] == "Bộ ảnh-G1" and _row_ma["anh_dang"] == "/media/thuvien/g1.jpg")
db.replace_schedules("tt_ma_anh", [])

# Gen (API): 3 kiểu content → cột Mã ảnh đúng ("Ảnh" / "Bộ ảnh-.." / trống).
_glib = db.tv_mang_them("GENLIB")
db.tv_bo_upsert({"mang_id": _glib, "ma": "G1", "link_anh": "/media/thuvien/g1.jpg", "su_dung": "Có"})
db.tv_bo_upsert({"mang_id": _glib, "ma": "G2", "link_anh": "/media/thuvien/g2.jpg", "su_dung": "Có"})
db.upsert_content({"loai": "thue", "ma_content": "GOWN", "noi_dung": "x",
                   "link_anh": "/media/content/own.jpg", "su_dung": "Có"})
db.upsert_content({"loai": "thue", "ma_content": "GLIB", "noi_dung": "x",
                   "link_anh": "", "ma_thu_vien": str(_glib), "su_dung": "Có"})
db.upsert_content({"loai": "thue", "ma_content": "GNONE", "noi_dung": "x",
                   "link_anh": "", "ma_thu_vien": "", "su_dung": "Có"})
_r_gma = _client.post("/api/schedule/thue/gen", json={
    "start": "08:00", "end": "14:00", "keyword_pool": ["kw"],
    "acc_settings": [
        {"ten": f"GMA{i}", "c_user": f"9900{i}", "page": "", "nghi": 15,
         "first_group_url": "123", "mode": "Page",
         "contents": ["GOWN", "GLIB", "GNONE"]}
        for i in range(3)]}).get_json()
_rows_gma = db.get_schedules("thue")
_by = lambda mc: [r for r in _rows_gma if r["ma_content"] == mc]
check("Gen Mã ảnh: content có ảnh riêng → nhãn 'Ảnh' + chốt đúng link",
      _r_gma.get("ok") and _by("GOWN")
      and all(r["ma_anh"] == "Ảnh" and r["anh_dang"] == "/media/content/own.jpg"
              for r in _by("GOWN")))
check("Gen Mã ảnh: content trỏ thư viện → nhãn 'GENLIB - <mã>' (tên thư viện) + link cùng bộ",
      _by("GLIB") and all(
          r["ma_anh"] in ("GENLIB - G1", "GENLIB - G2")
          and r["anh_dang"] == f"/media/thuvien/{r['ma_anh'].split(' - ', 1)[1].lower()}.jpg"
          for r in _by("GLIB")))
check("Gen Mã ảnh: content không ảnh + không thư viện → trống",
      _by("GNONE") and all(r["ma_anh"] == "" and r["anh_dang"] == "" for r in _by("GNONE")))
db.replace_schedules("thue", [])
db.tv_mang_xoa(_glib)
with db._conn() as _c_gma:
    _c_gma.execute("DELETE FROM content WHERE loai='thue' AND ma_content IN ('GOWN','GLIB','GNONE')")

# ── Chặn nhóm: acc bị FB hạn chế nhóm → Gen CHỈ giao đăng tường Page ─────────
import utils as _u_cn
check("có ChanNhomError (exception riêng cho acc bị chặn nhóm)",
      issubclass(_u_cn.ChanNhomError, _u_cn.PostError))
with db._conn() as _c_cn:
    _cols_acc = {r[1] for r in _c_cn.execute("PRAGMA table_info(accounts)").fetchall()}
check("accounts có cột chan_nhom", "chan_nhom" in _cols_acc)
check("acc_chan_nhom đọc đúng cờ",
      db.acc_chan_nhom({"chan_nhom": 1}) is True and db.acc_chan_nhom({"chan_nhom": 0}) is False
      and db.acc_chan_nhom({}) is False)
_cid_cnf = db.upsert_account({"ten_acc": "CNFlag", "c_user": "cnf1", "trang_thai": "Active"})
db.update_account_field(_cid_cnf, "chan_nhom", 1)
check("update_account_field lưu được chan_nhom",
      db.acc_chan_nhom(db.get_account_by_id(_cid_cnf)) is True)

# danh_dau_x_nhom_con_lai_hom_nay: đánh X slot nhóm, GIỮ đăng Page + Marketplace.
db.replace_schedules("cn_x", [
    {"loai": "cn_x", "stt": i + 1, "ma_content": "C", "ten_acc": "CNX", "c_user": "cnx1",
     "ten_page": "", "gio_dang": "23:59", "ma_nhom": "", "tu_khoa": "", "mode": "Page",
     "trang_thai": "Chờ", "hoat_dong": hd}
    for i, hd in enumerate(["dang_bai", "comment", "nuoi_nick", "dang_page", "marketplace"])])
db.danh_dau_x_nhom_con_lai_hom_nay("CNX", c_user="cnx1")
_tt_x = {r["hoat_dong"]: r["trang_thai"] for r in db.get_schedules("cn_x")}
check("chặn nhóm: đánh X slot đăng nhóm / comment / nuôi",
      _tt_x["dang_bai"].startswith("X") and _tt_x["comment"].startswith("X")
      and _tt_x["nuoi_nick"].startswith("X"))
check("chặn nhóm: GIỮ nguyên slot đăng tường Page + Marketplace",
      _tt_x["dang_page"] == "Chờ" and _tt_x["marketplace"] == "Chờ")
db.replace_schedules("cn_x", [])

# Gen (API): acc chặn nhóm chỉ còn slot dang_page; acc thường vẫn có việc nhóm.
db.upsert_page({"ten_page": "Page CN", "page_uid": "PGCN", "bai_dang_toi_da": 3})
db.upsert_page({"ten_page": "Page OK", "page_uid": "PGOK", "bai_dang_toi_da": 3})
db.upsert_account({"ten_acc": "CNGen", "c_user": "cn900", "loai_dang": "thue",
                   "trang_thai": "Active", "page_uid": "PGCN", "chan_nhom": 1,
                   "thoi_gian_nghi": 12})
db.upsert_account({"ten_acc": "CNok", "c_user": "cn901", "loai_dang": "thue",
                   "trang_thai": "Active", "page_uid": "PGOK", "chan_nhom": 0,
                   "thoi_gian_nghi": 12})
db.upsert_content({"loai": "thue", "ma_content": "GC1", "noi_dung": "x", "su_dung": "Có"})
_r_cn = _client.post("/api/schedule/thue/gen", json={
    "start": "08:00", "end": "14:00", "keyword_pool": ["kw"],
    "acc_settings": [
        {"ten": "CNGen", "c_user": "cn900", "page": "Page CN", "nghi": 12,
         "first_group_url": "123", "mode": "Page", "contents": ["GC1"]},
        {"ten": "CNok", "c_user": "cn901", "page": "Page OK", "nghi": 12,
         "first_group_url": "123", "mode": "Page", "contents": ["GC1"]}]}).get_json()
_rows_cn = db.get_schedules("thue")
_cn_only = [r for r in _rows_cn if r["ten_acc"] == "CNGen"]
_ok_only = [r for r in _rows_cn if r["ten_acc"] == "CNok"]
check("Gen chặn nhóm: acc CHỈ còn slot đăng tường Page (không việc nhóm)",
      _r_cn.get("ok") and _cn_only
      and all(r["hoat_dong"] == "dang_page" for r in _cn_only))
check("Gen: acc thường (không chặn) vẫn có slot đăng nhóm",
      _ok_only and any(r["hoat_dong"] == "dang_bai" for r in _ok_only))
db.replace_schedules("thue", [])
with db._conn() as _c_cn2:
    _c_cn2.execute("DELETE FROM accounts WHERE ten_acc IN ('CNFlag','CNGen','CNok')")
    _c_cn2.execute("DELETE FROM pages WHERE page_uid IN ('PGCN','PGOK')")
    _c_cn2.execute("DELETE FROM content WHERE loai='thue' AND ma_content='GC1'")

# Nhận diện tự động + nối scheduler + UI.
_pv_src = Path("page_via_poster.py").read_text(encoding="utf-8")
_via_src = Path("via_poster.py").read_text(encoding="utf-8")
check("poster báo ChanNhomError khi FB hạn chế nhóm (is_messaging_restricted)",
      "ChanNhomError" in _pv_src and "is_messaging_restricted" in _pv_src
      and "ChanNhomError" in _via_src and "is_messaging_restricted" in _via_src)
check("scheduler bắt ChanNhomError → _mark_chan_nhom (đánh dấu + đánh X slot nhóm)",
      "except ChanNhomError" in _sched_src and "def _mark_chan_nhom" in _sched_src
      and "danh_dau_x_nhom_con_lai_hom_nay" in _sched_src
      and 'update_account_field(a["id"], "chan_nhom", 1)' in _sched_src)
_ajs_cn = Path("static/js/app.js").read_text(encoding="utf-8")
check("bảng Tài khoản có cột 'Chặn nhóm' (ô tick)",
      'key:"chan_nhom"' in _ajs_cn and 'label:"Chặn nhóm"' in _ajs_cn)

# scheduler đăng ĐÚNG ảnh đã chốt (item['anh_dang']); lịch cũ mới roll động.
check("scheduler: 4 chỗ đăng dùng _anh_dang_cho(item, ct, c_user_v) + ưu tiên anh_dang",
      _sched_src.count("_anh_dang_cho(item, ct, c_user_v") == 4
      and 'item.get("anh_dang")' in _sched_src)

# Frontend: bảng lịch có cột "Mã ảnh" giữa Content và Từ khóa.
check("bảng lịch (app.js) có cột Mã ảnh + ô maAnhCell, colspan 7",
      ">Mã ảnh<" in _ajs_mkt and "maAnhCell" in _ajs_mkt and 'colspan="7"' in _ajs_mkt)

# Tóm tắt lịch: ngoài trạng thái, có hàng "Theo loại phiên" đếm từng hoat_dong.
check("tóm tắt lịch đếm theo loại phiên (đăng nhóm/Page/comment/nuôi/market)",
      "Theo loại phiên" in _ajs_mkt and "Đăng nhóm" in _ajs_mkt
      and "Đăng Page" in _ajs_mkt
      and 'hd("dang_bai")' in _ajs_mkt and 'hd("dang_page")' in _ajs_mkt
      and 'hd("comment")' in _ajs_mkt and 'hd("nuoi_nick")' in _ajs_mkt
      and 'hd("marketplace")' in _ajs_mkt)

db.tv_mang_xoa(_mr)
db.tv_mang_xoa(_mr0)

# ── Sao lưu Thư viện ảnh: xuất → máy mới → nhập (kèm ảnh) ───────────────────
import zipfile as _zf_tv, tempfile as _tf_tv, config as _cfg_tv
from io import BytesIO as _BIO_tv
_md_tv = Path(_tf_tv.mkdtemp()) / "media"          # thư mục ảnh TẠM — không đụng data/media thật
(_md_tv / "thuvien").mkdir(parents=True)
_goc_tv = (server.MEDIA_DIR, _st.MEDIA_DIR, _cfg_tv.THUVIEN_MEDIA_DIR)
server.MEDIA_DIR = _st.MEDIA_DIR = _md_tv
_cfg_tv.THUVIEN_MEDIA_DIR = str(_md_tv / "thuvien")
try:
    for _m in db.tv_mang_list():
        db.tv_mang_xoa(_m["id"])
    _u = lambda b: _st.save_thuvien_image(b, "x.jpg")
    _a1, _a2, _a3, _a4 = _u(b"anh-1"), _u(b"anh-2"), _u(b"anh-3"), _u(b"anh-4")
    _t1 = db.tv_mang_them("1PN")
    _t2 = db.tv_mang_them("Rỗng")
    db.tv_bo_upsert({"mang_id": _t1, "ma": "A1", "link_anh": f"{_a1}, {_a2}",
                     "su_dung": "Có", "ghi_chu": "bộ có mã"})
    db.tv_bo_upsert({"mang_id": _t1, "ma": "", "link_anh": _a3, "su_dung": "Có", "ghi_chu": ""})
    db.tv_bo_upsert({"mang_id": _t1, "ma": "A3", "link_anh": _a4, "su_dung": "Không", "ghi_chu": ""})
    _cid_tv = db.upsert_content({"loai": "thue", "ma_content": "TV-CT1", "noi_dung": "x",
                                 "link_anh": "", "su_dung": "Có", "ma_thu_vien": str(_t1)})

    _r_ex = _client.get("/api/thuvien/export-zip").get_json()
    _zp = _zf_tv.ZipFile(_r_ex["path"])
    check("Xuất thư viện: đủ thư viện / bộ ảnh / ảnh",
          _r_ex.get("ok") and _r_ex["so_thu_vien"] == 2 and _r_ex["so_bo"] == 3
          and _r_ex["so_anh"] == 4 and "thu_vien.xlsx" in _zp.namelist()
          and sum(n.startswith("images/") for n in _zp.namelist()) == 4)
    _bk_tv = Path(_r_ex["path"]).read_bytes()
    _r_exc = _client.get("/api/content/export-zip?loai=thue").get_json()
    _bk_ct = Path(_r_exc["path"]).read_bytes()

    # "Máy mới": thư viện trống, không có file ảnh, không có content đó.
    for _m in db.tv_mang_list():
        db.tv_mang_xoa(_m["id"])
    for _f in (_md_tv / "thuvien").iterdir():
        _f.unlink()
    db.delete_content(_cid_tv)
    _nhap = lambda b, url, **kv: _client.post(url, data={"file": (_BIO_tv(b), "bk.zip"), **kv},
                                              content_type="multipart/form-data").get_json()
    _r_im = _nhap(_bk_tv, "/api/thuvien/import-zip")
    _ds_tv = {m["ten"]: m["id"] for m in db.tv_mang_list()}
    _bo_tv = db.tv_bo_list(_ds_tv.get("1PN", -1))
    check("Nhập thư viện: tạo lại đủ tab, kể cả tab chưa có bộ ảnh",
          _r_im.get("ok") and set(_ds_tv) == {"1PN", "Rỗng"} and _r_im["tab_moi"] == 2)
    check("Nhập thư viện: đủ 3 bộ, giữ thứ tự / mã / Sử dụng / ghi chú",
          [(b["ma"], b["su_dung"], b["ghi_chu"]) for b in _bo_tv]
          == [("A1", "Có", "bộ có mã"), ("", "Có", ""), ("A3", "Không", "")])
    check("Nhập thư viện: ảnh chép về đĩa, link trỏ đúng file có thật",
          all((_md_tv.parent / u.strip().lstrip("/")).exists()
              for b in _bo_tv for u in b["link_anh"].split(","))
          and (_md_tv.parent / _bo_tv[0]["link_anh"].split(",")[0].strip().lstrip("/")
               ).read_bytes() == b"anh-1"
          and len(_bo_tv[0]["link_anh"].split(",")) == 2)
    _so_file = len(list((_md_tv / "thuvien").iterdir()))
    _r_im2 = _nhap(_bk_tv, "/api/thuvien/import-zip")
    check("Nhập lại cùng file: không nhân đôi bộ ảnh (kể cả bộ không có mã) hay file ảnh",
          _r_im2.get("ok") and _r_im2["them"] == 0 and _r_im2["bo_qua"] == 3
          and _r_im2["tab_moi"] == 0 and len(db.tv_bo_list(_ds_tv["1PN"])) == 3
          and len(list((_md_tv / "thuvien").iterdir())) == _so_file)
    # Máy đích ĐÃ CÓ bộ cùng mã nhưng ảnh khác (hai máy cùng đánh mã 1, 2, 3…):
    # nhập THÊM, giữ bộ sẵn có, bộ trùng mã đổi sang mã mới. Bản đầu bỏ qua vì
    # coi trùng mã là trùng bộ — nhập không thêm được gì.
    _tk = db.tv_mang_them("KHAC_MAY")
    _anh_cu = _u(b"anh-cu")
    db.tv_bo_upsert({"mang_id": _tk, "ma": "1", "link_anh": _anh_cu, "su_dung": "Có"})
    db.tv_bo_upsert({"mang_id": _tk, "ma": "2", "link_anh": _u(b"anh-cu-2"), "su_dung": "Có"})
    _buf_k = _BIO_tv()
    from openpyxl import Workbook as _WB_tv
    _wb_k = _WB_tv(); _ws_k = _wb_k.active; _ws_k.title = "Bộ ảnh"
    _ws_k.append(["Thư viện", "Mã bộ ảnh", "Ảnh", "Sử dụng", "Ghi chú"])
    _ws_k.append(["KHAC_MAY", "1", "aaaaaaaaaaa1.jpg", "Có", ""])
    _ws_k.append(["KHAC_MAY", "2", "aaaaaaaaaaa2.jpg", "Có", ""])
    _ws_k.append(["KHAC_MAY", "A", "aaaaaaaaaaa3.jpg", "Có", ""])
    _ws_k.append(["KHAC_MAY", "A", "aaaaaaaaaaa4.jpg", "Có", ""])
    _x = _BIO_tv(); _wb_k.save(_x)
    with _zf_tv.ZipFile(_buf_k, "w") as _z:
        _z.writestr("thu_vien.xlsx", _x.getvalue())
        for _i in range(1, 5):
            _z.writestr(f"images/aaaaaaaaaaa{_i}.jpg", f"moi-{_i}".encode())
    _r_k = _nhap(_buf_k.getvalue(), "/api/thuvien/import-zip")
    _ma_k = [(b["ma"], b["link_anh"]) for b in db.tv_bo_list(_tk)]
    check("Nhập THÊM: bộ sẵn có giữ nguyên, bộ trùng mã vẫn được thêm với mã mới",
          _r_k.get("ok") and _r_k["them"] == 4 and _r_k["doi_ma"] == 3
          and _ma_k[0] == ("1", _anh_cu)
          and [m for m, _ in _ma_k] == ["1", "2", "3", "4", "A", "A (2)"])
    _r_k2 = _nhap(_buf_k.getvalue(), "/api/thuvien/import-zip")
    check("Nhập THÊM lần 2 cùng file: không nhân đôi (nhận ra bộ theo ảnh)",
          _r_k2.get("ok") and _r_k2["them"] == 0 and _r_k2["bo_qua"] == 4
          and len(db.tv_bo_list(_tk)) == 6)
    # Kéo thả đổi vị trí tab thư viện (trái ↔ phải).
    _ids_tab = [m["id"] for m in db.tv_mang_list()]
    _r_ro = _client.post("/api/thuvien/mang/reorder", json={"ids": _ids_tab[::-1]}).get_json()
    check("Thư viện: kéo thả đổi vị trí tab → lưu đúng thứ tự mới",
          _r_ro.get("ok") and [m["id"] for m in db.tv_mang_list()] == _ids_tab[::-1]
          and len(_ids_tab) >= 2)
    _r_ic = _nhap(_bk_ct, "/api/content/import-zip", loai="thue")
    _ct_tv = db.get_content_by_code("TV-CT1", "thue") or {}
    check("Backup content mang theo Mã thư viện — sang máy mới trỏ đúng thư viện (theo tên)",
          _r_ic.get("ok") and str(_ct_tv.get("ma_thu_vien")) == str(_ds_tv["1PN"])
          and str(_ds_tv["1PN"]) != str(_t1))
    check("Nhập file không phải backup thư viện → báo rõ",
          "không phải file backup Thư viện" in (_nhap(_bk_ct, "/api/thuvien/import-zip")
                                                .get("error") or ""))
    if _ct_tv.get("id"):
        db.delete_content(_ct_tv["id"])
finally:
    server.MEDIA_DIR, _st.MEDIA_DIR, _cfg_tv.THUVIEN_MEDIA_DIR = _goc_tv
    for _m in db.tv_mang_list():
        db.tv_mang_xoa(_m["id"])

# ── Mã content có dấu cách thừa ("P062806 ") — gặp thật 23/10 ───────────────
# Gen ghi mã ĐÃ CẮT vào lịch, bảng content giữ dấu cách → tra mã trượt: cột Mã
# ảnh trống dù content trỏ thư viện, và lúc đăng báo "Không có content".
_tvsp = db.tv_mang_them("3PN_SP")
db.tv_bo_upsert({"mang_id": _tvsp, "ma": "7", "link_anh": "/media/thuvien/sp7.jpg", "su_dung": "Có"})
with db._conn() as _c_sp:                        # chèn THÔ, đúng như dữ liệu cũ đang có
    _c_sp.execute("INSERT INTO content (loai, ma_content, noi_dung, link_anh, su_dung, "
                  "ma_thu_vien, order_idx) VALUES ('loai4', 'P062806 ', 'x', '', 'Có', ?, 0)",
                  (str(_tvsp),))
check("tra content theo mã chịu được dấu cách thừa (runner tìm được content)",
      (db.get_content_by_code("P062806", "loai4") or {}).get("noi_dung") == "x")
_r_sp = _client.post("/api/schedule/loai4/gen", json={
    "start": "08:00", "end": "10:00", "keyword_pool": ["kw"],
    "acc_settings": [{"ten": "SP1", "c_user": "990555", "page": "", "nghi": 30,
                      "first_group_url": "123", "mode": "Page", "contents": []}]}).get_json()
_rows_sp = [r for r in db.get_schedules("loai4") if (r.get("hoat_dong") or "dang_bai") == "dang_bai"]
check("Gen: content 'P062806 ' trỏ thư viện → cột Mã ảnh có bộ ảnh (không còn trống)",
      _r_sp.get("ok") and _rows_sp
      and all(r["ma_anh"] == "3PN_SP - 7" and r["anh_dang"] == "/media/thuvien/sp7.jpg"
              for r in _rows_sp))
db.init_db()                                     # migration cắt dấu cách mã cũ
with db._conn() as _c_sp:
    _ma_sp = [r[0] for r in _c_sp.execute("SELECT ma_content FROM content WHERE loai='loai4'")]
check("migration: cắt dấu cách thừa của mã content đang có", _ma_sp == ["P062806"])
_id_sp = db.upsert_content({"loai": "loai4", "ma_content": "  Shophouse  ", "noi_dung": "y",
                            "su_dung": "Có"})
_client.post(f"/api/content/{_id_sp}/field", json={"field": "ma_content", "value": " SH2 "})
with db._conn() as _c_sp:
    _ma_sp2 = _c_sp.execute("SELECT ma_content FROM content WHERE id=?", (_id_sp,)).fetchone()[0]
check("lưu / sửa mã content tự cắt dấu cách thừa", _ma_sp2 == "SH2"
      and (db.get_content_by_code("Shophouse", "loai4") is None))
with db._conn() as _c_sp:
    _c_sp.execute("DELETE FROM content WHERE loai='loai4'")
db.replace_schedules("loai4", [])
db.tv_mang_xoa(_tvsp)

# ── dọn dẹp ────────────────────────────────────────────────────────────────
for suffix in ("", "-wal", "-shm"):
    try:
        Path(str(_tmp) + suffix).unlink(missing_ok=True)
    except OSError:
        pass   # best-effort; sqlite WAL có thể còn giữ file

print(f"\n{_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
