/* app.js — MNT_FB UI logic */

// ── Toast ─────────────────────────────────────────────────────
const Toast = {
    show(msg, type="info", dur=3000) {
        const el = document.createElement("div");
        el.className = `toast ${type}`;
        el.innerHTML = `<span>${type==="success"?"✓":type==="error"?"✕":"ℹ"}</span><span>${msg}</span>`;
        document.getElementById("toast-container").appendChild(el);
        setTimeout(() => { el.classList.add("dismissing"); setTimeout(()=>el.remove(),200); }, dur);
    },
    success: m => Toast.show(m,"success"),
    error:   m => Toast.show(m,"error"),
    info:    m => Toast.show(m,"info"),
};

// ── Modal helpers ─────────────────────────────────────────────
function openModal(title, bodyHtml) {
    document.getElementById("modal-title").textContent = title;
    document.getElementById("modal-body").innerHTML    = bodyHtml;
    document.getElementById("modal-overlay").style.display = "block";
    document.getElementById("modal-panel").style.display   = "block";
}
function closeModal() {
    document.getElementById("modal-overlay").style.display = "none";
    document.getElementById("modal-panel").style.display   = "none";
}

// ── Lightbox ──────────────────────────────────────────────────
let _lbImgs=[], _lbIdx=0;
let _lbMeta = {name:""};               // meta cho tên file download

function openLightbox(imgs, meta={}) {
    _lbImgs = typeof imgs==="string" ? JSON.parse(imgs) : imgs;
    if(!_lbImgs.length) return;
    _lbIdx  = 0;
    _lbMeta = {name: meta.name||""};
    let lb=document.getElementById("lightbox");
    if(!lb){
        lb=document.createElement("div"); lb.id="lightbox";
        lb.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:2000;display:flex;flex-direction:column;align-items:center;justify-content:center";
        lb.innerHTML=`
            <div style="position:absolute;top:14px;right:16px;display:flex;gap:10px;align-items:center">
                <a id="lb-dl" href="#" download onclick="lbDownload(event)"
                   style="background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;font-size:14px;font-weight:700;
                          padding:9px 20px;border-radius:9px;text-decoration:none;cursor:pointer;
                          box-shadow:0 2px 10px rgba(99,102,241,.5);letter-spacing:.02em">
                   ⬇ Tải ảnh này
                </a>
                <button onclick="lbDownloadAll()"
                    style="background:linear-gradient(135deg,#10b981,#059669);color:#fff;font-size:14px;font-weight:700;
                           padding:9px 20px;border:none;border-radius:9px;cursor:pointer;
                           box-shadow:0 2px 10px rgba(16,185,129,.5);letter-spacing:.02em">
                    ⬇ Tải tất cả
                </button>
                <button onclick="closeLightbox()"
                    style="background:rgba(255,255,255,.15);color:#fff;font-size:22px;width:38px;height:38px;
                           border:none;cursor:pointer;border-radius:50%;line-height:1">✕</button>
            </div>
            <button onclick="lbPrev()" style="position:absolute;left:16px;top:50%;transform:translateY(-50%);background:rgba(255,255,255,.15);color:#fff;font-size:28px;border:none;cursor:pointer;padding:10px 16px;border-radius:8px">‹</button>
            <button onclick="lbNext()" style="position:absolute;right:16px;top:50%;transform:translateY(-50%);background:rgba(255,255,255,.15);color:#fff;font-size:28px;border:none;cursor:pointer;padding:10px 16px;border-radius:8px">›</button>
            <img id="lb-img" style="max-width:90vw;max-height:78vh;object-fit:contain;border-radius:6px">
            <div id="lb-counter" style="color:#fff;font-size:13px;margin-top:12px;opacity:.7"></div>
            <div id="lb-thumbs" style="display:flex;gap:6px;margin-top:10px;overflow-x:auto;max-width:90vw;padding:4px"></div>`;
        lb.addEventListener("click", e=>{ if(e.target===lb) closeLightbox(); });
        document.body.appendChild(lb);
    }
    lb.style.display="flex"; renderLb();
}

function closeLightbox(){ const lb=document.getElementById("lightbox"); if(lb) lb.style.display="none"; }

function _lbFilename(url, idx){
    // Lấy extension từ URL
    const ext = (url.split("?")[0].split(".").pop().toLowerCase().match(/^(jpg|jpeg|png|webp|gif)$/) || ["jpg"])[0];
    const base = _lbMeta.name || "image";
    return `${base}_${idx + 1}.${ext}`;
}

function renderLb(){
    const url = _lbImgs[_lbIdx];
    document.getElementById("lb-img").src = url;
    document.getElementById("lb-counter").textContent = `${_lbIdx+1} / ${_lbImgs.length}`;
    document.getElementById("lb-thumbs").innerHTML = _lbImgs.map((u,i)=>
        `<img src="${u}" onclick="lbGoto(${i})" style="height:52px;width:52px;object-fit:cover;border-radius:4px;cursor:pointer;opacity:${i===_lbIdx?1:.4};border:2px solid ${i===_lbIdx?"var(--accent)":"transparent"}">`
    ).join("");
    const dl = document.getElementById("lb-dl");
    if(dl){ dl.href=url; dl.download=_lbFilename(url, _lbIdx); }
}

function lbPrev(){ _lbIdx=(_lbIdx-1+_lbImgs.length)%_lbImgs.length; renderLb(); }
function lbNext(){ _lbIdx=(_lbIdx+1)%_lbImgs.length; renderLb(); }
function lbGoto(i){ _lbIdx=i; renderLb(); }

async function _downloadBlob(url, filename){
    try{
        const r=await fetch(url); const blob=await r.blob();
        const a=document.createElement("a");
        a.href=URL.createObjectURL(blob); a.download=filename; a.click();
        URL.revokeObjectURL(a.href);
    } catch { window.open(url,"_blank"); }
}

function lbDownload(e){
    e.preventDefault();
    _downloadBlob(_lbImgs[_lbIdx], _lbFilename(_lbImgs[_lbIdx], _lbIdx));
}

async function lbDownloadAll(){
    for(let i=0;i<_lbImgs.length;i++){
        await _downloadBlob(_lbImgs[i], _lbFilename(_lbImgs[i], i));
        await new Promise(r=>setTimeout(r,350));
    }
    Toast.success(`✅ Đã tải ${_lbImgs.length} ảnh`);
}

// ── Navigation ────────────────────────────────────────────────
const PAGE_TITLES = {
    accounts:"Tài khoản", pages:"Page", content:"Content",
    "uid-groups":"UID Nhóm",
    "lich-homestay":"Lịch Homestay", "lich-thue":"Lịch Thuê",
    "lich-ban":"Lịch Bán", "lich-page":"Lịch Đăng Page", "lich-nuoi":"Lịch Nuôi nick",
    "comment-posts":"Bài đi Comment",
    "tham-gia-nhom":"Tham gia nhóm", "hanh-dong":"Hành động", logs:"Logs",
};

let _logInterval = null;
function navigate(page) {
    if(page!=="logs") { clearInterval(_logInterval); _logInterval=null; }
    _stopSchedAutoRefresh();   // rời trang lịch → ngừng tự làm mới
    document.querySelectorAll(".nav-item").forEach(el=>el.classList.toggle("active",el.dataset.page===page));
    document.querySelectorAll(".page").forEach(el=>el.style.display=el.id===`page-${page}`?"":"none");
    document.getElementById("header-title").textContent = PAGE_TITLES[page]||page;
    loadPageData(page);
}

function loadPageData(page) {
    if(page==="accounts")        loadAccounts();
    else if(page==="pages")      loadPages();
    else if(page==="content")    openContentTab(_currentContentLoai);
    else if(page==="uid-groups") loadUidGroups();
    else if(page==="comment-posts") renderCommentPostsPage();
    else if(page==="tham-gia-nhom") loadJoinSchedules();
    else if(page==="hanh-dong")     loadRunnerStatus();
    else if(page==="logs")       { loadLogs(); _logInterval=setInterval(loadLogs,2000); }
    else if(page.startsWith("lich-")) {
        const loai=page.replace("lich-","");
        renderSchedulePage(loai);
        loadSchedule(loai);
        _startSchedAutoRefresh(loai);
    }
}

async function hardRefresh() {
    loadPageData(document.querySelector(".nav-item.active")?.dataset.page||"accounts");
}

// ── Tự làm mới bảng lịch mỗi 3 phút ───────────────────────────
// Để người dùng theo dõi tình hình đăng bài mà không phải bấm Refresh.
let _schedInterval = null;
const SCHED_REFRESH_MS = 3 * 60 * 1000;   // 3 phút

function _stopSchedAutoRefresh(){
    clearInterval(_schedInterval);
    _schedInterval = null;
}

function _startSchedAutoRefresh(loai){
    _stopSchedAutoRefresh();   // tránh chồng nhiều timer khi chuyển tab / bấm Refresh
    _schedInterval = setInterval(()=>_autoRefreshSchedule(loai), SCHED_REFRESH_MS);
}

async function _autoRefreshSchedule(loai){
    // Đang sửa dở một ô → hoãn lần này, nếu vẽ lại bảng sẽ mất nội dung đang gõ.
    if(document.querySelector(`#${loai}-table .editing`)) return;
    await loadSchedule(loai);
}

// ── Tham gia nhóm ─────────────────────────────────────────────

let _joinRefreshTimer = null;

async function loadJoinSchedules() {
    const tbody = document.getElementById("join-table"); if(!tbody) return;
    try {
        const res = await API.joinSchedules();
        const badge = document.getElementById("join-running-badge");
        const count = document.getElementById("join-count");
        const anyRunning = res.running || res.data.some(r => r.is_running);
        if(badge) badge.style.display = anyRunning ? "inline" : "none";
        if(count) count.textContent = `${res.data.length} lịch`;

        // Auto-refresh mỗi 8s khi có bất kỳ phiên nào đang chạy
        clearTimeout(_joinRefreshTimer);
        if(anyRunning) {
            _joinRefreshTimer = setTimeout(loadJoinSchedules, 8000);
        }

        if(!res.data.length) {
            tbody.innerHTML = `<tr><td colspan="9" class="empty">Chưa có lịch tham gia nhóm nào</td></tr>`;
            return;
        }
        tbody.innerHTML = res.data.map(r => {
            const st        = r.trang_thai || "Chờ";
            const isRunning = !!r.is_running;
            let stBadge;
            if(st.startsWith("Hoàn thành")) stBadge = `<span class="badge badge-success">${st}</span>`;
            else if(isRunning || st.startsWith("Đang chạy")) stBadge = `<span class="badge badge-warning">⏳ Đang chạy</span>`;
            else if(st.startsWith("Lỗi"))   stBadge = `<span class="badge badge-danger">${st}</span>`;
            else                             stBadge = `<span class="badge badge-muted">${st}</span>`;

            const actionBtn = isRunning
                ? `<button onclick="stopJoin(${r.id})"
                       style="background:var(--danger-light);color:var(--danger);border:none;border-radius:5px;padding:4px 10px;cursor:pointer;font-size:12px;margin-right:4px">
                       ■ Stop
                   </button>`
                : `<button onclick="runJoin(${r.id})"
                       style="background:var(--success-light);color:var(--success);border:none;border-radius:5px;padding:4px 10px;cursor:pointer;font-size:12px;margin-right:4px">
                       ▶ Run
                   </button>`;

            return `<tr>
                <td style="text-align:center;font-weight:600">${r.ten_acc}</td>
                <td style="text-align:center;color:var(--text-secondary)">${r.ten_page}</td>
                <td style="text-align:center;font-weight:600">${r.gio_chay||"-"}</td>
                <td style="text-align:center">${r.tong_nhom||0}</td>
                <td style="text-align:center;color:var(--success);font-weight:600">${r.moi_join||0}</td>
                <td style="text-align:center;color:var(--text-muted)">${r.da_join||0}</td>
                <td style="text-align:center;color:var(--danger)">${r.loi||0}</td>
                <td style="text-align:center">${stBadge}</td>
                <td style="text-align:center;white-space:nowrap">
                    ${actionBtn}
                    <button onclick="deleteJoin(${r.id})"
                        style="background:var(--danger-light);color:var(--danger);border:none;border-radius:5px;width:26px;height:26px;cursor:pointer;font-size:13px">
                        🗑
                    </button>
                </td>
            </tr>`;
        }).join("");
    } catch(e) {
        tbody.innerHTML = `<tr><td colspan="9" class="empty" style="color:var(--danger)">${e.message}</td></tr>`;
    }
}

// Chỉ còn MỘT ô. Ô "delay đã join / bỏ qua" đã bỏ khỏi form vì phiên nay lọc
// sẵn nhóm đã tham gia trước khi chạy — đo hai phiên thật cùng ngày: phiên
// trước khi lọc gặp 5 lần "đã là thành viên", phiên sau lọc gặp 0 lần. Nhánh đó
// giờ chỉ còn nổ cho nhóm chờ duyệt và lỗi tải trang, chiếm 3% thời gian chờ
// (10 giây trên 320 giây). Không đáng để cân nhắc mỗi lần tạo lịch → để cứng.
function _delayPanel(dNew) {
    return `
    <div class="field-group">
        <label>Delay mới tham gia (giây)</label>
        <input id="js-delay-new" type="number" min="5" max="600" value="${dNew}"
               style="width:100%" title="Chờ N giây sau khi vừa join nhóm mới">
        <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
            Tham gia nhóm dồn dập là hành vi dễ bị chặn nhất — đây là ô đáng giữ.
            Nhóm đã tham gia được lọc sẵn nên không còn tốn thời gian ghé lại.
        </div>
    </div>`;
}

function openQuickJoinSchedule() {
    API.settings().then(setRes => {
        const dNew  = setRes.data?.join_delay_new  || "30";
        openModal("⚡ Tạo lịch nhanh — Tham gia nhóm", `
            <div style="display:flex;flex-direction:column;gap:12px">
                <div style="font-size:13px;color:var(--text-secondary);background:var(--bg-hover);padding:10px 12px;border-radius:var(--radius-sm);line-height:1.6">
                    Tự động tạo <strong>1 lịch / tài khoản Active có Page</strong>.<br>
                    Bỏ qua acc đã có lịch rồi.
                </div>
                ${_delayPanel(dNew)}
                <div style="font-size:11px;color:var(--text-muted)">
                    Chế độ Chrome (ẩn/hiện): toggle ở tab <strong>Hành động</strong>
                </div>
            </div>
            <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px">
                <button onclick="closeModal()" class="btn btn-ghost">Huỷ</button>
                <button onclick="saveQuickJoinSchedule()" class="btn btn-primary">⚡ Tạo lịch</button>
            </div>`);
    });
}

async function saveQuickJoinSchedule() {
    const dNew  = parseInt(document.getElementById("js-delay-new")?.value  || "30");
    try {
        const r = await API.joinGenQuick({delay_new: dNew});
        if(r.ok) {
            Toast.success(`✅ Đã tạo ${r.created} lịch mới (bỏ qua ${r.skipped} đã có)`);
            closeModal(); loadJoinSchedules();
        } else Toast.error(r.error);
    } catch(e) { Toast.error(e.message); }
}

function openAddJoinSchedule() {
    Promise.all([API.accounts(), API.pages(), API.settings()]).then(([accRes, pRes, setRes]) => {
        const accs  = (accRes.data||[]).filter(a => a.trang_thai === "Active");
        const pages = pRes.data || [];
        const dNew  = setRes.data?.join_delay_new  || "30";
        openModal("+ Thêm lịch tham gia nhóm", `
            <div style="display:flex;flex-direction:column;gap:12px">
                <div class="field-group">
                    <label>Tài khoản</label>
                    <select id="js-acc">
                        ${accs.map(a=>`<option value="${a.ten_acc}">${a.ten_acc}</option>`).join("")}
                    </select>
                </div>
                <div class="field-group">
                    <label>Page (switch sang Page này để join)</label>
                    <select id="js-page">
                        ${pages.map(p=>`<option value="${p.ten_page}">${p.ten_page}</option>`).join("")}
                    </select>
                </div>
                <div class="field-group">
                    <label>Giờ chạy (HH:MM) — để trống = chạy thủ công</label>
                    <input id="js-gio" type="text" placeholder="VD: 02:00">
                </div>
                ${_delayPanel(dNew)}
            </div>
            <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px">
                <button onclick="closeModal()" class="btn btn-ghost">Huỷ</button>
                <button onclick="saveJoinSchedule()" class="btn btn-primary">💾 Lưu</button>
            </div>`);
    });
}

async function saveJoinSchedule() {
    const dNew  = parseInt(document.getElementById("js-delay-new")?.value  || "30");
    await API.saveSettings({join_delay_new: String(dNew)}).catch(()=>{});
    const data = {
        ten_acc:  document.getElementById("js-acc")?.value||"",
        ten_page: document.getElementById("js-page")?.value||"",
        gio_chay: document.getElementById("js-gio")?.value||"",
    };
    try {
        const r = await API.joinAdd(data);
        if(r.ok) { Toast.success("Đã thêm lịch"); closeModal(); loadJoinSchedules(); }
        else Toast.error(r.error);
    } catch(e) { Toast.error(e.message); }
}

function isJoinHeadless() {
    // toggle-join-headless: checked = Hiển thị Chrome → headless=false
    return !document.getElementById("toggle-join-headless")?.checked;
}

function updateJoinHeadlessLabel() {
    const checked = document.getElementById("toggle-join-headless")?.checked;
    const lbl = document.getElementById("join-headless-label");
    if(lbl) {
        lbl.textContent  = checked ? "Hiển thị Chrome" : "Ẩn Chrome";
        lbl.style.color  = checked ? "var(--warning)" : "";
    }
}

async function runJoin(id) {
    const headless  = isJoinHeadless();
    const settings  = await API.settings().catch(()=>({data:{}}));
    const dNew      = parseInt(settings.data?.join_delay_new  || "30");
    const modeLabel = headless ? "ẩn Chrome" : "hiển thị Chrome";
    try {
        const r = await API.joinRun(id, headless, dNew);
        if(r.ok) {
            Toast.success(`▶ Khởi động (${modeLabel} | mới join: ${dNew}s)`);
            loadJoinSchedules();
        } else Toast.error(r.error);
    } catch(e) { Toast.error(e.message); }
}

async function stopJoin(id) {
    try {
        const r = await API.joinStop(id);
        if(r.ok) { Toast.success("■ Đã dừng"); loadJoinSchedules(); }
        else Toast.error(r.error);
    } catch(e) { Toast.error(e.message); }
}

async function deleteJoin(id) {
    if(!confirm("Xóa lịch này?")) return;
    try { await API.joinDelete(id); loadJoinSchedules(); }
    catch(e) { Toast.error(e.message); }
}

// ── Runner ────────────────────────────────────────────────────
const RUNNER_LABELS = {
    homestay:{title:"Homestay",icon:"🏠",color:"#34d399"},
    thue:    {title:"Thuê",    icon:"🏡",color:"#60a5fa"},
    ban:     {title:"Bán",     icon:"💰",color:"#fbbf24"},
    page:    {title:"Đăng Page",icon:"📄",color:"#c084fc"},
    nuoi:    {title:"Nuôi nick",icon:"🌱",color:"#6ee7b7"},
};
let _runnerStatus={};

async function loadRunnerStatus(){
    try{
        // Nạp cài đặt hiện/ẩn Chrome 1 lần đầu, để ô tick vẽ đúng trạng thái
        if(!Object.keys(_hienChromeMap).length) await napHienChrome();
        const res=await API.runStatus();
        _runnerStatus=res;
        renderRunnerGrid();
        renderSidebarStatus();
    }catch(e){}
}

