/* api.js — MNT_FB fetch wrapper */
const API = {
    async _fetch(url, opts = {}) {
        const res = await fetch(url, {
            headers: { "Content-Type": "application/json" }, ...opts,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    get:  (url)       => API._fetch(url),
    post: (url, body) => API._fetch(url, { method: "POST", body: JSON.stringify(body || {}) }),
    del:  (url)       => API._fetch(url, { method: "DELETE" }),

    // Runner
    runStatus:       ()           => API.get("/api/run/status"),
    runStart:        (loai, headless) => API.post(`/api/run/${loai}/start`, {headless}),
    runStop:         (loai)       => API.post(`/api/run/${loai}/stop`),

    // Accounts
    accounts:        (loai)       => API.get(`/api/accounts${loai ? '?loai='+loai : ''}`),
    saveAccount:     (data)       => API.post("/api/accounts/save", data),
    deleteAccount:   (id)         => API.del(`/api/accounts/${id}`),
    updateAccField:  (id, f, v)   => API.post(`/api/accounts/${id}/field`, {field:f, value:v}),
    accountSecrets:  (id)         => API.get(`/api/accounts/${id}/secrets`),
    reorderAccounts: (ids)        => API.post("/api/accounts/reorder", ids),
    insertAccRow:    (id, pos)    => API.post(`/api/accounts/${id}/insert-row`, {position:pos}),

    // Pages
    pages:           ()           => API.get("/api/pages"),
    savePage:        (data)       => API.post("/api/pages/save", data),
    updatePageField: (id, f, v)   => API.post(`/api/pages/${id}/field`, {field:f, value:v}),
    reorderPages:    (ids)        => API.post("/api/pages/reorder", ids),
    deletePage:      (id)         => API.del(`/api/pages/${id}`),
    exportPages:     ()           => API.get("/api/pages/export-excel"),

    // Content
    content:         (loai)       => API.get(`/api/content/${loai}`),
    saveContent:     (data)       => API.post("/api/content/save", data),
    updateContentField: (id, f, v) => API.post(`/api/content/${id}/field`, {field:f, value:v}),
    deleteContent:   (id)         => API.del(`/api/content/${id}`),
    quetAnhMoCoi:    (xoa)        => API.post("/api/content/quet-anh-mo-coi", {xoa}),
    reorderContent:  (ids)        => API.post("/api/content/reorder", ids),

    // UID Groups
    uidGroups:       ()           => API.get("/api/uid-groups"),
    deleteUidGroup:  (id)         => API.del(`/api/uid-groups/${id}`),
    reorderUidGroups:(ids)        => API.post("/api/uid-groups/reorder", ids),

    // Schedule
    schedule:        (loai)       => API.get(`/api/schedule/${loai}`),
    scheduleReset:   (loai)       => API.post(`/api/schedule/${loai}/reset`),
    scheduleStop:    (loai)       => API.post(`/api/schedule/${loai}/stop`),
    scheduleXoaHet:  (loai)       => API.post(`/api/schedule/${loai}/xoa-het`),
    thuCookie:       (id)         => API.post(`/api/accounts/${id}/thu-cookie`, {}),
    scheduleCell:    (loai, id, f, v) => API.post(`/api/schedule/${loai}/cell`, {id, field:f, value:v}),
    scheduleGen:     (loai, data) => API.post(`/api/schedule/${loai}/gen`, data),
    scheduleGenData: (loai)       => API.get(`/api/schedule/${loai}/gen-data`),
    schedulePageGen: (data)       => API.post("/api/schedule/page/gen", data),
    scheduleNuoiGen: (data)       => API.post("/api/schedule/nuoi/gen", data),
    nuoiMsgMau:      ()           => API.get("/api/nuoi/msg-mau"),

    // Logs
    logs: (loai, n=150) => API.get(`/api/logs/${loai}?n=${n}`),

    // Join groups
    joinSchedules:  (nguon)                         => API.get("/api/join/schedules"
                                                        + (nguon ? `?nguon=${encodeURIComponent(nguon)}` : "")),
    joinGenMarket:  ()                              => API.post("/api/join/gen-quick-market", {}),
    joinLamSach:    (id, bat)                       => API.post(`/api/join/${id}/lam-sach`, {bat: !!bat}),
    joinRunChain:   (nguon, headless)               => API.post("/api/join/run-chain", {nguon, headless}),
    joinStopChain:  (nguon)                         => API.post("/api/join/stop-chain", {nguon}),
    joinChainTT:    (nguon)                         => API.get("/api/join/chain-status"
                                                        + (nguon ? `?nguon=${encodeURIComponent(nguon)}` : "")),
    joinAdd:        (data)                          => API.post("/api/join/add", data),
    joinGenQuick:   (data)                          => API.post("/api/join/gen-quick", data),
    joinRun:        (id, headless, dNew)            => API.post(`/api/join/${id}/run`, {headless, delay_new: dNew}),
    joinStop:       (id)                            => API.post(`/api/join/${id}/stop`),
    joinStatus:     (id)                            => API.get(`/api/join/${id}/status`),
    joinDelete:     (id)                            => API.del(`/api/join/${id}`),
    logsJoin:       (n=200)                         => API.get(`/api/logs/join?n=${n}`),

    // Dọn thư mục profile (phiên đăng nhập Chrome của từng nick)
    profiles:       ()      => API.get("/api/profiles"),
    profilesXoa:    (ten)   => API.post("/api/profiles/xoa", {ten}),

    // Bài đi comment
    commentPosts:       (loai)       => API.get(`/api/comment-posts/${loai}`),
    commentPostsAdd:    (loai, urls) => API.post(`/api/comment-posts/${loai}/add`, {urls}),
    commentPostField:   (id, f, v)   => API.post(`/api/comment-posts/${id}/field`, {field:f, value:v}),
    commentPostDelete:  (id)         => API.del(`/api/comment-posts/${id}`),
    commentPostsClear:  (loai)       => API.post(`/api/comment-posts/${loai}/clear`, {}),
    commentCauMau:      ()           => API.get("/api/comment/cau-mau"),

    // Cảnh báo sức khoẻ acc
    canhBao:         ()           => API.get("/api/canh-bao"),
    canhBaoXong:     ()           => API.post("/api/canh-bao/xong", {}),

    // Settings
    settings:        ()           => API.get("/api/settings"),
    saveSettings:    (data)       => API.post("/api/settings/save", data),

    // Marketplace — lưu vẫn dùng saveSettings, chỉ ĐỌC là riêng vì server
    // phải trộn mặc định vào trước khi trả về.
    mktCaiDat:       ()           => API.get("/api/marketplace/cai-dat"),
    // Hai tab UID dùng chung một bộ route, chỉ khác tham số `ma_nhom`:
    // "" = UID Nhóm, "MARKET" = UID Marketplace.
    uidMarket:       ()           => API.get("/api/uid-groups/market"),
    uidThem:         (text, ma)   => API.post("/api/uid-groups/them", {text, ma_nhom: ma||""}),
    uidQuet:         (data)       => API.post("/api/uid-groups/quet", data),
    uidQuetTT:       (ma)         => API.get("/api/uid-groups/quet-trang-thai"
                                        + (ma ? `?ma_nhom=${encodeURIComponent(ma)}` : "")),
    exportUidGroups: (ma)         => API.get("/api/uid-groups/export-excel"
                                        + (ma ? `?ma_nhom=${encodeURIComponent(ma)}` : "")),

    // Telegram
    tgThu:           (data)       => API.post("/api/telegram/thu", data),
    tgTomTat:        ()           => API.get("/api/telegram/tom-tat"),
    tgTimChat:       (data)       => API.post("/api/telegram/tim-chat", data),

    // Lịch của máy
    lmThu:           ()           => API.post("/api/lich-may/thu", {}),
    lmDanhThuc:      ()           => API.get("/api/lich-may/danh-thuc"),
    lmCaiDanhThuc:   ()           => API.post("/api/lich-may/cai-danh-thuc", {}),

    // Sao lưu
    slTrangThai:     ()           => API.get("/api/sao-luu/trang-thai"),
    slNgay:          ()           => API.post("/api/sao-luu/ngay", {}),

    // App
    appShutdown:     ()           => API.post("/api/app/shutdown", {}),
};
