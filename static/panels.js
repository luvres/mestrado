// panels.js — os cinco instrumentos do controlador, no tempo.
//
// SUBSTITUI AS RÉGUAS, E O MOTIVO IMPORTA
//
//     A primeira versão desenhava cinco réguas com uma agulha: o estado de UM
//     minuto. Duas coisas quebraram.
//
//     Primeira, legibilidade: dezessete limiares e trinta siglas de regra numa
//     linha de 900px, em fonte de 8,5px e três alturas. Densidade sem
//     hierarquia — ninguém lê.
//
//     Segunda, e mais grave: o conteúdo de tese é TEMPORAL. "A barra sendo
//     espremida contra o limite" é a barra se aproximando de `LimiteInsercao` ao
//     longo do tempo. `LI` e `BD` não são marcas — são curvas, e uma agulha num
//     instante não mostra aproximação. Na régua do banco D elas simplesmente
//     saíam de cena: `LI = 2,58·Pot − 85` fica em −27 a 23% de potência.
//
//     Aqui cada grandeza é uma curva no tempo, `LI` e `BD` são curvas ao lado
//     dela, e o cursor atravessa os cinco painéis.
//
// A GRAMÁTICA DAS FAIXAS
//
//     faixa cheia          o termo é obrigatório (só `&&` até a raiz). Como a
//                          regra disparou, ele vale — e a curva está dentro.
//     contorno A, B, …     alternativas sob um `||`. Mesma letra vale junto;
//                          letras diferentes, basta uma. QUAL delas, a tela não
//                          diz: dizer exigiria avaliar (ver tree.js).
//     tracejado            a guarda do bloco.
//
// Nenhum número é calculado aqui. `LimiteInsercao` e `BD` chegam prontos no
// `estado` porque a aritmética do modelo é de 32 bits emulada e o JavaScript só
// tem `double` (PRD §6.2).

import { interface_, exato } from "./format.js";
import { termosDe, comparacao, valorDe } from "./tree.js";

export const PAINEIS = [
  { campo: "DeltaT",       nome: "ΔT",        unidade: "°C",     casas: 2 },
  { campo: "DeltaI",       nome: "ΔI",        unidade: "%",      casas: 2 },
  { campo: "DesvioDeltaI", nome: "Desvio ΔI", unidade: "%",      casas: 2 },
  { campo: "PosicaoBarra", nome: "Banco D",   unidade: "passos", casas: 0,
    // As referências móveis NÃO entram no cálculo da escala: `LI` desce a −27 e
    // achataria a barra num tracinho. Entram recortadas, e aparecem quando
    // chegam perto — que é exatamente quando importam.
    refs: [{ campo: "LimiteInsercao", rot: "LI", escala: false },
           { campo: "BD",             rot: "BD", escala: true }] },
  { campo: "Cboro",        nome: "Boro",      unidade: "ppm",    casas: 0 },
];

const ESQ = 52, DIR = 980, LARG = 1030;

// A ALTURA NÃO É FIXA, E ISSO É DE PROPÓSITO
//
//     Com `viewBox` de altura constante e `width:100%`, a altura em pixels sai
//     da proporção — cinco painéis viravam ~1090 px e a tela pedia rolagem. Aqui
//     é o contrário: quem manda é o espaço disponível. `defineAltura()` recebe a
//     altura em pixels de um painel e a largura da coluna, e converte para
//     unidades do `viewBox`; a escala uniforme então mapeia 1030 unidades na
//     largura e ALT unidades na altura pedida, exatamente.
//
//     A fonte continua estável porque depende só da largura: 10 unidades numa
//     coluna de 1500 px dão ~14,6 px, independentemente da altura do painel.
let ALT = 150, TOPO = 14, BASE = 126;
const EIXO_X = 30;                      // espaço do eixo do tempo, no último painel