function renderRunnerGrid(){
    const grid=document.getElementById("runner-grid"); if(!grid) return;
    grid.innerHTML=Object.entries(RUNNER_LABELS).map(([loai,cfg])=>{
        const running=_runnerStatus[loai]?.running||false;
        return `<div style="background:var(--bg-card);border:1px solid ${running?cfg.color:"var(--border)"};border-radius:var(--radius);padding:24px;text-align:center">
            <div style="font-size:32px;margin-bottom:8px">${cfg.icon}</div>
            <div style="font-size:16px;font-weight:700;margin-bottom:6px">${cfg.title}</div>
            <div style="margin-bottom:16px">
                <span class="status-dot ${running?"running":"stopped"}" style="display:inline-block;margin-right:6px;vertical-align:middle"></span>
                <span style="font-size:12px;color:${running?cfg.color:"var(--text-muted)"}">${running?"Đang chạy":"Đã dừng"}</span>
            </div>
            <label style="display:flex;align-items:center;justify-content:center;gap:6px;
                          font-size:11px;color:var(--text-muted);margin-bottom:10px;cursor:pointer"
                   title="Hiện cửa sổ Chrome để xem tận mắt — dùng khi cần tìm lỗi">
                <input type="checkbox" ${_hienChrome(loai)?"checked":""}
                       onchange="datHienChrome('${loai}',this.checked)"
                       style="width:14px;height:14px;cursor:pointer">
                👁 Hiện Chrome
            </label>
            ${running
                ?`<button class="btn btn-danger" style="width:100%" onclick="runnerStop('${loai}')">⏹ Dừng</button>`
                :`<button class="btn btn-primary" style="width:100%;background:${cfg.color}" onclick="runnerStart('${loai}')">▶ Run</button>`}
        </div>`;
    }).join("");
}

// Chế độ hiện/ẩn Chrome đặt RIÊNG cho từng loại runner, lưu vào settings nên
// còn nguyên sau khi khởi động lại. Trước đây chỉ có 1 công tắc chung ở đầu
// trang: muốn xem riêng Đăng Page phải gạt qua gạt lại, mà chạy rồi thì không
// nhìn được loại nào đang ở chế độ gì.
let _hienChromeMap = {};

function _hienChrome(loai){ return _hienChromeMap[loai] === true; }

async function datHienChrome(loai, hien){
    _hienChromeMap[loai] = hien;
    try{
        await API.saveSettings({ [`hien_chrome_${loai}`]: hien ? 1 : 0 });
        const cfg = RUNNER_LABELS[loai] || {};
        Toast.success(`${cfg.title}: ${hien ? "sẽ HIỆN cửa sổ Chrome" : "chạy ẩn"}`
                      + (_runnerStatus[loai]?.running ? " — cần Dừng rồi Run lại" : ""));
    }catch(e){ Toast.error(e.message); }
}

async function napHienChrome(){
    try{
        const s = (await API.settings()).data || {};
        _hienChromeMap = {};
        for(const loai of Object.keys(RUNNER_LABELS)){
            _hienChromeMap[loai] = String(s[`hien_chrome_${loai}`] || "0") === "1";
        }
    }catch(e){}
}

function renderSidebarStatus(){
    const box=document.getElementById("sidebar-runner-status"); if(!box) return;
    box.innerHTML=Object.entries(RUNNER_LABELS).map(([loai,cfg])=>{
        const r=_runnerStatus[loai]?.running||false;
        return `<div style="display:flex;align-items:center;gap:6px;font-size:11px;margin-bottom:3px">
            <span class="status-dot ${r?"running":"stopped"}" style="flex-shrink:0"></span>
            <span style="color:${r?cfg.color:"var(--text-muted)"}">${cfg.icon} ${cfg.title}</span>
        </div>`;
    }).join("");
}

function isHeadless(){
    return !document.getElementById("toggle-headless")?.checked;
}

function updateHeadlessLabel(){
    const checked = document.getElementById("toggle-headless")?.checked;
    document.getElementById("headless-label").textContent  = checked ? "Hiển thị Chrome (mặc định chung)" : "Ẩn Chrome (mặc định chung)";
    document.getElementById("headless-desc").textContent   = checked
        ? "Áp cho loại nào KHÔNG tự tick '👁 Hiện Chrome' ở thẻ bên dưới"
        : "Áp cho loại nào KHÔNG tự tick '👁 Hiện Chrome' ở thẻ bên dưới";
    document.getElementById("headless-label").style.color  = checked ? "var(--warning)" : "";
}

async function runnerStart(loai){
    // Ưu tiên cài đặt RIÊNG của loại này; chưa đặt thì theo công tắc chung.
    const headless = _hienChrome(loai) ? false : isHeadless();
    const mode = headless ? "" : " (Chrome hiển thị)";
    try{
        const r=await API.runStart(loai, headless);
        if(r.ok) Toast.success(`▶ Runner ${loai} đã khởi động${mode}`);
        else Toast.error(r.msg||r.error);
        await loadRunnerStatus();
    }
    catch(e){ Toast.error(e.message); }
}
async function runnerStop(loai){
    if(!confirm(`Dừng runner ${RUNNER_LABELS[loai]?.title}?`)) return;
    try{ await API.runStop(loai); Toast.success(`⏹ Đã dừng ${loai}`); await loadRunnerStatus(); }
    catch(e){ Toast.error(e.message); }
}
async function shutdownApp(){
    if(!confirm("Tắt toàn bộ phần mềm (server + runner đăng nền)?\n\nMuốn bật lại: khởi động lại máy công ty (app tự chạy) hoặc chạy RUN_APP.")) return;
    try{
        await API.appShutdown();
        Toast.success("🔴 Đang tắt phần mềm...");
        setTimeout(()=>{
            document.body.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;font-size:16px;color:#94a3b8;padding:20px">Phần mềm đã tắt.<br>Khởi động lại máy hoặc chạy RUN_APP để bật lại.</div>';
        }, 800);
    }catch(e){ Toast.error(e.message); }
}

// ── Accounts ──────────────────────────────────────────────────
const ACC_FIELDS = [
    {key:"ten_acc",label:"Tên acc"},
    {key:"loai_dang",label:"Loại đăng"},
    {key:"thoi_gian_nghi",label:"Nghỉ (p)"},
    {key:"link_profile",label:"Link profile"},
    {key:"email_sdt",label:"Email/SDT"},
    {key:"password",label:"Password",mono:true},
    {key:"ten_page",label:"Tên Page"},
    {key:"c_user",label:"c_user",mono:true},
    {key:"xs",label:"xs",mono:true},
    {key:"refresh",label:"Refresh"},
    {key:"trang_thai",label:"Trạng thái"},
    {key:"nuoi_nick",label:"Nuôi",type:"check"},
    {key:"nuoi_interval",label:"Chu kỳ (p)"},
    {key:"email_khoiphuc",label:"Email KP"},
    {key:"pass_khoiphuc",label:"Pass KP"},
    {key:"twofa",label:"2FA"},
    {key:"ghi_chu",label:"Ghi chú"},
];
let _accData=[];

// ── Sức khoẻ acc (xem suc_khoe_acc.py) ────────────────────────────────
const TRANG_THAI_HONG="Hỏng";
const TRANG_THAI_SPAM="Spam";
const TRANG_THAI_OPTIONS=["Active","Tạm dừng","Cookie hết hạn",TRANG_THAI_HONG,TRANG_THAI_SPAM];

function _dangNghi(r){
    if(!r.nghi_den) return false;
    const t=new Date(r.nghi_den);
    return !isNaN(t) && t>new Date();
}

/** Nhãn hiển thị cho cột Trạng thái — gộp trang_thai (DB) với nghi_den (tạm). */
function _trangThaiAcc(r){
    const val=r.trang_thai||"";
    const ls=r.lich_su_phien||"";
    const hong=ls?`${(ls.match(/x/g)||[]).length}/${ls.length} phiên gần nhất hỏng`
                 :"chưa có phiên nào";
    if(val===TRANG_THAI_HONG)
        return {nhan:"❌ Hỏng", mau:"var(--danger)", dam:true,
                chiTiet:`Máy tự tắt. Sửa ô này về Active để bật lại.`};
    if(val===TRANG_THAI_SPAM){
        const t=r.nghi_den?new Date(r.nghi_den):null;
        const den=(t&&!isNaN(t))?` tới ${String(t.getHours()).padStart(2,"0")}:`
                                 +`${String(t.getMinutes()).padStart(2,"0")}`:"";
        return {nhan:`🚫 Spam${den?" · dò lúc"+den.replace(" tới",""):""}`,
                mau:"var(--danger)", dam:true,
                chiTiet:`Facebook đã gỡ ${r.so_vi_pham>0?r.so_vi_pham+" bài":"bài"} của nick này. `
                       +`Nghỉ đăng và comment; nuôi nick vẫn chạy. `
                       +`Mỗi 60 phút tự chạy 1 phiên thăm dò — được thì chạy lại `
                       +`bình thường, chưa được thì nghỉ tiếp. Không cần làm gì.`};
    }
    if(val==="Cookie hết hạn")
        return {nhan:val, mau:"var(--danger)", dam:false, chiTiet:"Cần đăng nhập lại"};
    if(_dangNghi(r)){
        const t=new Date(r.nghi_den);
        const hh=String(t.getHours()).padStart(2,"0"), mm=String(t.getMinutes()).padStart(2,"0");
        return {nhan:`😴 Nghỉ tới ${hh}:${mm}`, mau:"var(--warning)", dam:false,
                chiTiet:`Lỗi liên tiếp nên tạm nghỉ, sau đó tự chạy lại. ${hong}`};
    }
    if(val==="Active")
        return {nhan:val, mau:"var(--text-secondary)", dam:false, chiTiet:hong};
    return {nhan:val||"-", mau:"var(--text-secondary)", dam:false, chiTiet:hong};
}

// Scheduler chạy ở tiến trình riêng nên không bắn toast thẳng lên được; nó ghi
// cảnh báo vào DB, chỗ này nhặt về. Bám theo nhịp 10s của loadRunnerStatus thay
// vì tự đặt timer riêng — một nhịp thăm dò là đủ cho cả hai việc.
async function loadCanhBaoAcc(){
    try{
        const res=await API.canhBao();
        if(!res.ok || !res.data?.length) return;
        res.data.forEach(c=>Toast.show(_escapeHtml(c.noi_dung), c.muc==="error"?"error":"info",
                                       c.muc==="error"?15000:8000));
        await API.canhBaoXong();
        // Cảnh báo vừa nổ nghĩa là trạng thái acc vừa đổi — vẽ lại bảng nếu
        // người dùng đang mở đúng tab đó.
        if(document.getElementById("acc-table")?.offsetParent) loadAccounts();
    }catch(e){}
}

// Server ghi file xuống đĩa rồi trả về đường dẫn — KHÔNG dùng <a download> vì
// app chạy trong cửa sổ pywebview, ở đó trình duyệt nhúng nuốt luôn lệnh tải
// file: code JS chạy hết và báo thành công nhưng không có file nào được lưu.
async function exportAccountsExcel(){
    try{
        const res=await API.get("/api/accounts/export-excel");
        if(!res.ok) throw new Error(res.error||"không rõ lỗi");
        Toast.show("Đã lưu: "+res.path, "success", 10000);
    }catch(e){ Toast.error("Lỗi xuất Excel: "+e.message); }
}

async function importAccountsExcel(e){
    const file=e.target.files[0]; if(!file) return;
    e.target.value="";  // reset để chọn lại cùng file vẫn kích hoạt onchange
    try{
        const fd=new FormData(); fd.append("file",file);
        const r=await fetch("/api/accounts/import-excel",{method:"POST",body:fd});
        const res=await r.json();
        if(!res.ok) throw new Error(res.error||"không rõ lỗi");
        Toast.success(`Đã thêm ${res.added} tài khoản mới, bỏ qua ${res.skipped} trùng`);
        loadAccounts();
    }catch(err){ Toast.error("Lỗi nhập Excel: "+err.message); }
}

// Mỗi acc phải mở một Chrome ẩn để đọc cookie nên có thể mất vài chục giây.
// Khoá nút trong lúc chạy, tránh người dùng bấm chồng làm mở nhiều Chrome
// cùng trỏ vào một profile — thứ chắc chắn làm hỏng dữ liệu đăng nhập.
async function refreshCookiesNow(){
    const btn=document.getElementById("btn-refresh-cookie");
    const cu=btn.textContent;
    btn.disabled=true; btn.textContent="⏳ Đang refresh...";
    try{
        const r=await fetch("/api/accounts/refresh-now",{method:"POST"});
        const res=await r.json();
        if(!res.ok) throw new Error(res.error||"không rõ lỗi");
        const n=(res.da_lam||[]).length, loi=(res.loi||[]).length;
        if(!n && !loi) Toast.info("Không có acc nào để Refresh = Yes");
        else if(loi)   Toast.error(`Xong ${n} acc, ${loi} acc lỗi — xem log`);
        else           Toast.success(`Đã refresh cookie ${n} acc: ${res.da_lam.join(", ")}`);
        loadAccounts();
    }catch(err){ Toast.error("Lỗi refresh: "+err.message); }
    finally{ btn.disabled=false; btn.textContent=cu; }
}

async function loadAccounts(){
    const tbody=document.getElementById("acc-table");
    const thead=document.getElementById("acc-thead");
    tbody.innerHTML=`<tr><td colspan="19" class="loading"><span class="spin">↻</span></td></tr>`;
    try{
        const res=await API.accounts();
        _accData=res.data;
        // Thead
        if(thead) thead.innerHTML=`<tr><th style="width:32px"></th>${ACC_FIELDS.map(f=>`<th style="text-align:center">${f.label}</th>`).join("")}<th style="width:60px;text-align:center">Xóa</th></tr>`;
        // Summary
        const box=document.getElementById("acc-summary");
        if(box){
            const total=res.data.length, active=res.data.filter(r=>r.trang_thai==="Active").length;
            // So khớp CHÍNH XÁC: "X_Thuê" chứa chuỗi con "Thuê" và "X_Bán" chứa
            // "Bán", dùng includes() sẽ đếm nhầm acc hỗn hợp vào nhóm chỉ đăng.
            const dem=v=>res.data.filter(r=>(r.loai_dang||"").trim()===v).length;
            const ban=dem("Bán"), thue=dem("Thuê"), hs=dem("Homestay");
            const hong=res.data.filter(r=>r.trang_thai===TRANG_THAI_HONG).length;
            const nghi=res.data.filter(r=>_dangNghi(r)).length;
            const o=[{l:"Tổng",v:total},{l:"Active",v:active},{l:"Bán",v:ban},{l:"Thuê",v:thue},{l:"Homestay",v:hs}];
            // Chỉ chiếm chỗ khi thực sự có acc hỏng/nghỉ — bình thường thanh này
            // giữ nguyên như cũ, không đẻ thêm hai ô số 0 nhìn như báo động giả.
            if(nghi) o.push({l:"Nghỉ tạm",v:nghi,c:"var(--warning)"});
            if(hong) o.push({l:"⚠️ Hỏng",v:hong,c:"var(--danger)"});
            box.innerHTML=o
                .map(s=>`<div class="metric-card" style="padding:10px 14px;flex:1;min-width:80px"><div class="metric-label">${s.l}</div><div class="metric-value" style="font-size:20px;${s.c?"color:"+s.c:""}">${s.v}</div></div>`).join("");
        }
        renderAccTable(res.data);
    }catch(e){ tbody.innerHTML=`<tr><td colspan="19" class="empty" style="color:var(--danger)">${e.message}</td></tr>`; }
}

