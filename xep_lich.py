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
    Đổi `ti_le` % slot đăng của các acc trong `accs` sang `hoat_dong`, rải đều
    trên TOÀN TRỤC thời gian. Dùng cho loại đăng "X_*": 25 → 75% đăng, 25% comment.

    Chỉ đụng slot đang là 'dang_bai' — slot đã bị nuôi nick chiếm thì giữ nguyên,
    nên phải gọi SAU bước chuyển nuôi.

    CÁCH LÀM: đếm tổng rồi chia đều, KHÔNG cộng dồn theo từng acc
    ─────────────────────────────────────────────────────────────
    1. Đếm N = tổng slot đăng đổi được, và n_a = số slot của từng acc.
    2. Hạn mức mỗi acc  k_a = làm tròn(n_a × ti_le / 100)  → giữ công bằng: acc
       đăng nhiều thì comment nhiều, không để một acc gánh hết.
    3. K = Σ k_a. Vị trí lý tưởng của phiên comment thứ j là (2j+1)·N / 2K —
       chia trục thành K khoảng đều nhau rồi lấy điểm giữa mỗi khoảng.
    4. Với từng vị trí lý tưởng, tìm slot GẦN NHẤT còn trống mà acc của nó chưa
       hết hạn mức. Dò ra hai phía nên khi vị trí lý tưởng trúng acc đã hết hạn
       mức thì vẫn đặt được cạnh đó, không mất phiên nào.

    VÌ SAO PHẢI LÀM TOÀN CỤC — bản cũ cộng dồn theo acc đã hỏng thật
    ────────────────────────────────────────────────────────────────
    Bản trước cho mỗi acc một bộ tích luỹ riêng, lệch pha nhau `k × 100 / n`. Nó
    chỉ tách được lần đổi ĐẦU TIÊN trong dãy riêng của mỗi acc, không kiểm soát
    được khoảng cách trên trục chung. Chỉ cần một slot nuôi nick chen vào là pha
    của acc đó xê dịch, và các acc đụng nhau:

        ..N....CCC.........CCC.........CCC.........CC     ← bản cũ

    Đo trên đúng lịch homestay của người dùng (3 acc xoay vòng 4 phút, tỉ lệ 25%,
    1 slot nuôi): 11 phiên comment, 7 lần dính liền nhau, khoảng cách nhảy
    1-1-10-1-1-10. Cách chia toàn cục cho ra khoảng cách đều 4 hoặc 5.

    Sửa `schedule` tại chỗ, trả về số slot đã đổi.
    """
    ti_le = max(0, min(100, int(ti_le or 0)))
    if not accs or ti_le == 0:
        return 0
    accs = set(accs)

    # Danh sách slot đổi được, giữ đúng thứ tự thời gian của lịch.
    vi_tri, chu = [], []
    for i, row in enumerate(schedule):
        ten = row.get("ten_acc")
        if ten in accs and (row.get("hoat_dong") or "dang_bai") == "dang_bai":
            vi_tri.append(i)
            chu.append(ten)
    N = len(vi_tri)
    if N == 0:
        return 0

    # Tổng số phiên comment cần có — làm tròn nửa lên, tính bằng số nguyên.
    K = (N * ti_le + 50) // 100
    if K == 0:
        return 0

    # Chia K cho từng acc theo PHẦN DƯ LỚN NHẤT, không làm tròn từng acc rời rạc.
    # Làm tròn rời rạc thì tổng bị lệch: 5 acc × 12 slot × 20% = 2.4 mỗi acc, làm
    # tròn xuống 2 nên tổng ra 10 thay vì 12 — tụt tỉ lệ từ 20% xuống 16.7%.
    dem, thu_tu = {}, []
    for ten in chu:
        if ten not in dem:
            dem[ten] = 0
            thu_tu.append(ten)
        dem[ten] += 1
    han = {ten: (n_a * ti_le) // 100 for ten, n_a in dem.items()}
    du  = {ten: (n_a * ti_le) % 100 for ten, n_a in dem.items()}
    con = K - sum(han.values())
    # Ưu tiên acc có phần dư lớn nhất; dư bằng nhau thì theo thứ tự xuất hiện
    # trong lịch để kết quả tất định, gọi lại hai lần ra y hệt.
    uu_tien = sorted(thu_tu, key=lambda t: (-du[t], thu_tu.index(t)))
    i = 0
    while con > 0 and uu_tien:
        ten = uu_tien[i % len(uu_tien)]
        if han[ten] < dem[ten]:        # không vượt số slot acc đó có
            han[ten] += 1
            con -= 1
        i += 1
        if i > len(uu_tien) * 2:       # mọi acc đã đầy, không chia tiếp được
            break
    K -= con                            # phần không chia được thì bỏ

    # Khoảng cách tối thiểu mong muốn giữa hai phiên comment. Bằng nửa nhịp lý
    # tưởng — đủ chặt để không dính cụm, đủ lỏng để luôn tìm được chỗ.
    #
    # Vì sao cần chặn riêng thay vì tin vào vị trí lý tưởng: khi nhịp lý tưởng
    # (100/ti_le) TRÙNG số acc — ví dụ 5 acc, tỉ lệ 20% → nhịp 5 — thì mọi vị trí
    # lý tưởng rơi đúng vào cùng MỘT acc (các slot cách nhau 5 đều thuộc một acc
    # trong vòng xoay 5). Acc đó hết hạn mức là thuật toán phải dò sang bên cạnh
    # và sinh ra hai phiên liền kề. Ca đó không có cách chia hoàn hảo nào cả —
    # nhưng dính LIỀN NHAU thì chặn được, và đó mới là thứ nhìn thấy trên lịch.
    khoang_min = max(2, (N // K) // 2)

    da_dung = [False] * N
    doi = 0
    for j in range(K):
        # Điểm giữa khoảng thứ j khi chia N slot thành K phần đều nhau.
        p = ((2 * j + 1) * N) // (2 * K)
        chon = -1
        # Thử với ràng buộc giãn cách trước; không được thì nới dần rồi mới thả.
        for gap in range(khoang_min, 0, -1):
            for d in range(N):
                for q in ((p + d), (p - d)) if d else (p,):
                    if not (0 <= q < N) or da_dung[q]:
                        continue
                    if han.get(chu[q], 0) <= 0:
                        continue
                    if any(da_dung[k] for k in
                           range(max(0, q - gap + 1), min(N, q + gap))):
                        continue
                    chon = q
                    break
                if chon >= 0:
                    break
            if chon >= 0:
                break
        if chon < 0:
            break                      # hết slot hợp lệ
        da_dung[chon] = True
        han[chu[chon]] -= 1
        schedule[vi_tri[chon]]["hoat_dong"] = hoat_dong
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