export function defineAltura(alturaPx, larguraPx) {
  const bruto = larguraPx > 0 ? (LARG * alturaPx) / larguraPx : 150;
  ALT = Math.max(58, bruto);            // abaixo disso não cabe rótulo nenhum
  TOPO = 8;
  BASE = ALT - 10;
  return ALT;
}

/** A calha do desenho, em % da coluna — o SVG reserva ESQ unidades à esquerda
 *  para os rótulos do eixo Y. A faixa de disparos e a linha do tempo usam estes
 *  mesmos números, senão os dois eixos do tempo não se alinham na vertical, que
 *  é a única razão de eles estarem empilhados. */
export const CALHA = { esq: (ESQ / LARG) * 100, larg: ((DIR - ESQ) / LARG) * 100 };
export const TICKS_T = [0, 200, 400, 600, 800, 1000, 1200, 1400];

function ticks(min, max, alturaUnidades = 112) {
  // menos tiques em painel baixo: 3 rótulos em 40 unidades viram uma mancha
  const alvo = Math.max(2, Math.min(4, Math.round(alturaUnidades / 26)));
  const bruto = (max - min) / alvo;
  const mag = Math.pow(10, Math.floor(Math.log10(bruto)));
  const passo = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => p >= bruto) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(min / passo) * passo; v <= max; v += passo)
    out.push(Math.round(v / passo) * passo);
  return out;
}

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");

/** Estado do desenho: domínios, calculados uma vez por corrida. */
let dom = new Map(), tmax = 1440, corrida = [];

export function prepara(amostras, horizonte) {
  corrida = amostras;
  tmax = horizonte;
  dom = new Map();
  for (const p of PAINEIS) {
    if (!amostras.length || amostras[0].estado[p.campo] === undefined) continue;
    const vs = amostras.map((a) => a.estado[p.campo]);
    for (const r of (p.refs || []).filter((r) => r.escala))
      vs.push(...amostras.map((a) => a.estado[r.campo]));
    let min = Math.min(...vs), max = Math.max(...vs);
    const folga = (max - min) * 0.1 || 1;
    dom.set(p.campo, { min: min - folga, max: max + folga });
  }
}

const px = (t) => ESQ + (t / tmax) * (DIR - ESQ);
const py = (p, v, base = BASE) => {
  const d = dom.get(p.campo);
  return base - ((v - d.min) / (d.max - d.min)) * (base - TOPO);
};
const caminho = (p, campo, base) =>
  corrida.map((a, i) => `${i ? "L" : "M"}${px(a.t).toFixed(1)},${py(p, a.estado[campo], base).toFixed(1)}`).join("");

