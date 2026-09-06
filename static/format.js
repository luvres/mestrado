// formato.js — como um numero vira texto.
//
// Duas regras, e elas nao sao a mesma:
//
//   `interface(x)` usa VIRGULA, porque a tela e em portugues;
//   `fonte(x)`     usa PONTO, porque o texto onde o numero e substituido e o
//                  texto literal do fonte C, e os literais dele sao `0.6`,
//                  `-2.2`, `222`. Escrever `5,16>0.6` misturaria os dois
//                  mundos numa linha so — foi um dos achados registrados no
//                  PRD §3.1.
//
// Nos dois casos as casas decimais sao PODADAS: `0,720` deixa um zero a toa, e
// a agulha do medidor fica mentindo precisao que o numero nao tem.

/** Poda zeros finais e o separador solto. */
function poda(s) {
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
}

/** Quantas casas fazem sentido para esta grandeza. Inteiro fica inteiro. */
function casas(x, max = 2) {
  if (Number.isInteger(x)) return 0;
  return Math.abs(x) >= 100 ? Math.min(1, max) : max;
}

/** Para a tela: virgula. */
export function interface_(x, max = 2) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return poda(Number(x).toFixed(casas(x, max))).replace(".", ",");
}

/** Para dentro da condicao: ponto, como no .c. */
export function fonte(x, max = 2) {
  if (x === null || x === undefined || Number.isNaN(x)) return "?";
  return poda(Number(x).toFixed(casas(x, max)));
}

/** O valor inteiro, sem arredondar — vai no `title`, para quem quiser conferir
 *  que a aritmetica de 32 bits nao foi maquiada. */
export function exato(x) {
  return String(x);
}