function renderAccTable(data){
    const tbody=document.getElementById("acc-table");
    const count=document.getElementById("acc-count");
    const filter=document.getElementById("acc-filter-loai")?.value||"";
    const rows=data.filter(r=>!filter||((r.loai_dang||"").trim()===filter));
    if(count) count.textContent=`${rows.length}/${data.length} tài khoản`;
    if(!rows.length){ tbody.innerHTML=`<tr><td colspan="19" class="empty">Không có tài khoản nào</td></tr>`; return; }
    tbody.innerHTML=rows.map(r=>{
        const CENTER_KEYS=["loai_dang","thoi_gian_nghi","link_profile","refresh","trang_thai","nuoi_interval"];
        const tds=ACC_FIELDS.map(f=>{
            const val=(r[f.key]||"").toString();
            const esc=val.replace(/"/g,"&quot;");
            if(f.type==="check"){
                const on=(val==="1");
                return `<td style="text-align:center"><input type="checkbox" ${on?"checked":""}
                    onclick="toggleAccCheck(event,${r.id},'${f.key}')"
                    style="width:16px;height:16px;cursor:pointer" title="Bật/tắt nuôi nick"></td>`;
            }
            const center=CENTER_KEYS.includes(f.key)?"text-align:center;":"";
            const style=`${center}font-size:${f.mono?"11px":"12px"};color:var(--text-secondary);${f.mono?"font-family:var(--font-mono);":""}max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap`;
            if(f.key==="loai_dang"){
                return `<td class="editable" data-id="${r.id}" data-field="${f.key}" data-val="${esc}" style="${center}color:${mauLoaiDang(val)};font-weight:600;font-size:12px" onclick="startAccEdit(this)">${val||"-"}</td>`;
            }
            if(f.key==="link_profile")
                return `<td class="editable" data-id="${r.id}" data-field="${f.key}" data-val="${esc}" style="${center}" onclick="startAccEdit(this)">${val?`<a href="${val}" target="_blank" style="color:var(--accent);font-size:12px" onclick="event.stopPropagation()">🔗</a>`:"-"}</td>`;
            if(f.key==="trang_thai"){
                const t=_trangThaiAcc(r);
                // data-val giữ giá trị THẬT trong DB, không phải nhãn hiển thị:
                // ô này sửa được, mà "😴 Nghỉ tới 14:20" không phải giá trị hợp lệ
                // để ghi ngược xuống cột trang_thai.
                return `<td class="editable" data-id="${r.id}" data-field="${f.key}" data-val="${esc}"
                    style="${center}font-size:12px;font-weight:${t.dam?"600":"400"};color:${t.mau}"
                    title="${_escapeHtml(t.chiTiet)}" onclick="startAccEdit(this)">${t.nhan}</td>`;
            }
            return `<td class="editable" data-id="${r.id}" data-field="${f.key}" data-val="${esc}" style="${style}" title="${esc}" onclick="startAccEdit(this)">${val||"-"}</td>`;
        }).join("");
        return `<tr draggable="true" data-id="${r.id}"
                    ondragstart="accDragStart(event,${r.id})"
                    ondragover="accDragOver(event)"
                    ondrop="accDrop(event,${r.id})"
                    ondragleave="accDragLeave(event)"
                    ondragend="accDragEnd(event)"
                    style="cursor:default">
            <td style="text-align:center;color:var(--text-muted);cursor:grab;font-size:16px;padding:4px 6px"
                title="Kéo để di chuyển hàng">☰</td>
            ${tds}
            <td style="text-align:center">
                <button title="Xóa" onclick="deleteAcc(${r.id})"
                    style="background:var(--danger-light);color:var(--danger);border:none;border-radius:6px;width:28px;height:28px;cursor:pointer;font-size:14px">🗑️</button>
            </td>
        </tr>`;
    }).join("");
}

function filterAccounts(){ renderAccTable(_accData); }

async function toggleAccCheck(e, id, field){
    const on = e.target.checked;
    try{
        const r = await API.updateAccField(id, field, on ? 1 : 0);
        if(r.ok){ const row=_accData.find(x=>x.id===id); if(row) row[field]=on?1:0; }
        else { Toast.error(r.error); e.target.checked = !on; }
    }catch(err){ Toast.error(err.message); e.target.checked = !on; }
}

// Trường credential — server chỉ trả dấu che, phải nạp giá trị thật khi sửa.
const ACC_SECRET_FIELDS = ["password","xs","twofa","pass_khoiphuc","email_khoiphuc"];
const ACC_SECRET_MASK   = "••••••";

async function startAccEdit(td){
    if(td.classList.contains("editing")) return;
    td.classList.add("editing");
    const id=td.dataset.id, field=td.dataset.field;
    let val=td.dataset.val||"";

    // Ô đang bị che → hỏi server giá trị thật (chỉ máy tại chỗ được phép).
    if(ACC_SECRET_FIELDS.includes(field) && val===ACC_SECRET_MASK){
        td.textContent="…";
        try{
            const r=await API.accountSecrets(parseInt(id));
            val=(r.data&&r.data[field])||"";
        }catch(e){
            td.classList.remove("editing"); td.textContent=ACC_SECRET_MASK;
            Toast.error("Chỉ sửa được credential trên máy tại chỗ");
            return;
        }
    }

    // Loại đăng là tập giá trị đóng — cho gõ tay thì sẽ có acc mang "C_home"
    // hay "Homestay " thừa khoảng trắng, và Gen lịch bỏ sót acc đó mà không
    // báo gì. Dùng dropdown để không thể nhập sai.
    // Trạng thái cũng dùng dropdown như Loại đăng: đây là ô để bật lại acc bị
    // máy tắt, gõ tay lệch một ký tự thì acc nằm ngoài mọi bộ lọc 'Active' mà
    // nhìn vẫn như đã bật.
    const CHON_SAN={loai_dang:LOAI_DANG_OPTIONS, trang_thai:TRANG_THAI_OPTIONS};
    if(CHON_SAN[field]){
        const sel=document.createElement("select");
        sel.style.cssText="width:100%;font-size:12px";
        const cur=val==="-"?"":val;
        CHON_SAN[field].forEach(o=>{
            const op=document.createElement("option");
            op.value=o; op.textContent=o||"-";
            if(o===cur) op.selected=true;
            sel.appendChild(op);
        });
        td.innerHTML=""; td.appendChild(sel); sel.focus();
        let xong=false;
        const luu=async()=>{
            if(xong) return; xong=true;
            const nv=sel.value; td.classList.remove("editing");
            td.dataset.val=nv;
            if(field==="loai_dang"){ td.style.color=mauLoaiDang(nv); }
            td.textContent=nv||"-";
            if(nv===cur) return;
            td.classList.add("saving");
            try{
                const r=await API.updateAccField(parseInt(id),field,nv);
                td.classList.remove("saving");
                if(r.ok){
                    td.classList.add("saved"); setTimeout(()=>td.classList.remove("saved"),1200);
                    // Bật về Active thì server xoá luôn lịch sử phiên và mốc
                    // nghỉ — nạp lại để bảng khớp với DB thay vì hiện giá trị cũ.
                    if(field==="trang_thai") loadAccounts();
                }
                else Toast.error(r.error);
            }catch(e){ td.classList.remove("saving"); Toast.error(e.message); }
        };
        sel.addEventListener("change",luu);
        sel.addEventListener("blur",luu);
        sel.addEventListener("keydown",e=>{
            if(e.key==="Escape"){ xong=true; td.classList.remove("editing"); td.textContent=cur||"-"; }
        });
        return;
    }

    const inp=document.createElement("input"); inp.type="text"; inp.value=val==="-"?"":val;
    td.innerHTML=""; td.appendChild(inp); inp.focus(); inp.select();
    async function commit(){
        const nv=inp.value; td.classList.remove("editing");
        const secret=ACC_SECRET_FIELDS.includes(field);
        // Không giữ credential trong DOM sau khi sửa xong — che lại ngay.
        td.dataset.val = secret ? (nv?ACC_SECRET_MASK:"") : nv;
        if(field==="link_profile") td.innerHTML=nv?`<a href="${nv}" target="_blank" style="color:var(--accent);font-size:12px">🔗</a>`:"-";
        else if(secret) td.textContent=nv?ACC_SECRET_MASK:"-";
        else td.textContent=nv||"-";
        if(nv===val) return;
        td.classList.add("saving");
        try{ const r=await API.updateAccField(parseInt(id),field,nv); td.classList.remove("saving"); if(r.ok){td.classList.add("saved");setTimeout(()=>td.classList.remove("saved"),1200);} else Toast.error(r.error); }
        catch(e){ td.classList.remove("saving"); Toast.error(e.message); }
    }
    inp.addEventListener("blur",commit);
    inp.addEventListener("keydown",e=>{ if(e.key==="Enter"){e.preventDefault();inp.blur();} if(e.key==="Escape"){inp.value=val;inp.blur();} });
}

// Loại đăng — tiền tố "C_" nghĩa là acc CHỈ ĐI COMMENT cho mảng đó, không
// đăng bài. Dùng cho acc bị Facebook dỡ bài nhưng vẫn comment được.
// Danh sách phải khớp LOAI_DANG_OPTIONS trong db.py.
const LOAI_DANG_OPTIONS = ["","Homestay","Thuê","Bán","X_Home","X_Thuê","X_Bán"];

// Loại đăng của PAGE. Khác LOAI_DANG_OPTIONS ở trên — cái đó là của tài khoản.
// Ô trống ở đầu là có chủ ý: Page để trống thì gen lịch BỎ QUA nó, dùng khi
// tạm không muốn đăng lên Page đó mà chưa muốn xoá khỏi danh sách.
// Một danh sách dùng chung cho cả bảng lẫn form thêm/sửa — trước đây chép cứng
// ở hai chỗ, sửa một chỗ là lệch ngay.
const LOAI_PAGE_OPTIONS = ["","Homestay","Thuê","Bán"];
const LOAI_PAGE_TRONG   = "—";        // chữ hiện ra cho ô trống
// Mỗi loại đăng MỘT màu riêng. Bản trước gom cả 3 loại "X_" vào một màu hồng và
// cả 3 loại "C_" vào một màu tím, nên nhìn bảng không tách được X_Home với
// X_Thuê — mà đó mới là thứ cần phân biệt khi soi acc nào đang chạy mảng nào.
//
// Bộ màu dưới đây chọn bằng đo đạc, không phải ước lượng bằng mắt:
//   · tương phản trên nền bảng (#1e293b) đều ≥ 5.2 — ngưỡng WCAG cho chữ thường
//     là 4.5, ô này lại còn in đậm
//   · khoảng cách Lab ΔE giữa hai màu gần nhau nhất = 41.4; dưới ~25 là dễ nhầm
//     ở cỡ chữ 12px. Bộ cũ chỉ đạt 22.2 giữa Thuê và biến thể của nó.
//   · trong số các bộ cùng đạt ΔE 41.4, chọn cách gán đưa mỗi biến thể về gần
//     sắc màu của mảng gốc nhất, để vẫn liếc ra được "đây là nhóm homestay".
// Đổi màu thì nên chạy lại phép đo đó trước.
function mauLoaiDang(v){
    if(v==="Homestay") return "#34d399";   // xanh ngọc
    if(v==="X_Home")   return "#22d3ee";   // xanh cyan
    if(v==="Thuê")     return "#60a5fa";   // xanh dương
    if(v==="X_Thuê")   return "#c084fc";   // tím
    if(v==="Bán")      return "#fbbf24";   // vàng hổ phách
    if(v==="X_Bán")    return "#f87171";   // đỏ san hô
    return "var(--text-secondary)";
}

function openAccForm(data={}){
    const f=(k,label,type="text")=>`<div class="field-group"><label>${label}</label><input type="${type}" id="af_${k}" value="${(data[k]||"").toString().replace(/"/g,"&quot;")}"></div>`;
    const fsel=(k,label,opts)=>`<div class="field-group"><label>${label}</label><select id="af_${k}">${opts.map(o=>`<option value="${o}" ${data[k]===o?"selected":""}>${o||"-"}</option>`).join("")}</select></div>`;
    openModal(data.id?"Sửa tài khoản":"Thêm tài khoản",`
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            ${f("ten_acc","Tên acc")} ${fsel("loai_dang","Loại đăng",LOAI_DANG_OPTIONS)}
            ${f("thoi_gian_nghi","Nghỉ (phút)")} ${f("ten_page","Tên Page")}
            ${f("link_profile","Link profile")} ${f("email_sdt","Email/SDT")}
            ${f("password","Password")} ${f("c_user","c_user")}
            <div class="field-group" style="grid-column:1/-1"><label>xs</label><input id="af_xs" value="${(data.xs||"").toString().replace(/"/g,"&quot;")}"></div>
            ${fsel("trang_thai","Trạng thái",TRANG_THAI_OPTIONS)}
            ${f("email_khoiphuc","Email khôi phục")} ${f("pass_khoiphuc","Pass khôi phục")}
            ${f("twofa","2FA")} ${f("ghi_chu","Ghi chú")}
        </div>
        ${data.id?`<input type="hidden" id="af_id" value="${data.id}">`:""}
        <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px">
            <button onclick="closeModal()" class="btn btn-ghost">Huỷ</button>
            <button onclick="saveAccForm()" class="btn btn-primary">💾 Lưu</button>
        </div>`);
}

async function saveAccForm(){
    const get=id=>document.getElementById(id)?.value||"";
    const data={
        id:        parseInt(get("af_id"))||undefined,
        ten_acc:   get("af_ten_acc"), loai_dang: get("af_loai_dang"),
        thoi_gian_nghi: parseInt(get("af_thoi_gian_nghi"))||30,
        ten_page:  get("af_ten_page"), link_profile: get("af_link_profile"),
        email_sdt: get("af_email_sdt"), password: get("af_password"),
        c_user:    get("af_c_user"),    xs:        get("af_xs"),
        trang_thai:get("af_trang_thai"),email_khoiphuc: get("af_email_khoiphuc"),
        pass_khoiphuc: get("af_pass_khoiphuc"), twofa: get("af_twofa"),
        ghi_chu:   get("af_ghi_chu"),
    };
    if(!data.id) delete data.id;
    try{ const r=await API.saveAccount(data); if(r.ok){Toast.success("Đã lưu");closeModal();loadAccounts();}else Toast.error(r.error); }
    catch(e){ Toast.error(e.message); }
}

async function deleteAcc(id){
    if(!confirm("Xóa tài khoản này?")) return;
    try{ await API.deleteAccount(id); Toast.success("Đã xóa"); loadAccounts(); }
    catch(e){ Toast.error(e.message); }
}

// ── Drag & Drop reorder — dùng chung cho mọi bảng ─────────────
let _dragId = null;

function accDragStart(e, id) {
    _dragId = id;
    e.dataTransfer.effectAllowed = "move";
    // Bảng Tài khoản/Page: draggable nằm trên <tr> nên currentTarget CHÍNH LÀ tr
    // (closest khớp chính nó) → không đổi hành vi.
    // Bảng Content/UID: draggable nằm trên ô ☰ để không chặn bôi đen text.
    const tr = e.currentTarget.closest("tr") || e.currentTarget;
    if (e.currentTarget !== tr) {
        // Kéo từ ô ☰ thì ảnh kéo phải là CẢ HÀNG, không phải mỗi ô đó
        try { e.dataTransfer.setDragImage(tr, 12, 12); } catch(_) {}
    }
    tr.style.opacity = "0.5";
}

function accDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    e.currentTarget.style.background = "var(--accent-light)";
}

function accDragLeave(e) {
    e.currentTarget.style.background = "";
}

// Thả ra ngoài bảng thì trước đây hàng bị kẹt mờ 0.5 tới lần render sau.
function accDragEnd(e) {
    (e.currentTarget.closest("tr") || e.currentTarget).style.opacity = "";
    _dragId = null;
}

async function _rowDrop(e, targetId, tbodyId, saveFn) {
    e.preventDefault();
    e.currentTarget.style.background = "";
    if (_dragId === null || _dragId === targetId) { _dragId = null; return; }

    const tbody = document.getElementById(tbodyId);
    if (!tbody) { _dragId = null; return; }
    const rows  = [...tbody.querySelectorAll("tr[data-id]")];
    const ids   = rows.map(r => parseInt(r.dataset.id));
    const fromI = ids.indexOf(_dragId);
    const toI   = ids.indexOf(targetId);
    if (fromI < 0 || toI < 0) { _dragId = null; return; }

    const moved = _dragId; _dragId = null;
    ids.splice(fromI, 1);
    ids.splice(toI, 0, moved);

    // Cập nhật UI ngay lập tức
    const rowMap = Object.fromEntries(rows.map(r => [parseInt(r.dataset.id), r]));
    ids.forEach(id => tbody.appendChild(rowMap[id]));
    rows.forEach(r => r.style.opacity = "");

    // Lưu vào DB
    try { await saveFn(ids); } catch(err) { Toast.error(err.message); }
}

async function accDrop(e, t)     { return _rowDrop(e, t, "acc-table",     API.reorderAccounts); }
async function pageDrop(e, t)    { return _rowDrop(e, t, "pages-table",   API.reorderPages); }
async function contentDrop(e, t) { return _rowDrop(e, t, "content-table", API.reorderContent); }
async function uidDrop(e, t)     { return _rowDrop(e, t, "uid-table",     API.reorderUidGroups); }

// ── Accounts — Insert row ─────────────────────────────────────
async function insertAccRow(refId, position) {
    try {
        const r = await API.insertAccRow(refId, position);
        if (r.ok) { Toast.success("Đã thêm hàng trống"); loadAccounts(); }
        else Toast.error(r.error);
    } catch(e) { Toast.error(e.message); }
}

// ── Pages ─────────────────────────────────────────────────────
async function loadPages(){
    const tbody=document.getElementById("pages-table"); if(!tbody) return;
    tbody.innerHTML=`<tr><td colspan="9" class="loading"><span class="spin">↻</span></td></tr>`;
    try{
        const res=await API.pages();

        // Summary
        const total=res.data.length;
        const active=res.data.filter(p=>p.bai_dang_toi_da>0).length;

        let sumBox=document.getElementById("pages-summary");
        if(!sumBox){
            sumBox=document.createElement("div");
            sumBox.id="pages-summary";
            sumBox.style.cssText="display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap";
            document.getElementById("page-pages").insertBefore(sumBox, document.querySelector("#page-pages .card"));
        }
        sumBox.innerHTML=[
            {l:"Tổng",v:total},{l:"Có lịch đăng",v:active,c:"var(--success)"}
        ].map(s=>`<div class="metric-card" style="padding:10px 14px;flex:1;min-width:80px">
            <div class="metric-label">${s.l}</div>
            <div class="metric-value" style="font-size:20px${s.c?";color:"+s.c:""}">${s.v}</div>
        </div>`).join("");

        if(!res.data.length){ tbody.innerHTML=`<tr><td colspan="9" class="empty">Chưa có Page nào</td></tr>`; return; }

        const ep=(p,field,style,mono)=>{
            const val=(p[field]||"").toString(); const esc=val.replace(/"/g,"&quot;");
            return `<td class="editable" data-id="${p.id}" data-field="${field}" data-val="${esc}"
                style="${mono?"font-family:var(--font-mono);font-size:11px;":"font-size:12px;"}color:var(--text-secondary);${style||""}"
                onclick="startPageEdit(this)">${val||"-"}</td>`;
        };

        tbody.innerHTML=res.data.map(p=>`<tr draggable="true" data-id="${p.id}"
                ondragstart="accDragStart(event,${p.id})"
                ondragover="accDragOver(event)"
                ondrop="pageDrop(event,${p.id})"
                ondragleave="accDragLeave(event)"
                ondragend="accDragEnd(event)"
                style="cursor:default">
            <td style="text-align:center;color:var(--text-muted);cursor:grab;font-size:16px;padding:4px 6px"
                title="Kéo để di chuyển hàng">☰</td>
            ${ep(p,"ten_page","font-weight:600;min-width:140px")}
            ${ep(p,"acc_quan_ly","min-width:110px;text-align:center")}
            ${ep(p,"page_uid","min-width:120px;text-align:center",true)}
            <td class="editable" data-id="${p.id}" data-field="loai_page" data-val="${(p.loai_page||"").replace(/"/g,"&quot;")}"
                onclick="startPageEdit(this)" style="font-size:12px;text-align:center">
                ${pageLoaiCell(p.loai_page)}
            </td>
            ${ep(p,"bai_dang_toi_da","text-align:center;font-weight:600")}
            <td class="editable" data-id="${p.id}" data-field="link_page" data-val="${(p.link_page||"").replace(/"/g,"&quot;")}"
                onclick="startPageEdit(this)" style="text-align:center">
                ${p.link_page?`<a href="${p.link_page}" target="_blank" style="color:var(--accent);font-size:12px" onclick="event.stopPropagation()">🔗</a>`:"-"}
            </td>
            ${ep(p,"ghi_chu","max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap")}
            <td style="text-align:center">
                <button onclick="deletePage(${p.id})"
                    style="background:var(--danger-light);color:var(--danger);border:none;border-radius:5px;width:28px;height:28px;cursor:pointer;font-size:13px">🗑️</button>
            </td>
        </tr>`).join("");
    }catch(e){ tbody.innerHTML=`<tr><td colspan="9" class="empty" style="color:var(--danger)">${e.message}</td></tr>`; }
}

function pageLoaiCell(loai){
    if(!loai) return `<span style="color:var(--text-muted)">-</span>`;
    if(loai.includes("Homestay")) return `<span style="color:#34d399;font-weight:600">Homestay</span>`;
    if(loai.includes("Thuê"))     return `<span style="color:#60a5fa;font-weight:600">Thuê</span>`;
    if(loai.includes("Bán"))      return `<span style="color:#fbbf24;font-weight:600">Bán</span>`;
    return `<span style="color:var(--text-secondary)">${loai}</span>`;
}

function startPageEdit(td){
    if(td.classList.contains("editing")) return;
    td.classList.add("editing");
    const id=td.dataset.id, field=td.dataset.field, val=td.dataset.val||"";
    let inp;
    if(field==="loai_page"){
        // Bốn lựa chọn: — (không đăng) / Homestay / Thuê / Bán.
        // Ô trống LUÔN có mặt, không chỉ khi giá trị đang sai như bản trước —
        // không thì chọn một loại rồi là không bao giờ bỏ chọn lại được.
        inp=document.createElement("select");
        inp.style.cssText="background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:12px;font-weight:600;cursor:pointer";
        const mkOpt=(v,t)=>{ const op=document.createElement("option"); op.value=v; op.textContent=t; op.style.cssText="background:var(--bg-card);color:var(--text-primary)"; return op; };
        const hienTai=(val==="-"?"":val);   // bảng hiện ô trống bằng dấu "-"
        LOAI_PAGE_OPTIONS.forEach(o=>{
            const op=mkOpt(o, o||LOAI_PAGE_TRONG);
            if(o===hienTai) op.selected=true;
            inp.appendChild(op);
        });
        // Giá trị lạ còn sót từ dữ liệu cũ thì giữ lại trong danh sách, để mở
        // ô ra rồi đóng lại không âm thầm xoá mất nó.
        if(hienTai && !LOAI_PAGE_OPTIONS.includes(hienTai)){
            const op=mkOpt(hienTai,hienTai); op.selected=true; inp.appendChild(op);
        }
    } else {
        inp=document.createElement("input"); inp.type="text"; inp.value=val==="-"?"":val;
    }
    td.innerHTML=""; td.appendChild(inp); inp.focus();
    if(inp.select) try{ inp.select(); }catch(e){}
    if(field==="loai_page") inp.addEventListener("change",()=>inp.blur());
    async function commit(){
        const nv=inp.value; td.classList.remove("editing"); td.dataset.val=nv;
        if(field==="loai_page") td.innerHTML=pageLoaiCell(nv);
        else if(field==="link_page") td.innerHTML=nv?`<a href="${nv}" target="_blank" style="color:var(--accent);font-size:12px" onclick="event.stopPropagation()">🔗</a>`:"-";
        else td.textContent=nv||"-";
        if(nv===val) return;
        td.classList.add("saving");
        try{
            const r=await API.updatePageField(parseInt(id),field,nv);
            td.classList.remove("saving");
            if(r.ok){td.classList.add("saved");setTimeout(()=>td.classList.remove("saved"),1200);}
            else Toast.error(r.error);
        }catch(e){td.classList.remove("saving");Toast.error(e.message);}
    }
    inp.addEventListener("blur",commit);
    inp.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();inp.blur();}if(e.key==="Escape"){inp.value=val;inp.blur();}});
}

