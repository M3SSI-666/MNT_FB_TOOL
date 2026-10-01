"""
join_groups_worker.py — Worker process tham gia nhóm.
Được gọi bởi server.py qua subprocess.
"""

import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import logger

SCHED_ID = int(os.environ.get("JOIN_SCHEDULE_ID", "0"))
ACC_NAME = os.environ.get("JOIN_ACC_NAME", "")
PAGE_UID = os.environ.get("JOIN_PAGE_UID", "")
# '' = sheet UID Nhóm (vào nhóm với vai Page), 'MARKET' = nhóm đã duyệt
# Marketplace (vào bằng chính nick cá nhân).
NGUON    = os.environ.get("JOIN_NGUON", "")

if not SCHED_ID or not ACC_NAME:
    logger.error("❌ Thiếu JOIN_SCHEDULE_ID hoặc JOIN_ACC_NAME")
    sys.exit(1)
# Page UID chỉ bắt buộc khi còn phải switch sang Page. Nhóm Marketplace vào
# bằng nick cá nhân nên không cần Page nào cả — đòi cho đủ là chặn oan.
if NGUON != "MARKET" and not PAGE_UID:
    logger.error("❌ Thiếu JOIN_PAGE_UID")
    sys.exit(1)

logger.info(f"🚀 Join Groups Worker")
logger.info(f"   Acc: {ACC_NAME} | "
            + ("Nhóm Marketplace, vào bằng nick cá nhân" if NGUON == "MARKET"
               else f"Page UID: {PAGE_UID}"))

from join_groups_runner import run_join_schedule
run_join_schedule(SCHED_ID, ACC_NAME, PAGE_UID, NGUON)
