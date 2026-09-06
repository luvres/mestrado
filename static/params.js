// params.js — os sete valores de partida: à vista e editáveis.
//
// POR QUE ISTO EXISTE (PRD §7.6)
//
//     R11, R12, R15 e R17 não disparam em NENHUM dos 6 cenários — é a interseção
//     de `nunca_dispararam` nos seis `results/API/cenario*-disparos.json`. Só
//     configurações de borda as alcançam. Com os sete editáveis a tela deixa de
//     "mostrar os 6 cenários" e passa a "rodar o controlador com o que você
//     quiser" — a única coisa que a figura impressa não tem.
//
// A ORDEM E OS RÓTULOS SÃO OS DO SIMULADOR
//
//     Estes sete não são uma escolha de interface: são os prompts que o operador
//     digita no simulador do Igor, na ordem em que ele pergunta
//     (V8_Reatividade_SimuladorIgor_linux.c:916-952). A mesma ordem está em
//     `scripts/cenarios.py:44` (ORDEM_PROMPTS) e no bloco `_sobre` de
//     `cenarios.json`. Os rótulos abaixo são o texto dos prompts, encurtado.
//
// AVISAR, NÃO TRAVAR
//
//     Nem a API nem o C impõem FAIXA a estes campos: não há `ge`/`le` para
//     potência, boro, barra, t1, t2 ou ΔI, e o "32 a 650 MW" é texto do prompt,
//     não validação. O formulário faz o mesmo — aceita qualquer número e o Rodar
//     continua habilitado — mas anota o que muda no modelo, com a linha do fonte
//     de onde o número veio.
//
//     Uma exceção, e ela não é faixa: `tempodilute` ganhou `gt=0` nos dois
//     serviços pelo mesmo motivo que `tmax` já tinha — os dois movem o relógio, e
//     um relógio que não avança faz a corrida nunca terminar. Aí o aviso anuncia
//     uma recusa que vem do serviço, e o erro chega pela barra vermelha.
//
//     Esses avisos NÃO são avaliação de regra. Comparar `cboro >= 1894.3` para
//     dizer "aqui a vazão satura" é uma nota sobre o modelo, não um veredito
//     sobre disparo: quem decide se uma regra disparou continua sendo o expert, e
//     a tela continua sem reavaliar condição nenhuma (§6.2).

import { interface_ } from "./format.js";

/** Os sete, na ordem dos prompts. */
export const CAMPOS = [
  { campo: "pot_turbina",   rotulo: "Potência inicial da turbina",        dica: "32 a 650 MW", uni: "MW",     passo: 1 },
  { campo: "cboro",         rotulo: "Concentração inicial de boro",       uni: "ppm",    passo: 10 },
  { campo: "posicao_barra", rotulo: "Posição inicial do banco D",         uni: "passos", passo: 1, inteiro: true },
  { campo: "tempodilute",   rotulo: "Intervalo de tempo por diluição",    uni: "min",    passo: 1, inteiro: true },
  { campo: "t1",            rotulo: "ΔT para a vazão mínima",  sigla: "t1", uni: "°C",   passo: 0.1 },
  { campo: "t2",            rotulo: "ΔT para a vazão máxima",  sigla: "t2", uni: "°C",   passo: 0.1 },
  { campo: "delta_i",       rotulo: "Delta I inicial",       sigla: "ΔI", uni: "%",      passo: 1 },
];

/** O horizonte entra junto porque as bordas usam 600 e 400, não 1440. */
export const HORIZONTE = { campo: "tmax", rotulo: "Horizonte da simulação", uni: "min", passo: 60 };

/**
 * As quatro configurações de borda. Os valores são os de
 * `scripts/verifica_expert.sh:94-98`, e as contagens esperadas são a tabela do
 * §8 de `steps/05-servico-expert.md` — nada aqui foi inventado. Nenhuma delas
 * tem transiente: só os sete valores e o horizonte.
 */
