"""
xep_lich.py — Phân bổ thời điểm cho các phiên trong ngày.

Mục tiêu: bài đăng **phủ đều** khung giờ, để trong nhóm lúc nào cũng có bài của
mình vừa nổi lên — thay vì dồn cục rồi để hở hàng chục phút.

Một phiên **comment** được coi ngang một phiên **đăng bài**: cùng nằm trong một
vòng xoay, cùng tính vào tổng lực. Acc để `Nghỉ 12 phút` nghĩa là 5 phiên/giờ,
bất kể phiên đó là đăng hay comment.

Cách tính
─────────
    tổng lực = Σ (60 / nghỉ_của_acc)      → số phiên mỗi giờ của cả đội
    độ nén   = 60 / tổng lực              → khoảng cách lý tưởng giữa 2 phiên

Acc thứ i khởi điểm ở `start + i × độ_nén` (lệch pha), rồi mỗi lần được xếp thì
đẩy mốc kế tiếp lên `nghỉ` phút. Mỗi vòng chọn acc nào đang tới lượt sớm nhất.

Vì sao cần ép giãn cách tối thiểu
─────────────────────────────────
Chỉ dựa vào "ai tới lượt sớm nhất" là chưa đủ. Khi các acc có chu kỳ KHÁC nhau
(vd 3 acc nghỉ 12p + 2 acc nghỉ 30p), sau vài vòng chúng trôi vào trùng pha và
sinh ra khoảng cách **0 phút** — hai phiên nổ cùng một phút, mở hai trình duyệt
một lúc, rồi để hở 6 phút phía sau. Đo trên cấu hình đó: 22 lần đụng độ, độ lệch
chuẩn khoảng cách 1.60.

Ép giãn cách tối thiểu = `độ_nén × HE_SO_GIAN_CACH` khắc phục:

    hệ số   slot   gap nhỏ nhất   độ lệch chuẩn
    ─────   ────   ────────────   ─────────────
    (không)  419        0             1.60
    0.70     415        2             1.33
    0.85     405        2             1.02      ← đang dùng
    1.00     385        3             0.88

Chọn 0.85: hết đụng độ, đều hơn hẳn, mà chỉ mất ~3% số slot. Ép lên 1.00 thì đều
nhất nhưng mất 8% slot và tạo ra nhịp **đều tăm tắp** — bản thân nhịp cố định
lại là dấu hiệu máy, đúng thứ `utils.jitter_ms` sinh ra để tránh.
"""

HE_SO_GIAN_CACH = 0.85


def tong_luc(accs) -> float:
    """Tổng số phiên mỗi giờ của cả đội. `accs`: [{'ten','nghi'}, ...]."""
    return sum(60 / max(1, int(a.get("nghi") or 1)) for a in accs)


def do_nen(accs) -> float:
    """Khoảng cách lý tưởng giữa hai phiên liên tiếp (phút)."""
    t = tong_luc(accs)
    return 60 / t if t else 60.0


def phan_bo_lich(accs, start_min: int, end_min: int,
                 he_so_gian_cach: float = HE_SO_GIAN_CACH) -> list:
    """
    Trả về [(phút_trong_ngày, tên_acc), ...] đã sắp theo thời gian.

    `accs`      : [{'ten': str, 'nghi': phút}, ...] — gồm CẢ acc đăng bài lẫn
                  acc chỉ comment; hàm này không phân biệt, đó là chủ đích.
    `start_min` / `end_min` : phút tính từ 00:00. Qua đêm thì end > 24*60.
    """
    accs = [a for a in accs if (a.get("ten") or "").strip()]
    if not accs or end_min <= start_min:
        return []

    dn = do_nen(accs)
    # Giãn cách tối thiểu — tối thiểu 1 phút, vì cùng một phút là đụng độ thật:
    # hai trình duyệt mở cùng lúc trên cùng một máy.
    gian_cach = max(1.0, dn * he_so_gian_cach)

    moc_ke = {a["ten"]: start_min + i * dn for i, a in enumerate(accs)}
    ra, truoc = [], None

    while True:
        cho = [(moc_ke[a["ten"]], i, a) for i, a in enumerate(accs)
               if moc_ke[a["ten"]] <= end_min]
        if not cho:
            break
        # Ai tới lượt sớm nhất thì được xếp trước. `i` phá hoà để kết quả tái
        # lập được, không phụ thuộc thứ tự dict.
        cho.sort(key=lambda x: (x[0], x[1]))
        t, _, acc = cho[0]

        if truoc is not None:
            t = max(t, truoc + gian_cach)
        phut = round(t)
        if phut > end_min:
            break

        ra.append((phut, acc["ten"]))
        truoc = t
        # Đẩy mốc kế tiếp từ thời điểm THỰC SỰ được xếp, không phải mốc lý
        # tưởng — nếu không, phần bị đẩy lùi do giãn cách sẽ dồn lại và acc đó
        # chạy dày hơn `nghỉ` của chính nó.
        moc_ke[acc["ten"]] = t + max(1, int(acc.get("nghi") or 1))

    return ra


