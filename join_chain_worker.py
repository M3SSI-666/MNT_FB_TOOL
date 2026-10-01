"""
Chạy LẦN LƯỢT mọi lịch tham gia nhóm của một nguồn, từ trên xuống dưới.

Mở trình duyệt của nick thứ nhất, tham gia đủ nhóm, đóng lại, rồi mới sang nick
kế tiếp — cho tới nick cuối cùng.

VÌ SAO KHÔNG CHẠY SONG SONG: mỗi nick là một phiên Chromium riêng ~1,1 GB. Máy
này đã 11,6/15,9 GB với 5 runner; bật 12 phiên cùng lúc là hết RAM. Chạy dồn
dập cũng đúng kiểu hành vi Facebook chặn nhanh nhất, mà nhóm Marketplace thì
phải chờ quản trị viên duyệt nên nhanh cũng chẳng vào sớm hơn.

THỨ TỰ phải khớp đúng thứ tự bảng đang hiện (id giảm dần). Người bấm nhìn hàng
trên cùng chạy trước; chạy theo thứ tự khác là họ không hiểu đang tới nick nào.

File pid: worker ghi `.runner_join_<id>.pid` cho ĐÚNG lịch đang chạy rồi xoá
khi xong, nên đèn "đang chạy" của từng hàng và nút Dừng sẵn có vẫn hoạt động
mà không phải sửa gì.
"""
import json
import os
import sys
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import _conn, set_setting
from utils import logger

BASE_DIR = Path(__file__).parent
NGUON    = os.environ.get("JOIN_NGUON", "")


def khoa_tt(nguon: str) -> str:
    return f"join_chain_tt_{nguon or 'UID'}"


def bao(**kw):
    set_setting(khoa_tt(NGUON), json.dumps(kw, ensure_ascii=False))


def pid_file(sched_id: int) -> Path:
    return BASE_DIR / f".runner_join_{sched_id}.pid"


def main():
    with _conn() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT id, ten_acc, page_uid FROM join_schedules "
            "WHERE COALESCE(nguon,'')=? ORDER BY id DESC", (NGUON,)).fetchall()]

    if not rows:
        bao(xong=True, tong=0, da=0, dang="", loi="Không có lịch nào")
        logger.info("Không có lịch nào để chạy")
        return

    ten = "Marketplace" if NGUON == "MARKET" else "UID Nhóm"
    logger.info(f"⛓️  Chạy lần lượt {len(rows)} nick — nhóm {ten}")
    bao(xong=False, tong=len(rows), da=0, dang="", loi="")

    from join_groups_runner import run_join_schedule

    da = 0
    for r in rows:
        sid, acc = r["id"], r["ten_acc"]
        logger.info(f"⛓️  [{da + 1}/{len(rows)}] ▶ {acc}")
        bao(xong=False, tong=len(rows), da=da, dang=acc, loi="")
        # Ghi pid của CHÍNH tiến trình chuỗi này vào file pid của lịch đang
        # chạy: giao diện hỏi "lịch này chạy chưa" bằng file đó, và nút Dừng
        # sẵn có cũng diệt theo pid đó — diệt là cả chuỗi dừng, đúng ý muốn.
        pid_file(sid).write_text(str(os.getpid()))
        try:
            run_join_schedule(sid, acc, r["page_uid"] or "", NGUON)
        except Exception as e:
            logger.error(f"⛓️  {acc}: hỏng — {e}")
            with _conn() as con:
                con.execute("UPDATE join_schedules SET trang_thai=? WHERE id=?",
                            (f"Lỗi: {e}"[:60], sid))
        finally:
            pid_file(sid).unlink(missing_ok=True)
        da += 1
        bao(xong=False, tong=len(rows), da=da, dang="", loi="")

    bao(xong=True, tong=len(rows), da=da, dang="", loi="")
    logger.info(f"⛓️  Xong cả {da} nick")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Sập thì phải báo ra, nếu không người bấm chỉ thấy nút đứng im.
        logger.exception("❌ Chuỗi tham gia nhóm hỏng")
        bao(xong=True, tong=0, da=0, dang="", loi=f"{type(e).__name__}: {e}"[:160])
        raise