export const BORDAS = [
  { id: "d178", rotulo: "D=178, ΔI=−1", alvo: "R11",
    valores: { pot_turbina: 650, cboro: 1800, posicao_barra: 178, tempodilute: 4, t1: -0.3, t2: -0.8, delta_i: -1, tmax: 600 },
    esperado: { R6: 1, R9: 106, R10: 1, R11: 3, R13: 111, R15: 1 } },
  { id: "d170", rotulo: "D=170, ΔI=−1", alvo: "R11 e R12",
    valores: { pot_turbina: 650, cboro: 1800, posicao_barra: 170, tempodilute: 4, t1: -0.3, t2: -0.8, delta_i: -1, tmax: 600 },
    esperado: { R6: 1, R10: 1, R11: 527, R12: 1, R13: 6, R15: 2 } },
  { id: "d150", rotulo: "D=150, ΔI=−4", alvo: "R12 de emergência",
    valores: { pot_turbina: 650, cboro: 1800, posicao_barra: 150, tempodilute: 4, t1: -0.3, t2: -0.8, delta_i: -4, tmax: 600 },
    esperado: { R1: 3, R2: 1, R3: 1, R4: 2, R5: 1, R6: 1, R12: 424, R13: 7, R15: 4, R18: 2 } },
  { id: "d144", rotulo: "32 MW, D=144, ΔI=12", alvo: "R17",
    valores: { pot_turbina: 32, cboro: 1800, posicao_barra: 144, tempodilute: 4, t1: -0.3, t2: -0.8, delta_i: 12, tmax: 400 },
    esperado: { R1: 8, R5: 9, R7: 9, R17: 9 },
    // O aviso não é decorativo: esta é a única configuração da bateria em que o
    // porte NÃO reproduz o original.
    alerta: `Esta configuração cai sobre a única divergência conhecida do porte: o ramo
      \`if (Pbase<0)\` zera Pbase no porte Linux e zerava Ptopo no original. Com Pot=4,92 % e
      ΔI=12 as duas versões divergem por completo — ΔI ~9,8 contra ~0,03 em t=261
      (steps/01-porte-linux-simulador.md:319-326). Vale como exploração do controlador;
      não reproduz o simulador do Igor.` },
];

/* ------------------------------------------------------------------ estado */

let cenario = null;      // número do cenário de origem
let doCenario = {};      // valores como estão em cenarios.json
let atual = {};          // valores correntes, já com as edições
let borda = null;        // a borda aplicada, se os valores ainda forem os dela
let aoAplicar = () => {};

const TRANSIENTE = ["transiente", "t_transiente", "alvo", "taxa"];

/** Carrega um cenário de `cenarios.json` como ponto de partida. */
export function defineCenario(n, cen) {
  cenario = n;
  doCenario = {};
  for (const [k, v] of Object.entries(cen)) {
    if (k === "descricao") continue;
    doCenario[k] = v;
  }
  atual = { ...doCenario };
  borda = null;
}

/** Os campos que vão no corpo de POST /expert/initialize. Nulos são omitidos —
 *  `tmax` ausente significaria o padrão de 700000 do serviço (PRD §5.3). */
export function corpo() {
  const p = {};
  for (const [k, v] of Object.entries(atual)) if (v !== null && v !== undefined) p[k] = v;
  return p;
}

export const temHorizonte = () => atual.tmax !== null && atual.tmax !== undefined;
export const horizonte = () => atual.tmax;

/** Difere do cenário de origem? */
export function modificado() {
  return Object.keys(doCenario).some((k) => (atual[k] ?? null) !== (doCenario[k] ?? null));
}

/** Como a corrida deve ser chamada na tela. */
export function rotulo(descricaoDoCenario) {
  if (borda) return `Borda — ${borda.rotulo}`;
  if (modificado()) return `Cenário ${cenario} (modificado)`;
  return `Cenário ${cenario} — ${descricaoDoCenario}`;
}

/** Contagens esperadas, quando a corrida é uma borda intacta. Só então há com
 *  que conferir: uma corrida arbitrária não tem referência (PRD §7.5). */
export const esperado = () => (borda ? borda.esperado : null);

/* ----------------------------------------------------------------- avisos */