function openPageForm(data={}){
    const f=(k,l)=>`<div class="field-group"><label>${l}</label><input id="pf_${k}" value="${(data[k]||"").toString().replace(/"/g,"&quot;")}"></div>`;
    openModal(data.id?"Sửa Page":"Thêm Page",`
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            ${f("ten_page","Tên Page")} ${f("acc_quan_ly","Acc quản lý")}
            ${f("page_uid","Page UID")}
            <div class="field-group"><label>Loại đăng</label><select id="pf_loai_page">
                ${LOAI_PAGE_OPTIONS.map(o=>`<option value="${o}" ${(data.loai_page||"")===o?"selected":""}>${o||LOAI_PAGE_TRONG+" (không đăng)"}</option>`).join("")}
            </select></div>
            ${f("bai_dang_toi_da","Bài đăng tối đa")}
            <div class="field-group" style="grid-column:1/-1">${f("link_page","Link Page")}</div>
            <div class="field-group" style="grid-column:1/-1">${f("ghi_chu","Ghi chú")}</div>
        </div>
        ${data.id?`<input type="hidden" id="pf_id" value="${data.id}">`:""}
        <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px">
            <button onclick="closeModal()" class="btn btn-ghost">Huỷ</button>
            <button onclick="savePageForm()" class="btn btn-primary">💾 Lưu</button>
        </div>`);
}

async function savePageForm(){
    const g=id=>document.getElementById(id)?.value||"";
    const data={
        id: parseInt(g("pf_id"))||undefined,
        ten_page: g("pf_ten_page"), acc_quan_ly: g("pf_acc_quan_ly"), page_uid: g("pf_page_uid"),
        loai_page: g("pf_loai_page"),
        bai_dang_toi_da: parseInt(g("pf_bai_dang_toi_da"))||0,
        link_page: g("pf_link_page"), ghi_chu: g("pf_ghi_chu"),
    };
    if(!data.id) delete data.id;
    try{ const r=await API.savePage(data); if(r.ok){Toast.success("Đã lưu");closeModal();loadPages();}else Toast.error(r.error); }
    catch(e){ Toast.error(e.message); }
}

async function deletePage(id){
    if(!confirm("Xóa Page này?")) return;
    try{ await API.deletePage(id); Toast.success("Đã xóa"); loadPages(); }
    catch(e){ Toast.error(e.message); }
}

async function exportPagesExcel(){
    try{
        const res=await API.exportPages();
        if(!res.ok) throw new Error(res.error||"không rõ lỗi");
        Toast.show(`Đã lưu ${res.count} Page: ${res.path}`, "success", 10000);
    }catch(e){ Toast.error("Lỗi xuất Excel: "+e.message); }
}

async function importPagesExcel(e){
    const file=e.target.files[0]; if(!file) return;
    e.target.value="";  // reset để chọn lại cùng file vẫn kích hoạt onchange
    try{
        const fd=new FormData(); fd.append("file",file);
        const r=await fetch("/api/pages/import-excel",{method:"POST",body:fd});
        const res=await r.json();
        if(!res.ok) throw new Error(res.error||"không rõ lỗi");
        Toast.success(`Đã thêm ${res.added} Page mới, bỏ qua ${res.skipped} trùng`);
        loadPages();
    }catch(err){ Toast.error("Lỗi nhập Excel: "+err.message); }
}

// ── Dialog (thay prompt/confirm của trình duyệt bằng modal in-app) ──
const Dialog = {
    _ensure(){
        if(document.getElementById("app-dialog-overlay")) return;
        const ov = document.createElement("div");
        ov.id = "app-dialog-overlay";
        ov.style.cssText = "display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:600";
        const panel = document.createElement("div");
        panel.id = "app-dialog-panel";
        panel.style.cssText = "display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);"
            + "width:400px;max-width:92vw;background:var(--bg-secondary);border:1px solid var(--border);"
            + "border-radius:var(--radius);z-index:601;box-shadow:var(--shadow-md);overflow:hidden";
        panel.innerHTML = `
            <div style="padding:18px 20px 4px">
                <div id="app-dialog-title" style="font-size:15px;font-weight:700;margin-bottom:6px"></div>
                <div id="app-dialog-msg" style="font-size:13px;color:var(--text-secondary);line-height:1.5"></div>
            </div>
            <div id="app-dialog-input-wrap" style="padding:8px 20px 0;display:none">
                <input id="app-dialog-input" style="width:100%;background:var(--bg-input);border:1px solid var(--border);
                    border-radius:var(--radius-sm);padding:9px 11px;color:var(--text-primary);font-size:13px;outline:none">
            </div>
            <div style="display:flex;gap:8px;justify-content:flex-end;padding:18px 20px">
                <button id="app-dialog-cancel" class="btn btn-ghost">Huỷ</button>
                <button id="app-dialog-ok" class="btn btn-primary">OK</button>
            </div>`;
        document.body.appendChild(ov);
        document.body.appendChild(panel);
    },
    _open(opts){
        this._ensure();
        const ov    = document.getElementById("app-dialog-overlay");
        const panel = document.getElementById("app-dialog-panel");
        const inpWrap = document.getElementById("app-dialog-input-wrap");
        const inp   = document.getElementById("app-dialog-input");
        const okBtn = document.getElementById("app-dialog-ok");
        const cancelBtn = document.getElementById("app-dialog-cancel");

        document.getElementById("app-dialog-title").textContent = opts.title || "";
        document.getElementById("app-dialog-msg").textContent    = opts.message || "";
        okBtn.textContent = opts.okText || "OK";
        okBtn.className   = "btn " + (opts.danger ? "btn-danger" : "btn-primary");

        const withInput = !!opts.withInput;
        inpWrap.style.display = withInput ? "block" : "none";
        if(withInput) inp.value = opts.value || "";

        ov.style.display = "block";
        panel.style.display = "block";
        if(withInput){ setTimeout(()=>{ inp.focus(); inp.select(); }, 30); }
        else setTimeout(()=>okBtn.focus(), 30);

        return new Promise(resolve=>{
            const cleanup = (val)=>{
                ov.style.display = "none";
                panel.style.display = "none";
                okBtn.onclick = cancelBtn.onclick = ov.onclick = null;
                document.removeEventListener("keydown", onKey);
                resolve(val);
            };
            const confirm = ()=> cleanup(withInput ? inp.value : true);
            const cancel  = ()=> cleanup(withInput ? null : false);
            const onKey = (e)=>{
                if(e.key === "Escape"){ e.preventDefault(); cancel(); }
                else if(e.key === "Enter" && (!withInput || document.activeElement === inp)){ e.preventDefault(); confirm(); }
            };
            okBtn.onclick = confirm;
            cancelBtn.onclick = cancel;
            ov.onclick = cancel;
            document.addEventListener("keydown", onKey);
        });
    },
    // Trả về chuỗi đã nhập, hoặc null nếu huỷ.
    prompt(title, value="", message=""){
        return this._open({title, message, value, withInput:true, okText:"OK"});
    },
    // Trả về true/false.
    confirm(title, message="", {danger=false, okText="OK"}={}){
        return this._open({title, message, withInput:false, danger, okText});
    },
};

// ── Content ───────────────────────────────────────────────────
// Content cố định 3 loại — khớp với phần Lịch (homestay/thue/ban).
// Không thêm/xóa/sửa tab để giữ logic đơn giản, đồng bộ với scheduler.
const CONTENT_CATEGORIES = [
    {key:"homestay", title:"Homestay"},
    {key:"thue",     title:"Thuê"},
    {key:"ban",      title:"Bán"},
];
let _currentContentLoai = "homestay";
let _ceditData = null;

function _escapeHtml(s){
    return (s||"").toString()
        .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
        .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function renderContentTabs(){
    const box = document.getElementById("content-tabs"); if(!box) return;
    box.innerHTML = CONTENT_CATEGORIES.map(c=>{
        const active = c.key === _currentContentLoai;
        return `<div class="content-tab ${active?"active":""}" data-loai="${c.key}"
                    onclick="switchContent('${c.key}')">${_escapeHtml(c.title)}</div>`;
    }).join("");
}

// Dọn ảnh không content nào dùng tới — đếm trước, hỏi rồi mới xóa.
async function donAnhMoCoi(){
    try{
        const r = await API.quetAnhMoCoi(false);
        if(!r.ok){ Toast.error(r.error); return; }
        if(!r.so_file){ Toast.success("Không có ảnh thừa nào"); return; }
        if(!confirm(`Tìm thấy ${r.so_file} ảnh không content nào dùng tới `
                   +`(${r.dung_luong_mb} MB).\n\nXóa hẳn khỏi ổ đĩa?`)) return;
        const x = await API.quetAnhMoCoi(true);
        if(x.ok) Toast.success(`Đã xóa ${x.da_xoa} ảnh — giải phóng ${x.dung_luong_mb} MB`);
        else Toast.error(x.error);
    }catch(e){ Toast.error(e.message); }
}

// Sao lưu content của tab đang xem KÈM ảnh ra file .zip (lưu vào Downloads).
async function exportContentZip(){
    try{
        const r=await fetch(`/api/content/export-zip?loai=${encodeURIComponent(_currentContentLoai)}`);
        const res=await r.json();
        if(!res.ok) throw new Error(res.error||"không rõ lỗi");
        Toast.show(`Đã lưu ${res.count} content + ${res.so_anh} ảnh: ${res.path}`, "success", 10000);
    }catch(e){ Toast.error("Lỗi xuất backup: "+e.message); }
}

// Nhập content từ .zip vào tab đang xem (thêm & bỏ trùng theo Mã content).
async function importContentZip(e){
    const file=e.target.files[0]; if(!file) return;
    e.target.value="";  // reset để chọn lại cùng file vẫn kích hoạt onchange
    try{
        const fd=new FormData();
        fd.append("file",file);
        fd.append("loai",_currentContentLoai);
        const r=await fetch("/api/content/import-zip",{method:"POST",body:fd});
        const res=await r.json();
        if(!res.ok) throw new Error(res.error||"không rõ lỗi");
        Toast.success(`Đã thêm ${res.added} content mới (${res.so_anh} ảnh), bỏ qua ${res.skipped} trùng`);
        loadContent(_currentContentLoai);
    }catch(err){ Toast.error("Lỗi nhập backup: "+err.message); }
}

function openContentTab(loai){
    const keys = CONTENT_CATEGORIES.map(c=>c.key);
    const target = keys.includes(loai) ? loai
                 : (keys.includes(_currentContentLoai) ? _currentContentLoai : keys[0]);
    loadContent(target);
}

async function loadContent(loai){
    _currentContentLoai = loai;
    renderContentTabs();
    document.querySelectorAll(".content-tab").forEach(b=>b.classList.toggle("active",b.dataset.loai===loai));
    const tbody=document.getElementById("content-table"); if(!tbody) return;
    tbody.innerHTML=`<tr><td colspan="7" class="loading"><span class="spin">↻</span></td></tr>`;
    try{
        const res=await API.content(loai);
        const total=res.data.length, active=res.data.filter(r=>r.su_dung==="Có").length;
        const box=document.getElementById("content-summary");
        if(box) box.innerHTML=[{l:"Tổng",v:total},{l:"Đang dùng",v:active,c:"var(--success)"},{l:"Tạm dừng",v:total-active}]
            .map(s=>`<div class="metric-card" style="padding:10px 14px;flex:1"><div class="metric-label">${s.l}</div><div class="metric-value" style="font-size:20px;${s.c?"color:"+s.c:""}">${s.v}</div></div>`).join("");

        if(!res.data.length){ tbody.innerHTML=`<tr><td colspan="7" class="empty">Chưa có content</td></tr>`; return; }

        // Helper: inline-editable cell
        const ec=(r,field,style)=>{
            const val=(r[field]||"").toString(); const esc=val.replace(/"/g,"&quot;");
            return `<td class="editable" data-id="${r.id}" data-field="${field}" data-val="${esc}"
                style="${style||"font-size:12px;color:var(--text-secondary)"}"
                onclick="startContentFieldEdit(this)">${val||"-"}</td>`;
        };

        tbody.innerHTML=res.data.map(r=>{
            const imgs=(r.link_anh||"").split(",").map(s=>s.trim()).filter(Boolean);
            const encImgs=encodeURIComponent(JSON.stringify(imgs));
            const suDung=r.su_dung==="Có";

            // draggable đặt trên ô ☰, KHÔNG đặt trên <tr>: nếu <tr> draggable thì
            // không bôi đen được text trong ô Nội dung (kéo chuột biến thành kéo hàng).
            return `<tr data-id="${r.id}" style="vertical-align:top"
                ondragover="accDragOver(event)"
                ondrop="contentDrop(event,${r.id})"
                ondragleave="accDragLeave(event)">
                <td draggable="true" ondragstart="accDragStart(event,${r.id})" ondragend="accDragEnd(event)"
                    style="text-align:center;color:var(--text-muted);cursor:grab;font-size:16px;padding:8px 6px;user-select:none"
                    title="Kéo để đổi thứ tự — thứ tự này quyết định content nào vào giờ nào khi Gen lịch">☰</td>
                ${ec(r,"ma_content","font-weight:600;text-align:center;white-space:nowrap;font-size:13px")}

                <!-- Nội dung: inline edit bằng textarea -->
                <td class="editable" data-id="${r.id}" data-field="noi_dung" data-val="${(r.noi_dung||"").replace(/"/g,"&quot;")}"
                    style="font-size:12px;color:var(--text-secondary);max-width:360px;white-space:pre-wrap;word-break:break-word;padding:8px 10px"
                    onclick="startContentNdEdit(this)">${r.noi_dung||"-"}</td>

                <!-- Ảnh: click mở lightbox. Thứ tự hiển thị = thứ tự đăng lên FB. -->
                <td style="padding:4px 6px;cursor:pointer" title="Click xem ảnh"
                    onclick="openLightbox(JSON.parse(decodeURIComponent('${encImgs}')),{name:'${r.ma_content}'})">
                    <div style="display:flex;gap:2px;flex-wrap:wrap;max-width:140px">
                        ${imgs.length
                            ?imgs.slice(0,4).map(u=>`<img src="${u}" style="width:34px;height:34px;object-fit:cover;border-radius:4px;border:1px solid var(--border)">`).join("")
                             +(imgs.length>4?`<div style="width:34px;height:34px;border-radius:4px;background:var(--bg-hover);display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--accent)">+${imgs.length-4}</div>`:"")
                            :`<span style="font-size:11px;color:var(--text-muted)">-</span>`}
                    </div>
                </td>

                <!-- Sử dụng: inline edit -->
                <td class="editable" data-id="${r.id}" data-field="su_dung" data-val="${r.su_dung||""}"
                    style="text-align:center;font-weight:600;font-size:12px;color:${suDung?"var(--success)":"var(--text-muted)"}"
                    onclick="startContentFieldEdit(this)">${r.su_dung||"-"}</td>

                <!-- Ghi chú: inline edit -->
                ${ec(r,"ghi_chu","font-size:12px;color:var(--text-muted);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap")}

                <td style="text-align:center;white-space:nowrap;padding:4px 6px">
                    <button title="Chỉnh sửa" style="background:var(--accent-light);color:var(--accent);border:none;border-radius:6px;width:28px;height:28px;cursor:pointer;font-size:14px;margin-right:3px"
                        onclick='openContentEdit(${JSON.stringify(r).replace(/"/g,"&quot;")})'>✏️</button>
                    <button title="Xóa" style="background:var(--danger-light);color:var(--danger);border:none;border-radius:6px;width:28px;height:28px;cursor:pointer;font-size:14px"
                        onclick="deleteContentItem(${r.id})">🗑️</button>
                </td>
            </tr>`;
        }).join("");
    }catch(e){ tbody.innerHTML=`<tr><td colspan="7" class="empty" style="color:var(--danger)">${e.message}</td></tr>`; }
}

// Inline edit Nội dung bằng textarea (giữ xuống dòng)
function startContentNdEdit(td){
    if(td.classList.contains("editing")) return;
    td.classList.add("editing");
    const id=td.dataset.id, val=td.dataset.val||"";
    const ta=document.createElement("textarea");
    ta.value=val==="-"?"":val;
    ta.style.cssText="width:100%;min-height:120px;background:var(--bg-input);border:1px solid var(--accent);border-radius:4px;padding:6px;color:var(--text-primary);font-size:12px;line-height:1.5;resize:vertical;outline:none;font-family:inherit";
    td.innerHTML=""; td.appendChild(ta); ta.focus();
    async function commit(){
        const nv=ta.value; td.classList.remove("editing"); td.dataset.val=nv;
        td.style.whiteSpace="pre-wrap"; td.textContent=nv||"-";
        if(nv===val) return;
        td.classList.add("saving");
        try{
            const r=await API.updateContentField(parseInt(id),"noi_dung",nv);
            td.classList.remove("saving");
            if(r.ok){td.classList.add("saved");setTimeout(()=>td.classList.remove("saved"),1200);}
            else Toast.error(r.error);
        }catch(e){td.classList.remove("saving");Toast.error(e.message);}
    }
    ta.addEventListener("blur",commit);
    ta.addEventListener("keydown",e=>{
        if(e.key==="Escape"){ta.value=val;ta.blur();}
        // Ctrl+Enter để lưu
        if(e.key==="Enter"&&e.ctrlKey){e.preventDefault();ta.blur();}
    });
}

// Inline edit cho các field đơn giản của content (ma_content, su_dung, ghi_chu)
function startContentFieldEdit(td){
    if(td.classList.contains("editing")) return;
    td.classList.add("editing");
    const id=td.dataset.id, field=td.dataset.field, val=td.dataset.val||"";
    const inp=document.createElement("input"); inp.type="text"; inp.value=val==="-"?"":val;
    td.innerHTML=""; td.appendChild(inp); inp.focus(); inp.select();
    async function commit(){
        const nv=inp.value; td.classList.remove("editing"); td.dataset.val=nv;
        // Cập nhật hiển thị
        if(field==="su_dung"){
            const ok=nv==="Có";
            td.style.color=ok?"var(--success)":"var(--text-muted)";
            td.textContent=nv||"-";
        } else {
            td.textContent=nv||"-";
        }
        if(nv===val) return;
        td.classList.add("saving");
        try{
            const r=await API.updateContentField(parseInt(id),field,nv);
            td.classList.remove("saving");
            if(r.ok){td.classList.add("saved");setTimeout(()=>td.classList.remove("saved"),1200);}
            else Toast.error(r.error);
        }catch(e){td.classList.remove("saving");Toast.error(e.message);}
    }
    inp.addEventListener("blur",commit);
    inp.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();inp.blur();}if(e.key==="Escape"){inp.value=val;inp.blur();}});
}

function switchContent(loai){ loadContent(loai); }

function openContentForm(){
    openContentEdit({loai:_currentContentLoai});
}

