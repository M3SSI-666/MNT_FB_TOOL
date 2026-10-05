"""
Quét toàn bộ mã nguồn tìm TÊN BIẾN ĐƯỢC ĐỌC MÀ KHÔNG HỀ TỒN TẠI.

Vì sao cần: ngày 22/09, commit "Sửa: quy kết spam cho sai nick" để lại trong
`comment_bai._ket_phien` một dòng đọc biến `kq` vốn không có ở đó. Dòng ấy nằm
trong `try/except Exception` nên `NameError` bị nuốt thành một dòng log hiền
lành "Kết phiên không trọn vẹn", và **bước dò spam của phiên comment không hề
chạy suốt 13 ngày** — 178 lần hỏng trên 184 phiên mà bảng vẫn báo bình thường.

Python không bắt được loại lỗi này lúc nạp module: `NameError` chỉ nổ khi dòng
đó chạy tới. Mà chỗ nguy hiểm nhất lại chính là nhánh hiếm chạy, bọc trong
`except` rộng — đúng chỗ mắt người khó soi nhất.

Chạy trực tiếp: `python kiem_ten_bien.py`
"""
import ast
import builtins
import pathlib

BUILTIN = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "_"}


def _ten_duoc_gan(node) -> set:
    """Mọi tên mà THÂN node này tự tạo ra — không chui vào hàm/lớp con."""
    ra = set()

    def di(n, goc=False):
        if not goc and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef)):
            ra.add(n.name)          # tên hàm con thì thấy, thân nó thì không
            return
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            ra.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                ra.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            ra.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            ra.update(n.names)
        elif isinstance(n, ast.arg):
            ra.add(n.arg)
        for con in ast.iter_child_nodes(n):
            di(con)

    di(node, goc=True)
    return ra


def _soi(node, ngoai: set, duong_dan: str, ten_ham: str, loi: list):
    """Soi một phạm vi, mang theo `ngoai` = tên của mọi phạm vi bao ngoài."""
    trong = ngoai | _ten_duoc_gan(node)

    def di(n, goc=False):
        if not goc and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _soi(n, trong, duong_dan, n.name, loi)
            return
        if not goc and isinstance(n, ast.ClassDef):
            _soi(n, trong, duong_dan, n.name, loi)
            return
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) \
                and n.id not in trong:
            loi.append((duong_dan, n.lineno, ten_ham, n.id))
        for con in ast.iter_child_nodes(n):
            di(con)

    di(node, goc=True)


def quet(thu_muc: str = ".") -> list:
    """Trả [(file, dòng, hàm, tên), ...] — rỗng là sạch."""
    loi = []
    for p in sorted(pathlib.Path(thu_muc).glob("*.py")):
        try:
            cay = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        _soi(cay, BUILTIN, p.name, "<mức file>", loi)
    return loi


if __name__ == "__main__":
    ds = quet()
    if ds:
        print(f"❌ {len(ds)} tên được đọc mà không tồn tại:")
        for f, l, h, t in ds:
            print(f"   {f}:{l}  trong {h}()  →  {t}")
    else:
        print("✅ Không có tên nào được đọc mà chưa định nghĩa.")
