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

if not SCHED_ID or not ACC_NAME or not PAGE_UID:
    logger.error("❌ Thiếu biến môi trường JOIN_SCHEDULE_ID / JOIN_ACC_NAME / JOIN_PAGE_UID")
    sys.exit(1)

logger.info(f"🚀 Join Groups Worker")
logger.info(f"   Acc: {ACC_NAME} | Page UID: {PAGE_UID}")

from join_groups_runner import run_join_schedule
run_join_schedule(SCHED_ID, ACC_NAME, PAGE_UID)
