"""Mã nhận dạng máy, dùng cho việc đăng ký và phê duyệt.

Yêu cầu đặt ra cho con số này:

  ỔN ĐỊNH   cài lại phần mềm, khởi động lại máy, đổi IP đều không làm nó đổi.
            Nếu nó đổi thì khách phải xin duyệt lại từ đầu — hỏng cả cơ chế.
  DUY NHẤT  hai máy khác nhau không được trùng, không thì duyệt một máy là mở
            cho cả hai.
  ĐỌC ĐƯỢC  khách phải đọc nó qua Zalo hoặc điện thoại cho bạn, nên phải ngắn
            và chia nhóm.
  KHÔNG LỘ  không mang tên máy, tên người dùng, hay số máy thật.

Cách làm: lấy MachineGuid mà Windows sinh ra lúc cài hệ điều hành, băm nó lại
rồi cắt lấy 12 ký tự. Băm chứ không gửi thẳng: MachineGuid là số định danh
thật của máy, gửi nguyên đi là để lộ nhiều hơn mức cần thiết — bên nhận chỉ
cần biết "vẫn là máy đó", không cần biết nó là máy nào.
"""

import hashlib
import os
import platform
import subprocess
import uuid
from pathlib import Path

# Trộn thêm chuỗi này trước khi băm, để mã máy của phần mềm này không trùng với
# mã máy mà một phần mềm khác cũng băm từ MachineGuid tính ra.
_MUOI = "MNT-FB-AutoPost"

# Bỏ các ký tự dễ đọc nhầm khi đánh vần qua điện thoại:
#   0 với O, 1 với I và L, 8 với B, 5 với S, 2 với Z
_CHU_CAI = "34679ACDEFGHJKMNPQRTUVWXY"


def _guid_windows():
    """MachineGuid do Windows sinh lúc cài hệ điều hành. Sống lâu nhất trong
    các thứ nhận dạng máy: cài lại phần mềm hay thay ổ cứng phụ đều không đổi."""
    try:
        r = subprocess.run(
            ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography",
             "/v", "MachineGuid"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for dong in (r.stdout or "").splitlines():
            if "MachineGuid" in dong:
                return dong.split()[-1].strip()
    except Exception:
        pass
    return ""


def _nguon_goc():
    """Chuỗi gốc để băm. Ưu tiên MachineGuid; không có thì lùi về địa chỉ MAC.

    MAC kém ổn định hơn — cắm thêm card mạng hay bật máy ảo là có thể đổi — nên
    chỉ dùng khi không còn cách nào. Thà mã máy đổi còn hơn phần mềm không chạy.
    """
    g = _guid_windows()
    if g:
        return "guid:" + g
    return "mac:" + format(uuid.getnode(), "012x")


def ma_may():
    """Trả về mã máy dạng ABCD-EFGH-JKMN."""
    thô = hashlib.sha256((_MUOI + "|" + _nguon_goc()).encode()).digest()
    # Đổi sang bảng chữ cái đã bỏ ký tự dễ nhầm, thay vì hex: hex có cả 0 và
    # nhiều chữ số, đọc qua điện thoại rất dễ sai.
    n = int.from_bytes(thô[:16], "big")
    ky_tu = []
    for _ in range(12):
        n, du = divmod(n, len(_CHU_CAI))
        ky_tu.append(_CHU_CAI[du])
    s = "".join(ky_tu)
    return f"{s[0:4]}-{s[4:8]}-{s[8:12]}"


def hop_le(ma):
    """Kiểm dạng của một mã máy người dùng gõ vào."""
    if not ma:
        return False
    s = str(ma).strip().upper().replace(" ", "")
    phan = s.split("-")
    if len(phan) != 3:
        return False
    return all(len(p) == 4 and all(c in _CHU_CAI for c in p) for p in phan)


if __name__ == "__main__":
    print("Mã máy này:", ma_may())
