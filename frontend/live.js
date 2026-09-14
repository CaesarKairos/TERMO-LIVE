// ============================================================
//  live.js — TERMO LIVE (interface vertical 9:16)
//  Tabuleiro 6x5 sempre visível, identidade do jogador fora do
//  tabuleiro, contagem regresiva e notificações em pt-BR.
//  Reconexão automática se o WebSocket cair.
// ============================================================

const WS_URL = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";

// Estado
let guesses = [];                 // palpites da rodada (ata 6)
let revealed = {};                // pos -> letra
let eliminated = new Set();       // letras eliminadas
let countdown = 0;                // temporizador da rodada
let rodadaAtiva = false;
let numeroRodada = 1;
let ws = null;
let palavraDigitada = "";

const $ = (id) => document.getElementById(id);
const MAX_LINHAS = 6;

// Escapar texto de usuário (anti-XSS)
function esc(texto) { return String(texto ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

function conectar() {
    try { ws = new WebSocket(WS_URL); } catch (e) { return setTimeout(conectar, 2000); }
    ws.onmessage = (ev) => { try { processar(JSON.parse(ev.data)); } catch (e) {} };
    ws.onclose = () => setTimeout(conectar, 2000);
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
}

// ------------------------------------------------------------
function processar(msg) {
    switch (msg.type) {
        case "connection": initEstado(msg.estado); break;
        case "new_round": novaRodada(msg); break;
        case "guess": adicionarPalpite(msg.palpite); break;
        case "correct": casoCorreto(msg); break;
        case "victory": mostrarVencedor(msg); break;
        case "leaderboard": renderRanking(msg.ranking); break;
        case "gift": notificarPresente(msg); break;
        case "hint": notificar(msg, msg.user || "", "💡 " + (msg.mensagem || "Pista")); break;
        case "reveal_letter": revelarLetra(msg); break;
        case "eliminate": eliminarLetra(msg); break;
        case "second_chance": notificar(msg, msg.user || "", "⏳ " + (msg.mensagem || "+1 tentativa")); break;
        case "shuffle": notificar(msg, msg.user || "", "🔀 " + (msg.mensagem || "Embaralhamento")); break;
        case "radar": notificar(msg, msg.user || "", "📡 " + (msg.mensagem || "Radar")); break;
        case "chaos": notificar(msg, msg.user || "", "🌀 " + (msg.mensagem || "Caos")); break;
        case "bonus": notificar(msg, msg.user || "", "🎁 " + (msg.mensagem || "Bônus")); break;
        case "steal_points": notificar(msg, msg.user || "", "🕵️ " + (msg.mensagem || "Roubo de pontos")); break;
        case "steal_points_result": notificar(msg, "", "🕵️ " + esc(msg.target) + " perdeu " + (msg.pts || 0) + " pontos"); break;
        case "lightning": notificar(msg, msg.user || "", "⚡ Palavra relâmpago!"); break;
        case "follow": notificar(msg, msg.user || "", "➕ te seguiu"); break;
        case "like": notificar(msg, msg.user || "", "❤️ deu like"); break;
        case "system": notificar(msg, "", msg.mensagem || ""); break;
    }
}

function initEstado(st) {
    if (st?.rodada) {
        numeroRodada = st.rodada.numero;
        countdown = st.rodada.relampago ? 20 : 120;
        rodadaAtiva = true;
        $("#numRodada").textContent = numeroRodada;
    }
    guesses = (st?.palpites || []).slice(-MAX_LINHAS);
    revealed = {};
    for (const i of (st?.reveladas || [])) revealed[i] = "";
    eliminated = new Set(st?.eliminadas || []);
    renderTabuleiro();
    renderRanking(st?.ranking || []);
    if (st?.ranking && st.ranking.length) renderUltimos(st.ranking.slice(0, 6));
    atualizarTeclado();
    atualizarStatus();
}

function novaRodada(msg) {
    rodadaAtiva = true;
    guesses = [];
    revealed = {};
    eliminated = new Set();
    countdown = msg.duracao || 120;
    numeroRodada = msg.round?.numero || numeroRodada + 1;
    $("#numRodada").textContent = numeroRodada;
    ocultarAviso();
    renderTabuleiro();
    $("#ultimo").innerHTML = '<span class="texto-vazio">Aguardando palpites no chat...</span>';
    $("#ultimos").innerHTML = "";
    palavraDigitada = "";
    atualizarTeclado();
    atualizarStatus();
}

function adicionarPalpite(info) {
    if (info) {
        guesses.push(info);
        if (guesses.length > MAX_LINHAS) guesses.shift();
    }
    renderTabuleiro();
    atualizarTeclado();
    atualizarStatus();
    renderUltimos([info].concat(guesses.slice(0, 4)));
    // Último palpite
    const u = $("#ultimo");
    u.innerHTML = "";
    const av = document.createElement("span"); av.className = "avatar";
    if (info.avatar) { const im = document.createElement("img"); im.src = info.avatar; av.appendChild(im); }
    u.appendChild(av);
    const nome = document.createElement("span"); nome.className = "nome-jogador"; nome.textContent = info.nome || "";
    u.appendChild(nome);
    const w = document.createElement("span"); w.className = "mini-word"; w.textContent = (info.palpite || "").toUpperCase();
    u.appendChild(w);
}

// ------------------------------------------------------------
//  Tabuleiro 6x5 sempre presente
// ------------------------------------------------------------
function renderTabuleiro() {
    const tabuleiro = $("#tabuleiro");
    tabuleiro.innerHTML = "";
    for (let r = 0; r < MAX_LINHAS; r++) {
        const linha = document.createElement("div");
        linha.className = "linha" + (r === guesses.length - 1 ? (guesses.length ? " nova" : "") : "");
        const g = r < guesses.length ? guesses[r] : null;
        for (let c = 0; c < 5; c++) {
            const celula = document.createElement("div");
            celula.className = "celula ausente";
            if (g) {
                const estado = g.resultado[c] || "ausente";
                celula.className = "celula " + estado;
                celula.textContent = g.palpite[c] || "·";
                if (r === guesses.length - 1) celula.classList.add("nova");
            } else {
                // linha vazia: apenas bordas claras
                celula.textContent = "";
                celula.style.opacity = "0.6";
            }
            if (revealed[c] && !g) { celula.textContent = revealed[c].toUpperCase(); celula.classList.add("revelada"); }
            linha.appendChild(celula);
        }
        tabuleiro.appendChild(linha);
    }
}

// ------------------------------------------------------------
function renderRanking(lista) {
    const ol = $("#listaRanking");
    ol.innerHTML = "";
    (lista || []).slice(0, 5).forEach((r) => {
        const li = document.createElement("li");
        const n = document.createElement("span"); n.textContent = (r.posicao || "") + ". " + (r.nome || "");
        const p = document.createElement("span"); p.className = "pts"; p.textContent = (r.pontos || 0) + " pts";
        li.appendChild(n); li.appendChild(p);
        ol.appendChild(li);
    });
}

function atualizarTeclado() {
    const estados = {};
    for (const palpite of guesses) {
        for (let i = 0; i < (palpite.palpite || "").length; i++) {
            const letra = palpite.palpite[i].toUpperCase();
            const estado = palpite.resultado?.[i] || "ausente";
            if (estado === "correct" || (estado === "present" && estados[letra] !== "correct")) estados[letra] = estado;
            if (!estados[letra]) estados[letra] = "ausente";
        }
    }
    document.querySelectorAll("[data-letra]").forEach((tecla) => {
        tecla.classList.remove("correta", "presente", "ausente");
        const estado = estados[tecla.dataset.letra];
        if (estado) tecla.classList.add(estado === "correct" ? "correta" : estado === "present" ? "presente" : "ausente");
    });
}

function atualizarStatus() {
    const rodada = $("#statusRodada");
    const palpite = $("#statusPalpite");
    if (rodada) rodada.textContent = rodadaAtiva ? "Rodada " + numeroRodada + " ativa" : "Rodada pausada";
    if (palpite) palpite.textContent = palavraDigitada ? "Palavra: " + palavraDigitada : "Aguardando palpites do chat";
}

function renderUltimos(lista) {
    const ul = $("#ultimos");
    ul.innerHTML = "";
    (lista || []).forEach((x) => {
        const li = document.createElement("li");
        const av = document.createElement("span"); av.className = "mini-avatar";
        if (x.avatar) { const im = document.createElement("img"); im.src = x.avatar; av.appendChild(im); av.style.overflow = "hidden"; }
        li.appendChild(av);
        li.appendChild(document.createTextNode(x.nome || ""));
        ul.appendChild(li);
    });
}

// ------------------------------------------------------------
//  Vencedor + contagem regresiva para nova rodada
// ------------------------------------------------------------
function mostrarVencedor(msg) {
    ocultarAviso();
    const av = $("#aviso");
    av.classList.add("mostrar");
    const cartel = document.createElement("div");
    cartel.className = "cartel";
    cartel.textContent = msg.mensagem || "";
    av.appendChild(cartel);
}

function novaRodadaContagem(seg) {
    // chamado pelo temporizador após o fim da rodada
    const av = $("#aviso");
    if (av.classList.contains("mostrar")) {
        let sub = av.querySelector(".sub");
        if (!sub) { sub = document.createElement("div"); sub.className = "sub"; av.appendChild(sub); }
        sub.textContent = "Nova rodada em " + seg + "...";
    }
}

function ocultarAviso() {
    const av = $("#aviso");
    av.innerHTML = "";
    av.classList.remove("mostrar");
}

// ------------------------------------------------------------
function revelarLetra(msg) {
    revealed[msg.pos] = msg.letra;
    notificar(msg, msg.user || "", "🔎 " + (msg.mensagem || "Letra revelada: " + msg.letra));
    renderTabuleiro();
}

function eliminarLetra(msg) {
    if (msg.letra) eliminated.add(String(msg.letra).toLowerCase());
    notificar(msg, msg.user || "", "🚫 " + (msg.mensagem || "Letra eliminada"));
    renderTabuleiro();
}

function casoCorreto(msg) {
    notificar(msg, msg.palpite?.nome || "", "🎉 " + ((msg.palpite?.nome || "") + " acertou! +" + (msg.pts || 0) + " pts"));
}

// =================== Notificações ===================
function notificar(msg, quem, texto) {
    const cont = $("#notificacoes");
    if (!cont) return;
    const n = document.createElement("div");
    n.className = "notif";
    if (quem) { const q = document.createElement("span"); q.className = "quem"; q.textContent = esc(quem); n.appendChild(q); }
    const t = document.createElement("span"); t.className = "titulo"; t.textContent = texto;
    n.appendChild(t);
    cont.prepend(n);
    while (cont.children.length > 4) cont.removeChild(cont.lastChild);
    setTimeout(() => { if (n.parentNode) n.remove(); }, 5000);
}

function notificarPresente(msg) {
    const cont = $("#notificacoes");
    if (!cont) return;
    const n = document.createElement("div");
    n.className = "notif";
    const q = document.createElement("span"); q.className = "quem"; q.textContent = esc(msg.user || "") + " enviou " + esc(msg.presente || "");
    const t = document.createElement("span"); t.className = "titulo"; t.textContent = esc(msg.habilidade || "");
    n.appendChild(q); n.appendChild(t);
    cont.prepend(n);
    while (cont.children.length > 4) cont.removeChild(cont.lastChild);
    setTimeout(() => { if (n.parentNode) n.remove(); }, 6000);
}

// =================== Temporizadores ===================
setInterval(() => {
    if (rodadaAtiva && countdown > 0) {
        countdown--;
        const m = String(Math.floor(countdown / 60)).padStart(2, "0");
        const s = String(countdown % 60).padStart(2, "0");
        const t = $("#temporizador");
        if (t) t.textContent = m + ":" + s;
        if (countdown <= 5) novaRodadaContagem(countdown);
    } else if (!rodadaAtiva) {
        // contagem para nova rodada quando pausa/antes de iniciar
    }
}, 1000);

// =================== Conectar ===================
conectar();

function processarTecla(valor) {
    if (valor === "apagar") palavraDigitada = palavraDigitada.slice(0, -1);
    else if (valor === "enviar") {
        if (palavraDigitada.length === 5) notificar({}, "", "Envie " + palavraDigitada + " no chat para registrar o palpite.");
        else notificar({}, "", "Digite uma palavra de 5 letras.");
    } else if (palavraDigitada.length < 5) {
        palavraDigitada += valor;
    }
    atualizarStatus();
}

document.querySelectorAll("[data-letra], [data-comando]").forEach((tecla) => {
    tecla.addEventListener("click", () => processarTecla(tecla.dataset.letra || tecla.dataset.comando));
});

document.addEventListener("keydown", (evento) => {
    if (/^[a-zA-Z]$/.test(evento.key)) processarTecla(evento.key.toUpperCase());
    else if (evento.key === "Backspace") processarTecla("apagar");
    else if (evento.key === "Enter") processarTecla("enviar");
});

const alternarPainel = (id) => $(id)?.classList.toggle("aberto");
$("#botaoRanking").addEventListener("click", () => alternarPainel("#painelRanking"));
$("#botaoStatus").addEventListener("click", () => alternarPainel("#painelStatus"));
document.querySelectorAll(".fechar-painel").forEach((botao) => botao.addEventListener("click", () => {
    botao.closest("aside")?.classList.remove("aberto");
    botao.closest("dialog")?.close();
}));
$("#botaoAjuda").addEventListener("click", () => $("#modalAjuda").showModal());