/** O que muda no modelo fora das faixas usuais. Cada aviso cita a fonte. */
export function avisos(v = atual) {
  const fora = [];
  const pot = v.pot_turbina / 6.5;                 // Pot em %, como no C:210

  if (v.pot_turbina < 32 || v.pot_turbina > 650)
    fora.push({ campo: "pot_turbina", txt: "o prompt do simulador declara 32 a 650 MW (C:916)" });
  if (v.cboro >= 1894.3)
    fora.push({ campo: "cboro", txt: "acima de 1894 ppm v1 satura em 5 lpm: a diluição deixa de responder ao boro (C:519-521)" });
  else if (v.cboro >= 1882.6)
    fora.push({ campo: "cboro", txt: "acima de 1883 ppm v2 satura em 10 lpm (C:523-525)" });
  if (v.cboro < 8)
    fora.push({ campo: "cboro", txt: "abaixo de 8 ppm R19 declara fim de ciclo na partida", grave: true });
  if (v.posicao_barra < 100)
    fora.push({ campo: "posicao_barra", txt: "abaixo de 100 passos o peso da barra muda de 6,5 para 20 pcm/passo (C:668)" });
  const li = 2.58 * pot - 85;                       // LimiteInsercao, C:1054
  if (v.posicao_barra <= li)
    fora.push({ campo: "posicao_barra", txt: `parte abaixo do limite de inserção (LI = ${interface_(li, 0)}); R12 alarma desde o início` });
  if (v.tempodilute <= 0)
    fora.push({ campo: "tempodilute", txt: "a API recusa (gt=0): o relógio deixaria de avançar e a corrida não terminaria", grave: true });
  if (v.t2 >= v.t1)
    fora.push({ campo: "t2", txt: "a rampa de vazão pressupõe t2 < t1; invertidos, o ramo do meio fica vazio (§5.5 do passo 3)" });
  if (v.delta_i > 2 * pot)
    fora.push({ campo: "delta_i", txt: "ΔI > 2·Pot leva ao ramo Pbase<0, onde o porte diverge do original (steps/01 §319-326)", grave: true });
  return fora;
}

/* ---------------------------------------------------------------- desenho */

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
const mostra = (c, v) =>
  v === null || v === undefined ? "—" : interface_(v, c.inteiro || c.passo >= 1 ? 0 : 2);

/** A linha compacta, sempre visível.
 *  A ficha da esquerda diz de qual configuração os valores vêm; o selo do
 *  cabeçalho é outra coisa — fala da última corrida. */
export function desenhaLinha(alvo, descricaoDoCenario = "") {
  const partes = CAMPOS.map((c) => {
    const mudou = (atual[c.campo] ?? null) !== (doCenario[c.campo] ?? null);
    const txt = `${c.sigla ? c.sigla + " " : ""}${mostra(c, atual[c.campo])}${
      c.uni === "%" || c.uni === "°C" ? "" : " " + c.uni}`;
    return `<span class="pv ${mudou ? "mudou" : ""}">${esc(txt)}</span>`;
  }).join('<i class="sep">·</i>');
  const h = temHorizonte()
    ? `<i class="sep">·</i><span class="pv ${atual.tmax !== doCenario.tmax ? "mudou" : ""}">${
        interface_(atual.tmax, 0)} min</span>`
    : "";
  const estado = borda
    ? `<span class="pestado borda">borda ${esc(borda.rotulo)}</span>`
    : modificado()
      ? `<span class="pestado borda">cenário ${cenario}, modificado</span>`
      : `<span class="pestado">cenário ${cenario}${descricaoDoCenario ? " — " + esc(descricaoDoCenario) : ""}</span>`;
  alvo.innerHTML = `<button class="abre-params" id="abre-params"
      title="editar os valores de partida">⚙ partida</button>${estado}${partes}${h}`;
  alvo.querySelector("#abre-params").addEventListener("click", abre);
}

function campoHtml(c, v, avisosDoCampo) {
  const val = v === null || v === undefined ? "" : v;
  return `<label class="pcampo">
    <span class="pnome">${esc(c.rotulo)}${c.sigla ? ` <b>${c.sigla}</b>` : ""}${
      c.dica ? ` <i>(${esc(c.dica)})</i>` : ""}</span>
    <input type="number" step="${c.passo}" value="${val}" data-campo="${c.campo}">
    <span class="puni">${esc(c.uni)}</span>
    ${avisosDoCampo.map((a) => `<span class="paviso ${a.grave ? "grave" : ""}">⚠ ${esc(a.txt)}</span>`).join("")}
  </label>`;
}

/** Abre o editor.
 *
 *  Um de cada vez: o modal usa `id` (`pmodal`, `paplica`, `prestaura`), e dois
 *  abertos ao mesmo tempo dão ids duplicados — `getElementById` passa a devolver
 *  o do modal velho, e aplicar grava os valores errados. Aconteceu num teste, e
 *  o resultado parecia bug de troca de cenário. */
