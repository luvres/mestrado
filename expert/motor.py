#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motor.py — o motor de inferencia: onde mora a estrategia de resolucao de conflito.

regras.py diz O QUE sao as 19 regras. Este modulo diz COMO elas sao aplicadas, e
essa e a decisao que steps/03-regras-controle.md §5.1 exigiu que fosse tomada
deliberadamente:

    "Os 19 blocos sao testados em sequencia fixa, e varios podem disparar no
     mesmo minuto; cada um enxerga o estado que o anterior deixou. Um motor de
     inferencia classico — casa todas, dispara UMA, recomeca — nao reproduz
     isso. A estrategia tem de ser escolhida: prioridade = ordem do fonte,
     disparo multiplo por ciclo."

E o que este motor faz, e ele faz so isso. As tres consequencias:

  1. PRIORIDADE = ORDEM. Nao ha pontuacao, especificidade nem recencia. A ordem
     de leitura de regras.BASE e a ordem de avaliacao, e e a ordem do fonte.

  2. DISPARO MULTIPLO. Nao se para na primeira que casa. Todas as 19 sao
     testadas, todo ciclo.

  3. ESTADO RELIDO A CADA REGRA. Depois de cada atuacao o estado e relido da
     planta, porque a regra seguinte tem de ver o que a anterior deixou. E por
     isso que a API do reator e de acao, e nao de ciclo.

A guarda e do BLOCO, avaliada uma vez na entrada. Se R1 dilui e DeltaT sobe
acima de -0,1, R2, R3 e R4 ainda sao avaliadas — o fonte nao reavalia a guarda.

