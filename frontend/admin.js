// ============================================================
//  admin.js — TERMO LIVE (painel local)
//  Controle manual e simulación de modo teste.
// ============================================================

function el(id) { return document.getElementById(id); }

async function api(method, url, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const r = await fetch(url, opts);
    let data = {};
    try { data = await r.json(); } catch (e) { data = { status: r.status }; }
    return data;
}

function post(url, body) { return api("POST", url, body); }

function log(msg) {
    const box = el("testLog");
    if (!box) return;
    box.textContent = "[ " + new Date().toLocaleTimeString() + " ] " + msg + "\n" + box.textContent;
    if (box.textContent.length > 4000) box.textContent = box.textContent.slice(0, 4000);
}

// ------------------------------------------------------------
async function refresh() {
    try {
        const st = await api("GET", "/api/state");
        const info = [
            "Rodada: #" + (st.rodada?.numero || "-"),
            "Palavra: " + (st.rodada?.palavra || "-"),
            "Tentativas: " + (st.rodada?.tentativas || 0) + "/" + (st.rodada?.max_tentativas || 0),
            "Jogadores: " + st.total_jogadores,
            "Modo teste: " + (st.modo_test ? "ativado" : "desativado"),
            "Pausada: " + (st.pausada ? "ativada" : "desativada"),
            "Palavras totais: " + (st.palavras?.total || 0),
            "Espectadores: " + (st.stats?.espectadores || 0),
        ].join("\n");
        el("stats").textContent = info;

        const tk = await api("GET", "/api/admin/tiktok");
        el("tiktok").textContent =
            "Conectado: " + (tk.conectado ? "conectado" : "desconectado") +
            "\nUsuário: @" + (tk.usuario || "-") +
            "\nModo teste: " + (tk.modo_test ? "ativado" : "desativado") +
            "\nErro: " + (tk.error || "-");

        const p = await api("GET", "/api/admin/palavra");
        el("palavra").textContent = p.palavra ? ("#" + (p.numero || "?") + " — " + p.palavra.toUpperCase()) : "Sem rodada";
    } catch (e) {
        el("stats").textContent = "Erro de conexão: " + e;
    }
}

// ------------------------------------------------------------
async function enviarComando() {
    const raw = el("cmd").value.trim();
    if (!raw) return;
    el("cmd").value = "";
    const parts = raw.slice(1).split(/\s+/);
    const cmd = (parts.shift() || "").toLowerCase();
    const arg = parts.join(" ");
    let res;
    if (cmd === "guess" || cmd === "palpite") res = await post("/api/test/guess", { word: arg, user: "test" });
    else if (cmd === "gift") res = await post("/api/test/gift", { gift: arg, user: "test" });
    else if (cmd === "follow") res = await post("/api/test/follow", { user: "test" });
    else if (cmd === "like") res = await post("/api/test/like", { user: "test" });
    else { log("Comando desconhecido: /" + cmd); return; }
    log("/" + cmd + " " + arg + " -> " + JSON.stringify(res));
}

// Simular palpites para testar toda a mecânica
const POOL = ["TERMO", "PEDRA", "TIGRE", "PRATO", "NOITE", "TARDE", "SABOR", "PAPEL", "RITMO", "MUNDO"];

async function simular() {
    try {
        const p = await api("GET", "/api/admin/palavra");
        let correta = p.palavra ? p.palavra.toUpperCase() : "TERMO";
        const alvo = Math.floor(Math.random() * 20);
        for (let i = 0; i < 20; i++) {
            const word = i === alvo ? correta : randomWord();
            const user = "usuário" + (1 + Math.floor(Math.random() * 6));
            await post("/api/test/guess", { word, user });
            log("@" + user + " -> " + word);
            await sleep(250);
        }
    } catch (e) { log("Erro na simulação: " + e); }
}

function randomWord() {
    return POOL[Math.floor(Math.random() * POOL.length)];
}
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

el("cmd").addEventListener("keydown", (e) => { if (e.key === "Enter") enviarComando(); });

refresh();
setInterval(refresh, 2000);
window.post = post;
window.enviarComando = enviarComando;
window.simular = simular;
window.el = el;