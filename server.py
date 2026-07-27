"""
server.py — Flask backend cho MNT_FB
Toàn bộ data từ SQLite local, không cần Google Sheets API.
"""

import os
import sys
import json
import time
import secrets
import subprocess
from datetime import timedelta
from pathlib import Path
from flask import (Flask, jsonify, render_template, request, send_from_directory,
                   session, redirect, url_for)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(str(BASE_DIR))

from config import PORT, LOG_DIR, MEDIA_DIR
from db import (
    init_db,
    # accounts
    get_accounts, get_account_by_name, upsert_account, delete_account, update_account_field,
    reorder_accounts, insert_account_at,
    # pages
    get_pages, get_page_by_name, upsert_page, delete_page, reorder_pages,
    # content
    get_content, get_content_by_code, upsert_content, delete_content,
    # uid groups
    get_uid_groups_by_code, get_all_uid_groups, upsert_uid_group, delete_uid_group,
    # schedules
    get_schedules, update_schedule_status, bulk_set_schedule_status,
    replace_schedules, update_schedule_field,
    # settings
    get_setting, set_setting, get_all_settings,
)
from utils import logger

# Init DB on startup
init_db()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.json.ensure_ascii = False
# Không cache file tĩnh (js/css) — luôn nạp bản mới sau khi sửa, khỏi phải Ctrl+F5
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
# Tự nạp lại template khi sửa index.html — khỏi phải restart server
app.config["TEMPLATES_AUTO_RELOAD"] = True

# ── Đăng nhập / bảo vệ truy cập từ xa ──────────────────────────
# Secret key cho session — lưu 1 lần để session không mất khi restart.
_secret = get_setting("app_secret_key", "")
if not _secret:
    _secret = secrets.token_hex(32)
    set_setting("app_secret_key", _secret)
app.secret_key = _secret
app.permanent_session_lifetime = timedelta(days=30)


def _is_local() -> bool:
    """Request đến từ chính máy này (cửa sổ app / localhost) → tin cậy, khỏi login."""
    ra = request.remote_addr or ""
    return ra in ("127.0.0.1", "::1", "localhost") or ra.startswith("127.")


def _password_set() -> bool:
    return bool(os.environ.get("MNT_PASSWORD") or get_setting("app_password_hash", ""))


def _password_ok(submitted: str) -> bool:
    """Ưu tiên biến môi trường MNT_PASSWORD; nếu không có thì dùng hash trong DB."""
    envp = os.environ.get("MNT_PASSWORD")
    if envp:
        return submitted == envp
    h = get_setting("app_password_hash", "")
    return bool(h) and check_password_hash(h, submitted)


@app.before_request
def _auth_guard():
    p = request.path
    # Cho qua: file tĩnh, trang login, và máy local (ngồi trực tiếp máy công ty)
    if p.startswith("/static/") or p == "/login" or p == "/favicon.ico":
        return
    if _is_local() or session.get("auth"):
        return
    # Truy cập từ xa chưa đăng nhập
    if p.startswith("/api/") or p.startswith("/media/") or p.startswith("/data/"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if _is_local() or session.get("auth"):
        return redirect(url_for("index"))
    error = ""
    if request.method == "POST":
        if _password_ok(request.form.get("password", "")):
            session.permanent = True
            session["auth"] = True
            return redirect(url_for("index"))
        error = "Sai mật khẩu"
    elif not _password_set():
        error = "Chưa đặt mật khẩu — hãy đặt trên máy công ty (tab Hành động) trước."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/app/set-password", methods=["POST"])
def api_set_password():
    """Đặt/đổi mật khẩu truy cập từ xa. Chỉ cho phép từ máy local hoặc đã đăng nhập."""
    if not (_is_local() or session.get("auth")):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    pw = (request.json or {}).get("password", "")
    if len(pw) < 4:
        return jsonify({"ok": False, "error": "Mật khẩu tối thiểu 4 ký tự"})
    set_setting("app_password_hash", generate_password_hash(pw))
    return jsonify({"ok": True})

# Boot ID đổi mỗi lần server khởi động — client dùng để phát hiện restart và tự reload.
APP_BOOT_ID = str(time.time())


@app.route("/api/ping")
def api_ping():
    return jsonify({"ok": True, "boot": APP_BOOT_ID})

# ── Serve media files ─────────────────────────────────────────
@app.route("/media/<path:filename>")
def serve_media(filename):
    return send_from_directory(str(MEDIA_DIR), filename)

@app.route("/data/media/<path:filename>")
def serve_media_alt(filename):
    return send_from_directory(str(MEDIA_DIR), filename)


# ── Runner management ─────────────────────────────────────────
RUNNER_CFG = {
    "homestay": {"sheet": "Chéo Homestay", "pid_file": ".runner_homestay.pid",
                 "log": str(LOG_DIR / "autopost_homestay.log")},
    "thue":     {"sheet": "Chéo Thuê",     "pid_file": ".runner_thue.pid",
                 "log": str(LOG_DIR / "autopost_thue.log")},
    "ban":      {"sheet": "Chéo Bán",      "pid_file": ".runner_ban.pid",
                 "log": str(LOG_DIR / "autopost_ban.log")},
    "page":     {"sheet": "Đăng bài Page", "pid_file": ".runner_page.pid",
                 "log": str(LOG_DIR / "autopost_page.log")},
    "nuoi":     {"sheet": "Nuôi nick",     "pid_file": ".runner_nuoi.pid",
                 "log": str(LOG_DIR / "autopost_nuoi.log")},
}
RUNNER_LOAI_MAP = {
    "homestay": "homestay",
    "thue":     "thue",
    "ban":      "ban",
    "page":     "page",
    "nuoi":     "nuoi",
}
STAGGER = {"homestay": 0, "thue": 8, "ban": 16, "page": 24, "nuoi": 32}


def _runner_pid(loai):
    pf = BASE_DIR / RUNNER_CFG[loai]["pid_file"]
    try:
        return int(pf.read_text().strip()) if pf.exists() else None
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    """
    Kiểm tra PID còn sống — KHÔNG dùng os.kill(pid, 0).
    Trên Windows os.kill(pid,0) gọi GenerateConsoleCtrlEvent (gửi Ctrl+C),
    raise lỗi khi server chạy dưới pythonw (không console) → false dương tính.
    """
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _runner_running(loai):
    pid = _runner_pid(loai)
    if not pid:
        return False
    if _pid_alive(pid):
        return True
    (BASE_DIR / RUNNER_CFG[loai]["pid_file"]).unlink(missing_ok=True)
    return False


def _kill_all_runners():
    """Kill tất cả scheduler process — kể cả orphan không có pid file."""
    # Bước 1: kill theo pid file
    for loai, cfg in RUNNER_CFG.items():
        pf = BASE_DIR / cfg["pid_file"]
        if pf.exists():
            try:
                pid = int(pf.read_text().strip())
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                   capture_output=True)
                else:
                    os.kill(pid, 15)
            except Exception:
                pass
            pf.unlink(missing_ok=True)

    # Bước 2: fallback — dùng wmic tìm mọi python process đang chạy scheduler.py
    if sys.platform == "win32":
        try:
            r = subprocess.run(
                ["wmic", "process", "where",
                 "(name='python.exe' or name='pythonw.exe') and CommandLine like '%scheduler.py%'",
                 "get", "ProcessId", "/format:value"],
                capture_output=True, text=True, timeout=8
            )
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.lower().startswith("processid="):
                    pid_str = line.split("=", 1)[1].strip()
                    if pid_str.isdigit() and pid_str != "0":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", pid_str],
                                       capture_output=True)
                        logger.info(f"  Killed orphan scheduler PID {pid_str}")
        except Exception as e:
            logger.warning(f"wmic kill fallback lỗi: {e}")


