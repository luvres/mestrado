// rule.js — a regra explicada, com os valores substituidos.
//
// Se a demonstracao inteira tivesse de caber num so elemento, seria este
// (PRD §4.2). O texto da condicao vem do expert, os valores vem do estado, a
// procedencia vem de `linha_c`.
//
// UMA COISA QUE ESTA TELA NAO FAZ: avaliar a expressao.
//
//   O veredito "verdadeira" nao e calculado aqui. Ele e um FATO REPORTADO: a
//   regra esta em `disparadas`, entao o motor do expert — que le o estado a cada
//   atuacao, na ordem do fonte — decidiu que ela e verdadeira. Reavaliar a
//   condicao em JavaScript seria a quinta copia da logica de decisao (§6.1) e,
//   pior, uma copia em double contra uma decisao tomada em float de 32 bits: a
//   tela acabaria mostrando "falsa" ao lado da regra acesa.
//
// A substituicao abaixo e, portanto, TIPOGRAFIA — troca o nome do campo pelo
// numero que ele tinha — e nao aritmetica.

import { fonte, exato } from "./format.js";

/** Um identificador so vira numero se for campo do estado; `t1`, `v2`, `a` e `b`
 *  tambem sao, e e por isso que as faixas de vazao de R1 aparecem preenchidas. */
function substitui(texto, estado) {
  return texto.replace(/\b[A-Za-z_][A-Za-z0-9_]*\b/g, (nome) => {
    const v = estado[nome];
    if (v === undefined || typeof v !== "number") return nome;
    return `<span class="sub" title="${nome} = ${exato(v)}">${fonte(v)}</span>`;
  });
}

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");

/** O consequente: o que a regra faz, e com que formula. */
function consequente(regra, estado) {
  const partes = [];
  for (const ef of regra.efeitos || []) {
    const d = ef.detalhe || {};
    const linhas = [];
    if (ef.quando) {
      linhas.push(`<div><span class="q">quando</span> ${esc(ef.quando)} → ${substitui(esc(ef.quando), estado)}</div>`);
    }
    for (const f of d.faixas || []) {
      linhas.push(`<div><span class="q">${esc(f.quando)}</span> → vazão ${esc(f.vazao)}
        = ${substitui(esc(f.vazao), estado)} lpm</div>`);
    }
    for (const p of d.passos || []) {
      linhas.push(`<div><span class="q">${esc(p.quando)}</span> → ${esc(p.passos)} passo(s)</div>`);
    }
    partes.push(`<details class="secao consequente"><summary>consequente — ${esc(ef.tipo)}</summary>
      <div class="faixas">${linhas.join("") || "<div>sem parametrização</div>"}</div>
      ${(d.faixas || []).length > 1 || (d.passos || []).length > 1
        ? `<div class="lacuna"><b>§5.5:</b> qual fórmula venceu, e portanto quanto saiu de
             fato, <b>a resposta do ciclo não informa</b>.</div>`
        : ""}
    </details>`);
  }
  return partes.join("");
}

export function desenha(alvo, regra, estado, saida) {
  if (!regra) {
    alvo.innerHTML = `<div class="vazio">Nenhuma regra disparou neste minuto —
      o expert percorreu as 19 e nenhuma condição foi verdadeira.</div>`;
    return;
  }
  const cond = esc(regra.condicao);
  alvo.innerHTML = `
    <div class="regracab">
      <span class="regraid">${regra.id}</span>
      <span class="regradesc">${esc(regra.descricao)}</span>
      <span class="etiq">bloco ${esc(regra.bloco)}</span>
      <span class="etiq">ordem ${regra.prioridade}/19</span>
    </div>
    ${regra.guarda_do_bloco
      ? `<div class="guarda">guarda do bloco: ${esc(regra.guarda_do_bloco)}
           → ${substitui(esc(regra.guarda_do_bloco), estado)}</div>`
      : ""}
    <div class="cond lit">${cond}</div>
    <div class="cond">${substitui(cond, estado)} &nbsp;→&nbsp;
      <span class="veredito">verdadeira</span></div>
    <div class="linha-c">
      fonte: V8_Reatividade_SimuladorIgor_linux.c:${regra.linha_c} &nbsp;·&nbsp;
      texto de <b>GET /expert/regras</b>, campo <b>condicao</b> — não é paráfrase.
      O veredito é o disparo relatado pelo expert; a tela não reavalia a expressão.
    </div>
    ${consequente(regra, estado)}
    <details class="console">
      <summary>console deste minuto — <code>saida_b64</code>, decodificado</summary>
      <pre>${esc(saida || "(nada impresso)")}</pre>
    </details>`;
}