function openContentEdit(data){
    _ceditData=data;
    document.getElementById("cedit-title").textContent=data.id?"Sửa content":"Thêm content";
    document.getElementById("cedit-body").innerHTML=`
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div class="field-group"><label>Mã content</label><input id="ce_ma" value="${data.ma_content||""}"></div>
            <div class="field-group"><label>Sử dụng</label><select id="ce_su"><option value="Có" ${data.su_dung==="Có"?"selected":""}>Có</option><option value="Không" ${data.su_dung==="Không"?"selected":""}>Không</option></select></div>
        </div>
        <div class="field-group"><label>Nội dung</label><textarea id="ce_nd" rows="8" style="width:100%;background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-primary);font-size:13px;line-height:1.6;resize:vertical;outline:none;font-family:inherit">${data.noi_dung||""}</textarea></div>
        <div class="field-group">
            <label>Ảnh <span style="font-weight:400;color:var(--text-muted);font-size:11px">— đăng lên Facebook theo đúng thứ tự này, ảnh đầu tiên đứng đầu bài</span></label>
            <div id="ce_thumbs" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px">${(data.link_anh||"").split(",").filter(Boolean).map((u,i)=>`<div class="cedit-thumb"><img src="${u.trim()}"><button class="remove-btn" onclick="_removeImg(${i})">✕</button></div>`).join("")}</div>
            <div class="upload-zone" onclick="document.getElementById('ce_imgs_file').click()" ondragover="event.preventDefault()" ondrop="_dropImgs(event)">
                <div class="upload-zone__icon">📤</div>
                <div class="upload-zone__text">Kéo thả hoặc <span>click để chọn</span></div>
                <div class="upload-zone__sub">Nhiều ảnh cùng lúc</div>
                <input id="ce_imgs_file" type="file" accept="image/*" multiple style="display:none" onchange="_imgsFile(event)">
            </div>
        </div>
        <div class="field-group"><label>Ghi chú</label><input id="ce_note" value="${data.ghi_chu||""}"></div>`;
    document.getElementById("cedit-overlay").style.display="block";
    document.getElementById("cedit-panel").style.display="flex";

    // Track images in memory
    window._ceImgUrls = (data.link_anh||"").split(",").map(s=>s.trim()).filter(Boolean);
}

function closeContentEdit(){
    document.getElementById("cedit-overlay").style.display="none";
    document.getElementById("cedit-panel").style.display="none";
}

function _removeImg(i){ window._ceImgUrls.splice(i,1); _reRenderImgThumbs(); }
function _reRenderImgThumbs(){
    document.getElementById("ce_thumbs").innerHTML=window._ceImgUrls.map((u,i)=>
        `<div class="cedit-thumb"><img src="${u}"><button class="remove-btn" onclick="_removeImg(${i})">✕</button></div>`
    ).join("");
}

async function _uploadImg(file){
    const loai = _ceditData?.loai || _currentContentLoai;
    const fd=new FormData(); fd.append("image",file); fd.append("loai",loai);
    const r=await fetch("/api/content/upload-image",{method:"POST",body:fd});
    const data=await r.json();
    if(!data.ok) throw new Error(data.error);
    return data.url;
}

async function _imgsFile(e){
    for(const file of e.target.files){
        try{ const url=await _uploadImg(file); window._ceImgUrls.push(url); }
        catch(err){ Toast.error(err.message); }
    }
    _reRenderImgThumbs(); e.target.value="";
}
function _dropImgs(e){ e.preventDefault(); const files=[...e.dataTransfer.files].filter(f=>f.type.startsWith("image/")); Promise.all(files.map(f=>_uploadImg(f))).then(urls=>{window._ceImgUrls.push(...urls);_reRenderImgThumbs();}).catch(err=>Toast.error(err.message)); }

async function saveContentEdit(){
    const btn=document.getElementById("cedit-save-btn");
    btn.disabled=true; btn.innerHTML='<span class="spin">↻</span>';
    const data={
        id:         _ceditData?.id||undefined,
        loai:       _ceditData?.loai||_currentContentLoai,
        ma_content: document.getElementById("ce_ma")?.value||"",
        su_dung:    document.getElementById("ce_su")?.value||"Có",
        noi_dung:   document.getElementById("ce_nd")?.value||"",
        link_anh:   (window._ceImgUrls||[]).join(", "),
        ghi_chu:    document.getElementById("ce_note")?.value||"",
    };
    if(!data.id) delete data.id;
    try{
        const r=await API.saveContent(data);
        if(r.ok){ Toast.success("Đã lưu"); closeContentEdit(); loadContent(data.loai); }
        else Toast.error(r.error);
    }catch(e){ Toast.error(e.message); }
    btn.disabled=false; btn.innerHTML="💾 Lưu";
}

async function deleteContentItem(id){
    if(!confirm("Xóa content này?")) return;
    try{ await API.deleteContent(id); Toast.success("Đã xóa"); loadContent(_currentContentLoai); }
    catch(e){ Toast.error(e.message); }
}

// ── UID Groups ────────────────────────────────────────────────
async function loadUidGroups(){
    const tbody=document.getElementById("uid-table"); if(!tbody) return;
    try{
        const res=await API.uidGroups();
        // Chỉ hiện nhóm từ sheet "UID Nhóm" (ma_nhom trống) — TIME1-7 dùng nội bộ
        res.data = res.data.filter(g => !g.ma_nhom || g.ma_nhom === "");
        document.getElementById("uid-count").textContent=`${res.data.length} nhóm`;
        if(!res.data.length){ tbody.innerHTML=`<tr><td colspan="5" class="empty">Chưa có UID nhóm</td></tr>`; return; }
        tbody.innerHTML=res.data.map(g=>{
            const tv = g.thanh_vien > 0
                ? `<span style="font-size:12px;color:var(--text-secondary)">${Number(g.thanh_vien).toLocaleString("vi")}</span>`
                : `<span style="color:var(--text-muted)">-</span>`;
            const linkCell = g.link_url && g.link_url.startsWith("http")
                ? `<a href="${g.link_url}" target="_blank" style="font-family:var(--font-mono);font-size:11px;color:var(--accent)">${g.uid} 🔗</a>`
                : `<span style="font-family:var(--font-mono);font-size:11px;color:var(--text-secondary)">${g.uid}</span>`;
            return `<tr data-id="${g.id}"
                ondragover="accDragOver(event)"
                ondrop="uidDrop(event,${g.id})"
                ondragleave="accDragLeave(event)">
                <td draggable="true" ondragstart="accDragStart(event,${g.id})" ondragend="accDragEnd(event)"
                    style="text-align:center;color:var(--text-muted);cursor:grab;font-size:16px;padding:4px 6px;user-select:none"
                    title="Kéo để di chuyển hàng">☰</td>
                <td style="text-align:center">${linkCell}</td>
                <td style="font-size:12px">${g.ten_nhom||"-"}</td>
                <td style="text-align:center">${tv}</td>
                <td style="text-align:center">
                    <button onclick="deleteUidGroup(${g.id})" style="background:var(--danger-light);color:var(--danger);border:none;border-radius:5px;width:26px;height:26px;cursor:pointer;font-size:12px">🗑️</button>
                </td>
            </tr>`;
        }).join("");
    }catch(e){ tbody.innerHTML=`<tr><td colspan="5" class="empty" style="color:var(--danger)">${e.message}</td></tr>`; }
}

function openUidGroupForm(data={}){
    const f=(k,l)=>`<div class="field-group"><label>${l}</label><input id="uf_${k}" value="${(data[k]||"").toString().replace(/"/g,"&quot;")}"></div>`;
    openModal(data.id?"Sửa UID nhóm":"Thêm UID nhóm",`
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            ${f("ma_nhom","Mã nhóm (TIME1...)")} ${f("uid","UID nhóm")}
            ${f("ten_nhom","Tên nhóm")} ${f("ghi_chu","Ghi chú")}
        </div>
        ${data.id?`<input type="hidden" id="uf_id" value="${data.id}">`:""}
        <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px">
            <button onclick="closeModal()" class="btn btn-ghost">Huỷ</button>
            <button onclick="saveUidGroupForm()" class="btn btn-primary">💾 Lưu</button>
        </div>`);
}

async function saveUidGroupForm(){
    const g=id=>document.getElementById(id)?.value||"";
    const data={ id:parseInt(g("uf_id"))||undefined, ma_nhom:g("uf_ma_nhom"), uid:g("uf_uid"), ten_nhom:g("uf_ten_nhom"), ghi_chu:g("uf_ghi_chu") };
    if(!data.id) delete data.id;
    try{ const r=await API.saveUidGroup(data); if(r.ok){Toast.success("Đã lưu");closeModal();loadUidGroups();}else Toast.error(r.error); }
    catch(e){ Toast.error(e.message); }
}

async function deleteUidGroup(id){
    if(!confirm("Xóa UID nhóm này?")) return;
    try{ await API.deleteUidGroup(id); Toast.success("Đã xóa"); loadUidGroups(); }
    catch(e){ Toast.error(e.message); }
}

async function exportUidGroupsExcel(){
    try{
        const res=await API.exportUidGroups();
        if(!res.ok) throw new Error(res.error||"không rõ lỗi");
        Toast.show(`Đã lưu ${res.count} UID: ${res.path}`, "success", 10000);
    }catch(e){ Toast.error("Lỗi xuất Excel: "+e.message); }
}

async function importUidGroupsExcel(e){
    const file=e.target.files[0]; if(!file) return;
    e.target.value="";  // reset để chọn lại cùng file vẫn kích hoạt onchange
    try{
        const fd=new FormData(); fd.append("file",file);
        const r=await fetch("/api/uid-groups/import-excel",{method:"POST",body:fd});
        const res=await r.json();
        if(!res.ok) throw new Error(res.error||"không rõ lỗi");
        Toast.success(`Đã thêm ${res.added} UID mới, bỏ qua ${res.skipped} trùng`);
        loadUidGroups();
    }catch(err){ Toast.error("Lỗi nhập Excel: "+err.message); }
}

// ── Schedule pages ────────────────────────────────────────────
const SCHEDULE_LABELS = {
    homestay:{title:"Homestay", kw:"Homestay Times City",
              defaultFirstGroup:"https://www.facebook.com/groups/311375961636397/"},
    thue:    {title:"Thuê",     kw:"Chợ cư dân,Cộng,Làng,times city & park hill",
              defaultFirstGroup:"https://www.facebook.com/groups/346244929095372"},
    ban:     {title:"Bán",      kw:"Chợ cư dân,Cộng,Làng,times city & park hill",
              defaultFirstGroup:"https://www.facebook.com/groups/346244929095372"},
    page:    {title:"Đăng Page", kw:"", defaultFirstGroup:""},
    // Lịch cho acc CHỈ NUÔI: tick Nuôi + để trống cột Loại đăng
    nuoi:    {title:"Nuôi nick", kw:"", defaultFirstGroup:""},
};
let _schedData={};

function renderSchedulePage(loai){
    const el=document.getElementById(`page-lich-${loai}`); if(!el) return;
    const cfg=SCHEDULE_LABELS[loai]||{};
    el.innerHTML=`
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:14px">
            <button class="btn btn-primary" onclick="openGenSchedule('${loai}')">▶ Gen lịch</button>
            ${loai==="nuoi"?`<button class="btn btn-ghost" onclick="openNuoiSettings()">⚙️ Cài đặt nuôi</button>`:""}
            <button class="btn btn-ghost"   onclick="resetSchedule('${loai}')">🔄 Reset → Chờ</button>
            <button class="btn btn-danger"  onclick="stopSchedule('${loai}')">⏹ Dừng → X</button>
            <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
                <select id="${loai}-filter" class="btn btn-ghost" style="padding:6px 10px" onchange="renderScheduleTable('${loai}',_schedData['${loai}']||[])">
                    <option value="">Tất cả</option><option value="Chờ">Chờ</option>
                    <option value="done">✅</option><option value="fail">❌</option><option value="X😴">😴 Nghỉ</option><option value="Nghỉ Spam">🚫 Nghỉ Spam</option><option value="X">X</option>
                </select>
                <span id="${loai}-count" style="font-size:12px;color:var(--text-muted)"></span>
            </div>
        </div>
        <div id="${loai}-summary" style="display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap"></div>
        <div class="card"><div class="table-wrap"><table>
            <thead><tr>
                <th>Giờ</th><th>Acc</th><th>Page</th><th>Content</th>
                <th style="text-align:center">Từ khóa</th>
                <th>Mode</th><th style="text-align:center">Trạng thái</th>
            </tr></thead>
            <tbody id="${loai}-table"><tr><td colspan="7" class="loading"><span class="spin">↻</span></td></tr></tbody>
        </table></div></div>`;
}

// ── Bài đi Comment ────────────────────────────────────────────
// Acc bị dỡ bài vẫn comment được; comment vào bài cũ làm bài nổi lên đầu nhóm.
const CMT_LOAI = [["homestay","🏠 Homestay"],["thue","🏡 Thuê"],["ban","💰 Bán"]];
let _cmtLoai = "homestay";

function renderCommentPostsPage(){
    const el=document.getElementById("page-comment-posts"); if(!el) return;
    el.innerHTML=`
        <div style="display:flex;gap:4px;margin-bottom:14px;align-items:center;flex-wrap:wrap">
            <div id="cmt-tabs" style="display:flex;gap:4px"></div>
            <button class="btn btn-ghost" style="margin-left:auto;font-size:12px" onclick="openCommentSettings()">⚙️ Cài đặt comment</button>
            <button class="btn btn-danger" style="font-size:12px" onclick="clearCommentPosts()">🗑 Xoá hết</button>
            <button class="btn btn-primary" style="font-size:12px" onclick="openAddCommentPosts()">+ Dán danh sách link</button>
        </div>
        <div style="font-size:12px;line-height:1.7;color:var(--text-muted);margin-bottom:12px;padding:10px;background:var(--bg-hover);border-radius:var(--radius-sm)">
            Link ở đây <b>tự điền</b> sau mỗi lần đăng chéo — không phải dán tay.
            Đến phiên, acc mở vài bài và để lại một comment lấy từ thư viện câu → bài nổi lên đầu nhóm.<br>
            Bật cho từng acc bằng cột <b>Loại đăng</b> ở bảng Tài khoản: <b>X_</b> = vừa đăng vừa comment,
            <b>C_</b> = chỉ comment. Đổi xong nhớ <b>Gen lịch</b> lại.<br>
            Mỗi phiên bốc <b>tối đa 1 link mỗi nhóm</b>, ưu tiên bài cũ nhất chưa comment.
            Danh sách giữ <b>300 link mới nhất</b>, link cũ bị đẩy ra sẽ xoá hẳn. Link chết (bài đã bị xoá) phát hiện lúc comment là <b>tự xoá khỏi danh sách</b>.
        </div>
        <div id="cmt-tomtat"></div>
        <div class="card"><div class="table-wrap"><table>
            <thead><tr>
                <th style="width:44px;text-align:center">#</th>
                <th>Link bài viết</th>
                <th style="width:150px;text-align:center">Page đã đăng</th>
                <th style="width:150px">Ghi chú</th>
                <th style="width:120px;text-align:center">Comment lần cuối</th>
                <th style="width:60px;text-align:center">Số lần</th>
                <th style="width:150px;text-align:center">Trạng thái</th>
                <th style="width:44px"></th>
            </tr></thead>
            <tbody id="cmt-table"><tr><td colspan="8" class="loading"><span class="spin">↻</span></td></tr></tbody>
        </table></div></div>`;
    renderCmtTabs();
    loadCommentPosts(_cmtLoai);
}

function renderCmtTabs(){
    const box=document.getElementById("cmt-tabs"); if(!box) return;
    box.innerHTML=CMT_LOAI.map(([k,ten])=>
        `<button class="btn ${_cmtLoai===k?"btn-primary":"btn-ghost"}" style="font-size:12px"
                 onclick="switchCmtLoai('${k}')">${ten}</button>`).join("");
}

function switchCmtLoai(loai){ _cmtLoai=loai; renderCmtTabs(); loadCommentPosts(loai); }

async function loadCommentPosts(loai){
    const tb=document.getElementById("cmt-table"); if(!tb) return;
    try{
        let rows=(await API.commentPosts(loai)).data||[];
        // Mới nhất lên đầu — kho là cửa sổ trượt, link cũ sắp bị đẩy ra nên
        // không đáng nằm chỗ dễ nhìn nhất.
        rows = rows.slice().reverse();
        _renderCmtTomTat(rows);
        if(!rows.length){
            tb.innerHTML=`<tr><td colspan="8" class="empty">Chưa có link nào cho loại này — bấm "+ Dán danh sách link"</td></tr>`;
            return;
        }
        tb.innerHTML=rows.map((r,i)=>`
            <tr>
                <td style="text-align:center;color:var(--text-muted);font-size:12px">${i+1}</td>
                <td style="font-size:12px;max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                    <a href="${r.url}" target="_blank" style="color:var(--accent);text-decoration:none">${_escapeHtml(r.url)}</a>
                </td>
                <td style="text-align:center;font-size:12px;color:${r.page?"#f472b6":"var(--text-muted)"}"
                    title="${r.page?("uid "+_escapeHtml(r.page)):"Link cũ chưa gắn Page — sẽ bị bỏ qua khi bật 'chỉ comment bài chính chủ'"}">
                    ${r.page?_escapeHtml(r.ten_page||r.page):"—"}
                </td>
                <td class="editable" data-id="${r.id}" data-field="ghi_chu" data-val="${_escapeHtml(r.ghi_chu||"")}"
                    style="font-size:12px;color:var(--text-muted)" onclick="startCmtFieldEdit(this)">${_escapeHtml(r.ghi_chu||"")||"-"}</td>
                <td style="text-align:center;font-size:12px;color:var(--text-muted)">${r.lan_cuoi||"-"}</td>
                <td style="text-align:center;font-size:12px">${r.so_lan||0}</td>
                <td style="text-align:center;font-size:11px">${_escapeHtml(r.trang_thai||"")||"-"}</td>
                <td style="text-align:center">
                    <button title="Xoá" style="background:var(--danger-light);color:var(--danger);border:none;border-radius:6px;width:26px;height:26px;cursor:pointer"
                            onclick="delCommentPost(${r.id})">✕</button>
                </td>
            </tr>`).join("");
    }catch(e){ tb.innerHTML=`<tr><td colspan="8" class="empty" style="color:var(--danger)">${e.message}</td></tr>`; }
}

// Bao nhiêu link đã gắn Page — link chưa gắn sẽ bị bỏ qua khi Page tìm bài
// chính chủ, nên cần thấy ngay tỉ lệ.
function _renderCmtTomTat(rows){
    const box=document.getElementById("cmt-tomtat"); if(!box) return;
    if(!rows.length){ box.innerHTML=""; return; }
    const co=rows.filter(r=>r.page).length, chua=rows.length-co;
    const theoPage={};
    rows.filter(r=>r.page).forEach(r=>{ const k=r.ten_page||r.page; theoPage[k]=(theoPage[k]||0)+1; });
    box.innerHTML=`
        <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;padding:8px 12px;margin-bottom:10px;
                    background:var(--bg-hover);border:1px solid var(--border);border-radius:var(--radius-sm);font-size:12px">
            <span><b>${rows.length}</b>/300 link</span>
            <span style="color:#f472b6">đã gắn Page: <b>${co}</b></span>
            ${chua?`<span style="color:var(--text-muted)">chưa gắn: <b>${chua}</b> (link cũ, sẽ bị đẩy ra dần)</span>`:""}
            ${Object.entries(theoPage).map(([k,n])=>`<span style="color:var(--text-muted)">${_escapeHtml(k)}: ${n}</span>`).join("")}
        </div>`;
}

function startCmtFieldEdit(td){
    if(td.querySelector("input")) return;
    const cu=td.dataset.val||"", id=td.dataset.id, field=td.dataset.field;
    td.innerHTML=`<input value="${_escapeHtml(cu)}" style="width:100%;font-size:12px">`;
    const inp=td.querySelector("input"); inp.focus(); inp.select();
    const luu=async()=>{
        const v=inp.value;
        try{ await API.commentPostField(id,field,v); td.dataset.val=v; td.innerHTML=_escapeHtml(v)||"-"; }
        catch(e){ Toast.error(e.message); td.innerHTML=_escapeHtml(cu)||"-"; }
    };
    inp.onblur=luu;
    inp.onkeydown=e=>{ if(e.key==="Enter") inp.blur(); if(e.key==="Escape"){ inp.onblur=null; td.innerHTML=_escapeHtml(cu)||"-"; } };
}

