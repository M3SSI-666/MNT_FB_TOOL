"""
Dừng sạch server + mọi runner. Dùng cho RESTART.bat và UPDATE.bat.

VÌ SAO KHÔNG DÙNG .BAT NỮA — đo trên máy thật ngày 19/09:

  taskkill /F /PID <server>      → treo, cửa sổ cmd đứng im ở dòng
                                   "Kill Flask server PID 13680"
  taskkill /F /T /PID <runner>   → treo >20 giây, chạy hai lần, tiến trình
                                   vẫn sống
  Get-CimInstance Win32_Process  → 30 giây chưa xong khi máy đang tải nặng,
  (lọc theo CommandLine)           và trả CommandLine rỗng cho tiến trình do
                                   Task Scheduler khởi chạy → không thấy gì

Cả ba cách đều phải đi hỏi vòng qua RPC/WMI rồi duyệt tiến trình của CẢ MÁY.
Máy này lúc chạy nhiều phiên có hơn hai trăm tiến trình nên chúng nghẽn ở đó.

Cách ở đây: chụp một ảnh danh sách tiến trình (CreateToolhelp32Snapshot) rồi gọi
thẳng TerminateProcess. Cùng phép đo đó: chết trong 0,00 giây.

Nguồn tìm runner cũng khác: đọc FILE KHOÁ `.runner_<loai>.lock`. Hệ điều hành chỉ
nhả khoá khi tiến trình giữ nó chết, nên đây là câu trả lời duy nhất không nói
dối — không phụ thuộc file pid còn hay mất, cũng không phụ thuộc quyền đọc dòng
lệnh.

Dùng:
    python dung_het.py            # dừng hết
    python dung_het.py 13680      # dừng hết, kèm mấy PID chỉ đích danh
"""
import os
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Toàn bộ phần xử lý tiến trình dùng chung với server — xem `tien_trinh.py`.
import tien_trinh


def pid_giu_khoa() -> list:
    """PID của runner đang giữ khoá. Không import được thì bỏ qua, đừng chết."""
    try:
        import khoa_runner as kr
    except Exception:
        return []
    ra = []
    for loai in ("homestay", "thue", "ban", "page", "nuoi"):
        try:
            if kr.dang_giu(loai):
                p = kr.pid_dang_giu(loai)
                if p:
                    ra.append(p)
        except Exception:
            pass
    return ra


def pid_tu_file() -> list:
    ra = []
    for loai in ("homestay", "thue", "ban", "page", "nuoi"):
        f = f".runner_{loai}.pid"
        if os.path.exists(f):
            try:
                ra.append(int(open(f).read().strip()))
            except (OSError, ValueError):
                pass
            try:
                os.unlink(f)
            except OSError:
                pass
    return ra


def main():
    them = [int(a) for a in sys.argv[1:] if a.isdigit()]
    goc  = list(dict.fromkeys(them + pid_giu_khoa() + pid_tu_file()))
    if not goc:
        print("  Khong co tien trinh nao de dung.")
        return
    t0   = time.time()
    xong = tien_trinh.diet_cay(goc, han_giay=10)
    sot  = [p for p in goc if p not in xong]
    print(f"  Da dung {len(xong)}/{len(goc)} tien trinh trong {time.time()-t0:.2f}s"
          + (f" | CHUA dung duoc: {sot}" if sot else ""))


if __name__ == "__main__":
    main()
