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


def delete_image(url_path: str):
    """Xóa ảnh theo URL path (bắt đầu bằng /data/media/...)."""
    if not url_path or not url_path.startswith("/"):
        return
    abs_path = MEDIA_DIR.parent / url_path.lstrip("/")
    if abs_path.exists():
        abs_path.unlink()
        logger.info(f"  🗑️  Deleted image: {url_path}")


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