function openAddCommentPosts(){
    const ten=(CMT_LOAI.find(([k])=>k===_cmtLoai)||[])[1]||_cmtLoai;
    openModal(`+ Dán danh sách link — ${ten}`, `
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
            Mỗi dòng một link bài viết. Link đã có trong danh sách sẽ tự bỏ qua.
        </div>
        <textarea id="cmt_urls" rows="12" style="width:100%;font-family:var(--font-mono);font-size:12px;padding:8px;background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius-sm)"
            placeholder="https://www.facebook.com/groups/123456/posts/789/&#10;https://www.facebook.com/groups/123456/posts/790/"></textarea>
        <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px">
            <button onclick="closeModal()" class="btn btn-ghost">Huỷ</button>
            <button onclick="saveAddCommentPosts()" class="btn btn-primary">💾 Thêm</button>
        </div>`);
}

async function saveAddCommentPosts(){
    const v=document.getElementById("cmt_urls")?.value||"";
    try{
        const r=await API.commentPostsAdd(_cmtLoai, v);
        if(!r.ok){ Toast.error(r.error); return; }
        Toast.success(`Đã thêm ${r.them} link${r.bo_trung?` · bỏ ${r.bo_trung} link trùng`:""}`);
        closeModal(); loadCommentPosts(_cmtLoai);
    }catch(e){ Toast.error(e.message); }
}

async function delCommentPost(id){
    try{ await API.commentPostDelete(id); loadCommentPosts(_cmtLoai); }
    catch(e){ Toast.error(e.message); }
}

async function clearCommentPosts(){
    const ten=(CMT_LOAI.find(([k])=>k===_cmtLoai)||[])[1]||_cmtLoai;
    if(!confirm(`Xoá TOÀN BỘ link của ${ten}?`)) return;
    try{
        const r=await API.commentPostsClear(_cmtLoai);
        Toast.success(`Đã xoá ${r.da_xoa} link`); loadCommentPosts(_cmtLoai);
    }catch(e){ Toast.error(e.message); }
}

async function openCommentSettings(){
    let s={};
    try{ s=(await API.settings()).data||{}; }catch(e){}
    const v=(k,dv)=>{ const x=s[k]; return (x===undefined||x==="")?dv:x; };
    const num=(k,dv,w=70)=>`<input id="cs_${k}" type="number" value="${_escapeHtml(String(v(k,dv)))}" style="width:${w}px;text-align:center">`;
    const row=(label,inner,hint="")=>`
        <div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
            <div style="flex:1"><div style="font-size:13px">${label}</div>
            ${hint?`<div style="font-size:11px;color:var(--text-muted);margin-top:2px">${hint}</div>`:""}</div>
            <div>${inner}</div>
        </div>`;
    const pool=(k,ten)=>`
        <div class="field-group" style="margin-top:10px">
            <label style="display:flex;align-items:center;gap:8px">
                <span>${ten} — <span style="font-weight:400;color:var(--text-muted)">mỗi dòng 1 câu</span></span>
                <span id="cs_dem_${k}" style="margin-left:auto;font-size:11px;color:var(--text-muted)"></span>
            </label>
            <textarea id="cs_comment_pool_${k}" rows="6" oninput="_demCmtPool('${k}')"
                style="width:100%;font-size:13px;padding:8px;background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius-sm)"
                placeholder="Còn phòng không bạn ơi&#10;Cho mình xin thông tin với&#10;Giá này bao gồm gì vậy ạ">${_escapeHtml(String(v("comment_pool_"+k,"")))}</textarea>
        </div>`;

    openModal("⚙️ Cài đặt comment", `
      <div style="max-height:65vh;overflow:auto;padding-right:6px">
        <div style="font-size:12px;line-height:1.6;padding:10px;margin-bottom:12px;border-radius:var(--radius-sm);background:rgba(220,150,0,.10);border:1px solid rgba(220,150,0,.35)">
          ⚠️ <b>Comment trùng nội dung là cách nhanh nhất mất luôn quyền comment.</b>
          Thư viện càng nhiều câu càng an toàn — mỗi phiên bốc ngẫu nhiên và không lặp câu ở hai bài liền nhau.
          Mỗi phiên comment vào bao nhiêu bài thì đặt ở <i>Số bài mỗi phiên</i>.
        </div>

        <div style="font-size:12px;line-height:1.7;color:var(--text-muted);margin:4px 0 12px;padding:9px 11px;background:var(--bg-hover);border-radius:var(--radius-sm)">
            <b>Một phiên chạy y hệt luồng đăng bài Page</b>, chỉ khác bước cuối:
            story cá nhân → newsfeed cá nhân → chuyển sang Page → <b>comment từng bài</b>
            → lướt newsfeed + like 1 bài → kết thúc.<br>
            Thời lượng các bước lấy đúng theo luồng đăng bài nên không cần chỉnh riêng.
            Page luôn <b>ưu tiên comment bài của chính mình</b>; chưa có bài nào thì lùi về
            dùng chung kho.
        </div>

        ${row("Tỉ lệ comment của acc X_ (%)", num("comment_ti_le",25),
              "25 = 75% slot đăng bài, 25% slot comment. Chỉ áp cho loại đăng X_Home / X_Thuê / X_Bán.")}
        ${row("Số bài mỗi phiên", num("comment_so_bai",9),
              "Tối đa 1 bài mỗi nhóm — nên không bao giờ vượt quá số nhóm đang có trong danh sách")}
        ${row("Nghỉ giữa 2 bài (giây)",
              `${num("comment_nghi_min",10)} — ${num("comment_nghi_max",15)}`,
              "Comment liên tiếp không nghỉ là dấu hiệu máy rõ nhất")}

        <div style="display:flex;align-items:center;gap:8px;margin:16px 0 6px">
            <span style="font-size:12px;font-weight:700;color:var(--accent)">THƯ VIỆN CÂU THEO LOẠI</span>
            <span style="margin-left:auto;display:flex;gap:6px">
                <button type="button" class="btn btn-ghost" style="padding:3px 8px;font-size:11px"
                        title="Thêm câu mẫu còn thiếu vào cả 3 loại, giữ nguyên câu bạn đã tự viết"
                        onclick="napCauMauComment(true)">➕ Thêm câu mẫu</button>
                <button type="button" class="btn btn-ghost" style="padding:3px 8px;font-size:11px"
                        title="XOÁ hết câu đang có rồi thay bằng bộ mẫu 30 câu/loại"
                        onclick="napCauMauComment(false)">📥 Nạp lại từ đầu</button>
            </span>
        </div>
        ${pool("homestay","🏠 Homestay")}
        ${pool("thue","🏡 Thuê")}
        ${pool("ban","💰 Bán")}
      </div>
      <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px">
        <button onclick="closeModal()" class="btn btn-ghost">Huỷ</button>
        <button onclick="saveCommentSettings()" class="btn btn-primary">💾 Lưu</button>
      </div>`);
    CMT_LOAI.forEach(([k])=>_demCmtPool(k));
}

/**
 * Nạp thư viện câu mẫu vào cả 3 ô cùng lúc.
 * `them=true`  → chỉ thêm câu còn thiếu, giữ nguyên câu người dùng tự viết.
 * `them=false` → thay sạch, có hỏi lại vì đây là thao tác xoá dữ liệu.
 */
async function napCauMauComment(them){
    if(!them && !confirm("Xoá hết câu đang có ở cả 3 loại rồi thay bằng bộ mẫu 30 câu/loại?\n\n"
                       + "Câu bạn tự viết sẽ mất. Muốn giữ lại thì bấm Huỷ rồi chọn “Thêm câu mẫu”."))
        return;
    try{
        const r=await API.commentCauMau();
        if(!r.ok){ Toast.error(r.error); return; }
        const bao=[];
        CMT_LOAI.forEach(([k,ten])=>{
            const ta=document.getElementById(`cs_comment_pool_${k}`);
            const mau=(r.data?.[k]||"").split("\n").map(s=>s.trim()).filter(Boolean);
            if(!ta || !mau.length) return;
            let ra=mau;
            if(them){
                const cu=ta.value.split("\n").map(s=>s.trim()).filter(Boolean);
                // So khớp không phân biệt hoa thường: bấm hai lần không được đẻ
                // ra bản sao chỉ khác mỗi chữ đầu viết hoa.
                const da=new Set(cu.map(s=>s.toLowerCase()));
                ra=[...cu, ...mau.filter(m=>!da.has(m.toLowerCase()))];
            }
            ta.value=ra.join("\n");
            _demCmtPool(k);
            bao.push(`${ten.replace(/^\S+\s/,"")} ${ra.length}`);
        });
        if(!bao.length){ Toast.error("comment_mau.txt không có câu nào"); return; }
        // Toast.success chỉ nhận 1 tham số — dùng Toast.show để đặt được thời lượng.
        Toast.show((them?"Đã thêm — ":"Đã nạp — ")+bao.join(" · ")+" câu. Nhớ bấm Lưu.", "success", 6000);
    }catch(e){ Toast.error(e.message); }
}

function _demCmtPool(k){
    const ta=document.getElementById(`cs_comment_pool_${k}`), el=document.getElementById(`cs_dem_${k}`);
    if(!ta||!el) return;
    const n=ta.value.split("\n").filter(s=>s.trim()).length;
    el.textContent=n?`${n} câu`:"";
}

async function saveCommentSettings(){
    const g=id=>document.getElementById(`cs_${id}`);
    const gi=(id,dv)=>{ const n=parseInt(g(id)?.value); return isNaN(n)?dv:n; };
    const data={
        comment_ti_le:    gi("comment_ti_le",25),
        comment_so_bai:   gi("comment_so_bai",9),
        comment_nghi_min: gi("comment_nghi_min",10),
        comment_nghi_max: gi("comment_nghi_max",15),
    };
    CMT_LOAI.forEach(([k])=>{ data["comment_pool_"+k]=g("comment_pool_"+k)?.value||""; });
    if(data.comment_nghi_min > data.comment_nghi_max){
        Toast.error("Nghỉ giữa 2 bài: giá trị đầu phải nhỏ hơn giá trị sau"); return;
    }
    if(data.comment_so_bai < 1){ Toast.error("Số bài mỗi phiên phải từ 1 trở lên"); return; }
    if(data.comment_ti_le < 0 || data.comment_ti_le > 100){
        Toast.error("Tỉ lệ comment phải từ 0 đến 100"); return;
    }
    // Bật comment mà thư viện rỗng thì phiên sẽ tự bỏ qua — báo trước cho khỏi
    // ngồi soi log tưởng hỏng cookie.
    const rong=CMT_LOAI.filter(([k])=>!(data["comment_pool_"+k]||"").trim()).map(([,t])=>t);
    try{
        const r=await API.saveSettings(data);
        if(r.ok){
            Toast.success(`Đã lưu${rong.length?` — chưa có câu cho: ${rong.join(", ")}`:""}`);
            closeModal();
        } else Toast.error(r.error);
    }catch(e){ Toast.error(e.message); }
}

// ── Biến thể ảnh chống dedupe ─────────────────────────────────
async function openBienTheSettings(){
    let s={};
    try{ s=(await API.settings()).data||{}; }catch(e){}
    const v=(k,dv)=>{ const x=s[k]; return (x===undefined||x==="")?dv:x; };
    const cd=String(v("anh_bien_the_cuong_do","manh"));
    const opt=(val,ten,mo)=>`<option value="${val}" ${cd===val?"selected":""}>${ten} — ${mo}</option>`;

    openModal("🎲 Biến thể ảnh", `
      <div style="max-height:65vh;overflow:auto;padding-right:6px">
        <div style="font-size:12px;line-height:1.6;color:var(--text-muted);margin-bottom:14px">
          Bật cái này thì <b>mỗi lượt đăng</b> tạo một bản sao: lệch nhẹ độ sáng và độ tương phản,
          rồi dán một <b>mã 8 ký tự</b> vào một trong 4 góc (mỗi ảnh một mã, ghi trong log để tra ngược).
          <b>Ảnh gốc không bị sửa</b>, bản sao xoá ngay sau khi đăng xong.
        </div>
        <div style="font-size:12px;line-height:1.6;padding:10px;margin-bottom:14px;border-radius:var(--radius-sm);background:rgba(220,150,0,.10);border:1px solid rgba(220,150,0,.35)">
          ⚠️ <b>Đo thật trên ảnh homestay: chỉ dịch được 0,2–0,4 trên 64 bit</b> — trong khi
          ngưỡng Facebook coi là cùng ảnh là 8 bit. Nghĩa là bộ này đổi được file và xoá EXIF,
          nhưng <b>gần như không né được thuật toán nhận ảnh trùng</b>. Mã ở góc đóng góp ~0 bit:
          thuật toán hạ ảnh về lưới 32×32 nên vài chục pixel ở góc bị xoá mất.
          Tăng cỡ chữ mã cũng không giúp gì.<br>
          Muốn thực sự né thì phải bật <b>lật ngang</b> bên dưới (~33/64 bit).
        </div>

        <label style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border);cursor:pointer">
            <input id="bt_bat" type="checkbox" ${String(v("anh_bien_the_bat","0"))==="1"?"checked":""}
                   style="width:18px;height:18px;cursor:pointer">
            <span style="font-size:13px;font-weight:600">Bật biến thể ảnh khi đăng</span>
        </label>

        <div style="padding:12px 0;border-bottom:1px solid var(--border)">
            <div style="font-size:13px;margin-bottom:6px">Cường độ</div>
            <select id="bt_cuong_do" style="width:100%;padding:7px;background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius-sm)">
                ${opt("nhe","Nhẹ","sáng/tương phản ±2%, mã rất mờ")}
                ${opt("vua","Vừa","sáng/tương phản ±4%, mã mờ")}
                ${opt("manh","Mạnh","sáng/tương phản ±6%, mã rõ hơn chút")}
            </select>
        </div>

        <label style="display:flex;align-items:center;gap:10px;padding:12px 0;border-bottom:1px solid var(--border);cursor:pointer">
            <input id="bt_lat_ngang" type="checkbox" ${String(v("anh_bien_the_lat_ngang","0"))==="1"?"checked":""}
                   style="width:18px;height:18px;cursor:pointer;flex-shrink:0">
            <span>
                <span style="font-size:13px;font-weight:600">Lật ngang ảnh</span>
                <span style="display:block;font-size:11px;color:var(--text-muted);margin-top:2px">
                    <b>Đây là thứ duy nhất trong bảng này thực sự né được hash</b> — đo ra ~33/64 bit,
                    so với 0,2–0,4 của sáng/tương phản/mã cộng lại.
                    Đổi lại ảnh soi gương: chữ trong ảnh bị ngược, bố cục đảo bên.
                    Chỉ bật nếu ảnh của bạn không có chữ.
                </span>
            </span>
        </label>

        <div style="margin-top:14px;padding:10px;background:var(--bg-hover);border-radius:var(--radius-sm);font-size:11px;line-height:1.6;color:var(--text-muted)">
            <b>Tự kiểm chứng, đừng tin suông.</b> Mở CMD tại thư mục phần mềm và chạy:<br>
            <code style="font-family:var(--font-mono);font-size:11px">python anh_bien_the.py data/media/content/homestay --manh</code><br>
            Nó in ra khoảng cách hash giữa ảnh gốc và biến thể trên chính ảnh của bạn.
            Thấy báo "chưa đủ" thì tăng cường độ hoặc bật lật ngang.
            <br><br>
            <b>Không phải viên đạn bạc.</b> Cái này chỉ né so khớp mức pixel. Facebook còn
            nhận dạng theo <i>nội dung</i> ảnh, và caption trùng nhau thường bị soi nặng hơn ảnh.
        </div>
      </div>
      <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px">
        <button onclick="closeModal()" class="btn btn-ghost">Huỷ</button>
        <button onclick="saveBienTheSettings()" class="btn btn-primary">💾 Lưu</button>
      </div>`);
}

async function saveBienTheSettings(){
    const g=id=>document.getElementById(`bt_${id}`);
    const data={
        anh_bien_the_bat:       g("bat")?.checked?1:0,
        anh_bien_the_cuong_do:  g("cuong_do")?.value||"manh",
        anh_bien_the_lat_ngang: g("lat_ngang")?.checked?1:0,
    };
    try{
        const r=await API.saveSettings(data);
        if(r.ok){
            Toast.success(data.anh_bien_the_bat
                ? `Đã bật — cường độ ${data.anh_bien_the_cuong_do}${data.anh_bien_the_lat_ngang?" + lật ngang":""}`
                : "Đã tắt biến thể ảnh");
            closeModal();
        } else Toast.error(r.error);
    }catch(e){ Toast.error(e.message); }
}

// ── Cài đặt nuôi nick ─────────────────────────────────────────
async function openNuoiSettings(){
    let s={};
    try{ s=(await API.settings()).data||{}; }catch(e){}
    const v=(k,dv)=>{ const x=s[k]; return (x===undefined||x==="")?dv:x; };
    const chk=(k,dv)=>String(v(k,dv))==="1"?"checked":"";
    const row=(label,inner,hint="")=>`
        <div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
            <div style="flex:1">
                <div style="font-size:13px">${label}</div>
                ${hint?`<div style="font-size:11px;color:var(--text-muted);margin-top:2px">${hint}</div>`:""}
            </div>
            <div>${inner}</div>
        </div>`;
    const num=(k,dv,w=70)=>`<input id="ns_${k}" type="number" value="${_escapeHtml(String(v(k,dv)))}" style="width:${w}px;text-align:center">`;
    const sw =(k,dv)=>`<input id="ns_${k}" type="checkbox" ${chk(k,dv)} style="width:18px;height:18px;cursor:pointer">`;

    openModal("⚙️ Cài đặt nuôi nick", `
      <div style="max-height:65vh;overflow:auto;padding-right:6px">
        <div style="font-size:12px;font-weight:700;color:var(--accent);margin:4px 0 6px">HÀNH ĐỘNG MỖI PHIÊN</div>
        ${row("📖 Lướt story",           sw("nuoi_enable_story",1))}
        ${row("📜 Lướt newsfeed",        sw("nuoi_enable_feed",1), "Chỉ đọc, không like")}
        ${row("👍 Like dạo",             sw("nuoi_enable_like",1))}
        ${row("💬 Nhắn tin nhóm",        sw("nuoi_enable_message",1), "Cần link nhóm + thư viện câu bên dưới")}

        <div style="font-size:12px;font-weight:700;color:var(--accent);margin:16px 0 6px">THÔNG SỐ</div>
        ${row("Số like mỗi phiên",       num("nuoi_like_count",1))}
        ${row("Độ dài phiên (giây)",
              `${num("nuoi_session_min_sec",300)} — ${num("nuoi_session_max_sec",480)}`,
              "Mặc định 300–480s (5–8 phút)")}

        <div style="font-size:12px;font-weight:700;color:var(--accent);margin:16px 0 6px">💬 NHẮN TIN NHÓM</div>
        <div class="field-group" style="margin-bottom:10px">
            <label style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <span>Link nhóm chat nội bộ — <span style="font-weight:400;color:var(--text-muted)">mỗi dòng 1 nhóm, mỗi phiên vào ngẫu nhiên 1 nhóm</span></span>
                <span id="ns_group_count" style="margin-left:auto;font-size:11px;color:var(--text-muted)"></span>
            </label>
            <textarea id="ns_nuoi_msg_group_url" rows="4" oninput="_updateGroupCount()"
                style="width:100%;font-family:var(--font-mono);font-size:12px;padding:8px;background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius-sm)"
                placeholder="https://www.facebook.com/messages/t/1234567890&#10;https://www.facebook.com/messages/t/9876543210">${_escapeHtml(String(v("nuoi_msg_group_url","")))}</textarea>
        </div>
        ${row("Số tin nhắn mỗi phiên",
              `${num("nuoi_msg_min",2)} — ${num("nuoi_msg_max",3)}`)}
        <div class="field-group" style="margin-top:10px">
            <label style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <span>Thư viện câu — <span style="font-weight:400;color:var(--text-muted)">mỗi dòng 1 câu, bốc ngẫu nhiên</span></span>
                <span style="margin-left:auto;display:flex;gap:6px;align-items:center">
                    <span id="ns_pool_count" style="font-size:11px;color:var(--text-muted)"></span>
                    <button type="button" class="btn btn-ghost" style="padding:3px 8px;font-size:11px"
                            onclick="loadMsgMau(false)">📥 Nạp 500 câu mẫu</button>
                    <button type="button" class="btn btn-ghost" style="padding:3px 8px;font-size:11px"
                            onclick="loadMsgMau(true)">➕ Thêm vào</button>
                </span>
            </label>
            <textarea id="ns_nuoi_msg_pool" rows="8" oninput="_updatePoolCount()"
                style="width:100%;font-family:inherit;font-size:13px;padding:8px;background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius-sm)"
                placeholder="Hôm nay trời đẹp nhỉ&#10;Mọi người ăn trưa chưa&#10;Cuối tuần này đi đâu chơi không">${_escapeHtml(String(v("nuoi_msg_pool","")))}</textarea>
        </div>
      </div>
      <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px">
        <button onclick="closeModal()" class="btn btn-ghost">Huỷ</button>
        <button onclick="saveNuoiSettings()" class="btn btn-primary">💾 Lưu</button>
      </div>`);
    _updatePoolCount();
    _updateGroupCount();
}