/** As faixas da regra selecionada, no painel de uma grandeza. */
function faixasDaRegra(p, regra, estado, base) {
  if (!regra) return { desenho: "", rotulos: [] };
  const desenho = [], rotulos = [];

  const termos = termosDe(regra.condicao).map((f) => ({ ...f, guarda: false }));
  // A guarda também tem estrutura: a do bloco II é `DesvioDeltaI > 2 ||
  // DesvioDeltaI < -2`, uma disjunção. Achatá-la repetiria, dentro da guarda, o
  // erro que esta versão veio corrigir na condição.
  for (const f of termosDe(regra.guarda_do_bloco || ""))
    if (f.texto) termos.push({ ...f, guarda: true });

  for (const t of termos) {
    const c = comparacao(t.texto);
    if (!c || c.campo !== p.campo) continue;
    const acima = c.op === ">" || c.op === ">=";
    const marca = (t.guarda ? "guarda" : regra.id) + (t.ramo ? `·${t.ramo}` : "");
    const rot = `${marca}: ${p.nome}${c.op}${c.rot}`;
    const classe = t.guarda ? "guarda" : t.obrigatorio ? "obrigatorio" : "alternativa";

    if (c.fixo !== undefined) {
      const y = py(p, c.fixo, base);
      if (y < TOPO - 2 || y > base + 2) {
        // Fronteira fora do painel. Se o lado que satisfaz é o lado visível,
        // então TODA a faixa desenhada satisfaz o termo — e isso é geometria da
        // região, não avaliação do estado. O contrário não é dito.
        if ((y > base && acima) || (y < TOPO && !acima)) {
          desenho.push(`<rect class="regiao ${classe}" x="${ESQ}" y="${TOPO}"
            width="${DIR - ESQ}" height="${base - TOPO}"/>`);
          rotulos.push({ y: base - 8, txt: `${rot} — toda a faixa satisfaz`, classe });
        } else {
          rotulos.push({ y: base - 8, txt: `${rot} — fronteira fora desta faixa`, classe: "fraco" });
        }
        continue;
      }
      const h = Math.max(0, acima ? y - TOPO : base - y);
      desenho.push(`<rect class="regiao ${classe}" x="${ESQ}" y="${acima ? TOPO : y}"
          width="${DIR - ESQ}" height="${h}"/>
        <line class="fronteira ${classe}" x1="${ESQ}" y1="${y}" x2="${DIR}" y2="${y}"/>`);
      rotulos.push({ y, txt: rot, classe });
    } else {
      // Limiar móvel: a fronteira é uma curva, e a região é o polígono até a borda.
      const pts = corrida.map((a) => `${px(a.t).toFixed(1)},${py(p, valorDe(c, a.estado), base).toFixed(1)}`);
      const canto = acima ? `${DIR},${TOPO} ${ESQ},${TOPO}` : `${DIR},${base} ${ESQ},${base}`;
      desenho.push(`<polygon class="regiao ${classe}" points="${pts.join(" ")} ${canto}"/>
        <polyline class="fronteira ${classe}" points="${pts.join(" ")}"/>`);
      rotulos.push({ y: py(p, valorDe(c, estado), base), txt: rot, classe });
    }
  }
  return { desenho: desenho.join(""), rotulos };
}

function painel(p, amostra, ultimo, regra, limiaresFracos) {
  const e = amostra.estado;
  const d = dom.get(p.campo);
  // O último painel não fica MAIOR para caber o eixo: ele cede área de desenho.
  // Crescer quebraria a conta de altura total, que é o que tira a rolagem.
  const base = ultimo ? BASE - EIXO_X : BASE;

  const grade = ticks(d.min, d.max, base - TOPO).map((v) =>
    `<line class="grade" x1="${ESQ}" y1="${py(p, v, base)}" x2="${DIR}" y2="${py(p, v, base)}"/>
     <text class="rotgrade" x="${ESQ - 6}" y="${py(p, v, base) + 3}">${interface_(v, p.casas)}</text>`
  ).join("");

  const fracos = (limiaresFracos.get(p.campo) || [])
    .filter((v) => v > d.min && v < d.max)
    .map((v) => `<line class="limiar" x1="${ESQ}" y1="${py(p, v, base)}" x2="${DIR}" y2="${py(p, v, base)}"/>`)
    .join("");

  const { desenho, rotulos } = faixasDaRegra(p, regra, e, base);

  const refs = (p.refs || []).map((r) => `<path class="refcurva" d="${caminho(p, r.campo, base)}"/>`).join("");
  const refRots = (p.refs || []).map((r) => {
    const y = py(p, corrida[corrida.length - 1].estado[r.campo], base);
    return y < TOPO || y > base ? "" : `<text class="refrot" x="${DIR + 5}" y="${y + 3}">${r.rot}</text>`;
  }).join("");

  let ultimoY = -99;
  const rots = rotulos.sort((a, b) => a.y - b.y).map((r) => {
    let y = Math.max(TOPO + 9, Math.min(base - 4, r.y - 4));
    if (y - ultimoY < 11) y = ultimoY + 11;
    ultimoY = y;
    return `<text class="rotfaixa ${r.classe}" x="${ESQ + 6}" y="${y}">${esc(r.txt)}</text>`;
  }).join("");

  const cx = px(amostra.t), cy = py(p, e[p.campo], base);
  const eixo = ultimo
    ? [0, 200, 400, 600, 800, 1000, 1200, 1400].filter((t) => t <= tmax).map((t) =>
        `<text class="eixot" x="${px(t)}" y="${base + 16}">${t}</text>`).join("") +
      `<text class="eixot" x="${(ESQ + DIR) / 2}" y="${base + 29}">tempo simulado (minutos)</text>`
    : "";

  return `<div class="painel">
    <div class="rot">
      <span class="nome">${p.nome}</span>
      <span class="val" title="${exato(e[p.campo])}">${interface_(e[p.campo], p.casas)}</span>
      <span class="uni">${p.unidade}</span>
      ${p.campo === "PosicaoBarra"
        ? `<span class="refval">LI=${interface_(e.LimiteInsercao, 0)} · BD=${interface_(e.BD, 0)}</span>`
        : ""}
    </div>
    <svg viewBox="0 0 1030 ${ALT}" role="img" aria-label="${p.nome} no tempo">
      <defs><clipPath id="rec-${p.campo}">
        <rect x="${ESQ}" y="${TOPO}" width="${DIR - ESQ}" height="${base - TOPO}"/>
      </clipPath></defs>
      ${grade}${fracos}
      <g clip-path="url(#rec-${p.campo})">
        ${desenho}${refs}
        <path class="curva" d="${caminho(p, p.campo, base)}"/>
      </g>
      <line class="eixo" x1="${ESQ}" y1="${base}" x2="${DIR}" y2="${base}"/>
      <line class="cursor" x1="${cx}" y1="${TOPO}" x2="${cx}" y2="${base}"/>
      <circle class="ponto" cx="${cx}" cy="${cy}" r="3"/>
      ${refRots}${rots}${eixo}
    </svg>
  </div>`;
}

