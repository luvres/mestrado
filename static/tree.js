// tree.js — a estrutura booleana do antecedente, e nada além disso.
//
// POR QUE ISTO EXISTE
//
//     A primeira versão desenhava uma faixa por comparação e chamava todas de
//     "termo da conjunção". Nove das dezenove condições têm `||` — R1, R2, R3,
//     R5, R7, R8, R9, R17 e R18 —, e nelas a tela afirmava algo falso: pintava
//     `PosicaoBarra>=222` como região a satisfazer enquanto a barra estava em
//     194 e a regra tinha disparado assim mesmo, por outro ramo do `ou`.
//
//     Então o desenho precisa da ÁRVORE, não da lista de comparações.
//
// O QUE ISTO **NÃO** FAZ: avaliar.
//
//     `comparacao()` devolve campo, operador e o outro lado. Nunca compara. Um
//     `194 >= 222` calculado aqui seria decidir de novo, em `double`, o que o
//     expert decidiu em float de 32 bits — e num caso de fronteira os dois
//     discordariam, deixando a tela mostrar "falso" ao lado da regra acesa
//     (PRD §6.2). Qual ramo venceu é informação que só o motor tem; enquanto a
//     API não a reportar, a tela mostra a estrutura e cala sobre o resultado.
//
// A profundidade, depois de achatar `&&` de `&&` e `||` de `||`, nunca passa de
// dois em nenhuma das 19 — mas o percurso abaixo é recursivo de qualquer forma,
// porque nada na API promete que continuará assim.

/** Tira os parênteses que envolvem a expressão inteira. */
function desembrulha(t) {
  t = t.trim();
  while (t.startsWith("(") && t.endsWith(")")) {
    let prof = 0, envolve = true;
    for (let i = 0; i < t.length; i++) {
      prof += (t[i] === "(") - (t[i] === ")");
      if (prof === 0 && i < t.length - 1) { envolve = false; break; }
    }
    if (!envolve) break;
    t = t.slice(1, -1).trim();
  }
  return t;
}

/**
 * Quebra a condição em árvore. `||` liga mais fraco que `&&`, então quebra antes.
 * @returns {{op:"&&"|"||", filhos:Array}|{termo:string}}
 */
export function arvore(texto) {
  const t = desembrulha(texto || "");
  for (const op of ["||", "&&"]) {
    const partes = [];
    let prof = 0, atual = "", achou = false;
    for (let i = 0; i < t.length; i++) {
      prof += (t[i] === "(") - (t[i] === ")");
      if (prof === 0 && t.slice(i, i + 2) === op) {
        partes.push(atual); atual = ""; achou = true; i += 1; continue;
      }
      atual += t[i];
    }
    partes.push(atual);
    if (achou) {
      const filhos = [];
      for (const p of partes) {
        const f = arvore(p);
        // achata: `a && (b && c)` é a mesma conjunção de três
        if (f.op === op) filhos.push(...f.filhos); else filhos.push(f);
      }
      return { op, filhos };
    }
  }
  return { termo: t };
}

const LETRAS = "ABCDEFGH";

/**
 * Percorre a árvore e classifica cada folha.
 *
 *   obrigatorio  a folha só tem `&&` no caminho até a raiz. Como a regra
 *                disparou, ela É verdadeira — e a faixa pode ser cheia.
 *   ramo         a folha está sob algum `||`. Recebe a letra do ramo: mesma
 *                letra significa "estes valem juntos"; letras diferentes são
 *                alternativas, e basta uma. Qual delas, a tela não diz.
 */
export function folhas(no, obrigatorio = true, ramo = null, saida = []) {
  if (no.termo !== undefined) {
    saida.push({ texto: no.termo, obrigatorio, ramo });
    return saida;
  }
  if (no.op === "&&") {
    for (const f of no.filhos) folhas(f, obrigatorio, ramo, saida);
  } else {
    no.filhos.forEach((f, i) => {
      const letra = ramo ? `${ramo}${i + 1}` : LETRAS[i] || String(i + 1);
      folhas(f, false, letra, saida);
    });
  }
  return saida;
}

/** As folhas de uma condição, já classificadas. */
export const termosDe = (condicao) => folhas(arvore(condicao));

/** Uma comparação: campo, operador, e o outro lado — fixo ou móvel. */
const CMP = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*(.+?)\s*$/;
const DESLOCADO = /^\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*([+-])\s*(\d+(?:\.\d+)?)\s*\)$/;

export function comparacao(texto) {
  const m = (texto || "").match(CMP);
  if (!m) return null;
  const [, campo, op, dir] = m;
  const n = Number(dir);
  if (!Number.isNaN(n)) return { campo, op, fixo: n, rot: dir };
  const d = dir.match(DESLOCADO);
  if (d) return { campo, op, ref: d[1], desloca: (d[2] === "-" ? -1 : 1) * Number(d[3]),
                  rot: `${d[1]}${d[2]}${d[3]}` };
  if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(dir) && dir !== campo)
    return { campo, op, ref: dir, desloca: 0, rot: dir };
  return null;
}

/** O valor da comparação NESTE minuto — móvel depende do estado. */
export const valorDe = (c, estado) =>
  c.fixo !== undefined ? c.fixo : estado[c.ref] + c.desloca;