def _kill_join_workers():
    """Kill mọi tiến trình join_groups_worker.py đang chạy."""
    if sys.platform != "win32":
        return
    try:
        subprocess.run(
            ["wmic", "process", "where",
             "(name='python.exe' or name='pythonw.exe') and CommandLine like '%join_groups_worker%'",
             "delete"],
            capture_output=True, timeout=8
        )
    except Exception as e:
        logger.warning(f"kill join worker lỗi: {e}")


def _shutdown_all():
    """Tắt sạch: server (đang tự thoát) + runner đăng nền + join worker."""
    logger.info("🛑 Đóng app — tắt toàn bộ runner nền...")
    try:
        _kill_all_runners()
        _kill_join_workers()
    except Exception as e:
        logger.warning(f"shutdown lỗi: {e}")


# ═══════════════════════════════════════════════════════════════
# Pages — HTML
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/app/shutdown", methods=["POST"])
def api_app_shutdown():
    """Tắt sạch phần mềm: dừng runner + join worker rồi thoát hẳn server.
    Dùng khi muốn giải phóng tài nguyên (bật lại: khởi động máy / RUN_APP)."""
    import threading as _th
    def _bye():
        time.sleep(0.6)          # để response kịp trả về client
        _shutdown_all()
        os._exit(0)              # thoát cả server (và cửa sổ app nếu có)
    _th.Thread(target=_bye, daemon=True).start()
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════
# API — Runner
# ═══════════════════════════════════════════════════════════════

@app.route("/api/run/status")
def run_status():
    return jsonify({loai: {"running": _runner_running(loai)} for loai in RUNNER_CFG})


@app.route("/api/run/<loai>/start", methods=["POST"])
def run_start(loai):
    if loai not in RUNNER_CFG:
        return jsonify({"ok": False, "error": "Loại không hợp lệ"})
    if _runner_running(loai):
        return jsonify({"ok": False, "msg": f"Runner {loai} đang chạy rồi"})
    cfg      = RUNNER_CFG[loai]
    delay    = STAGGER.get(loai, 0)
    headless = (request.json or {}).get("headless", True)
    flags    = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    env      = {**os.environ,
                "SCHEDULER_LOAI":        loai,
                "SCHEDULER_LOG_FILE":    cfg["log"],
                "SCHEDULER_START_DELAY": str(delay),
                "HEADLESS":              "true" if headless else "false"}
    proc  = subprocess.Popen([sys.executable, "-X", "utf8", "scheduler.py"],
                             cwd=str(BASE_DIR), creationflags=flags, env=env)
    (BASE_DIR / cfg["pid_file"]).write_text(str(proc.pid))
    return jsonify({"ok": True, "pid": proc.pid})


