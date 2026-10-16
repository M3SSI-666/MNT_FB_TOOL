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
    vi_tri, chu = _slot_doi_duoc(schedule, accs)
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

    return _rai_deu(schedule, vi_tri, chu, han, hoat_dong)


def _slot_doi_duoc(schedule: list, accs: set):
    """Vị trí + tên acc của các slot còn 'dang_bai' thuộc `accs`, theo thứ tự lịch."""
    vi_tri, chu = [], []
    for i, row in enumerate(schedule):
        ten = row.get("ten_acc")
        if ten in accs and (row.get("hoat_dong") or "dang_bai") == "dang_bai":
            vi_tri.append(i)
            chu.append(ten)
    return vi_tri, chu


def chuyen_slot_so_luong(schedule: list, han_map: dict,
                         hoat_dong: str = "marketplace") -> int:
    """Đổi ĐÚNG `han_map[acc]` slot của từng acc sang `hoat_dong`, rải đều.

    Khác `chuyen_slot_theo_ti_le` ở chỗ nhận SỐ LƯỢNG tuyệt đối mỗi acc thay vì
    một tỉ lệ chung. Cần cho trường hợp mỗi acc một % riêng tính trên TỔNG phiên
    của chính nó: tính sẵn số lượng ngoài rồi gọi vào đây, nên comment% và
    marketplace% đều là % của tổng chứ không phải của phần còn lại.

    Số vượt quá slot acc đó còn trống thì tự cắt. Sửa tại chỗ, trả về số đã đổi.
    """
    accs = {t for t, k in han_map.items() if k > 0}
    if not accs:
        return 0
    vi_tri, chu = _slot_doi_duoc(schedule, accs)
    if not vi_tri:
        return 0
    dem = {}
    for ten in chu:
        dem[ten] = dem.get(ten, 0) + 1
    # Không đổi nhiều hơn số slot acc đó thực có.
    han = {ten: min(int(han_map.get(ten, 0) or 0), dem.get(ten, 0)) for ten in dem}
    return _rai_deu(schedule, vi_tri, chu, han, hoat_dong)


def _rai_deu(schedule: list, vi_tri: list, chu: list, han: dict,
             hoat_dong: str) -> int:
    """Đặt các phiên vào slot, rải đều trên trục, giữ `han` mỗi acc. Lõi dùng
    chung cho cả chuyển theo tỉ lệ lẫn theo số lượng."""
    N = len(vi_tri)
    K = sum(han.values())
    if N == 0 or K == 0:
        return 0

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


def rai_tu_khoa(rows: list, pool: list, khoa: str = "ten_acc", can=None) -> None:
    """Gán từ khoá cho các dòng lịch, XEN KẼ theo thứ tự thời gian của cả bảng.

    Hai luật, theo thứ tự ưu tiên:
      1. Hai dòng LIỀN NHAU không trùng từ khoá — quay vòng A → B → C → D → A…
      2. Mỗi nick cũng quay ĐỀU đủ các từ khoá: ưu tiên từ khoá nick đó dùng ít
         nhất, và không lặp lại từ khoá nó vừa dùng ở phiên trước.

    Bản cũ chia theo nick: nick thứ i bắt đầu ở từ khoá `i × n_kw ÷ n_nick`
    rồi tự tiến một bước mỗi phiên của nó. 11 nick, 4 từ khoá → điểm bắt đầu
    0,0,0,1,1,1,2,2,2,3,3 — ba nick đứng liền nhau dùng chung một từ khoá, bảng
    lịch thành từng cụm 3 dòng trùng nhau (người dùng thấy 13/10).

    Chỉ quay vòng chung thì không đủ: số nick chia hết cho số từ khoá (8 nick,
    4 từ khoá) là mỗi nick dính CỐ ĐỊNH một từ khoá cả ngày — luật 2 chặn việc đó.

    `rows` phải xếp theo thời gian. `can(row)` → dòng có cần từ khoá không;
    dòng không cần thì để trống và không làm lệch vòng.
    """
    pool = [k.strip() for k in (pool or []) if k and k.strip()]
    n = len(pool)
    if not n:
        return
    g, truoc = 0, None
    cuoi_acc, dem_acc = {}, {}
    for r in rows:
        if can is not None and not can(r):
            r["tu_khoa"] = ""
            continue
        acc = r.get(khoa, "")
        dem = dem_acc.setdefault(acc, [0] * n)
        vong = [(g + j) % n for j in range(n)]
        ung = ([i for i in vong if i != truoc and i != cuoi_acc.get(acc)]
               or [i for i in vong if i != truoc] or vong)
        i = min(ung, key=lambda x: (dem[x], vong.index(x)))
        r["tu_khoa"] = pool[i]
        dem[i] += 1
        cuoi_acc[acc] = truoc = i
        g = (i + 1) % n



