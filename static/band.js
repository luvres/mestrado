// band.js — as 19 regras empilhadas, com uma marca onde cada uma disparou.
//
// E a unica visualizacao que mostra a base FUNCIONANDO COMO BASE DE REGRAS
// (PRD §4.3): densidades diferentes, regras que nunca acendem, o padrao mudando
// durante o transiente. E a tabela de results/RESUMO.md, alinhada no tempo.
//
// TIQUES, NAO BLOCOS — e a §7.3 do PRD continua em aberto.
//
//   Uma diluicao consome 22 minutos simulados, uma boracao 18, uma barra 2, e
//   blocos com essas larguras seriam mais fieis. Duas saidas foram consideradas,
//   e nenhuma serve por enquanto:
//
//     escrever 22/18/2 aqui  — copia para o cliente um pedaco do modelo, que e
//                              justamente o que o §6.2 proibe;
//     medir pelo salto do t  — TENTADO E ERRADO. O intervalo ate a amostra
//                              seguinte nao e a duracao da acao: em regime, o
//                              simulador so volta a imprimir a cada ~47 minutos,
//                              e um movimento de barra de 2 minutos virava um
//                              bloco de 47.
//
//   Entao o disparo e um tique no minuto em que aconteceu, e o intervalo ate a
//   amostra seguinte fica no `title`, onde nao mente sobre largura. Desenhar
//   duracao de verdade exige a API dizer quanto durou a acao — e o mesmo tipo de
//   pedido do §5.5.

import { CALHA } from "./panels.js";

/** Cor por tipo de efeito, para a faixa dizer que acao foi tomada. */
function tipoDaRegra(regra) {
  const tipos = (regra.efeitos || []).map((e) => e.tipo);
  for (const t of ["diluir", "borar", "barra", "alarme"]) if (tipos.includes(t)) return t;
  return "outro";
}

export function monta(alvo, base) {
  alvo.innerHTML = base
    .map(
      (r) => `<span class="rrot" id="rot-${r.id}" title="${r.descricao}">${r.id}</span>
              <div class="rlinha" id="linha-${r.id}"></div>`
    )
    .join("");
}

/**
 * @param {Array} base as 19 regras
 * @param {Array} corrida amostras {t, disparadas}
 * @param {number} tmax horizonte, para a escala horizontal
 */
export function pinta(base, corrida, tmax) {
  const porRegra = new Map(base.map((r) => [r.id, []]));
  corrida.forEach((amostra, i) => {
    const fim = i + 1 < corrida.length ? corrida[i + 1].t : amostra.t + 1;
    for (const id of amostra.disparadas) {
      if (porRegra.has(id)) porRegra.get(id).push([amostra.t, fim]);
    }
  });

  for (const r of base) {
    const intervalos = porRegra.get(r.id);
    const linha = document.getElementById(`linha-${r.id}`);
    const tipo = tipoDaRegra(r);
    linha.innerHTML = intervalos
      .map(([a, b]) => {
        const esq = CALHA.esq + (a / tmax) * CALHA.larg;
        return `<span class="bloco b-${tipo}" style="left:${esq}%"
                 title="${r.id} · disparou no minuto ${a} · próxima amostra em ${b} (${b - a} min depois)"></span>`;
      })
      .join("");
    const rot = document.getElementById(`rot-${r.id}`);
    const morta = intervalos.length === 0;
    // Linha fina para quem não dispara: some da conta de altura sem sumir da
    // tela. Que 11 das 19 nunca acendam neste cenário é parte do que a faixa diz.
    rot.classList.toggle("morta", morta);
    linha.classList.toggle("morta", morta);
    rot.title = `${r.descricao} — ${intervalos.length} disparo(s)`;
  }
}

/** Acende os rotulos das regras que estao disparadas no minuto do cursor. */
export function acende(base, acesas) {
  for (const r of base) {
    document.getElementById(`rot-${r.id}`).classList.toggle("aceso", acesas.includes(r.id));
  }
}

export const LEGENDA = [
  ["diluir", "diluição"],
  ["borar", "boração"],
  ["barra", "movimento de barra"],
  ["alarme", "alarme"],
];