def chuyen_slot_theo_ti_le(schedule: list, accs, ti_le: int,
                           hoat_dong: str = "comment") -> int:
    """
    Với acc trong `accs`, đổi `ti_le` % số slot đăng của acc đó sang `hoat_dong`.
    Dùng cho loại đăng "X_*": mặc định 25 → 75% đăng bài, 25% comment.

    Rải đều bằng bộ tích luỹ (Bresenham): mỗi slot cộng `ti_le`, chạm 100 thì
    đổi slot đó rồi trừ 100. Tính bằng SỐ NGUYÊN nên không trôi số như cộng dồn
    số thực qua vài trăm slot.

    LỆCH PHA GIỮA CÁC ACC — chỗ này mới là mấu chốt
    ────────────────────────────────────────────────
    Nếu mọi acc đều bắt đầu tích luỹ từ 0 thì acc nào cũng đổi đúng slot thứ 4
    CỦA RIÊNG NÓ. Mà lịch xoay vòng đều giữa các acc, nên slot thứ 4 của cả 4
    acc rơi liền kề nhau → dính thành cụm:

        ............CCCC........      ← 4 phiên comment liên tiếp

    Cho acc thứ k khởi điểm ở `k × 100 / n` thì mỗi acc chạm ngưỡng ở một nhịp
    khác nhau, và các phiên comment rải đều xen kẽ giữa các slot đăng:

        ...C..C..C..C..C..C.....

    Chỉ đụng slot đang là 'dang_bai' — slot đã bị nuôi nick chiếm thì giữ nguyên,
    nên phải gọi SAU bước chuyển nuôi.

    Sửa `schedule` tại chỗ, trả về số slot đã đổi.
    """
    ti_le = max(0, min(100, int(ti_le or 0)))
    if not accs or ti_le == 0:
        return 0
    accs = set(accs)

    # Thứ tự XUẤT HIỆN trong lịch, không phải thứ tự bảng chữ cái — đó chính là
    # thứ tự xoay vòng, nên lệch pha theo nó mới tách được các acc kề nhau.
    thu_tu = []
    for row in schedule:
        ten = row.get("ten_acc")
        if ten in accs and ten not in thu_tu:
            thu_tu.append(ten)
    n = len(thu_tu) or 1

    tich_luy = {ten: (i * 100) // n for i, ten in enumerate(thu_tu)}

    doi = 0
    for row in schedule:
        ten = row.get("ten_acc")
        if ten not in tich_luy:
            continue
        if (row.get("hoat_dong") or "dang_bai") != "dang_bai":
            continue
        tich_luy[ten] += ti_le
        if tich_luy[ten] >= 100:
            tich_luy[ten] -= 100
            row["hoat_dong"] = hoat_dong
            doi += 1
    return doi


def thong_ke(ra: list) -> dict:
    """Số liệu để hiển thị / kiểm tra: khoảng cách giữa các phiên liên tiếp."""
    if len(ra) < 2:
        return {"so_slot": len(ra), "gap_min": 0, "gap_max": 0, "gap_tb": 0.0}
    gaps = [ra[i + 1][0] - ra[i][0] for i in range(len(ra) - 1)]
    tb = sum(gaps) / len(gaps)
    return {
        "so_slot": len(ra),
        "gap_min": min(gaps),
        "gap_max": max(gaps),
        "gap_tb":  round(tb, 2),
        "lech_chuan": round((sum((g - tb) ** 2 for g in gaps) / len(gaps)) ** 0.5, 2),
    }