// Nạp thư viện câu mẫu. append=false: thay hết | true: nối thêm (bỏ câu trùng).
async function loadMsgMau(append){
    const ta=document.getElementById("ns_nuoi_msg_pool"); if(!ta) return;
    try{
        const r=await API.nuoiMsgMau();
        if(!r.ok){ Toast.error(r.error); return; }
        const mau=(r.text||"").split("\n").map(s=>s.trim()).filter(Boolean);
        let out=mau;
        if(append){
            const cu=ta.value.split("\n").map(s=>s.trim()).filter(Boolean);
            out=[...cu, ...mau.filter(m=>!cu.includes(m))];
        }
        ta.value=out.join("\n");
        _updatePoolCount();
        Toast.success(append?`Đã thêm — tổng ${out.length} câu`:`Đã nạp ${out.length} câu`);
    }catch(e){ Toast.error(e.message); }
}

// Đếm số nhóm chat hợp lệ (mỗi dòng 1 link) — khớp với parse_group_urls bên Python.
function _dsNhomChat(){
    const ta=document.getElementById("ns_nuoi_msg_group_url");
    if(!ta) return [];
    const ra=[];
    for(const d of (ta.value||"").replace(/,/g,"\n").split("\n")){
        const u=d.trim();
        if(u.startsWith("http") && !ra.includes(u)) ra.push(u);
    }
    return ra;
}

function _updateGroupCount(){
    const el=document.getElementById("ns_group_count");
    if(!el) return;
    const n=_dsNhomChat().length;
    el.textContent = n ? `${n} nhóm` : "";
}

function _updatePoolCount(){
    const ta=document.getElementById("ns_nuoi_msg_pool");
    const el=document.getElementById("ns_pool_count");
    if(!ta||!el) return;
    const n=ta.value.split("\n").filter(s=>s.trim()).length;
    el.textContent=n?`${n} câu`:"";
}

async function saveNuoiSettings(){
    const g =id=>document.getElementById(`ns_${id}`);
    const gi=(id,dv)=>{ const n=parseInt(g(id)?.value); return isNaN(n)?dv:n; };
    const gc=id=>g(id)?.checked?1:0;
    const data={
        nuoi_enable_story:     gc("nuoi_enable_story"),
        nuoi_enable_feed:      gc("nuoi_enable_feed"),
        nuoi_enable_like:      gc("nuoi_enable_like"),
        nuoi_enable_message:   gc("nuoi_enable_message"),
        nuoi_like_count:       gi("nuoi_like_count",1),
        nuoi_session_min_sec:  gi("nuoi_session_min_sec",300),
        nuoi_session_max_sec:  gi("nuoi_session_max_sec",480),
        nuoi_msg_min:          gi("nuoi_msg_min",2),
        nuoi_msg_max:          gi("nuoi_msg_max",3),
        // Lưu lại dạng đã chuẩn hoá: mỗi dòng 1 link, bỏ trùng
        nuoi_msg_group_url:    _dsNhomChat().join("\n"),
        nuoi_msg_pool:         g("nuoi_msg_pool")?.value||"",
    };
    const nNhom = _dsNhomChat().length;
    if(data.nuoi_session_min_sec > data.nuoi_session_max_sec){
        Toast.error("Độ dài phiên: giá trị đầu phải nhỏ hơn giá trị sau"); return;
    }
    if(data.nuoi_msg_min > data.nuoi_msg_max){
        Toast.error("Số tin nhắn: giá trị đầu phải nhỏ hơn giá trị sau"); return;
    }
    // Bật nhắn tin mà chưa có nhóm/câu thì phiên nuôi sẽ tự bỏ qua — báo trước.
    const nPool=(data.nuoi_msg_pool||"").split("\n").filter(s=>s.trim()).length;
    if(data.nuoi_enable_message && (!nNhom || !nPool)){
        Toast.error("Bật nhắn tin thì phải có ít nhất 1 link nhóm và 1 câu"); return;
    }
    try{
        const r=await API.saveSettings(data);
        if(r.ok){ Toast.success(`Đã lưu${data.nuoi_enable_message?` · ${nNhom} nhóm · ${nPool} câu`:""}`); closeModal(); }
        else Toast.error(r.error);
    }catch(e){ Toast.error(e.message); }
}

async function loadSchedule(loai){
    try{
        const res=await API.schedule(loai);
        _schedData[loai]=res.data;
        renderScheduleSummary(loai,res.data);
        renderScheduleTable(loai,res.data);
    }catch(e){
        const tb=document.getElementById(`${loai}-table`);
        if(tb) tb.innerHTML=`<tr><td colspan="7" class="empty" style="color:var(--danger)">${e.message}</td></tr>`;
    }
}

function renderScheduleSummary(loai,data){
    const box=document.getElementById(`${loai}-summary`); if(!box) return;
    const total=data.length,cho=data.filter(r=>r.trang_thai==="Chờ").length,
          done=data.filter(r=>r.trang_thai.startsWith("✅")).length,
          fail=data.filter(r=>r.trang_thai.startsWith("❌")).length,
          nghi=data.filter(r=>r.trang_thai==="X😴").length,
          stop=data.filter(r=>r.trang_thai==="X").length;
    box.innerHTML=[{l:"Tổng",v:total},{l:"Chờ",v:cho},{l:"✅",v:done},{l:"❌",v:fail},{l:"😴 Nghỉ",v:nghi},{l:"X",v:stop}]
        .map(s=>`<div class="metric-card" style="padding:10px 14px;flex:1;min-width:70px"><div class="metric-label">${s.l}</div><div class="metric-value" style="font-size:20px">${s.v}</div></div>`).join("");
}

function renderScheduleTable(loai,data){
    const tbody=document.getElementById(`${loai}-table`); if(!tbody) return;
    const count=document.getElementById(`${loai}-count`);
    const filter=document.getElementById(`${loai}-filter`)?.value||"";
    const rows=(data||[]).filter(r=>{
        const st=r.trang_thai||"";
        if(!filter) return true;
        if(filter==="done") return st.startsWith("✅");
        if(filter==="fail") return st.startsWith("❌");
        return st===filter;
    });
    if(count) count.textContent=`${rows.length}/${(data||[]).length}`;
    if(!rows.length){ tbody.innerHTML=`<tr><td colspan="7" class="empty">Không có dòng nào</td></tr>`; return; }
    const sc=(r,field,style)=>{
        const val=(r[field]||"").toString(); const esc=val.replace(/"/g,"&quot;");
        return `<td class="editable" data-id="${r.id}" data-loai="${loai}" data-field="${field}" data-val="${esc}" style="font-size:12px;${style||""}" onclick="startSchedEdit(this)">${val||"-"}</td>`;
    };
    tbody.innerHTML=rows.map(r=>{
        const st=r.trang_thai||"";
        let stBadge;
        if(st.startsWith("✅")) stBadge=`<span class="badge badge-success">${st}</span>`;
        else if(st.startsWith("🌱")) stBadge=`<span class="badge" style="background:#064e3b;color:#6ee7b7">${st}</span>`;
        else if(st.startsWith("❌")) stBadge=`<span class="badge badge-danger">${st.slice(0,30)}</span>`;
        // "Bỏ qua" KHÔNG phải lỗi — phiên chạy bình thường nhưng danh sách link
        // đang trống. Gộp chung với lỗi thì cả bảng nhìn như hỏng hết, trong
        // khi việc cần làm chỉ là dán thêm link.
        else if(st.includes("bỏ qua"))
            stBadge=`<span class="badge" style="background:#422006;color:#fbbf24"
                       title="Không phải lỗi — chưa có link trong tab Bài đi Comment cho loại này.">⏸ ${st.replace(/^💬\s*/,"")}</span>`;
        else if(st.startsWith("💬")) stBadge=`<span class="badge" style="background:#1e3a5f;color:#93c5fd">${st}</span>`;
        else if(st==="X😴") stBadge=`<span class="badge" style="background:#422006;color:#fbbf24" title="Máy tự tắt vì acc nghỉ/chết/cookie hết hạn — sẽ tự về Chờ ngày mai">😴 Nghỉ</span>`;
        else if(st==="X") stBadge=`<span class="badge badge-muted">X</span>`;
        else if(st==="Chờ") stBadge=`<span class="badge badge-warning">Chờ</span>`;
        else stBadge=`<span class="badge badge-muted">${st||"-"}</span>`;
        // Slot đã bị chuyển thành phiên nuôi / comment — hiển thị khác để dễ phân biệt.
        const hd=(r.hoat_dong||"dang_bai");
        const contentCell=
            hd==="nuoi_nick"
            ? `<td style="text-align:center"><span class="badge" style="background:#064e3b;color:#6ee7b7">🌱 Nuôi nick</span></td>`
            : hd==="comment"
            ? `<td style="text-align:center"><span class="badge" style="background:#1e3a5f;color:#93c5fd">💬 Comment</span></td>`
            : sc(r,"ma_content","text-align:center");
        return `<tr>
            ${sc(r,"gio_dang","font-weight:600;white-space:nowrap")}
            ${sc(r,"ten_acc","")} ${sc(r,"ten_page","color:var(--text-secondary)")}
            ${contentCell}
            ${sc(r,"tu_khoa","text-align:center;color:var(--text-secondary)")}
            ${sc(r,"mode","text-align:center")}
            <td class="editable" data-id="${r.id}" data-loai="${loai}" data-field="trang_thai" data-val="${(r.trang_thai||"").replace(/"/g,"&quot;")}" style="text-align:center" onclick="startSchedEdit(this)">${stBadge}</td>
        </tr>`;
    }).join("");
}

function startSchedEdit(td){
    if(td.classList.contains("editing")) return;
    td.classList.add("editing");
    const id=td.dataset.id, loai=td.dataset.loai, field=td.dataset.field, val=td.dataset.val||"";
    const inp=document.createElement("input"); inp.type="text"; inp.value=val==="-"?"":val;
    td.innerHTML=""; td.appendChild(inp); inp.focus(); inp.select();
    async function commit(){
        const nv=inp.value; td.classList.remove("editing"); td.dataset.val=nv; td.textContent=nv||"-";
        if(nv===val) return;
        td.classList.add("saving");
        try{
            const r=await API.scheduleCell(loai,parseInt(id),field,nv);
            td.classList.remove("saving");
            if(r.ok){td.classList.add("saved");setTimeout(()=>td.classList.remove("saved"),1200);}
            else Toast.error(r.error);
        }catch(e){td.classList.remove("saving");Toast.error(e.message);}
    }
    inp.addEventListener("blur",commit);
    inp.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();inp.blur();}if(e.key==="Escape"){inp.value=val;inp.blur();}});
}

async function resetSchedule(loai){
    if(!confirm(`Reset TẤT CẢ → 'Chờ'?`)) return;
    try{ const r=await API.scheduleReset(loai); if(r.ok){Toast.success(`Reset ${r.updated} dòng`);loadSchedule(loai);}else Toast.error(r.error); }
    catch(e){Toast.error(e.message);}
}

async function stopSchedule(loai){
    if(!confirm(`Dừng TẤT CẢ → 'X'?`)) return;
    try{ const r=await API.scheduleStop(loai); if(r.ok){Toast.success(`Dừng ${r.updated} dòng`);loadSchedule(loai);}else Toast.error(r.error); }
    catch(e){Toast.error(e.message);}
}

// ── Gen lịch ──────────────────────────────────────────────────
let _genLoai="", _genAccData=[], _genContents=[];

async function openGenSchedule(loai){
    _genLoai=loai;
    const cfg=SCHEDULE_LABELS[loai]||{};
    document.getElementById("gen-panel-title").textContent=`▶ Gen lịch ${cfg.title}`;
    document.getElementById("gen-overlay").style.display="block";
    document.getElementById("gen-panel").style.display="flex";

    if(loai==="page"){
        // Ưu tiên thiết lập gen Page gần nhất đã lưu; chưa có thì dùng mặc định.
        let pp = {};
        try{ const s=await API.settings(); pp=JSON.parse(s.data?.gen_prefs_page||"{}"); }catch(e){ pp={}; }
        const vAcc   = _escapeHtml(pp.acc || "Nguyễn Hương");
        const vStart = _escapeHtml(String(pp.start_hour ?? 7));
        const vEnd   = _escapeHtml(String(pp.end_hour ?? 23));
        document.getElementById("gen-panel-body").innerHTML=`
            <div class="field-group"><label>Tài khoản đăng</label><input id="gen-page-acc" value="${vAcc}"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="field-group"><label>Giờ bắt đầu</label><input id="gen-page-start" type="number" value="${vStart}"></div>
                <div class="field-group"><label>Giờ kết thúc</label><input id="gen-page-end" type="number" value="${vEnd}"></div>
            </div>
            <div style="font-size:12px;color:var(--text-muted);background:var(--bg-hover);padding:10px;border-radius:var(--radius-sm)">
                Lấy Page từ bảng Pages (Bài đăng tối đa > 0), pick content ngẫu nhiên, trải đều khung giờ.
            </div>`;
        return;
    }

    if(loai==="nuoi"){
        // Acc CHỈ NUÔI: tick Nuôi + để trống Loại đăng. Chu kỳ lấy từ cột
        // "Chu kỳ (p)" của từng acc, nên form chỉ cần khung giờ hoạt động.
        let pp={};
        try{ const s=await API.settings(); pp=JSON.parse(s.data?.gen_prefs_nuoi||"{}"); }catch(e){ pp={}; }
        const vStart=_escapeHtml(pp.start||"07:00"), vEnd=_escapeHtml(pp.end||"23:00");
        let list=[];
        try{
            const r=await API.accounts();
            list=(r.data||[]).filter(a=>String(a.nuoi_nick)==="1" && !(a.loai_dang||"").trim());
        }catch(e){}
        const info = list.length
            ? list.map(a=>`${a.ten_acc} — mỗi ${a.nuoi_interval||150} phút`).join("<br>")
            : `<span style="color:var(--warning)">Chưa có acc nào 'chỉ nuôi'. Cần: tick <b>Nuôi</b> + để <b>TRỐNG</b> cột Loại đăng.</span>`;
        document.getElementById("gen-panel-body").innerHTML=`
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="field-group"><label>Giờ bắt đầu</label><input id="gen-nuoi-start" value="${vStart}"></div>
                <div class="field-group"><label>Giờ kết thúc</label><input id="gen-nuoi-end" value="${vEnd}"></div>
            </div>
            <div style="font-size:12px;color:var(--text-muted);background:var(--bg-hover);padding:10px;border-radius:var(--radius-sm);line-height:1.7">
                <b>Acc chỉ nuôi (${list.length}):</b><br>${info}
            </div>`;
        return;
    }

    document.getElementById("gen-panel-body").innerHTML=`<div class="loading"><span class="spin">↻</span> Đang tải acc...</div>`;
    try{
        const res=await API.scheduleGenData(loai);
        _genAccData=res.accs; _genContents=res.contents;
        // Ưu tiên thiết lập gen gần nhất đã lưu; chưa có thì mới dùng mặc định.
        const p = res.prefs || {};
        const vStart = _escapeHtml(p.start || "05:00");
        const vEnd   = _escapeHtml(p.end   || "03:00");
        const vFirst = _escapeHtml(p.first_group || cfg.defaultFirstGroup || "");
        const vKw    = _escapeHtml(("keyword" in p) ? p.keyword : (cfg.kw || ""));
        document.getElementById("gen-panel-body").innerHTML=`
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="field-group"><label>Giờ bắt đầu</label><input id="gen-start" value="${vStart}"></div>
                <div class="field-group"><label>Giờ kết thúc</label><input id="gen-end" value="${vEnd}"></div>
            </div>
            <div class="field-group">
                <label>Nhóm đầu <span style="color:var(--text-muted);font-weight:400">(link hoặc UID — dùng chung cho mọi acc để mở composer)</span></label>
                <input id="gen-first-group" type="text" value="${vFirst}"
                    placeholder="https://www.facebook.com/groups/...">
            </div>
            <div class="field-group"><label>Từ khóa (cách nhau dấu phẩy)</label><input id="gen-kw" value="${vKw}"></div>
            ${_renderNhip(res.nhip, res.accs)}
            <div style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em">Cài đặt từng tài khoản</div>
            <div id="gen-accs">${_renderGenAccs(res.accs, res.contents)}</div>`;
    }catch(e){
        document.getElementById("gen-panel-body").innerHTML=`<div class="empty" style="color:var(--danger)">${e.message}</div>`;
    }
}

// Tóm tắt nhịp phủ — cho thấy phiên comment tính ngang phiên đăng bài, và
// khoảng cách trung bình giữa hai phiên bất kỳ trong ngày.
function _renderNhip(nhip, accs){
    if(!nhip) return "";
    const nCmt = accs.filter(a=>a.chi_comment).length;
    const nPost = accs.length - nCmt;
    return `
    <div style="background:var(--bg-hover);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px;font-size:12px;line-height:1.7">
        <b>Nhịp phủ nhóm</b> — phiên comment tính ngang phiên đăng bài<br>
        <span style="color:var(--text-muted)">Đăng bài:</span> ${nPost} acc · <b>${nhip.luc_dang}</b> phiên/h
        &nbsp;·&nbsp;
        <span style="color:#c084fc">Comment:</span> ${nCmt} acc · <b>${nhip.luc_comment}</b> phiên/h<br>
        <span style="color:var(--text-muted)">Tổng lực:</span> <b>${nhip.tong_luc}</b> phiên/h
        → trung bình <b>${nhip.do_nen} phút</b> lại có một phiên nổ, rải đều cả khung giờ.
    </div>
`;
}

