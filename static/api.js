// api.js — as quatro chamadas que a tela faz, e uma so promessa: se algo falhar,
// isto LEVANTA. Nunca devolve um valor de consolacao.
//
// O frontend anterior tratava erro do expert como "sem acao": a simulacao seguia
// com o controle desligado e ninguem percebia. Aqui, qualquer resposta que nao
// seja 2xx vira `ErroDeServico`, quem chamou para a corrida, e a barra vermelha
// aparece (PRD §2).
//
// O navegador fala com UM servico so, o expert. Nunca com o reactor: quem chama
// o reactor e o expert, por dentro da rede dos conteineres. Por isso as URLs sao
// relativas a origem desta pagina — e por isso `reactor_url` NAO e enviado no
// corpo de /initialize (o padrao do servico, `http://reactor-simulator:8008`, so
// resolve la dentro; o navegador nao alcanca esse nome e nao precisa).

export class ErroDeServico extends Error {
  constructor(mensagem, { onde, status = null, corpo = "" } = {}) {
    super(mensagem);
    this.name = "ErroDeServico";
    this.onde = onde;
    this.status = status;
    this.corpo = corpo;
  }
}

async function chama(metodo, caminho, corpo) {
  let r;
  try {
    r = await fetch(caminho, {
      method: metodo,
      headers: corpo === undefined ? {} : { "content-type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch (e) {
    // Rede caiu, servico fora do ar, origem errada. Nao ha resposta nenhuma.
    throw new ErroDeServico(`não foi possível falar com o expert (${e.message})`, {
      onde: `${metodo} ${caminho}`,
    });
  }
  const texto = await r.text();
  if (!r.ok) {
    throw new ErroDeServico(`o expert respondeu ${r.status}`, {
      onde: `${metodo} ${caminho}`,
      status: r.status,
      corpo: texto.slice(0, 500),
    });
  }
  return texto ? JSON.parse(texto) : null;
}

/** A base inteira, uma vez, na partida. E a mesma coisa que decide — nao uma
 *  documentacao paralela que pode envelhecer. */
export const regras = () => chama("GET", "/expert/regras");

/** Abre a sessao. `params` vem de cenarios.json; `tmax` tem de ir SEMPRE, porque
 *  o padrao do servico e 700000 e `{}` roda o ciclo completo, nao o cenario 1. */
export const iniciar = (params) => chama("POST", "/expert/initialize", params);

/** Avanca um minuto simulado e devolve estado, disparadas e os bytes impressos. */
export const ciclo = (sid) => chama("POST", `/expert/${sid}/ciclo`, {});

/** Fecha a sessao. O servico guarda no maximo 32; deixar sessao aberta a cada
 *  clique em Rodar esgota o registro. */
export const encerrar = (sid) => chama("DELETE", `/expert/${sid}`);