def _hien_content(r: dict) -> bool:
    """Dòng có hiện mã content trên bảng lịch (đăng bài / Marketplace / đăng page)."""
    return (r.get("hoat_dong") or "dang_bai") in ("dang_bai", "marketplace", "dang_page")


def rai_content(rows: list, contents: list, khoa: str = "ten_acc", hien=None) -> None:
    """Gán content cho các dòng lịch: TRẢI ĐỀU cho từng nick, XEN KẼ trên bảng.

    Chọn cho từng dòng theo thứ tự thời gian, nới dần từng bậc tới khi có ứng viên:
      1. Content nick đó dùng ÍT NHẤT (đi hết một vòng mới lặp lại), khác dòng
         đăng ngay trước trên bảng, khác content nick vừa đăng.
      2. Nới: content nick đó dùng nhiều hơn tối đa 1 lần — vẫn khác dòng trước
         và khác content vừa đăng.
      3. Nới tiếp: cho nick lặp content vừa đăng (không quá 2 lần liên tiếp) để
         hai dòng liền nhau trên bảng vẫn khác nhau.
      4. Bất đắc dĩ: trùng dòng trước.
    Hoà thì chọn content cả bảng dùng ít nhất, rồi theo vòng quay.

    Bản cũ cho mỗi nick một con trỏ riêng bắt đầu ở ô "Content đầu" — các nick
    đứng liền nhau không biết nhau nên bảng ra cụm 5–9 dòng cùng content
    (lịch Bán thật: 79% cặp dòng liền nhau trùng). Ưu tiên tuyệt đối "liền nhau
    khác nhau" cũng sai: chỉ 2 content mà số nick chẵn là có nick đăng MỘT
    content cả ngày — tệ hơn nhiều. Với 2 content không cách nào đạt cả hai
    (lịch Bán thật còn ~14% trùng); từ 4 content trở lên thì gần như 0%.

    Chạy SAU khi đã chuyển slot nuôi/comment/Marketplace, vì chỉ dòng `hien(row)`
    (mặc định: đăng bài + Marketplace) mới hiện mã content. Dòng comment / nuôi
    vẫn được gán content (slot comment có thể thành phiên nhử đăng bài) nhưng
    không làm lệch vòng.
    """
    pool = list(dict.fromkeys(str(c).strip() for c in (contents or []) if c and str(c).strip()))
    n = len(pool)
    if not n:
        return
    hien = hien or _hien_content
    tong = [0] * n
    dem_acc, da_dang = {}, {}
    g, truoc = 0, None
    for r in rows:
        acc = r.get(khoa, "")
        dem = dem_acc.setdefault(acc, [0] * n)
        ls = da_dang.setdefault(acc, [])
        cuoi = ls[-1] if ls else None
        vong = [(g + j) % n for j in range(n)]
        m = min(dem)
        it_nhat = [i for i in vong if dem[i] == m]
        if not hien(r):
            ung = [i for i in it_nhat if i != cuoi] or it_nhat
            r["ma_content"] = pool[ung[0]]
            continue
        lap3 = lambda i: len(ls) >= 2 and ls[-1] == ls[-2] == i
        ung = ([i for i in it_nhat if i != truoc and i != cuoi]
               or [i for i in vong if dem[i] <= m + 1 and i != truoc and i != cuoi]
               or [i for i in vong if dem[i] <= m + 1 and i != truoc and not lap3(i)]
               or [i for i in it_nhat if i != truoc] or it_nhat)
        i = min(ung, key=lambda x: (dem[x], tong[x], vong.index(x)))
        r["ma_content"] = pool[i]
        dem[i] += 1
        tong[i] += 1
        ls.append(i)
        truoc = i
        g = (i + 1) % n
