"""
storage.py — Local file storage (thay thế Google Drive + Cloudinary)
Ảnh được lưu tại: data/media/content/{loai}/ và data/media/uploads/
"""

import os
import shutil
import tempfile
import mimetypes
import urllib.request
from pathlib import Path
from typing import Optional

from config import MEDIA_DIR, CONTENT_MEDIA_DIRS
from utils import logger

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ═══════════════════════════════════════════════════════════════
# Upload ảnh (từ bytes hoặc file path)
# ═══════════════════════════════════════════════════════════════

def save_image(file_bytes: bytes, filename: str, loai: str = "uploads") -> str:
    """
    Lưu ảnh vào thư mục local, trả về URL path tương đối.
    URL dạng: /media/content/homestay/abc.jpg (phục vụ qua Flask static)
    """
    dest_dir = Path(CONTENT_MEDIA_DIRS.get(loai, str(MEDIA_DIR / "uploads")))
    dest_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        ext = ".jpg"

    # Tạo tên file unique
    import uuid
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    dest_path = dest_dir / safe_name

    with open(dest_path, "wb") as f:
        f.write(file_bytes)

    # Trả về URL path relative để dùng trong <img src="">
    rel = dest_path.relative_to(MEDIA_DIR.parent)
    url = "/" + str(rel).replace("\\", "/")
    logger.info(f"  💾 Saved image: {safe_name} → {url}")
    return url


def delete_image(url_path: str) -> bool:
    """Xóa ảnh theo URL path (bắt đầu bằng /data/media/...)."""
    if not url_path or not url_path.startswith("/"):
        return False
    abs_path = MEDIA_DIR.parent / url_path.lstrip("/")
    try:
        if abs_path.exists():
            abs_path.unlink()
            logger.info(f"  🗑️  Đã xóa ảnh: {url_path}")
            return True
    except OSError as e:
        logger.warning(f"  ⚠️  Không xóa được {url_path}: {e}")
    return False


def xoa_anh_khong_dung(ung_vien: set) -> int:
    """
    Xóa các ảnh trong `ung_vien` mà KHÔNG còn content nào trỏ tới.

    Phải kiểm tra lại toàn bộ content vì một ảnh có thể được nhiều content dùng
    chung — xóa content này không có nghĩa ảnh đó thành rác.
    """
    if not ung_vien:
        return 0
    from db import get_all_content_image_urls
    con_dung = get_all_content_image_urls()
    return sum(1 for u in ung_vien if u not in con_dung and delete_image(u))


def quet_anh_mo_coi(xoa: bool = False, bo_qua_moi_giay: int = 3600) -> dict:
    """
    Quét thư mục content, tìm ảnh không content nào trỏ tới.

    `bo_qua_moi_giay`: bỏ qua file vừa tạo gần đây (mặc định 1 giờ) — ảnh được
    lưu lên đĩa NGAY khi chọn file, trước lúc bấm Lưu content, nên quét ngay có
    thể xóa nhầm ảnh người dùng đang upload dở.
    """
    import time as _t
    from db import get_all_content_image_urls
    con_dung = {os.path.basename(u) for u in get_all_content_image_urls()}
    bay_gio  = _t.time()

    mo_coi, tong_byte, da_xoa = [], 0, 0
    for thu_muc in CONTENT_MEDIA_DIRS.values():
        p = Path(thu_muc)
        if not p.exists():
            continue
        for f in p.iterdir():
            if not f.is_file() or f.suffix.lower() not in ALLOWED_EXTS:
                continue
            if f.name in con_dung:
                continue
            if bay_gio - f.stat().st_mtime < bo_qua_moi_giay:
                continue                      # mới upload, có thể chưa kịp lưu
            mo_coi.append(f.name)
            tong_byte += f.stat().st_size
            if xoa:
                try:
                    f.unlink()
                    da_xoa += 1
                except OSError as e:
                    logger.warning(f"  ⚠️  Không xóa được {f.name}: {e}")

    if xoa:
        logger.info(f"  🧹 Dọn ảnh mồ côi: xóa {da_xoa} file, "
                    f"giải phóng {tong_byte/1024/1024:.1f} MB")
    return {"so_file": len(mo_coi), "dung_luong_mb": round(tong_byte / 1024 / 1024, 1),
            "da_xoa": da_xoa}


# ═══════════════════════════════════════════════════════════════
# Download ảnh để đăng bài (trả về local paths cho poster)
# ═══════════════════════════════════════════════════════════════

def prepare_images_for_post(image_urls: str) -> tuple[list[str], Optional[str]]:
    """
    Chuẩn bị ảnh để đăng lên Facebook.

    Args:
        image_urls: Comma-separated URLs (có thể là /data/media/... local hoặc https:// external)

    Returns:
        (local_paths, temp_dir)
        - local_paths: đường dẫn tuyệt đối các file ảnh, đã sort (hook đầu tiên)
        - temp_dir: thư mục temp nếu có download, None nếu dùng file local trực tiếp
    """
    if not image_urls:
        return [], None

    urls = [u.strip() for u in image_urls.split(",") if u.strip()]
    if not urls:
        return [], None

    local_paths = []
    temp_dir    = None
    needs_temp  = any(u.startswith("http") for u in urls)

    if needs_temp:
        temp_dir = tempfile.mkdtemp(prefix="mnt_fb_")

    pad = len(str(len(urls)))

    for i, url in enumerate(urls, 1):
        filename = f"{str(i).zfill(pad)}"

        if url.startswith("/"):
            # Local file (dạng /data/media/...)
            abs_path = MEDIA_DIR.parent / url.lstrip("/")
            if abs_path.exists():
                local_paths.append(str(abs_path))
            else:
                logger.warning(f"  ⚠️  File không tồn tại: {abs_path}")

        elif url.startswith("http"):
            # External URL (Cloudinary, v.v.) — download về temp
            ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
            if ext not in {"jpg","jpeg","png","webp","gif"}:
                ext = "jpg"
            dest = os.path.join(temp_dir, f"{filename}.{ext}")
            try:
                urllib.request.urlretrieve(url, dest)
                local_paths.append(dest)
                logger.info(f"  ✅ Download: {url[:60]} → {filename}.{ext}")
            except Exception as e:
                logger.error(f"  ❌ Download failed {url[:60]}: {e}")

    # Sort theo tên file để hook (đầu tiên) luôn đứng đầu
    local_paths.sort(key=lambda p: os.path.basename(p))
    return local_paths, temp_dir


def cleanup_temp(temp_dir: Optional[str]):
    """Xóa thư mục temp sau khi đăng xong."""
    if temp_dir and os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# List images in a content folder
# ═══════════════════════════════════════════════════════════════

def list_content_images(loai: str, content_id: int = None) -> list[str]:
    """Trả về list URL path ảnh trong thư mục content."""
    folder = Path(CONTENT_MEDIA_DIRS.get(loai, str(MEDIA_DIR / "uploads")))
    if not folder.exists():
        return []
    urls = []
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() in ALLOWED_EXTS:
            rel = f.relative_to(MEDIA_DIR.parent)
            urls.append("/" + str(rel).replace("\\", "/"))
    return urls