/**
 * @param alvo        onde desenhar
 * @param amostra     {t, estado, disparadas}
 * @param regra       a regra selecionada (ou null)
 * @param fracos      Map campo -> limiares que esta corrida alcança
 */
export function desenha(alvo, amostra, regra, fracos) {
  const uteis = PAINEIS.filter((p) => dom.has(p.campo));
  alvo.innerHTML = uteis
    .map((p, i) => painel(p, amostra, i === uteis.length - 1, regra, fracos))
    .join("") + semPainel(regra, uteis);
}

/** Nem toda grandeza testada tem painel: `VariacaoDeltaI`, de R1 e R2, não é uma
 *  das cinco. O termo existe e vale — some do desenho, não do texto. */
function semPainel(regra, uteis) {
  if (!regra) return "";
  const campos = new Set(uteis.map((p) => p.campo));
  const fora = [];
  for (const t of termosDe(regra.condicao).concat(termosDe(regra.guarda_do_bloco || ""))) {
    const c = comparacao(t.texto);
    if (!c || campos.has(c.campo)) continue;
    const marca = t.ramo ? `${regra.id}·${t.ramo}` : regra.id;
    fora.push(`${marca}: ${esc(t.texto)}`);
  }
  return fora.length
    ? `<p class="sem-painel">sem painel próprio, mas parte da condição: ${fora.join(" · ")}</p>`
    : "";
}

/** Os limiares fixos que as regras alcançadas por ESTA corrida citam. */
export function limiaresFracos(base, disparadasNaCorrida) {
  const m = new Map();
  for (const r of base) {
    if (!disparadasNaCorrida.has(r.id)) continue;
    for (const t of termosDe(r.condicao).concat(termosDe(r.guarda_do_bloco || ""))) {
      const c = comparacao(t.texto);
      if (!c || c.fixo === undefined) continue;
      if (!m.has(c.campo)) m.set(c.campo, new Set());
      m.get(c.campo).add(c.fixo);
    }
  }
  return new Map([...m].map(([k, v]) => [k, [...v]]));
}