@app.route("/api/run/<loai>/stop", methods=["POST"])
def run_stop(loai):
    if loai not in RUNNER_CFG:
        return jsonify({"ok": False, "error": "Loại không hợp lệ"})
    killed = []
    # Kill theo pid file
    pid = _runner_pid(loai)
    if pid:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, 15)
            killed.append(pid)
        except Exception:
            pass
        (BASE_DIR / RUNNER_CFG[loai]["pid_file"]).unlink(missing_ok=True)

    # Fallback: kill orphan theo loai env var
    if sys.platform == "win32":
        try:
            loai_val = RUNNER_LOAI_MAP[loai]
            r = subprocess.run(
                ["wmic", "process", "where",
                 f"(name='python.exe' or name='pythonw.exe') and CommandLine like '%scheduler.py%' and CommandLine like '%{loai_val}%'",
                 "get", "ProcessId", "/format:value"],
                capture_output=True, text=True, timeout=6
            )
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.lower().startswith("processid="):
                    pid_str = line.split("=", 1)[1].strip()
                    if pid_str.isdigit() and pid_str != "0":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", pid_str], capture_output=True)
                        killed.append(int(pid_str))
        except Exception:
            pass

    return jsonify({"ok": True, "killed": killed})


# ═══════════════════════════════════════════════════════════════
# API — Accounts
# ═══════════════════════════════════════════════════════════════

# Các trường credential không bao giờ được trả về trong danh sách tài khoản.
# Muốn xem giá trị thật phải gọi /api/accounts/<id>/secrets từ máy local.
SECRET_ACCOUNT_FIELDS = ("password", "xs", "twofa", "pass_khoiphuc", "email_khoiphuc")
SECRET_MASK = "••••••"


def _mask_account(row: dict) -> dict:
    out = dict(row)
    for f in SECRET_ACCOUNT_FIELDS:
        out[f] = SECRET_MASK if (out.get(f) or "").strip() else ""
    return out


@app.route("/api/accounts")
def api_accounts():
    loai = request.args.get("loai")
    rows = get_accounts(loai=loai)
    return jsonify({"ok": True, "data": [_mask_account(r) for r in rows]})


@app.route("/api/accounts/<int:acc_id>/secrets")
def api_account_secrets(acc_id):
    """Trả về credential thật của 1 tài khoản — CHỈ cho máy local.

    Phiên đăng nhập từ xa cố tình không được phép, vì mật khẩu Facebook và mã
    2FA không nên đi qua mạng chỉ để hiển thị trên bảng điều khiển.
    """
    if not _is_local():
        return jsonify({"ok": False, "error": "Chỉ xem được trên máy tại chỗ"}), 403
    from db import get_account_by_id
    row = get_account_by_id(acc_id)
    if not row:
        return jsonify({"ok": False, "error": "Không tìm thấy tài khoản"}), 404
    return jsonify({"ok": True, "data": {f: row.get(f, "") for f in SECRET_ACCOUNT_FIELDS}})


