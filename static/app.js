// app.js — orquestracao. Roda a corrida, guarda o vetor, e liga o cursor a tudo.
//
// O QUE ESTE ARQUIVO NAO TEM: o laco de controle.
//
//   `POST /expert/{sid}/ciclo` ja percorre as 19 regras na ordem do fonte,
//   relendo o estado a cada atuacao. Aqui so se pede o proximo minuto e se guarda
//   a resposta. No projeto anterior esse laco existia em cinco lugares, e o
//   comentario que sobrou depois da remocao dizia o porque: "qualquer divergencia
//   faria a demonstracao da defesa mostrar uma coisa e o capitulo de resultados
//   relatar outra" (PRD §6.1).
//
// O vetor da corrida sao ~260 amostras nos cenarios 1 a 5 — uma por chamada de
// ciclo, nao uma por minuto, porque o simulador salta o relogio. O frontend
// anterior morreu exatamente aqui, mas porque guardava 700 mil pontos tentando
// animar o cenario 6; o cenario 6 fica fora da timeline (PRD §7.4).

import * as api from "./api.js";
import * as panels from "./panels.js";
import * as rule from "./rule.js";
import * as band from "./band.js";
import { CALHA, TICKS_T } from "./panels.js";
import * as params from "./params.js";

const $ = (id) => document.getElementById(id);

const app = {
  base: [],          // as 19 regras
  porRegra: new Map(),
  fracos: new Map(), // limiares que esta corrida alcança, por grandeza
  cenarios: null,
  corrida: [],       // [{t, estado, disparadas, saida}]
  tmax: 1440,
  regraSel: null,    // qual das regras do minuto está sendo explicada
  rodando: false,
  noTeto: false,     // a última corrida bateu no teto de amostras?
  parar: false,      // pedido de interrupção pelo botão
};

// Teto de amostras do CLIENTE. O laço abaixo pergunta ao serviço quando parar
// (`pode_continuar`), e o serviço só para no horizonte ou no fim de ciclo. Com o
// horizonte editável, um `tmax` de 700000 pede 514 mil chamadas e reproduz a
// morte do frontend anterior — 700 mil pontos guardados (PRD §9). Um
// `tempodilute` muito negativo faz o mesmo por outro caminho: o relógio anda
// para trás e `pode_continuar` nunca fica falso. O teto para e DIZ que parou.
const TETO_AMOSTRAS = 20000;

/* ---------------------------------------------------------------- falha visivel */

function mostraErro(e) {
  $("erro").hidden = false;
  $("erro").innerHTML = `<b>A corrida parou.</b>
    <span>${e.onde || ""} — ${e.message}${e.corpo ? ` · ${e.corpo}` : ""}</span>`;
  $("led").className = "led morta";
  $("rotulo-servico").textContent = "expert:8009 sem resposta";
}
function limpaErro() {
  $("erro").hidden = true;
  $("led").className = "led viva";
  $("rotulo-servico").textContent = "expert:8009 ⇄ reactor:8008";
}

/* ------------------------------------------------------------------- a corrida */

async function roda() {
  if (app.rodando) return;
  const n = $("cenario").value;

  // O corpo vem do formulário, que nasce do cenário. Duas armadilhas do PRD §5.3
  // continuam valendo: `tmax` tem de ir explícito (o padrão do serviço é 700000),
  // e `reactor_url` NÃO vai — o padrão interno é que vale, e o navegador nem
  // alcançaria aquele nome.
  const corpo = params.corpo();
  if (!params.temHorizonte()) {
    mostraErro({ onde: "cenarios.json", message: `o cenário ${n} não tem tmax — fora da timeline (§7.4)` });
    return;
  }
  app.tmax = params.horizonte();

  app.rodando = true;
  app.parar = false;
  // O botão vira Parar em vez de desabilitar: com o horizonte editável uma
  // corrida pode pedir dezenas de milhares de ciclos, e ficar sem saída durante
  // minutos é defeito, não paciência.
  $("rodar").textContent = "■ Parar";
  $("cenario").disabled = true;
  app.corrida = [];
  limpaErro();

  let sid = null;
  try {
    const inicio = await api.iniciar(corpo);
    sid = inicio.sessao;

    let r = inicio;
    // Uma chamada por ciclo. O servico e quem diz quando parar: `pode_continuar`
    // fica falso no horizonte ou quando R19 declara fim de ciclo.
    let guarda = 0;
    do {
      r = await api.ciclo(sid);
      app.corrida.push({
        t: r.estado.t,
        estado: r.estado,
        disparadas: r.disparadas,
        saida: r.saida_b64 ? decodifica(r.saida_b64) : "",
      });
      if (++guarda % 20 === 0) {
        $("progresso").textContent = `rodando… t = ${r.estado.t} de ${app.tmax}`;
        await new Promise((ok) => setTimeout(ok, 0)); // deixa a tela respirar
      }
    } while (r.pode_continuar && !app.parar && app.corrida.length < TETO_AMOSTRAS);

    app.noTeto = r.pode_continuar;
    $("progresso").textContent = app.parar
      ? `interrompida · ${app.corrida.length} amostras · t = ${r.estado.t}`
      : app.noTeto
        ? `parou no teto de ${TETO_AMOSTRAS} amostras · t = ${r.estado.t} de ${app.tmax}`
        : `${app.corrida.length} ciclos · t até ${r.estado.t}${r.termino ? ` · ${r.termino}` : ""}`;
  } catch (e) {
    mostraErro(e);
    return;
  } finally {
    app.rodando = false;
    $("rodar").textContent = "▷ Rodar";
    $("cenario").disabled = false;
    // A sessao e fechada mesmo depois de erro: o servico guarda no maximo 32.
    if (sid) api.encerrar(sid).catch(() => {});
  }

  const alcancadas = new Set(app.corrida.flatMap((a) => a.disparadas));
  app.fracos = panels.limiaresFracos(app.base, alcancadas);
  panels.prepara(app.corrida, app.tmax);
  band.pinta(app.base, app.corrida, app.tmax);
  const s = $("slider");
  s.max = String(app.corrida.length - 1);
  s.value = String(app.corrida.length - 1);
  s.disabled = false;
  eixoDoTempo();
  mostra(app.corrida.length - 1);
  selo();
}

