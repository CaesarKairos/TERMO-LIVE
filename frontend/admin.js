// ============================================================
//  admin.js — TERMO LIVE (painel local)
//  Controle manual e simulação do modo teste.
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

async function enviarPresenteTeste() {
    const presente = el("giftSel").value;
    const status = el("giftTestStatus");
    if (status) {
        status.className = "gift-test-status aguardando";
        status.textContent = "Enviando " + presente + "...";
    }
    try {
        const result = await post("/api/admin/testar-presente", { gift: presente });
        const sucesso = result.ok === true;
        const mensagem = sucesso
            ? "✓ " + presente + " ativou " + (result.habilidade || "a habilidade") + "."
            : "✕ " + presente + ": " + traduzirMotivo(result.motivo);
        if (status) {
            status.className = "gift-test-status " + (sucesso ? "sucesso" : "falha");
            status.textContent = mensagem;
        }
        log("Teste de presente: " + JSON.stringify(result));
    } catch (erro) {
        if (status) {
            status.className = "gift-test-status falha";
            status.textContent = "✕ Não foi possível comunicar com o servidor.";
        }
        log("Erro ao testar presente: " + erro);
    }
}

function traduzirMotivo(motivo) {
    return {
        cooldown: "aguarde o cooldown",
        "rodada-inativa": "não há uma rodada ativa",
        desativado: "presente desativado",
        "nao-configurado": "presente não configurado",
        "sem-presente": "nenhum presente selecionado"
    }[motivo] || motivo || "não ativado";
}

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
        const modoTeste = Boolean(st.modo_test);
        const statusTeste = el("testModeStatus");
        if (statusTeste) {
            statusTeste.textContent = modoTeste
                ? "Modo teste ativado: simulações liberadas."
                : "Modo teste desativado: defina TEST_MODE=true no .env e reinicie o servidor.";
            statusTeste.className = modoTeste ? "teste-ativo" : "teste-inativo";
        }

        const tk = await api("GET", "/api/admin/tiktok");
        el("tiktok").textContent =
            "Conectado: " + (tk.conectado ? "conectado" : "desconectado") +
            "\nUsuário: @" + (tk.usuario || "-") +
            "\nModo teste: " + (tk.modo_test ? "ativado" : "desativado") +
            "\nErro: " + (tk.error || "-");

        const p = await api("GET", "/api/admin/palavra");
        el("palavra").textContent = p.palavra ? ("#" + (p.numero || "?") + " — " + p.palavra.toUpperCase()) : "Sem rodada";
        await carregarPresentes();
    } catch (e) {
        el("stats").textContent = "Erro de conexão: " + e;
    }
}

let presentesCarregados = false;
async function carregarPresentes() {
    if (presentesCarregados) return;
    const data = await api("GET", "/api/admin/gifts");
    if (!data.gifts) return;
    const box = el("giftsConfig");
    const acoes = data.acoes || {};
    const opcoes = Object.entries(acoes).map(([action, label]) => '<option value="' + action + '">' + label + '</option>').join("");
    box.innerHTML = data.gifts.map((gift) =>
        '<div class="gift-config"><strong>' + gift.nome + '</strong><select data-gift-action="' + gift.nome.replace(/"/g, "&quot;") + '">' +
        opcoes.replace('value="' + gift.action + '"', 'value="' + gift.action + '" selected') + '</select><em>' +
        (gift.ativo ? "Ativo" : "Inativo") + '</em><button type="button" data-gift-toggle="' +
        gift.nome.replace(/"/g, "&quot;") + '">' + (gift.ativo ? "Desativar" : "Ativar") + '</button></div>'
    ).join("");
    box.querySelectorAll("[data-gift-toggle]").forEach((button) => button.addEventListener("click", async () => {
        const gift = data.gifts.find((item) => item.nome === button.dataset.giftToggle);
        await post("/api/admin/gifts/config", { gift: gift.nome, enabled: !gift.ativo });
        presentesCarregados = false;
        carregarPresentes();
    }));
    box.querySelectorAll("[data-gift-action]").forEach((select) => select.addEventListener("change", async () => {
        await post("/api/admin/gifts/config", { gift: select.dataset.giftAction, action: select.value, enabled: true });
        presentesCarregados = false;
        carregarPresentes();
    }));
    if (el("giftCooldown")) el("giftCooldown").value = data.cooldown;
    presentesCarregados = true;
}

async function salvarCooldown() {
    const cooldown = Number(el("giftCooldown").value);
    const result = await post("/api/admin/gifts/config", { cooldown });
    log("Cooldown dos presentes -> " + JSON.stringify(result));
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
    if (cmd === "guess" || cmd === "palpite") res = await post("/api/test/comment", { word: arg, user: "teste" });
    else if (cmd === "gift" || cmd === "presente") res = await post("/api/test/gift", { gift: arg, user: "teste" });
    else if (cmd === "follow") res = await post("/api/test/follow", { user: "test" });
    else if (cmd === "like") res = await post("/api/test/like", { user: "test" });
    else { log("Comando desconhecido: /" + cmd); return; }
    log("/" + cmd + " " + arg + " -> " + JSON.stringify(res));
}

// Simular palpites para testar toda a mecânica
const POOL = ["TERMO", "PEDRA", "TIGRE", "PRATO", "NOITE", "TARDE", "SABOR", "PAPEL", "RITMO", "MUNDO"];

async function simular() {
    try {
        const state = await api("GET", "/api/state");
        if (!state.modo_test) {
            log("Simulação bloqueada: TEST_MODE não está ativado. Reinicie o servidor após alterar o .env.");
            return;
        }
        const p = await api("GET", "/api/admin/palavra");
        let correta = p.palavra ? p.palavra.toUpperCase() : "TERMO";
        const alvo = Math.floor(Math.random() * 20);
        for (let i = 0; i < 20; i++) {
            if (!await garantirRodadaAtiva()) return;
            const word = i === alvo ? correta : randomWord();
            const user = "simulacao" + (i + 1);
            const resultado = await post("/api/test/comment", { word, user });
            log("@" + user + " -> " + word);
            if (resultado.ok === false) log("Resposta: " + JSON.stringify(resultado));
            await sleep(250);
        }
    } catch (e) { log("Erro na simulação: " + e); }
}

async function garantirRodadaAtiva() {
    let state = await api("GET", "/api/state");
    let rodada = state.rodada;
    if (rodada && rodada.tentativas < rodada.max_tentativas && !rodada.vencedor) return true;
    log("A rodada terminou. Iniciando uma nova rodada para a simulação...");
    const nova = await post("/api/admin/nova-round", { word: "" });
    if (nova.ok !== true) {
        log("Não foi possível iniciar uma nova rodada: " + JSON.stringify(nova));
        return false;
    }
    return aguardarRodadaAtiva();
}

async function aguardarRodadaAtiva() {
    for (let tentativa = 0; tentativa < 20; tentativa++) {
        const state = await api("GET", "/api/state");
        const rodada = state.rodada;
        if (rodada && rodada.tentativas < rodada.max_tentativas && !rodada.vencedor) return true;
        await sleep(250);
    }
    log("A nova rodada ainda não está ativa. Tente simular novamente.");
    return false;
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
window.salvarCooldown = salvarCooldown;
window.enviarPresenteTeste = enviarPresenteTeste;
window.el = el;