@app.route("/api/accounts/save", methods=["POST"])
def api_accounts_save():
    data = request.json or {}
    # Form gửi lại dấu che nếu người dùng không sửa trường đó — bỏ qua để
    # không ghi đè credential thật bằng chuỗi "••••••".
    for f in SECRET_ACCOUNT_FIELDS:
        if data.get(f) == SECRET_MASK:
            data.pop(f)
    try:
        acc_id = upsert_account(data)
        return jsonify({"ok": True, "id": acc_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/accounts/<int:acc_id>/field", methods=["POST"])
def api_accounts_field(acc_id):
    body = request.json or {}
    if body.get("field") in SECRET_ACCOUNT_FIELDS and body.get("value") == SECRET_MASK:
        return jsonify({"ok": True, "skipped": True})   # không đổi gì
    try:
        update_account_field(acc_id, body["field"], body["value"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/accounts/<int:acc_id>", methods=["DELETE"])
def api_accounts_delete(acc_id):
    delete_account(acc_id)
    return jsonify({"ok": True})


@app.route("/api/accounts/reorder", methods=["POST"])
def api_accounts_reorder():
    ordered_ids = request.json or []
    try:
        reorder_accounts([int(i) for i in ordered_ids])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/pages/reorder", methods=["POST"])
def api_pages_reorder():
    ordered_ids = request.json or []
    try:
        reorder_pages([int(i) for i in ordered_ids])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/accounts/<int:ref_id>/insert-row", methods=["POST"])
def api_accounts_insert_row(ref_id):
    position = (request.json or {}).get("position", "below")
    try:
        new_id = insert_account_at(ref_id, position)
        return jsonify({"ok": True, "id": new_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════════════════════════════════════════════════════════
# API — Pages
# ═══════════════════════════════════════════════════════════════

@app.route("/api/pages")
def api_pages():
    return jsonify({"ok": True, "data": get_pages()})


@app.route("/api/pages/save", methods=["POST"])
def api_pages_save():
    data = request.json or {}
    try:
        pid = upsert_page(data)
        return jsonify({"ok": True, "id": pid})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/pages/<int:page_id>/field", methods=["POST"])
def api_pages_field(page_id):
    body = request.json or {}
    field = body.get("field","")
    value = body.get("value","")
    safe = {"ten_page","page_uid","link_page","loai_page","bai_dang_toi_da","ghi_chu"}
    if field not in safe:
        return jsonify({"ok": False, "error": f"Field không hợp lệ: {field}"})
    try:
        from db import _conn
        with _conn() as con:
            con.execute(f"UPDATE pages SET {field}=? WHERE id=?", (value, page_id))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/pages/<int:page_id>", methods=["DELETE"])
def api_pages_delete(page_id):
    delete_page(page_id)
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════
# API — Content
# ═══════════════════════════════════════════════════════════════

@app.route("/api/content/<loai>")
def api_content(loai):
    rows = get_content(loai)
    return jsonify({"ok": True, "data": rows})


@app.route("/api/content/save", methods=["POST"])
def api_content_save():
    data = request.json or {}
    try:
        cid = upsert_content(data)
        return jsonify({"ok": True, "id": cid})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/content/<int:content_id>/field", methods=["POST"])
def api_content_field(content_id):
    body  = request.json or {}
    field = body.get("field", "")
    value = body.get("value", "")
    safe  = {"ma_content","noi_dung","link_anh_hook","link_anh","su_dung","ghi_chu"}
    if field not in safe:
        return jsonify({"ok": False, "error": f"Field không hợp lệ: {field}"})
    try:
        from db import _conn
        with _conn() as con:
            con.execute(f"UPDATE content SET {field}=? WHERE id=?", (value, content_id))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/content/<int:content_id>", methods=["DELETE"])
def api_content_delete(content_id):
    delete_content(content_id)
    return jsonify({"ok": True})


@app.route("/api/content/upload-image", methods=["POST"])
def api_content_upload_image():
    """Upload ảnh lên local storage."""
    from storage import save_image
    loai = request.form.get("loai", "uploads")
    file = request.files.get("image")
    if not file:
        return jsonify({"ok": False, "error": "Không có file"})
    try:
        url = save_image(file.read(), file.filename, loai)
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# Danh mục (tab) của Content — CỐ ĐỊNH 3 loại, khớp với phần Lịch (homestay/thue/ban).
# Không cho thêm/xóa/sửa tab để giữ logic đơn giản, đồng bộ với scheduler.
CONTENT_CATEGORIES = [
    {"key": "homestay", "title": "Homestay", "icon": "🏠"},
    {"key": "thue",     "title": "Thuê",     "icon": "🏡"},
    {"key": "ban",      "title": "Bán",      "icon": "💰"},
]


@app.route("/api/content-categories")
def api_content_categories():
    return jsonify({"ok": True, "data": CONTENT_CATEGORIES})


# ═══════════════════════════════════════════════════════════════
# API — UID Groups
# ═══════════════════════════════════════════════════════════════

@app.route("/api/uid-groups")
def api_uid_groups():
    return jsonify({"ok": True, "data": get_all_uid_groups()})


@app.route("/api/uid-groups/save", methods=["POST"])
def api_uid_groups_save():
    data = request.json or {}
    try:
        gid = upsert_uid_group(data)
        return jsonify({"ok": True, "id": gid})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/uid-groups/<int:gid>", methods=["DELETE"])
def api_uid_groups_delete(gid):
    delete_uid_group(gid)
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════
# API — Schedules
# ═══════════════════════════════════════════════════════════════

@app.route("/api/schedule/<loai>")
def api_schedule(loai):
    rows = get_schedules(loai)
    return jsonify({"ok": True, "data": rows})


@app.route("/api/schedule/<loai>/reset", methods=["POST"])
def api_schedule_reset(loai):
    count = bulk_set_schedule_status(loai, "✅", "Chờ")
    count += bulk_set_schedule_status(loai, "❌", "Chờ")
    count += bulk_set_schedule_status(loai, "X", "Chờ")
    return jsonify({"ok": True, "updated": count})


@app.route("/api/schedule/<loai>/stop", methods=["POST"])
def api_schedule_stop(loai):
    count = bulk_set_schedule_status(loai, "Chờ", "X")
    return jsonify({"ok": True, "updated": count})


@app.route("/api/schedule/<loai>/cell", methods=["POST"])
def api_schedule_cell(loai):
    body = request.json or {}
    try:
        update_schedule_field(body["id"], body["field"], body["value"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/schedule/<loai>/gen", methods=["POST"])
def api_schedule_gen(loai):
    """Gen lịch đăng chéo (Homestay/Thuê/Bán) và lưu vào SQLite."""
    body         = request.json or {}
    start_str    = body.get("start", "05:00")
    end_str      = body.get("end",   "03:00")
    keyword_pool = body.get("keyword_pool", [])
    acc_settings = body.get("acc_settings", [])

    def parse_hhmm(s, dh, dm):
        try:
            h, m = map(int, s.split(":"))
            return h * 60 + m
        except Exception:
            return dh * 60 + dm

    def min_to_time(m):
        return f"{(m // 60) % 24:02d}:{m % 60:02d}"

    START_MIN = parse_hhmm(start_str, 5, 0)
    end_raw   = parse_hhmm(end_str, 3, 0)
    END_MIN   = end_raw if end_raw > START_MIN else end_raw + 24 * 60

    if not acc_settings:
        return jsonify({"ok": False, "error": "Không có acc nào"})

    # "Nhóm đầu" (UID/link mở composer) là bắt buộc — fail sớm thay vì lỗi lúc chạy.
    thieu = [a["ten"] for a in acc_settings if not (a.get("first_group_url", "") or "").strip()]
    if thieu:
        return jsonify({"ok": False,
                        "error": "Thiếu 'Nhóm đầu' cho acc: " + ", ".join(thieu)})

    n_kw   = len(keyword_pool) if keyword_pool else 1
    n_accs = len(acc_settings)

    tong_luc = sum(60 / a["nghi"] for a in acc_settings)
    do_nen   = 60 / tong_luc

    contents = acc_settings[0].get("contents", []) if acc_settings else []
    if not contents:
        # Lấy từ DB
        from db import get_content
        contents = [r["ma_content"] for r in get_content(loai, su_dung="Có")]
    if not contents:
        return jsonify({"ok": False, "error": f"Không có content '{loai}' nào (Sử dụng=Có)"})

    n_contents     = len(contents)
    content_cursor = {a["ten"]: a.get("c_offset", 0) for a in acc_settings}
    keyword_cursor = {a["ten"]: (i * n_kw // n_accs) % n_kw for i, a in enumerate(acc_settings)}
    next_time      = {a["ten"]: START_MIN + i * do_nen for i, a in enumerate(acc_settings)}

    schedule = []
    while True:
        eligible = [(next_time[a["ten"]], i, a)
                    for i, a in enumerate(acc_settings)
                    if next_time[a["ten"]] <= END_MIN]
        if not eligible:
            break
        eligible.sort(key=lambda x: x[0])
        t_float, _, acc = eligible[0]
        t_min = round(t_float)
        if t_min > END_MIN:
            break

        cur_c = content_cursor[acc["ten"]]
        content_cursor[acc["ten"]] = (cur_c + 1) % n_contents

        mode_acc = acc.get("mode", "Hybrid")
        cur_kw   = keyword_cursor[acc["ten"]]
        if keyword_pool and mode_acc in ("Via", "Hybrid"):
            tu_khoa = keyword_pool[cur_kw % n_kw]
            keyword_cursor[acc["ten"]] = (cur_kw + 1) % n_kw
        else:
            tu_khoa = ""

        # ma_nhom = URL/UID nhóm đầu để mở composer (đã validate là luôn có).
        ma_nhom_val = acc.get("first_group_url", "").strip()

        schedule.append({
            "loai":       loai,
            "stt":        len(schedule) + 1,
            "ma_content": contents[cur_c % n_contents],
            "ten_acc":    acc["ten"],
            "ten_page":   acc["page"],
            "gio_dang":   min_to_time(t_min),
            "ma_nhom":    ma_nhom_val,
            "tu_khoa":    tu_khoa,
            "mode":       mode_acc,
            "trang_thai": "Chờ",
        })
        next_time[acc["ten"]] = t_float + acc["nghi"]

    if not schedule:
        return jsonify({"ok": False, "error": "Không tạo được lịch"})

    # ── Nuôi nick: chuyển một số slot của acc bật nuôi thành phiên nuôi ──
    # Nick càng non → chuyển càng nhiều (đăng ít, nuôi nhiều). Đọc thẳng từ DB
    # theo tên acc nên không cần đổi luồng gen ở frontend.
    n_warm = 0
    try:
        from nuoi_nick import plan_warming_conversion
        acc_names = {r["ten_acc"] for r in schedule}
        warm_accs = {a["ten_acc"]: a.get("nuoi_interval")
                     for a in get_accounts()
                     if a["ten_acc"] in acc_names and int(a.get("nuoi_nick", 0) or 0) == 1}
        if warm_accs:
            n_warm = plan_warming_conversion(schedule, warm_accs)
    except Exception as e:
        logger.warning(f"Nuôi nick: bỏ qua chuyển slot ({e})")

    replace_schedules(loai, schedule)

    # Lưu thiết lập gần nhất để lần gen sau prefill (thay cho hardcode mặc định).
    set_setting(f"gen_prefs_{loai}", json.dumps({
        "start":       start_str,
        "end":         end_str,
        "first_group": (acc_settings[0].get("first_group_url", "") or "").strip(),
        "keyword":     ",".join(keyword_pool),
    }, ensure_ascii=False))

    return jsonify({"ok": True, "total": len(schedule),
                    "nuoi": n_warm,
                    "from": schedule[0]["gio_dang"],
                    "to":   schedule[-1]["gio_dang"]})


@app.route("/api/schedule/nuoi/gen", methods=["POST"])
def api_schedule_nuoi_gen():
    """
    Gen lịch cho acc CHỈ NUÔI — acc có tick 'Nuôi' nhưng cột 'Loại đăng' để trống
    (không được phân công đăng bài). Mỗi acc vào một phiên nuôi mỗi `nuoi_interval`
    phút; các acc lệch pha nhau để không cùng mở trình duyệt một lúc.
    """
    from nuoi_nick import build_warming_schedule, normalize_interval
    body  = request.json or {}
    start = body.get("start", "07:00")
    end   = body.get("end",   "23:00")

    accs = [{"ten": a["ten_acc"], "interval": normalize_interval(a.get("nuoi_interval"))}
            for a in get_accounts(trang_thai="Active")
            if int(a.get("nuoi_nick", 0) or 0) == 1
            and not (a.get("loai_dang") or "").strip()]

    if not accs:
        return jsonify({"ok": False,
                        "error": "Không có acc nào 'chỉ nuôi' "
                                 "(cần: tick Nuôi + để TRỐNG cột Loại đăng + Trạng thái Active)"})

    rows = build_warming_schedule(accs, start, end)
    if not rows:
        return jsonify({"ok": False, "error": "Không tạo được lịch nuôi"})

    replace_schedules("nuoi", rows)
    set_setting("gen_prefs_nuoi", json.dumps({"start": start, "end": end}, ensure_ascii=False))
    return jsonify({"ok": True, "total": len(rows), "accs": len(accs),
                    "from": rows[0]["gio_dang"], "to": rows[-1]["gio_dang"]})


@app.route("/api/schedule/page/gen", methods=["POST"])
def api_schedule_page_gen():
    """Gen lịch Đăng bài Page từ bảng pages + content local."""
    import random as _random
    body    = request.json or {}
    acc     = body.get("acc", "")
    start_h = int(body.get("start_hour", 7))
    end_h   = int(body.get("end_hour", 23))

    CONTENT_LOAI_MAP = {"Homestay": "homestay", "Thuê": "thue", "Bán": "ban"}

    pages = [p for p in get_pages() if p.get("bai_dang_toi_da", 0) > 0]
    if not pages:
        return jsonify({"ok": False, "error": "Không có Page nào có 'Bài đăng tối đa' > 0"})

    page_items = []
    for p in pages:
        ct_loai = CONTENT_LOAI_MAP.get(p.get("loai_page", ""), "")
        if not ct_loai:
            continue
        codes = [r["ma_content"] for r in get_content(ct_loai, su_dung="Có")]
        if not codes:
            continue
        n      = min(p["bai_dang_toi_da"], len(codes))
        picked = _random.sample(codes, n)
        page_items.append({"ten_page": p["ten_page"], "picked": picked})

    if not page_items:
        return jsonify({"ok": False, "error": "Không có content nào"})

    def interleave(lists):
        res = []; iters = [list(l) for l in lists]
        while any(iters):
            for l in iters:
                if l: res.append(l.pop(0))
        return res

    mixed    = interleave([[(p["ten_page"], c) for c in p["picked"]] for p in page_items])
    total    = len(mixed)
    total_min = (end_h - start_h) * 60
    interval  = total_min / (total - 1) if total > 1 else 0

    schedule = []
    for i, (ten_page, ma_content) in enumerate(mixed):
        t = start_h * 60 + round(i * interval)
        schedule.append({
            "loai":       "page",
            "stt":        i + 1,
            "ma_content": ma_content,
            "ten_acc":    acc,
            "ten_page":   ten_page,
            "gio_dang":   f"{(t//60)%24:02d}:{t%60:02d}",
            "ma_nhom":    "",
            "tu_khoa":    "",
            "mode":       "PAGE",
            "trang_thai": "Chờ",
        })

    replace_schedules("page", schedule)

    # Lưu thiết lập gen Page gần nhất để lần sau prefill.
    set_setting("gen_prefs_page", json.dumps({
        "acc":        acc,
        "start_hour": start_h,
        "end_hour":   end_h,
    }, ensure_ascii=False))

    return jsonify({"ok": True, "total": len(schedule),
                    "from": schedule[0]["gio_dang"],
                    "to":   schedule[-1]["gio_dang"]})


@app.route("/api/schedule/<loai>/gen-data")
def api_schedule_gen_data(loai):
    """Lấy data cho form gen lịch: acc active + content pool."""
    accs_db = get_accounts(loai=loai.capitalize(), trang_thai="Active")
    if loai == "homestay":
        accs_db = [a for a in get_accounts(trang_thai="Active")
                   if "Homestay" in (a.get("loai_dang") or "")]
    elif loai == "thue":
        accs_db = [a for a in get_accounts(trang_thai="Active")
                   if "Thuê" in (a.get("loai_dang") or "")]
    elif loai == "ban":
        accs_db = [a for a in get_accounts(trang_thai="Active")
                   if "Bán" in (a.get("loai_dang") or "")]

    accs = []
    for a in accs_db:
        try:
            nghi = int(a.get("thoi_gian_nghi", 30))
        except Exception:
            nghi = 30
        accs.append({
            "ten":      a["ten_acc"],
            "page":     a.get("ten_page", ""),
            "nghi":     nghi,
            "luc_dang": round(60 / nghi, 2),
        })

    contents = [r["ma_content"] for r in get_content(loai, su_dung="Có")]

    # Thiết lập gen gần nhất đã lưu (link nhóm đầu, từ khóa, giờ) — None nếu chưa có.
    prefs = None
    raw = get_setting(f"gen_prefs_{loai}", "")
    if raw:
        try:
            prefs = json.loads(raw)
        except Exception:
            prefs = None

    return jsonify({"ok": True, "accs": accs, "contents": contents, "prefs": prefs})


# ═══════════════════════════════════════════════════════════════
# API — Logs
# ═══════════════════════════════════════════════════════════════

def _read_log(filename, n=150):
    f = Path(filename)
    if not f.exists():
        return "(Chưa có log)"
    try:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception as e:
        return f"Lỗi: {e}"


@app.route("/api/logs/<loai>")
def api_logs(loai):
    n = int(request.args.get("n", 150))
    log_map = {
        "homestay": str(LOG_DIR / "autopost_homestay.log"),
        "thue":     str(LOG_DIR / "autopost_thue.log"),
        "ban":      str(LOG_DIR / "autopost_ban.log"),
        "page":     str(LOG_DIR / "autopost_page.log"),
        "nuoi":     str(LOG_DIR / "autopost_nuoi.log"),
    }
    fname = log_map.get(loai)
    if not fname:
        return jsonify({"ok": False, "error": "Loại không hợp lệ"})
    return jsonify({"ok": True, "text": _read_log(fname, n)})


# ═══════════════════════════════════════════════════════════════
# API — Settings
# ═══════════════════════════════════════════════════════════════

@app.route("/api/settings")
def api_settings():
    return jsonify({"ok": True, "data": get_all_settings()})


@app.route("/api/settings/save", methods=["POST"])
def api_settings_save():
    body = request.json or {}
    for k, v in body.items():
        set_setting(k, str(v))
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════
# Entry
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# API — Tham gia nhóm
# ═══════════════════════════════════════════════════════════════

JOIN_LOG_FILE = str(LOG_DIR / "join_groups.log")

def _join_pid_file(sched_id: int) -> Path:
    return BASE_DIR / f".runner_join_{sched_id}.pid"

def _join_pid_alive(pid: int) -> bool:
    return _pid_alive(pid)

def _join_running_for(sched_id: int) -> bool:
    pf = _join_pid_file(sched_id)
    if not pf.exists():
        return False
    try:
        pid = int(pf.read_text().strip())
        if pid and _join_pid_alive(pid):
            return True
    except Exception:
        pass
    pf.unlink(missing_ok=True)
    return False

def _any_join_running() -> bool:
    return any(_join_running_for(int(pf.stem.split("_")[-1]))
               for pf in BASE_DIR.glob(".runner_join_*.pid"))

def _reset_stale_join():
    """Reset từng schedule bị stuck 'Đang chạy' khi process đã chết."""
    try:
        from db import _conn
        rows = _conn().execute(
            "SELECT id FROM join_schedules WHERE trang_thai='Đang chạy'"
        ).fetchall()
        for row in rows:
            sid = row[0]
            if not _join_running_for(sid):
                with _conn() as con:
                    con.execute("UPDATE join_schedules SET trang_thai='Chờ' WHERE id=?", (sid,))
    except Exception:
        pass


@app.route("/api/join/schedules")
def api_join_schedules():
    try:
        _reset_stale_join()
        from db import _conn
        rows = [dict(r) for r in _conn().execute(
            "SELECT * FROM join_schedules ORDER BY id DESC"
        ).fetchall()]
        # Gắn trạng thái running per-row
        for r in rows:
            r["is_running"] = _join_running_for(r["id"])
        return jsonify({"ok": True, "data": rows, "running": _any_join_running()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/join/add", methods=["POST"])
def api_join_add():
    body     = request.json or {}
    ten_acc  = body.get("ten_acc","").strip()
    ten_page = body.get("ten_page","").strip()
    gio_chay = body.get("gio_chay","").strip()
    if not ten_acc or not ten_page:
        return jsonify({"ok": False, "error": "Thiếu Acc hoặc Page"})
    try:
        from db import _conn, get_account_by_name, resolve_page_uid
        page_uid = resolve_page_uid(get_account_by_name(ten_acc, ten_page), ten_page)
        with _conn() as con:
            cur = con.execute(
                "INSERT INTO join_schedules (ten_acc,ten_page,page_uid,gio_chay,created_at) VALUES (?,?,?,?,datetime('now','localtime'))",
                (ten_acc, ten_page, page_uid, gio_chay)
            )
        return jsonify({"ok": True, "id": cur.lastrowid})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/join/gen-quick", methods=["POST"])
def api_join_gen_quick():
    """Tạo lịch nhanh: mỗi acc Active có page → 1 lịch tham gia nhóm."""
    body       = request.json or {}
    delay_new  = int(body.get("delay_new",  30))
    delay_skip = int(body.get("delay_skip",  5))
    # Lưu settings để dùng khi Run
    set_setting("join_delay_new",  str(delay_new))
    set_setting("join_delay_skip", str(delay_skip))

    try:
        accs    = get_accounts(trang_thai="Active")
        created = 0
        skipped = 0
        from db import _conn, resolve_page_uid
        with _conn() as con:
            for acc in accs:
                ten_acc  = acc["ten_acc"]
                ten_page = (acc.get("ten_page") or "").strip()
                if not ten_page:
                    continue
                # Bỏ qua nếu đã có lịch cho cặp này
                existing = con.execute(
                    "SELECT id FROM join_schedules WHERE ten_acc=? AND ten_page=?",
                    (ten_acc, ten_page)
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
                page_uid = resolve_page_uid(acc, ten_page)
                con.execute(
                    "INSERT INTO join_schedules (ten_acc,ten_page,page_uid,gio_chay,trang_thai,created_at) "
                    "VALUES (?,?,?,?,?,datetime('now','localtime'))",
                    (ten_acc, ten_page, page_uid, "", "Chờ")
                )
                created += 1
        return jsonify({"ok": True, "created": created, "skipped": skipped})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/join/<int:sched_id>/run", methods=["POST"])
def api_join_run(sched_id):
    # Cho phép song song — chỉ chặn nếu chính schedule này đang chạy
    if _join_running_for(sched_id):
        return jsonify({"ok": False, "error": f"Lịch #{sched_id} đang chạy rồi"})
    try:
        from db import _conn
        row = _conn().execute("SELECT * FROM join_schedules WHERE id=?", (sched_id,)).fetchone()
        if not row: return jsonify({"ok": False, "error": "Không tìm thấy lịch"})
        row = dict(row)
        body       = request.json or {}
        headless   = body.get("headless", True)
        delay_new  = int(body.get("delay_new",  get_setting("join_delay_new",  "30") or "30"))
        delay_skip = int(body.get("delay_skip", get_setting("join_delay_skip",  "5") or "5"))
        flags      = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        env        = {**os.environ,
                      "JOIN_SCHEDULE_ID":   str(sched_id),
                      "JOIN_ACC_NAME":      row["ten_acc"],
                      "JOIN_PAGE_UID":      row["page_uid"],
                      "HEADLESS":           "true" if headless else "false",
                      "JOIN_DELAY_NEW":     str(delay_new),
                      "JOIN_DELAY_SKIP":    str(delay_skip),
                      "SCHEDULER_LOG_FILE": JOIN_LOG_FILE}
        with _conn() as con:
            con.execute("UPDATE join_schedules SET trang_thai='Đang chạy', moi_join=0, da_join=0, loi=0, tong_nhom=0 WHERE id=?", (sched_id,))
        proc = subprocess.Popen([sys.executable, "-X", "utf8", "join_groups_worker.py"],
                                cwd=str(BASE_DIR), creationflags=flags, env=env)
        _join_pid_file(sched_id).write_text(str(proc.pid))
        return jsonify({"ok": True, "pid": proc.pid})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/join/<int:sched_id>/stop", methods=["POST"])
def api_join_stop(sched_id):
    pf = _join_pid_file(sched_id)
    killed = False
    if pf.exists():
        try:
            pid = int(pf.read_text().strip())
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            killed = True
        except Exception:
            pass
        pf.unlink(missing_ok=True)
    try:
        from db import _conn
        with _conn() as con:
            con.execute("UPDATE join_schedules SET trang_thai='Chờ' WHERE id=?", (sched_id,))
    except Exception:
        pass
    return jsonify({"ok": True, "killed": killed})


@app.route("/api/join/<int:sched_id>/status")
def api_join_status(sched_id):
    try:
        from db import _conn
        row = _conn().execute("SELECT * FROM join_schedules WHERE id=?", (sched_id,)).fetchone()
        if not row: return jsonify({"ok": False, "error": "Không tìm thấy"})
        return jsonify({"ok": True, "data": dict(row), "running": _join_running_for(sched_id)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/join/<int:sched_id>", methods=["DELETE"])
def api_join_delete(sched_id):
    try:
        from db import _conn
        with _conn() as con:
            con.execute("DELETE FROM join_schedules WHERE id=?", (sched_id,))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/logs/join")
def api_logs_join():
    n = int(request.args.get("n", 200))
    return jsonify({"ok": True, "text": _read_log(JOIN_LOG_FILE, n)})


def _wait_server_ready(port: int, timeout: float = 15.0):
    """Chờ Flask nhận kết nối trước khi mở cửa sổ (tránh trang lỗi lúc đầu)."""
    import socket
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _serve():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    import threading
    _kill_all_runners()

    # --browser  : mở bằng trình duyệt mặc định (chế độ web cũ, để debug)
    # --no-browser: chỉ chạy server, không mở gì (server chạy ẩn)
    # (mặc định)  : mở CỬA SỔ APP riêng bằng pywebview — tách biệt với Chrome
    if "--browser" in sys.argv:
        import webbrowser
        webbrowser.open(f"http://localhost:{PORT}")
        _serve()
    elif "--no-browser" in sys.argv:
        _serve()
    else:
        try:
            import webview
        except ImportError:
            # Chưa cài pywebview → fallback mở trình duyệt như cũ
            import webbrowser
            webbrowser.open(f"http://localhost:{PORT}")
            _serve()
        else:
            # Icon riêng (chữ MNT xanh) — tách khỏi icon pythonw mặc định
            _icon = str(BASE_DIR / "static" / "mnt.ico")
            if sys.platform == "win32":
                try:
                    import ctypes
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MNT.AutoPost")
                except Exception:
                    pass

            # Flask chạy nền, cửa sổ app giữ thread chính
            threading.Thread(target=_serve, daemon=True).start()
            _wait_server_ready(PORT)
            win = webview.create_window(
                "MNT AutoPost",
                f"http://localhost:{PORT}",
                width=1440, height=920,
                min_size=(1024, 700),
            )
            # Nhấn X = tắt sạch: dừng luôn runner đăng nền + join worker
            win.events.closing += _shutdown_all
            # block đến khi đóng cửa sổ → tiến trình kết thúc
            try:
                webview.start(icon=_icon)
            except TypeError:
                webview.start()   # pywebview cũ không hỗ trợ tham số icon
