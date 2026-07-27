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

    // Content
    content:         (loai)       => API.get(`/api/content/${loai}`),
    saveContent:     (data)       => API.post("/api/content/save", data),
    updateContentField: (id, f, v) => API.post(`/api/content/${id}/field`, {field:f, value:v}),
    deleteContent:   (id)         => API.del(`/api/content/${id}`),

    // UID Groups
    uidGroups:       ()           => API.get("/api/uid-groups"),
    saveUidGroup:    (data)       => API.post("/api/uid-groups/save", data),
    deleteUidGroup:  (id)         => API.del(`/api/uid-groups/${id}`),

    // Schedule
    schedule:        (loai)       => API.get(`/api/schedule/${loai}`),
    scheduleReset:   (loai)       => API.post(`/api/schedule/${loai}/reset`),
    scheduleStop:    (loai)       => API.post(`/api/schedule/${loai}/stop`),
    scheduleCell:    (loai, id, f, v) => API.post(`/api/schedule/${loai}/cell`, {id, field:f, value:v}),
    scheduleGen:     (loai, data) => API.post(`/api/schedule/${loai}/gen`, data),
    scheduleGenData: (loai)       => API.get(`/api/schedule/${loai}/gen-data`),
    schedulePageGen: (data)       => API.post("/api/schedule/page/gen", data),
    scheduleNuoiGen: (data)       => API.post("/api/schedule/nuoi/gen", data),

    // Logs
    logs: (loai, n=150) => API.get(`/api/logs/${loai}?n=${n}`),

    // Join groups
    joinSchedules:  ()                              => API.get("/api/join/schedules"),
    joinAdd:        (data)                          => API.post("/api/join/add", data),
    joinGenQuick:   (data)                          => API.post("/api/join/gen-quick", data),
    joinRun:        (id, headless, dNew, dSkip)     => API.post(`/api/join/${id}/run`, {headless, delay_new: dNew, delay_skip: dSkip}),
    joinStop:       (id)                            => API.post(`/api/join/${id}/stop`),
    joinStatus:     (id)                            => API.get(`/api/join/${id}/status`),
    joinDelete:     (id)                            => API.del(`/api/join/${id}`),
    logsJoin:       (n=200)                         => API.get(`/api/logs/join?n=${n}`),

    // Settings
    settings:        ()           => API.get("/api/settings"),
    saveSettings:    (data)       => API.post("/api/settings/save", data),

    // App
    appShutdown:     ()           => API.post("/api/app/shutdown", {}),
    setPassword:     (pw)         => API.post("/api/app/set-password", {password:pw}),
};