/** Como esta corrida pode (ou não) ser conferida.
 *
 *  Uma corrida arbitrária não tem contagem em results/API/ nem curva da
 *  dissertação para comparar (PRD §7.5) — e a tela diz isso em vez de deixar
 *  parecer que bate com alguma coisa. As quatro bordas são a exceção: a tabela
 *  do §8 de steps/05 tem a contagem esperada de cada regra, então ali dá para
 *  conferir de verdade. */
function selo() {
  const alvo = $("selo");
  const esperado = params.esperado();
  if (app.parar || app.noTeto) {
    alvo.className = "selo-corrida borda";
    alvo.textContent = app.parar ? "interrompida" : "parou no teto";
    alvo.title = app.parar
      ? "A corrida foi interrompida antes do fim: as contagens estão incompletas."
      : `A corrida parou no teto de ${TETO_AMOSTRAS} amostras: as contagens estão incompletas.`;
    return;
  }
  if (esperado) {
    const obtido = {};
    for (const a of app.corrida) for (const id of a.disparadas) obtido[id] = (obtido[id] || 0) + 1;
    const divergem = Object.entries(esperado).filter(([id, n]) => (obtido[id] || 0) !== n);
    alvo.className = `selo-corrida ${divergem.length ? "borda" : "ok"}`;
    alvo.textContent = divergem.length ? `${divergem.length} divergem do §8` : "confere com o §8";
    alvo.title = Object.entries(esperado)
      .map(([id, n]) => `${id}: esperado ${n} · obtido ${obtido[id] || 0}`).join("\n");
    return;
  }
  if (params.modificado()) {
    alvo.className = "selo-corrida borda";
    alvo.textContent = "sem referência";
    alvo.title = "Corrida com parâmetros alterados: não há contagem em results/API/ nem curva da dissertação para comparar (PRD §7.5).";
    return;
  }
  alvo.className = "selo-corrida";
  alvo.textContent = "";
  alvo.title = "";
}

/** base64 → texto. Os bytes vem em latin-1, como o C os imprimiu. */
function decodifica(b64) {
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new TextDecoder("latin1").decode(bytes);
}

/* -------------------------------------------------------------------- o cursor */

function mostra(i) {
  const a = app.corrida[i];
  if (!a) return;
  $("treloj").textContent = a.t;
  $("ciclo").textContent = `min · ciclo ${i + 1}/${app.corrida.length}`;

  // Uma regra por vez. Desenhar as faixas das três que dispararam no mesmo
  // minuto empilhava regiões translúcidas até o painel virar um borrão.
  const idSel = a.disparadas.includes(app.regraSel) ? app.regraSel : (a.disparadas[0] || null);
  const regra = idSel ? app.porRegra.get(idSel) : null;

  $("fichas").innerHTML = a.disparadas.length
    ? `<span class="ftitulo">disparou aqui:</span>` + a.disparadas.map((id) => {
        const r = app.porRegra.get(id);
        return `<button class="ficha ${id === idSel ? "sel" : ""}" data-id="${id}">${id}
          <span class="fdesc">${r ? r.descricao : ""}</span></button>`;
      }).join("")
    : `<span class="ftitulo">nenhuma regra disparou neste minuto</span>`;
  for (const b of $("fichas").querySelectorAll(".ficha")) {
    b.addEventListener("click", () => { app.regraSel = b.dataset.id; mostra(+$("slider").value); });
  }

  // A altura de cada painel vem do espaço que sobrou, não da proporção do SVG —
  // é isso que faz o dashboard caber na janela sem rolagem.
  const cx0 = $("paineis");
  // A largura que importa é a do SVG, não a do contêiner: a coluna do rótulo
  // fica fora dele. Usar a do contêiner deixava a escala menor que a caixa, e
  // cada painel sobrava uma faixa vazia.
  const svg0 = cx0.querySelector(".painel > svg");
  const largura = svg0 ? svg0.clientWidth : cx0.clientWidth - 178;
  panels.defineAltura(cx0.clientHeight / panels.PAINEIS.length, largura);
  panels.desenha(cx0, a, regra, app.fracos);
  rule.desenha($("painel-regra"), regra, a.estado, a.saida);

  band.acende(app.base, a.disparadas);
  // O cursor é posicionado por MEDIÇÃO, não por `calc()`: a conta envolve
  // multiplicar uma porcentagem por um comprimento, o que o CSS não faz — a
  // primeira tentativa produzia uma expressão inválida e o cursor ia para a
  // borda da tela. Medir a linha da faixa dá a mesma calha dos painéis.
  const frac = a.t / app.tmax;
  const c = $("cursor");
  const linha = $("grade").querySelector(".rlinha");
  const cartao = c.closest(".faixa");
  if (linha && cartao) {
    c.hidden = false;                      // medir antes de mostrar dá rect zerado
    const rl = linha.getBoundingClientRect();
    const rc = cartao.getBoundingClientRect();
    const rg = $("grade").getBoundingClientRect();
    c.style.left = `${rl.left - rc.left + ((CALHA.esq + frac * CALHA.larg) / 100) * rl.width}px`;
    c.style.top = `${rg.top - rc.top - 8}px`;
    c.style.height = `${rg.height + 16}px`;
  }
}