export function abre() {
  if (document.getElementById("pmodal")) return;
  const av = avisos();
  const porCampo = (nome) => av.filter((a) => a.campo === nome);
  const tr = atual.transiente
    ? `${atual.transiente}${atual.t_transiente != null ? `, no minuto ${atual.t_transiente}` : ""}${
        atual.alvo ? ` · alvo ${atual.alvo} MW a ${atual.taxa} MW/min` : ""}`
    : "sem transiente de carga";

  const caixa = document.createElement("div");
  caixa.className = "pmodal";
  caixa.id = "pmodal";
  caixa.innerHTML = `<div class="pcaixa" role="dialog" aria-label="parâmetros de partida">
    <h3>Parâmetros de partida</h3>
    <p class="pfonte">Os sete valores que o operador digita, na ordem em que o simulador
      pergunta — <code>V8_Reatividade_SimuladorIgor_linux.c:916-952</code></p>

    <div class="pcampos">
      ${CAMPOS.map((c) => campoHtml(c, atual[c.campo], porCampo(c.campo))).join("")}
      <hr>
      ${campoHtml(HORIZONTE, atual.tmax, porCampo("tmax"))}
      <p class="ptravado">do cenário, não editável: <b>${esc(tr)}</b></p>
    </div>

    <div class="pbordas">
      <h4>Configurações de borda — alcançam as 4 regras que nenhum cenário acende</h4>
      ${BORDAS.map((b) => `<button class="pborda" data-borda="${b.id}">
          <b>${esc(b.rotulo)}</b><span>${esc(b.alvo)}</span></button>`).join("")}
      <p class="pnota">Valores de <code>scripts/verifica_expert.sh:94-98</code>; contagens
        esperadas da tabela do §8 de <code>steps/05-servico-expert.md</code>.</p>
      <p class="paviso grave" id="palerta" hidden></p>
    </div>

    <p class="pnota">Nem a API nem o fonte impõem faixa a estes campos
      (<code>expert/models.py:26-32</code>) — os avisos dizem o que muda no modelo, e o
      Rodar continua habilitado.</p>

    <div class="pacoes">
      <button id="prestaura">↺ restaurar cenário ${cenario}</button>
      <span class="espaco"></span>
      <button id="pcancela">cancelar</button>
      <button id="paplica" class="rodar">aplicar</button>
    </div>
  </div>`;
  document.body.appendChild(caixa);

  const rascunho = { ...atual };
  const redesenha = () => {
    const av2 = avisos(rascunho);
    for (const el of caixa.querySelectorAll(".pcampo")) {
      const nome = el.querySelector("input").dataset.campo;
      for (const a of el.querySelectorAll(".paviso")) a.remove();
      for (const a of av2.filter((x) => x.campo === nome)) {
        el.insertAdjacentHTML("beforeend",
          `<span class="paviso ${a.grave ? "grave" : ""}">⚠ ${esc(a.txt)}</span>`);
      }
    }
  };

  for (const inp of caixa.querySelectorAll("input[data-campo]")) {
    inp.addEventListener("input", () => {
      const n = inp.value === "" ? null : Number(inp.value);
      rascunho[inp.dataset.campo] = Number.isNaN(n) ? null : n;
      borda = null;
      redesenha();
    });
  }

  for (const b of caixa.querySelectorAll(".pborda")) {
    b.addEventListener("click", () => {
      const cfg = BORDAS.find((x) => x.id === b.dataset.borda);
      Object.assign(rascunho, cfg.valores);
      for (const k of TRANSIENTE) rascunho[k] = null;   // as bordas não têm transiente
      for (const inp of caixa.querySelectorAll("input[data-campo]")) {
        const v = rascunho[inp.dataset.campo];
        inp.value = v === null || v === undefined ? "" : v;
      }
      for (const outro of caixa.querySelectorAll(".pborda")) outro.classList.remove("sel");
      b.classList.add("sel");
      const alerta = caixa.querySelector("#palerta");
      alerta.hidden = !cfg.alerta;
      if (cfg.alerta) alerta.textContent = "⚠ " + cfg.alerta.replace(/\s+/g, " ").trim();
      caixa.querySelector(".ptravado").innerHTML = "do cenário, não editável: <b>sem transiente de carga</b>";
      redesenha();
      rascunho.__borda = cfg.id;
    });
  }

  const fecha = () => caixa.remove();
  caixa.querySelector("#pcancela").addEventListener("click", fecha);
  caixa.addEventListener("click", (e) => { if (e.target === caixa) fecha(); });
  caixa.querySelector("#prestaura").addEventListener("click", () => {
    atual = { ...doCenario }; borda = null; fecha(); aoAplicar();
  });
  caixa.querySelector("#paplica").addEventListener("click", () => {
    const id = rascunho.__borda;
    delete rascunho.__borda;
    atual = { ...rascunho };
    borda = id ? BORDAS.find((x) => x.id === id) : null;
    fecha();
    aoAplicar();
  });
}

export function liga(cb) { aoAplicar = cb; }