Tres variaveis do lado do controle sobrevivem entre regras e entre ciclos, como
as globais do .c: Vazao, VazaoBoro e Vboro. Vazao importa: se nenhuma das tres
faixas casasse, o fonte usaria a vazao da diluicao anterior.
"""

from observacao import espaco
from regras import BASE
from saida import printf, putc_raw, tamanho

# O bloco de estado que R17, R18 e R19 imprimem. Identico nas tres, por isso
# esta aqui; o que e dado da regra e SE ele sai (Alarmar.despejo) — os alarmes
# de limite de insercao de R11 e R12 imprimem so a linha, sem despejo.
_DESPEJO = (("\n\n\nt=%.0f", "t"), ("\nZ=%d", "z"), ("\nPot=%.2f", "Pot"),
            ("\nTmed=%.1f", "Tmed"), ("\nTref=%.1f", "Tref"),
            ("\nAlvo DeltaI=%f", "AlvoDeltaI"), ("\nDeltaI=%f", "DeltaI"),
            ("\nDesvioDeltaI=%f", "DesvioDeltaI"),
            ("\nVariacaoDeltaI=%f", "VariacaoDeltaI"),
            ("\nPosicao Barra=%d", "PosicaoBarra"), ("\nCboro=%f\n\n\n", "Cboro"))


class Motor:
    """Aplica uma base de regras a uma planta.

    `planta` e qualquer objeto com estado(), tipos(), passo(), diluir(),
    borar() e mover_barra() — a interface que reactor/main.py publica. O motor
    nao sabe se ela esta atras de HTTP ou no mesmo processo.
    """

    def __init__(self, planta, base=BASE):
        self.planta = planta
        self.base = base
        self.termino = ""
        self.disparos = {}          # id da regra -> quantas vezes disparou
        self.ciclos = 0
        # Globais do lado do controle, preservadas entre ciclos como no .c.
        self.Vazao = None
        self.VazaoBoro = None
        self.Vboro = None

    # -- leitura ---------------------------------------------------------

    def ve(self):
        return espaco(self.planta.estado(), self.planta.tipos())

    # -- um minuto -------------------------------------------------------

    def ciclo(self):
        """A planta avanca um minuto, depois as 19 regras na ordem do fonte.

        Devolve os ids das regras que dispararam, na ordem em que dispararam.
        """
        self.planta.passo()
        self.ciclos += 1
        disparadas = []

        for bloco in self.base:
            if bloco.guarda is not None and not bloco.guarda(self.ve()):
                continue
            for regra in bloco.regras:
                e = self.ve()
                if not regra.condicao(e):
                    continue
                disparadas.append(regra.id)
                self.disparos[regra.id] = self.disparos.get(regra.id, 0) + 1
                self._dispara(regra, e)
        return disparadas

    def _dispara(self, regra, e):
        for efeito in regra.efeitos:
            # Consequente partido (steps/03 §5.4): em R11 e R12 o alarme sai com
            # a condicao externa e a boracao so com ela E DeltaI<0.
            if efeito.quando is not None and not efeito.quando(e):
                continue
            getattr(self, "_" + efeito.tipo)(efeito, e)
            e = self.ve()          # o efeito mexeu na planta

    # -- os quatro consequentes -----------------------------------------

    def _diluir(self, efeito, e):
        # As tres faixas sao testadas em sequencia, sem `else`: e o que o fonte
        # faz (L722, 727, 732). Sao exaustivas e exclusivas para t1 > t2, mas o
        # motor nao supoe isso — so repete a sequencia.
        for condicao, vazao in efeito.faixas:
            if condicao is None or condicao(e):
                self.Vazao = vazao(e)
                printf("\n\nDeltaT: %f\n\n", e["DeltaT"])
                printf(efeito.texto, self.Vazao)
        self.planta.diluir(self.Vazao)

    def _borar(self, efeito, e):
        self.VazaoBoro = efeito.vazao(e)
        if efeito.satura is not None and self.VazaoBoro > efeito.satura:
            self.VazaoBoro = type(self.VazaoBoro)(efeito.satura)
        # Vboro e calculado sobre o VazaoBoro JA SATURADO, e o arredondamento a
        # 32 bits do produto tem de acontecer aqui, nao na planta.
        self.Vboro = efeito.volume(dict(e, VazaoBoro=self.VazaoBoro))
        printf(efeito.texto)
        self.planta.borar(self.VazaoBoro, self.Vboro)

    def _barra(self, efeito, e):
        printf(efeito.texto)
        printf("\n\nPosicao Anterior do Banco D: %d passos", e["PosicaoBarra"])
        passos = None
        for condicao, quantos in efeito.passos:
            # Aqui HA `else` (R9 escolhe -1 ou -2), entao para na primeira.
            if condicao is None or condicao(e):
                passos = int(quantos(e))
                break
        printf("\n\nPosicao Atual do Banco D: %d passos\n", e["PosicaoBarra"] + passos)
        self.planta.mover_barra(passos)

    def _alarme(self, efeito, e):
        for formato, grandeza in efeito.cabecalho:
            if grandeza is None:
                printf(formato)
            else:
                printf(formato, e[grandeza])
        i = 0
        while i < efeito.enche:
            putc_raw(b'\xb1')      # printf("%c",177): UM byte, nao UTF-8
            i = i + 1
        if efeito.despejo:
            for formato, grandeza in _DESPEJO:
                printf(formato, e[grandeza])
        if efeito.encerra:
            self.termino = "fim"

    # -- a corrida -------------------------------------------------------

    def pode_continuar(self):
        """A condicao do laco do .c, inteira: a metade da planta (t < tmax) mais
        a metade do controle (termino != "fim", posta por R19)."""
        return self.termino != "fim" and self.planta.pode_continuar()

    def executa(self, max_ciclos=None, max_bytes=None):
        """Roda ate o fim de ciclo, o horizonte, `max_ciclos` ou `max_bytes`.

        `max_bytes` existe porque o numero de ciclos nao mede a memoria. No fim
        do ciclo de queima as diluicoes ficam frequentes — R1 dispara quase 6 mil
        vezes na corrida completa — e um pedaco de 20 mil ciclos que custava
        ~18 MB no comeco custa varias vezes isso no fim. Sem um teto em BYTES, um
        cliente pedindo muitos ciclos derruba o servico por memoria, e a corrida
        aparece como divergencia.
        """
        n = 0
        while self.pode_continuar():
            if max_ciclos is not None and n >= max_ciclos:
                break
            if max_bytes is not None and tamanho() >= max_bytes:
                break
            self.ciclo()
            n = n + 1
        if self.termino == "fim" or not self.planta.pode_continuar():
            printf("\n\nFim do Programa\n\n")
        return n