function eixoDoTempo() {
  // Os mesmos tiques dos painéis, nas mesmas posições — os dois eixos do tempo
  // têm de bater, senão o cursor mente sobre onde está.
  // O último tique redondo sai se estiver colado no fim: "1400 1440" vira borrão.
  const ts = TICKS_T.filter((t) => t <= app.tmax * 0.96);
  ts.push(app.tmax);
  $("eixot").innerHTML = ts.map((t) =>
    `<span style="left:${CALHA.esq + (t / app.tmax) * CALHA.larg}%">${t}</span>`).join("");
  $("slider").style.marginLeft = `${CALHA.esq}%`;
  $("slider").style.width = `${CALHA.larg}%`;
}

/* -------------------------------------------------------------------- a partida */

async function comeca() {
  try {
    app.base = await api.regras();
    app.porRegra = new Map(app.base.map((r) => [r.id, r]));
    band.monta($("grade"), app.base);
    limpaErro();
  } catch (e) {
    mostraErro(e);
    return;
  }

  try {
    const r = await fetch("cenarios.json");
    if (!r.ok) throw new Error(`cenarios.json respondeu ${r.status}`);
    app.cenarios = (await r.json()).cenarios;
  } catch (e) {
    mostraErro({ onde: "GET cenarios.json", message: e.message });
    return;
  }

  $("cenario").innerHTML = Object.entries(app.cenarios)
    .map(([n, c]) => `<option value="${n}" ${c.tmax === null ? "disabled" : ""}>
        Cenário ${n} — ${c.descricao}${c.tmax === null ? " (fora da timeline, §7.4)" : ""}</option>`)
    .join("");
  $("cenario").value = "3";
  params.liga(() => { atualizaParams(); });
  $("cenario").addEventListener("change", () => {
    params.defineCenario($("cenario").value, app.cenarios[$("cenario").value]);
    atualizaParams();
  });
  params.defineCenario("3", app.cenarios["3"]);
  atualizaParams();

  $("legenda").innerHTML =
    band.LEGENDA.map(([t, nome]) => `<span><i class="b-${t}"></i>${nome}</span>`).join("") +
    `<span style="margin-left:auto">esmaecidas: nunca disparam neste cenário</span>`;

  $("paineis").innerHTML = `<div class="vazio">Escolha um cenário e aperte Rodar.</div>`;
  $("painel-regra").innerHTML = `<div class="vazio">As 19 regras já foram carregadas de
    <code>GET /expert/regras</code>. Falta a corrida.</div>`;
}

/* ------------------------------------------------------------------- os eventos */

/** Redesenha a linha dos sete valores. O `<option>` do seletor NÃO é reescrito:
 *  mutar o texto dele deixaria o rótulo "modificado" grudado no cenário depois
 *  de trocar de cenário. O estado vive na própria linha. */
function atualizaParams() {
  const n = $("cenario").value;
  params.desenhaLinha($("params"), app.cenarios[n].descricao);
}

$("rodar").addEventListener("click", () => {
  if (app.rodando) { app.parar = true; return; }
  roda();
});
$("slider").addEventListener("input", (e) => mostra(+e.target.value));

// Redimensionar muda o espaço disponível, e a altura dos painéis é medida —
// então tem de ser refeita. `requestAnimationFrame` espera o layout assentar.
let redesenho = null;
window.addEventListener("resize", () => {
  if (!app.corrida.length) return;
  cancelAnimationFrame(redesenho);
  redesenho = requestAnimationFrame(() => mostra(+$("slider").value));
});
$("tema").addEventListener("click", () => {
  const h = document.documentElement;
  h.dataset.tema = h.dataset.tema === "escuro" ? "claro" : "escuro";
});

comeca();