function _renderGenAccs(accs, contents){
    if(!accs.length) return `<div class="empty">Không có acc Active nào cho loại này</div>`;
    const n = accs.length;
    const nc = contents.length;
    return accs.map((acc,i)=>{
        // Trải đều content: acc[0]=H1, acc[1]=H5, acc[2]=H9, acc[3]=H13 (với 17 content, 4 acc)
        const defC = contents[Math.floor(i * nc / n) % nc] || "";
        // Acc chỉ comment không dùng content lẫn mode — vẫn render <select> ẩn
        // để runGen đọc theo chỉ số i không bị lệch, nhưng không bày ra cho rối.
        const oCmt = acc.chi_comment;          // đang dính spam — ẩn ô Content/Mode
        const oMix = acc.hon_hop;              // X_* — vẫn đăng bài nên giữ nguyên ô
        return `
        <div style="background:var(--bg-hover);border:1px solid ${oCmt?"#c084fc55":"var(--border)"};border-radius:var(--radius-sm);padding:12px;margin-bottom:8px">
            <div style="font-weight:600;font-size:13px;margin-bottom:${oCmt?0:10}px">${acc.ten}
                ${oCmt?`<span class="badge" style="background:#3b1f5e;color:#c084fc;margin-left:6px">💬 chỉ comment</span>`:""}
                ${oMix?`<span class="badge" style="background:#4c1d3d;color:#f472b6;margin-left:6px">📝💬 đăng + comment</span>`:""}
                <span style="font-size:11px;font-weight:400;color:var(--text-muted)"> — nghỉ ${acc.nghi}p · lực ${acc.luc_dang} phiên/h</span>
            </div>
            <div style="display:${oCmt?"none":"grid"};grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
                <div class="field-group">
                    <label>Content đầu <span style="color:var(--text-muted);font-weight:400">(bắt đầu từ)</span></label>
                    <select id="acc-c-${i}">
                        ${contents.map(c=>`<option value="${c}" ${c===defC?"selected":""}>${c}</option>`).join("")}
                    </select>
                </div>
                <div class="field-group">
                    <label>Mode</label>
                    <select id="acc-m-${i}">
                        <option value="Hybrid" selected>Hybrid</option>
                        <option value="Via">Via</option>
                    </select>
                </div>
            </div>
        </div>`;
    }).join("");
}

function closeGen(){
    document.getElementById("gen-overlay").style.display="none";
    document.getElementById("gen-panel").style.display="none";
}

async function runGen(){
    const btn=document.getElementById("gen-run-btn"); btn.disabled=true; btn.innerHTML='<span class="spin">↻</span>';
    try{
        let res;
        if(_genLoai==="nuoi"){
            res=await API.scheduleNuoiGen({
                start: document.getElementById("gen-nuoi-start")?.value||"07:00",
                end:   document.getElementById("gen-nuoi-end")?.value||"23:00",
            });
        } else if(_genLoai==="page"){
            res=await API.schedulePageGen({
                acc: document.getElementById("gen-page-acc")?.value||"",
                start_hour: parseInt(document.getElementById("gen-page-start")?.value||"7"),
                end_hour:   parseInt(document.getElementById("gen-page-end")?.value||"23"),
            });
        } else {
            const kwPool=(document.getElementById("gen-kw")?.value||"").split(",").map(s=>s.trim()).filter(Boolean);
            const firstGroup=(document.getElementById("gen-first-group")?.value||"").trim();
            if(!firstGroup){ Toast.error("Chưa nhập 'Nhóm đầu' để mở composer"); btn.disabled=false; btn.innerHTML="▶ Tạo lịch"; return; }
            const accSettings=_genAccData.map((acc,i)=>({
                ten:       acc.ten,
                page:      acc.page,
                nghi:      acc.nghi,
                luc_dang:  acc.luc_dang,
                c_offset:  _genContents.indexOf(document.getElementById(`acc-c-${i}`)?.value||"")||0,
                first_group_url: firstGroup,
                mode:      document.getElementById(`acc-m-${i}`)?.value||"Hybrid",
                contents:  _genContents,
            }));
            res=await API.scheduleGen(_genLoai,{
                start:document.getElementById("gen-start")?.value||"05:00",
                end:document.getElementById("gen-end")?.value||"03:00",
                keyword_pool:kwPool, acc_settings:accSettings,
            });
        }
        if(res.ok){ Toast.success(`✅ Đã tạo ${res.total} dòng${res.nuoi?` · 🌱 ${res.nuoi} nuôi`:""} (${res.from}→${res.to})`); closeGen(); loadSchedule(_genLoai); }
        else Toast.error(res.error);
    }catch(e){ Toast.error(e.message); }
    btn.disabled=false; btn.innerHTML="▶ Tạo lịch";
}

// ── Logs ──────────────────────────────────────────────────────
let _logAutoInterval=null;
async function loadLogs(){
    const n=parseInt(document.getElementById("log-lines")?.value||"80");
    const runners=["homestay","thue","ban","page","nuoi"];
    await Promise.all(runners.map(async loai=>{
        const box=document.getElementById(`log-${loai}`); if(!box) return;
        try{
            const r=await API.logs(loai,n);
            const html=(r.text||"").replace(/</g,"&lt;").split("\n").map(l=>{
                if(/\[ERROR\]/.test(l)) return `<span class="l-error">${l}</span>`;
                if(/\[WARNING\]/.test(l)) return `<span class="l-warn">${l}</span>`;
                if(/✅/.test(l)) return `<span class="l-success">${l}</span>`;
                return `<span class="l-info">${l}</span>`;
            }).join("\n");
            box.innerHTML=html; box.scrollTop=box.scrollHeight;
        }catch(e){ if(box) box.textContent="Lỗi: "+e.message; }
    }));
    // Join log
    const joinBox=document.getElementById("log-join"); if(!joinBox) return;
    try{
        const r=await API.logsJoin(n*2);
        const html=(r.text||"").replace(/</g,"&lt;").split("\n").map(l=>{
            if(/\[ERROR\]/.test(l)) return `<span class="l-error">${l}</span>`;
            if(/\[WARNING\]/.test(l)) return `<span class="l-warn">${l}</span>`;
            if(/✅|Hoàn thành/.test(l)) return `<span class="l-success">${l}</span>`;
            if(/⏭️|Đã là/.test(l)) return `<span class="l-info" style="opacity:0.6">${l}</span>`;
            return `<span class="l-info">${l}</span>`;
        }).join("\n");
        joinBox.innerHTML=html; joinBox.scrollTop=joinBox.scrollHeight;
    }catch(e){ if(joinBox) joinBox.textContent="Lỗi: "+e.message; }
}

// ── Đăng ký và chờ duyệt ──────────────────────────────────────
// Chỉ chạy khi máy chủ báo bat_buoc=true, tức là đã gắn khoá công khai. Chưa
// gắn thì phần mềm hoạt động y như trước, không thấy màn hình này bao giờ.

let _duyetHen = null;          // nhịp dày, dùng khi đang bị chặn
let _duyetHenDaiHan = null;    // nhịp thưa, dùng khi đã được vào

async function _duyetKiem(){
    let j;
    try{
        j = await (await fetch("/api/phe-duyet/status", {cache:"no-store"})).json();
    }catch(e){ return; }

    const lop = document.getElementById("duyet-overlay");
    if(!lop) return;

    if(!j.bat_buoc || j.cho_vao){
        lop.style.display = "none";
        if(_duyetHen){ clearInterval(_duyetHen); _duyetHen = null; }
        // Được vào rồi vẫn hỏi lại đều đặn, vì hai lý do:
        //   - máy chủ mới biết máy này CÒN ĐANG DÙNG, để hiện trong bảng quản lý
        //   - thu hồi quyền có hiệu lực trong vòng 30 phút, thay vì phải đợi
        //     hết hạn nhớ 7 ngày
        if(j.bat_buoc && !_duyetHenDaiHan){
            _duyetHenDaiHan = setInterval(_duyetKiem, 30*60*1000);
        }
        return;
    }

    lop.style.display = "flex";
    document.getElementById("duyet-ma-may").textContent = j.ma_may || "…";

    const icon = document.getElementById("duyet-icon");
    const tieu = document.getElementById("duyet-tieu-de");
    const mota = document.getElementById("duyet-mo-ta");
    const form = document.getElementById("duyet-form");

    if(j.trang_thai === "cho_duyet"){
        // Đã gửi rồi — không cho gửi lại nữa, chỉ chờ.
        icon.textContent = "⏳";
        tieu.textContent = "Đang chờ duyệt";
        mota.innerHTML = "Đã gửi đăng ký. Gửi mã máy ở dưới cho chủ phần mềm "+
                         "để được duyệt nhanh hơn.<br>Màn hình này tự tắt khi được duyệt.";
        form.style.display = "none";
        // Chờ duyệt thì hỏi thưa hơn — người ta duyệt bằng tay, không có
        // chuyện đổi trong vài giây.
        if(!_duyetHen) _duyetHen = setInterval(_duyetKiem, 20000);
        return;
    }

    if(j.trang_thai === "bi_cat"){
        icon.textContent = "⛔";
        tieu.textContent = "Quyền sử dụng đã bị thu hồi";
        mota.textContent = "Liên hệ chủ phần mềm nếu bạn nghĩ đây là nhầm lẫn.";
        form.style.display = "none";
        if(!_duyetHen) _duyetHen = setInterval(_duyetKiem, 20000);
        return;
    }

    icon.textContent = "🔑";
    tieu.textContent = "Đăng ký sử dụng";
    mota.textContent = "Điền thông tin rồi gửi. Chủ phần mềm duyệt xong là bạn dùng được.";
    form.style.display = "";
    if(j.thong_bao) document.getElementById("duyet-loi").textContent = j.thong_bao;
    if(!_duyetHen) _duyetHen = setInterval(_duyetKiem, 20000);
}

async function guiDangKy(){
    const nut = document.getElementById("duyet-gui");
    const loi = document.getElementById("duyet-loi");
    loi.textContent = "";
    const than = {
        ten:        document.getElementById("duyet-ten").value,
        dien_thoai: document.getElementById("duyet-dt").value,
        email:      document.getElementById("duyet-email").value,
    };
    if(!than.ten.trim()){ loi.textContent = "Chưa nhập họ tên."; return; }
    if(!than.dien_thoai.trim() && !than.email.trim()){
        loi.textContent = "Nhập số điện thoại hoặc Gmail."; return;
    }
    nut.disabled = true; nut.textContent = "Đang gửi…";
    try{
        const j = await (await fetch("/api/phe-duyet/dang-ky", {
            method:"POST", headers:{"Content-Type":"application/json"},
            body: JSON.stringify(than)
        })).json();
        if(!j.ok){ loi.textContent = j.error || "Không gửi được."; }
        else { await _duyetKiem(); }
    }catch(e){ loi.textContent = "Không gửi được: " + e.message; }
    nut.disabled = false; nut.textContent = "Gửi đăng ký";
}

// ── Chromium: lần chạy đầu ────────────────────────────────────
// Máy vừa cài xong chưa có Chromium. Che màn hình và tải, vì chưa có nó thì
// không đăng bài / comment / nuôi nick được — cho vào app cũng chẳng làm gì.

let _chromiumHen = null;

async function _chromiumKiem(){
    let j;
    try{
        j = await (await fetch("/api/chromium/status", {cache:"no-store"})).json();
    }catch(e){ return; }

    const lop = document.getElementById("chromium-overlay");
    if(!lop) return;

    if(j.da_co){
        lop.style.display = "none";
        if(_chromiumHen){ clearInterval(_chromiumHen); _chromiumHen = null; }
        return;
    }

    lop.style.display = "flex";
    const pt = j.phan_tram || 0;
    document.getElementById("chromium-thanh").style.width = pt + "%";
    document.getElementById("chromium-phantram").textContent =
        j.loi ? "Có lỗi" : (pt + "%");
    document.getElementById("chromium-dong").textContent =
        j.loi ? j.loi : (j.dong_cuoi || "");

    // Chưa ai bắt đầu thì bắt đầu, rồi hỏi tiến độ mỗi 2 giây.
    if(!j.dang_chay && !j.loi){
        await fetch("/api/chromium/install", {method:"POST"});
    }
    if(!_chromiumHen) _chromiumHen = setInterval(_chromiumKiem, 2000);
}

// ── Cập nhật phiên bản ────────────────────────────────────────
// Bấm số phiên bản dưới logo → hiện các bản đã phát hành để chọn.
// Việc tải và thay code do UPDATE.bat làm; ở đây chỉ hỏi và gọi.

function _thoat(s){
    return String(s||"").replace(/[&<>"']/g, c => (
        {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

// Ghi chú viết bằng markdown cho người đọc. Không kéo cả thư viện markdown về
// chỉ để hiện vài dòng — bỏ các dấu **, > và - đầu dòng là đủ sạch để đọc.
function _ghiChuGon(s){
    return _thoat(String(s||"")
        .replace(/\*\*/g, "")
        .replace(/^>\s?/gm, "")
        .replace(/^-\s/gm, "• ")
        .trim());
}

async function moBangCapNhat(){
    openModal("Phiên bản", `<div style="color:var(--text-muted);font-size:13px">
        Đang hỏi GitHub xem có bản nào…</div>`);
    let j;
    try{
        j = await (await fetch("/api/versions", {cache:"no-store"})).json();
    }catch(e){
        document.getElementById("modal-body").innerHTML =
            `<div style="color:var(--danger)">Không hỏi được danh sách bản: ${_thoat(e.message)}</div>`;
        return;
    }
    if(!j.ok){
        document.getElementById("modal-body").innerHTML =
            `<div style="color:var(--danger)">${_thoat(j.error||"Không lấy được danh sách bản.")}</div>`;
        return;
    }

    const moi = j.ban_moi;
    let html = "";

    if(j.canh_bao){
        html += `<div style="background:var(--danger-light);color:var(--danger);
            padding:8px 10px;border-radius:var(--radius-sm);font-size:12px;margin-bottom:12px">
            ${_thoat(j.canh_bao)}</div>`;
    }

    // Việc chính, để riêng lên trên: hoặc mời cập nhật, hoặc báo đã mới nhất.
    if(moi){
        html += `<div style="margin-bottom:6px;font-size:13px">
            Có bản mới: <b>${_thoat(moi.tag)}</b>
            <span style="color:var(--text-muted)">${_thoat(moi.ngay)}</span></div>
            <button onclick="chayCapNhat('${_thoat(moi.tag)}', false)"
                style="width:100%;background:var(--accent);color:#fff;padding:10px;
                       border-radius:var(--radius-sm);font-weight:700">
                Cập nhật lên ${_thoat(moi.tag)}</button>`;
        if(moi.ghi_chu){
            html += `<div class="ban-ghichu" style="margin-top:10px">${_ghiChuGon(moi.ghi_chu)}</div>`;
        }
    }else{
        html += `<div style="font-size:13px">Bạn đang dùng bản mới nhất —
            <b>v${_thoat(j.hien_tai)}</b>.</div>`;
    }

    html += `<div style="margin:16px 0 8px;font-size:12px;color:var(--text-muted);
        border-top:1px solid var(--border);padding-top:12px">
        Dữ liệu của bạn — tài khoản, page, content, UID nhóm — không bị đụng tới
        dù cập nhật hay lùi bản. Phần mềm tự sao lưu trước mỗi lần cập nhật.</div>`;

    html += `<details><summary style="cursor:pointer;font-size:13px;padding:4px 0">
        Tất cả các bản (${j.versions.length})</summary>
        <div class="ban-list" style="margin-top:10px">`;
    for(const m of j.versions){
        const dangChay = m.huong === "dang_chay";
        let nut = "";
        if(dangChay){
            nut = `<span style="color:var(--accent);font-size:11px">đang dùng</span>`;
        }else if(m.huong === "moi"){
            nut = `<button onclick="chayCapNhat('${_thoat(m.tag)}', false)"
                     style="background:var(--accent);color:#fff">Cập nhật</button>`;
        }else{
            nut = `<button onclick="chayCapNhat('${_thoat(m.tag)}', true)"
                     style="background:transparent;color:var(--text-muted);
                            border:1px solid var(--border)">Lùi về</button>`;
        }
        html += `<div class="ban-item${dangChay?" dang-chay":""}">
            <div class="ban-head"><span>${_thoat(m.tag)}</span>
                <span class="ngay">${_thoat(m.ngay)}</span></div>
            ${m.ghi_chu ? `<div class="ban-ghichu">${_ghiChuGon(m.ghi_chu)}</div>` : ""}
            <div style="margin-top:8px">${nut}</div>
        </div>`;
    }
    html += `</div></details>`;
    document.getElementById("modal-body").innerHTML = html;
}

async function chayCapNhat(tag, laLui){
    // Lùi bản là mất những gì đã sửa sau đó — hỏi lại cho chắc.
    if(laLui && !confirm(
        `Lùi về ${tag}?\n\n`+
        `Bản này CŨ HƠN bản đang chạy, nên mọi sửa lỗi và tính năng thêm sau đó `+
        `sẽ mất. Dữ liệu của bạn vẫn giữ nguyên.`)) return;

    document.getElementById("modal-body").innerHTML =
        `<div style="font-size:13px;line-height:1.7">
            Đang cập nhật lên <b>${_thoat(tag)}</b>…<br>
            <span style="color:var(--text-muted)">
            Một cửa sổ đen sẽ hiện lên để bạn theo dõi. Phần mềm tự tắt rồi mở
            lại, trang này sẽ tự nạp lại. Đừng tắt cửa sổ đó giữa chừng.</span>
        </div>`;
    try{
        const j = await (await fetch("/api/update", {
            method:"POST", headers:{"Content-Type":"application/json"},
            body: JSON.stringify({version: tag})
        })).json();
        if(!j.ok){
            document.getElementById("modal-body").innerHTML =
                `<div style="color:var(--danger)">${_thoat(j.error||"Không chạy được.")}</div>`;
        }
    }catch(e){
        // Server bị UPDATE.bat tắt ngay giữa lượt gọi là chuyện BÌNH THƯỜNG,
        // không phải lỗi. Nhịp heartbeat sẽ tự nạp lại trang khi server sống dậy.
    }
}

// ── Tự reload khi server restart ──────────────────────────────
// Mỗi lần server khởi động, /api/ping trả boot id mới. Tab đang mở phát hiện
// boot id đổi → tự location.reload() thành bản mới. Nhờ vậy RESTART không cần
// mở tab thứ hai (server chạy kèm --no-browser), tab cũ tự làm mới chính nó.
let _bootId = null;
async function _heartbeat(){
    try{
        const r = await fetch("/api/ping", {cache:"no-store"});
        const j = await r.json();
        // Nhịp này vốn để phát hiện server restart; tiện thể đổ luôn số phiên
        // bản vào sidebar, khỏi thêm một lượt gọi riêng.
        if(j.version){
            const el = document.getElementById("app-version");
            if(el && el.textContent !== "v"+j.version) el.textContent = "v"+j.version;
        }
        if(_bootId === null){ _bootId = j.boot; }
        else if(j.boot && j.boot !== _bootId){ location.reload(); }
    }catch(e){ /* server đang restart — bỏ qua, thử lại lần sau */ }
}

// ── Init ──────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", ()=>{
    document.querySelectorAll(".nav-item").forEach(el=>el.addEventListener("click",()=>navigate(el.dataset.page)));
    navigate("accounts");
    loadRunnerStatus();
    setInterval(loadRunnerStatus,10000);
    loadCanhBaoAcc();
    setInterval(loadCanhBaoAcc,10000);
    _heartbeat();
    setInterval(_heartbeat, 2000);
    // Dò bản mới: mỗi lần mở app một lần, rồi mỗi 6 tiếng. Không dò dày hơn vì
    // mỗi lượt là một lần fetch git qua mạng, mà bản mới thì hàng tuần mới có.
    _doBanMoi();
    setInterval(_doBanMoi, 6*60*60*1000);
    _chromiumKiem();
    _duyetKiem();
});

// Chỉ để bật cái chấm cạnh số phiên bản. Khách không phải tự đi mở bảng ra xem
// mới biết có bản mới.
async function _doBanMoi(){
    try{
        const j = await (await fetch("/api/versions", {cache:"no-store"})).json();
        const el = document.getElementById("app-version-cham");
        if(el) el.classList.toggle("co-ban-moi", !!(j.ok && j.ban_moi));
    }catch(e){ /* không mạng — để nguyên, lần sau dò lại */ }
}
