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
let _lbMeta = {name:"", isHook:false}; // meta cho tên file download

function openLightbox(imgs, meta={}) {
    _lbImgs = typeof imgs==="string" ? JSON.parse(imgs) : imgs;
    if(!_lbImgs.length) return;
    _lbIdx  = 0;
    _lbMeta = {name: meta.name||"", isHook: !!meta.isHook};
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
    if(_lbMeta.isHook && _lbImgs.length===1) return `${base}_hook.${ext}`;
    if(_lbMeta.isHook && idx===0)            return `${base}_hook.${ext}`;
    const num = _lbMeta.isHook ? idx : idx + 1; // hook chiếm slot 0 nếu mixed
    return `${base}_${num}.${ext}`;
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

function _delayPanel(dNew, dSkip) {
    return `
    <div style="display:flex;gap:10px">
        <div class="field-group" style="flex:1">
            <label>Delay mới tham gia (giây)</label>
            <input id="js-delay-new" type="number" min="5" max="600" value="${dNew}"
                   style="width:100%" title="Chờ N giây sau khi vừa join nhóm mới">
        </div>
        <div class="field-group" style="flex:1">
            <label>Delay đã join / bỏ qua (giây)</label>
            <input id="js-delay-skip" type="number" min="1" max="60" value="${dSkip}"
                   style="width:100%" title="Chờ N giây khi nhóm đã là thành viên rồi">
        </div>
    </div>`;
}

function openQuickJoinSchedule() {
    API.settings().then(setRes => {
        const dNew  = setRes.data?.join_delay_new  || "30";
        const dSkip = setRes.data?.join_delay_skip || "5";
        openModal("⚡ Tạo lịch nhanh — Tham gia nhóm", `
            <div style="display:flex;flex-direction:column;gap:12px">
                <div style="font-size:13px;color:var(--text-secondary);background:var(--bg-hover);padding:10px 12px;border-radius:var(--radius-sm);line-height:1.6">
                    Tự động tạo <strong>1 lịch / tài khoản Active có Page</strong>.<br>
                    Bỏ qua acc đã có lịch rồi.
                </div>
                ${_delayPanel(dNew, dSkip)}
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
    const dSkip = parseInt(document.getElementById("js-delay-skip")?.value || "5");
    try {
        const r = await API.joinGenQuick({delay_new: dNew, delay_skip: dSkip});
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
        const dSkip = setRes.data?.join_delay_skip || "5";
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
                ${_delayPanel(dNew, dSkip)}
            </div>
            <div style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px">
                <button onclick="closeModal()" class="btn btn-ghost">Huỷ</button>
                <button onclick="saveJoinSchedule()" class="btn btn-primary">💾 Lưu</button>
            </div>`);
    });
}

async function saveJoinSchedule() {
    const dNew  = parseInt(document.getElementById("js-delay-new")?.value  || "30");
    const dSkip = parseInt(document.getElementById("js-delay-skip")?.value || "5");
    await API.saveSettings({join_delay_new: String(dNew), join_delay_skip: String(dSkip)}).catch(()=>{});
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
    const dSkip     = parseInt(settings.data?.join_delay_skip || "5");
    const modeLabel = headless ? "ẩn Chrome" : "hiển thị Chrome";
    try {
        const r = await API.joinRun(id, headless, dNew, dSkip);
        if(r.ok) {
            Toast.success(`▶ Khởi động (${modeLabel} | mới join: ${dNew}s | bỏ qua: ${dSkip}s)`);
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
            ${running
                ?`<button class="btn btn-danger" style="width:100%" onclick="runnerStop('${loai}')">⏹ Dừng</button>`
                :`<button class="btn btn-primary" style="width:100%;background:${cfg.color}" onclick="runnerStart('${loai}')">▶ Run</button>`}
        </div>`;
    }).join("");
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
    document.getElementById("headless-label").textContent  = checked ? "Hiển thị Chrome" : "Ẩn Chrome (Headless)";
    document.getElementById("headless-desc").textContent   = checked
        ? "Chrome hiển thị — dùng để kiểm tra & debug"
        : "Chrome chạy nền, không hiện cửa sổ";
    document.getElementById("headless-label").style.color  = checked ? "var(--warning)" : "";
}

async function runnerStart(loai){
    const headless = isHeadless();
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
            const ban=res.data.filter(r=>(r.loai_dang||"").includes("Bán")).length;
            const thue=res.data.filter(r=>(r.loai_dang||"").includes("Thuê")).length;
            const hs=res.data.filter(r=>(r.loai_dang||"").includes("Homestay")).length;
            box.innerHTML=[{l:"Tổng",v:total},{l:"Active",v:active},{l:"Bán",v:ban},{l:"Thuê",v:thue},{l:"Homestay",v:hs}]
                .map(s=>`<div class="metric-card" style="padding:10px 14px;flex:1;min-width:80px"><div class="metric-label">${s.l}</div><div class="metric-value" style="font-size:20px">${s.v}</div></div>`).join("");
        }
        renderAccTable(res.data);
    }catch(e){ tbody.innerHTML=`<tr><td colspan="19" class="empty" style="color:var(--danger)">${e.message}</td></tr>`; }
}

function renderAccTable(data){
    const tbody=document.getElementById("acc-table");
    const count=document.getElementById("acc-count");
    const filter=document.getElementById("acc-filter-loai")?.value||"";
    const rows=data.filter(r=>!filter||((r.loai_dang||"").includes(filter)));
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
                const color=val.includes("Bán")?"#fbbf24":val.includes("Thuê")?"#60a5fa":val.includes("Homestay")?"#34d399":"var(--text-secondary)";
                return `<td class="editable" data-id="${r.id}" data-field="${f.key}" data-val="${esc}" style="${center}color:${color};font-weight:600;font-size:12px" onclick="startAccEdit(this)">${val||"-"}</td>`;
            }
            if(f.key==="link_profile")
                return `<td class="editable" data-id="${r.id}" data-field="${f.key}" data-val="${esc}" style="${center}" onclick="startAccEdit(this)">${val?`<a href="${val}" target="_blank" style="color:var(--accent);font-size:12px" onclick="event.stopPropagation()">🔗</a>`:"-"}</td>`;
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

function openAccForm(data={}){
    const f=(k,label,type="text")=>`<div class="field-group"><label>${label}</label><input type="${type}" id="af_${k}" value="${(data[k]||"").toString().replace(/"/g,"&quot;")}"></div>`;
    const fsel=(k,label,opts)=>`<div class="field-group"><label>${label}</label><select id="af_${k}">${opts.map(o=>`<option value="${o}" ${data[k]===o?"selected":""}>${o||"-"}</option>`).join("")}</select></div>`;
    openModal(data.id?"Sửa tài khoản":"Thêm tài khoản",`
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            ${f("ten_acc","Tên acc")} ${fsel("loai_dang","Loại đăng",["","Bán","Thuê","Homestay"])}
            ${f("thoi_gian_nghi","Nghỉ (phút)")} ${f("ten_page","Tên Page")}
            ${f("link_profile","Link profile")} ${f("email_sdt","Email/SDT")}
            ${f("password","Password")} ${f("c_user","c_user")}
            <div class="field-group" style="grid-column:1/-1"><label>xs</label><input id="af_xs" value="${(data.xs||"").toString().replace(/"/g,"&quot;")}"></div>
            ${fsel("trang_thai","Trạng thái",["Active","Tạm dừng","Cookie hết hạn"])}
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
        // Dropdown 3 lựa chọn (Homestay / Thuê / Bán)
        inp=document.createElement("select");
        inp.style.cssText="background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:12px;font-weight:600;cursor:pointer";
        const opts=["Homestay","Thuê","Bán"];
        const mkOpt=(v,t)=>{ const op=document.createElement("option"); op.value=v; op.textContent=t; op.style.cssText="background:var(--bg-card);color:var(--text-primary)"; return op; };
        if(!opts.includes(val)){
            const b=mkOpt("","—"); b.selected=true; inp.appendChild(b);
        }
        opts.forEach(o=>{ const op=mkOpt(o,o); if(o===val) op.selected=true; inp.appendChild(op); });
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
                ${["Homestay","Thuê","Bán"].map(o=>`<option value="${o}" ${data.loai_page===o?"selected":""}>${o}</option>`).join("")}
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
    tbody.innerHTML=`<tr><td colspan="8" class="loading"><span class="spin">↻</span></td></tr>`;
    try{
        const res=await API.content(loai);
        const total=res.data.length, active=res.data.filter(r=>r.su_dung==="Có").length;
        const box=document.getElementById("content-summary");
        if(box) box.innerHTML=[{l:"Tổng",v:total},{l:"Đang dùng",v:active,c:"var(--success)"},{l:"Tạm dừng",v:total-active}]
            .map(s=>`<div class="metric-card" style="padding:10px 14px;flex:1"><div class="metric-label">${s.l}</div><div class="metric-value" style="font-size:20px;${s.c?"color:"+s.c:""}">${s.v}</div></div>`).join("");

        if(!res.data.length){ tbody.innerHTML=`<tr><td colspan="8" class="empty">Chưa có content</td></tr>`; return; }

        // Helper: inline-editable cell
        const ec=(r,field,style)=>{
            const val=(r[field]||"").toString(); const esc=val.replace(/"/g,"&quot;");
            return `<td class="editable" data-id="${r.id}" data-field="${field}" data-val="${esc}"
                style="${style||"font-size:12px;color:var(--text-secondary)"}"
                onclick="startContentFieldEdit(this)">${val||"-"}</td>`;
        };

        tbody.innerHTML=res.data.map(r=>{
            const imgs=(r.link_anh||"").split(",").map(s=>s.trim()).filter(Boolean);
            const hook=r.link_anh_hook||"";
            const allImgs=hook?[hook,...imgs]:imgs;
            const encAll=encodeURIComponent(JSON.stringify(allImgs));
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

                <!-- Ảnh Hook: click mở lightbox -->
                <td style="text-align:center;padding:6px">
                    ${hook
                        ?`<img src="${hook}" style="width:56px;height:56px;object-fit:cover;border-radius:6px;border:2px solid var(--warning);cursor:pointer"
                            title="Ảnh Hook — click xem"
                            onclick="openLightbox(['${hook}'],{name:'${r.ma_content}',isHook:true})">`
                        :`<span style="color:var(--text-muted);font-size:11px">-</span>`}
                </td>

                <!-- Ảnh thường: click mở lightbox -->
                <td style="padding:4px 6px;cursor:pointer" title="Click xem ảnh"
                    onclick="openLightbox(JSON.parse(decodeURIComponent('${encImgs}')),{name:'${r.ma_content}',isHook:false})">
                    <div style="display:flex;gap:2px;flex-wrap:wrap;max-width:100px">
                        ${imgs.length
                            ?imgs.slice(0,3).map(u=>`<img src="${u}" style="width:34px;height:34px;object-fit:cover;border-radius:4px;border:1px solid var(--border)">`).join("")
                             +(imgs.length>3?`<div style="width:34px;height:34px;border-radius:4px;background:var(--bg-hover);display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--accent)">+${imgs.length-3}</div>`:"")
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
    }catch(e){ tbody.innerHTML=`<tr><td colspan="8" class="empty" style="color:var(--danger)">${e.message}</td></tr>`; }
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
            <label>Ảnh Hook</label>
            <div id="ce_hook_thumb" style="display:flex;gap:8px;margin-bottom:8px">${data.link_anh_hook?`<div class="cedit-thumb" style="border:2px solid var(--warning)"><img src="${data.link_anh_hook}"><button class="remove-btn" onclick="_removeHook()">✕</button></div>`:""}</div>
            <div class="upload-zone upload-zone--hook" onclick="document.getElementById('ce_hook_file').click()" ondragover="event.preventDefault()" ondrop="_dropHook(event)">
                <div class="upload-zone__icon">📤</div>
                <div class="upload-zone__text">Kéo thả hoặc <span>click để chọn</span></div>
                <div class="upload-zone__sub">1 ảnh hook</div>
                <input id="ce_hook_file" type="file" accept="image/*" style="display:none" onchange="_hookFile(event)">
            </div>
        </div>
        <div class="field-group">
            <label>Ảnh</label>
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
    window._ceHookUrl = data.link_anh_hook||"";
    window._ceImgUrls = (data.link_anh||"").split(",").map(s=>s.trim()).filter(Boolean);
}

function closeContentEdit(){
    document.getElementById("cedit-overlay").style.display="none";
    document.getElementById("cedit-panel").style.display="none";
}

function _removeHook(){ window._ceHookUrl=""; document.getElementById("ce_hook_thumb").innerHTML=""; }
function _removeImg(i){ window._ceImgUrls.splice(i,1); _reRenderImgThumbs(); }
function _reRenderImgThumbs(){
    document.getElementById("ce_thumbs").innerHTML=window._ceImgUrls.map((u,i)=>
        `<div class="cedit-thumb"><img src="${u}"><button class="remove-btn" onclick="_removeImg(${i})">✕</button></div>`
    ).join("");
}

async function _uploadImg(file, isHook=false){
    const loai = _ceditData?.loai || _currentContentLoai;
    const fd=new FormData(); fd.append("image",file); fd.append("loai",loai);
    const r=await fetch("/api/content/upload-image",{method:"POST",body:fd});
    const data=await r.json();
    if(!data.ok) throw new Error(data.error);
    return data.url;
}

async function _hookFile(e){
    const file=e.target.files[0]; if(!file) return;
    try{
        const url=await _uploadImg(file,true);
        window._ceHookUrl=url;
        document.getElementById("ce_hook_thumb").innerHTML=`<div class="cedit-thumb" style="border:2px solid var(--warning)"><img src="${url}"><button class="remove-btn" onclick="_removeHook()">✕</button></div>`;
    }catch(err){ Toast.error(err.message); }
    e.target.value="";
}

function _dropHook(e){ e.preventDefault(); const f=e.dataTransfer.files[0]; if(f)_uploadImg(f,true).then(u=>{window._ceHookUrl=u;document.getElementById("ce_hook_thumb").innerHTML=`<div class="cedit-thumb" style="border:2px solid var(--warning)"><img src="${u}"><button class="remove-btn" onclick="_removeHook()">✕</button></div>`;}).catch(err=>Toast.error(err.message)); }

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
        link_anh_hook: window._ceHookUrl||"",
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
                    <option value="done">✅</option><option value="fail">❌</option><option value="X">X</option>
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
                style="width:100%;font-family:var(--font-mono);font-size:12px;padding:8px;background:var(--bg-input,var(--bg-hover));color:var(--text);border:1px solid var(--border);border-radius:var(--radius-sm)"
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
                style="width:100%;font-family:inherit;font-size:13px;padding:8px;background:var(--bg-input,var(--bg-hover));color:var(--text);border:1px solid var(--border);border-radius:var(--radius-sm)"
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
          stop=data.filter(r=>r.trang_thai==="X").length;
    box.innerHTML=[{l:"Tổng",v:total},{l:"Chờ",v:cho},{l:"✅",v:done},{l:"❌",v:fail},{l:"X",v:stop}]
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
        else if(st==="X") stBadge=`<span class="badge badge-muted">X</span>`;
        else if(st==="Chờ") stBadge=`<span class="badge badge-warning">Chờ</span>`;
        else stBadge=`<span class="badge badge-muted">${st||"-"}</span>`;
        // Slot đã bị chuyển thành phiên nuôi nick — hiển thị khác để dễ phân biệt.
        const isWarm=(r.hoat_dong||"dang_bai")==="nuoi_nick";
        const contentCell=isWarm
            ? `<td style="text-align:center"><span class="badge" style="background:#064e3b;color:#6ee7b7">🌱 Nuôi nick</span></td>`
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
            <div style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em">Cài đặt từng tài khoản</div>
            <div id="gen-accs">${_renderGenAccs(res.accs, res.contents)}</div>`;
    }catch(e){
        document.getElementById("gen-panel-body").innerHTML=`<div class="empty" style="color:var(--danger)">${e.message}</div>`;
    }
}

function _renderGenAccs(accs, contents){
    if(!accs.length) return `<div class="empty">Không có acc Active nào cho loại này</div>`;
    const n = accs.length;
    const nc = contents.length;
    return accs.map((acc,i)=>{
        // Trải đều content: acc[0]=H1, acc[1]=H5, acc[2]=H9, acc[3]=H13 (với 17 content, 4 acc)
        const defC = contents[Math.floor(i * nc / n) % nc] || "";
        return `
        <div style="background:var(--bg-hover);border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;margin-bottom:8px">
            <div style="font-weight:600;font-size:13px;margin-bottom:10px">${acc.ten}
                <span style="font-size:11px;font-weight:400;color:var(--text-muted)"> — nghỉ ${acc.nghi}p · lực ${acc.luc_dang} bài/h</span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
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

// ── Tự reload khi server restart ──────────────────────────────
// Mỗi lần server khởi động, /api/ping trả boot id mới. Tab đang mở phát hiện
// boot id đổi → tự location.reload() thành bản mới. Nhờ vậy RESTART không cần
// mở tab thứ hai (server chạy kèm --no-browser), tab cũ tự làm mới chính nó.
let _bootId = null;
async function _heartbeat(){
    try{
        const r = await fetch("/api/ping", {cache:"no-store"});
        const j = await r.json();
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
    _heartbeat();
    setInterval(_heartbeat, 2000);
});
