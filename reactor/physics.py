#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
physics.py — o modelo da planta, sem nenhuma regra de controle.

FRONTEIRA (a razao de existir deste arquivo)

    Este modulo sabe o que o reator FAZ; nao sabe o que se DEVE fazer com ele.
    As 19 regras levantadas em steps/03-regras-controle.md ficam todas do outro
    lado da API, no servico expert. Aqui nao existe nenhum `if` que decida
    diluir, borar ou mover barra: existem so os efeitos dessas acoes.

    O corte foi feito regra a regra, e cai sempre no mesmo lugar:

      - O ANTECEDENTE (a condicao) e do expert, sempre.
      - A PARAMETRIZACAO do consequente e do expert: quanta vazao de diluicao
        (faixas de DeltaT com v1/v2/rampa), quanto volume de boro, quantos
        passos de barra. Sao decisoes de controle — steps/03 §4 as classifica
        como "escolhem *quanto*, nao *se*".
      - O TEXTO especifico da regra e do expert. R1 imprime "Iniciada a
        Diluicao..." e R5 imprime "Iniciada a Correcao do Delta I por
        Diluicao..." para a mesma acao de planta; o texto identifica a regra,
        nao o efeito. Idem "Posicao Anterior/Atual do Banco D", que o expert
        imprime antes de chamar mover_barra() — por isso a ordem da saida
        remontada continua a do fonte.
      - O EFEITO e daqui: mistura de boro, homogeneizacao termica, redistribuicao
        de potencia entre topo e base, oscilacao de Xe/I, avanco do relogio.

    Consequencia pratica: as regras nao sao atomicas (steps/03 §5.1) — cada uma
    ve o estado que a anterior deixou. Por isso a API e de granularidade de
    ACAO, e nao de ciclo: o expert avalia R1, aplica, recebe o estado novo,
    avalia R2 sobre ele, e assim por diante. Um endpoint que recebesse as 19
    decisoes de uma vez nao reproduziria o fonte.

O QUE E COPIA LITERAL

    Tudo abaixo do marcador "bloco copiado" e transcricao byte a byte de
    simulador.py, o porte provado identico ao C no Passo 2:

        sed -n '262,291p' simulador.py   declaracoes + __setattr__
        sed -n '331,384p' simulador.py   AplicaRunback/Rampa/TransienteAuto
        sed -n '460,848p' simulador.py   modelo do nucleo + os 6 atuadores

    Nao editar aqui: editar em simulador.py e reextrair. tests/test_genealogia.py
    compara os blocos byte a byte e falha se divergirem.

DIFERENCAS DELIBERADAS EM RELACAO AO simulador.py

  - WIN_ORIGINAL era global de ambiente; virou self.win_original, por sessao.
  - O nome do arquivo de amostras virou self.arquivo, por sessao.
  - GravaDados levanta excecao em vez de sys.exit(1): um servico nao morre
    porque uma sessao nao conseguiu abrir arquivo.
  - VariacaodeCarga() e o bloco kbhit() do laco nao foram trazidos: kbhit() e
    fixo em 0 nos dois portes, o bloco e codigo morto (steps/03 §4) e um servico
    HTTP nao tem stdin. Os dois caminhos que ele alimentava — runback e rampa —
    entram por AplicaTransienteAuto(), que foi trazida.
  - `termino` nao existe aqui: quem declara fim de ciclo e R19, do lado do
    expert. A planta so informa t e tmax; quem fecha a malha decide parar.
"""

import math

from f32 import F, _para_int
from saida import printf

# Tipos de transiente de carga — mesmos valores de simulador.py.
TR_NENHUM = 0
TR_RUNBACK_BAP = 1     # desarme da bomba de agua de alimentacao principal -> 300 MW
TR_RUNBACK_CIRC = 2    # desarme da bomba de agua de circulacao -> 400 MW
TR_RUNBACK_400 = 3
TR_RUNBACK_300 = 4
TR_RUNBACK_150 = 5
TR_RAMPA = 6           # variacao lenta: alvo=<MW>, taxa=<MW/min>

TRANSIENTES = {
    "runback-bap": TR_RUNBACK_BAP,
    "runback-circ": TR_RUNBACK_CIRC,
    "runback-400": TR_RUNBACK_400,
    "runback-300": TR_RUNBACK_300,
    "runback-150": TR_RUNBACK_150,
    "rampa": TR_RAMPA,
}

ARQUIVO_PADRAO = "Modelagem_Reator_api.txt"

CABECALHO_AMOSTRAS = (
    "Tempo    Pot Rx    Pot Turbina     Tmed   Delta I  Cboro  Banco D"
    "  Volume de Água\n\n\n"
)


class ErroDeGravacao(RuntimeError):
    """simulador.py faz sys.exit(1); um servico nao pode."""


class Planta:
    """O reator: estado fisico e os efeitos das tres alavancas de reatividade."""

    # --- inicio do bloco copiado de simulador.py (linhas 262-291) ----------

    _FLOAT = frozenset("""
        Tref Tmedantes Tmed VariacaoTmed DeltaIantes DeltaI AlvoDeltaI
        DesvioDeltaI VariacaoDeltaI Cboro Cboro1 DeltaT Vazao Vagua VaguaTemp
        t1 t2 v1 v2 a b t ty valor razao Msrr alfaboro alfamoderador thom
        betaeff Ptopo Ptopo0 Pbase Pbase0 Pbase1 erazao Deltaro Trx lambda_
        inversoTrx DeltaPbase DeltaPtopo Pot taxatempreal y Vboro VazaoBoro
        LimiteInsercao ConvertXe_Ro Ro RoAntes PbaseAntes PotAntes erro
        DefPotAntes DefPot PotAlvo AlvoTurbina AlvoTref TaxaTurbina ModuloTref
        ModuloTaxa PotTurbina PotTurbinaTemp argAlvo argTaxa
    """.split())

    _INT = frozenset("""
        PosicaoBarra DeltaBarra tempo Retira1passo correcao aux i tempodilute
        x diferenca taxatemp z tXe BD Runbackmanual
        transienteTipo tTransiente transienteAplicado
    """.split())

    _DOUBLE = frozenset("""
        tmax Nxeb Nxeg Nxe0 Nxeg0 NxeAntes lambdaXe sigmaXe Fnb Fnb0 Fng Fng0
        gamaI Sigmaf gamaXe lambdaI Ni0 Nig0 Nib Nig
    """.split())

    def __setattr__(self, nome, v):
        if nome in self._FLOAT:
            v = F(v)
        elif nome in self._INT:
            v = _para_int(v)
        elif nome in self._DOUBLE:
            v = float(v)
        object.__setattr__(self, nome, v)

    # --- fim do bloco copiado ---------------------------------------------

    def __init__(self, arquivo=ARQUIVO_PADRAO, win_original=False):
        # Fora dos tres conjuntos: nao passam por __setattr__, sao da sessao.
        self.arquivo = arquivo
        self.win_original = win_original
        # Variaveis globais do C: duracao estatica, zero-inicializadas.
        for nome in self._FLOAT:
            setattr(self, nome, 0)
        for nome in self._INT:
            setattr(self, nome, 0)
        for nome in self._DOUBLE:
            setattr(self, nome, 0)
        # Inicializadores explicitos do .c
        self.transienteTipo = TR_NENHUM
        self.tTransiente = 10        # minuto de aplicacao do transiente
        self.transienteAplicado = 0
        self.tmax = 700000           # limite de horizonte da simulacao (minutos)

    # =======================================================================
    # Gravacao das amostras
    # =======================================================================

    def GravaDados(self):
        try:
            arquivo = open(self.arquivo, "a", encoding="utf-8")
        except OSError as e:
            printf("Problemas na abertura do arquivo!\n")
            raise ErroDeGravacao(str(e))
        else:
            arquivo.write("%.0f       %.2f     %.1f          %.1f      %.3f"
                          "        %.0f       %d     %.0f\n"
                          % (self.t, self.Pot, self.PotTurbina, self.Tmed,
                             self.DeltaI, self.Cboro, self.PosicaoBarra,
                             self.VaguaTemp))
        arquivo.close()
        return

    # =======================================================================
    # Interface do servico — partida
    # =======================================================================

    def inicializa(self, pot_turbina, cboro, posicao_barra, tempodilute,
                   t1, t2, delta_i, tmax=700000, transiente=TR_NENHUM,
                   t_transiente=10, alvo=0.0, taxa=0.0, truncar=True):
        """Prologo de main(): os 7 valores do operador e os derivados de Cboro.

        Os printf() de prompt ("Digite a Potencia Inicial...") foram mantidos na
        mesma ordem e com o mesmo texto, ainda que aqui nao haja teclado: a
        saida remontada tem de bater byte a byte com a do porte fiel. O que muda
        e a origem do valor — parametro em vez de scanf.
        """
        self.tmax = tmax
        self.transienteTipo = transiente
        self.tTransiente = t_transiente
        self.argAlvo = alvo
        self.argTaxa = taxa

        printf("\n\t\t\t\t\t******************************")
        printf("\n\t\t\t\t\tCONTROLE AUTOMATICO DO REATOR")
        printf("\n\t\t\t\t\t******************************\n")
        printf("\t\t\t\t\t")
        # O .c abre em append e conta com um arquivo limpo; um servico nao pode
        # contar com isso, entao a sessao trunca ao nascer. O conteudo final e o
        # mesmo — o cabecalho so e escrito uma vez, aqui.
        try:
            arquivo = open(self.arquivo, "w" if truncar else "a", encoding="utf-8")
        except OSError as e:
            printf("Problemas na abertura do arquivo!\n")
            raise ErroDeGravacao(str(e))
        else:
            arquivo.write(CABECALHO_AMOSTRAS)
        arquivo.close()
        # for(i=0; i<29; i++) {
        #     printf("%c",177); }

        printf("\n\n\nDigite a Potencia Inicial da Turbina em MW (32 a 650MW): ")
        self.PotTurbina = pot_turbina
        self.Pot = self.PotTurbina / 6.5
        self.PotAlvo = self.Pot
        self.Tref = 0.113 * self.Pot + 291.7
        self.Tmed = self.Tref
        self.AlvoTref = self.Tref
        printf("\nValor da Temperatura Media Inicial do SRR %.1f°C", self.Tmed)
        # scanf("%f",&Tmed);
        printf("\n\nDigite o Valor da Concentracao Inicial de Boro (ppm): ")
        self.Cboro = cboro
        printf("\nDigite a Posicao Inicial do Banco de Controle D (passos): ")
        self.PosicaoBarra = posicao_barra
        # printf("\nDigite o Valor do Coeficiente de Reatividade do Boro (pcm/ppm): ");
        # scanf("%f",&alfaboro);
        # printf("\nDigite o Valor do Coeficiente de Temperatura do Moderador (pcm/°C): ");
        # scanf("%f",&alfamoderador);
        printf("\nDigite o Intervalo de Tempo por Diluicao (minutos): ")
        self.tempodilute = tempodilute
        printf("\nDigite o Delta de Temperatura para a Vazao Minima (°C): ")
        self.t1 = t1
        printf("\nDigite o Delta de Temperatura para a Vazao Maxima (°C): ")
        self.t2 = t2
        # printf("\nDigite o Valor da Vazao de Diluicao Minima (lpm): ");
        # scanf("%d",&v1);
        # printf("\nDigite o Valor da Vazao de Diluicao Maxima (lpm): ");
        # scanf("%d",&v2);
        # printf("\nDigite o Valor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: ");
        # scanf("%d",&a);
        # printf("\nDigite o Valor do Coeficiente B da Equacao de Diluicao: Vazao= -A.DeltaT + B: ");
        # scanf("%d",&b);
        self.Msrr = 132440
        # printf("\nDigite o Tempo de Homogeneizacao da Massa do SRR (minutos): ");
        # scanf("%f",&thom);
        self.thom = 18
        printf("\nDigite o Delta I Inicial: ")
        self.DeltaI = delta_i
        printf("\n\nPARA INSERIR UMA VARIACAO DE CARGA DIGITE v EM QUALQUER MOMENTO DO CICLO DE OPERACAO\n\n\n")

        self.lambda_ = 0.1   # λ médio;
        self.DeltaT = self.Tmed - self.Tref
        self.t = 0
        self.x = 0
        self.y = 0
        self.ty = 0
        if self.Cboro > 800:
            self.betaeff = 594   # 594pcm no IDC
        else:
            self.betaeff = 522   # 522pcm no FDC
        self.taxatempreal = (2601 - self.Cboro) / 6.31   # (2568-Cboro)/6.4;
        self.taxatemp = self.taxatempreal                # tempo de redução de 0,1ºC
        printf("\nTaxa de Reducao de 0,1°C na Temperatura do SRR Devido a Queima: %d", self.taxatemp)
        self.alfamoderador = 0.02849 * self.Cboro - 75.02849
        printf("\nCoeficiente de Temperatura do Moderador: %f pcm/°C", self.alfamoderador)
        self.alfaboro = 0.0005363 * self.Cboro - 7.285363
        printf("\nValor do Coeficiente de Reatividade do Boro: %f pcm/ppm\n", self.alfaboro)
        self.v1 = -0.05307 * self.Cboro + 100.5307
        if self.v1 <= 0:
            self.v1 = 5
        printf("\nValor da Vazao de Diluicao Minima: %.0f lpm", self.v1)
        self.v2 = -0.24022 * self.Cboro + 452.24022
        if self.v2 <= 0:
            self.v2 = 10
        printf("\nValor da Vazao de Diluicao Maxima: %.0f lpm", self.v2)
        self.a = 2 * self.v1
        printf("\nValor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f", self.a)
        self.b = self.v1
        printf("\nValor do Coeficiente B da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f\n", self.b)

        self.TaxaTurbina = 0

        # PARAMENTROS REFERENTES AO XE NO MAIN

        self.Nxe0 = (self.Pot / 100) * 3.70461 * math.pow(10, 14)   # 3.70461*pow(10,14);
        self.Nxeb = self.Nxe0
        self.Nxeg = self.Nxe0
        self.Nxeg0 = self.Nxe0
        self.Ni0 = (self.Pot / 100) * 9.589 * math.pow(10, 14)      # 9.589*pow(10,14);
        self.Nib = self.Ni0
        self.Nig = self.Ni0
        self.Nig0 = self.Ni0
        self.lambdaXe = 2.116 * math.pow(10, -5)
        self.sigmaXe = 2.6 * math.pow(10, -18)
        self.gamaI = 0.056
        self.Sigmaf = 0.01
        self.gamaXe = 0.056
        self.lambdaI = 2.92 * math.pow(10, -5)
        self.ConvertXe_Ro = -6.8636 * math.pow(10, -12)

        self.lambda_ = 0.1
        self.betaeff = 594

        self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
        self.Pbase = (2 * self.Pot - self.DeltaI) / 2
        self.Fnb0 = 5 * math.pow(10, 13) * self.Pot / 100
        self.Fng0 = self.Fnb0
        # Ro=-2542.696533;
        self.RoAntes = self.Nxe0 * self.ConvertXe_Ro

        self.PotAntes = self.Pot
        self.PbaseAntes = self.Pot

        self.z = 0
        self.tXe = 0
        self.erro = 0
        self.VaguaTemp = 0
        return

    # =======================================================================
    # Interface do servico — um minuto de laco
    # =======================================================================

    def passo(self):
        """Corpo do laco de main() ATE a linha anterior a primeira regra.

        Transcricao de simulador.py linhas 1162-1291, dedentada de um nivel e
        sem o bloco kbhit() (codigo morto). Termina exatamente onde comeca o
        controle: o `if DeltaT < -0.1` que despacha R1-R4 e do expert.

        A condicao do laco (`termino != "fim" and t < tmax`) tambem nao esta
        aqui: `termino` e de R19. Quem fecha a malha consulta pode_continuar().
        """
        # sleep(1);
        self.t = self.t + 1
        self.z = self.z + 1
        self.tXe = self.tXe + 1
        self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
        self.Pbase = (2 * self.Pot - self.DeltaI) / 2
        # Corrige Tmed conforme a queima
        self.taxatempreal = (2601 - self.Cboro) / 6.31
        self.taxatemp = self.taxatempreal        # tempo de redução de 0,1ºC
        self.valor = (self.t / self.taxatemp)
        self.aux = self.valor
        if self.aux == self.valor:
            self.Tmedantes = self.Tmed
            self.Tmed = self.Tmed - 0.1
            self.x = self.x + 1
            self.DeltaT = self.Tmed - self.Tref
            self.VariacaoTmed = self.Tmed - self.Tmedantes
        if self.aux > self.x:
            self.diferenca = self.aux - self.x
            self.Tmedantes = self.Tmed
            self.Tmed = self.Tmed - (0.1 * self.diferenca)
            self.x = self.aux
            self.DeltaT = self.Tmed - self.Tref
            self.VariacaoTmed = self.Tmed - self.Tmedantes
        # Fim da correção de Tmed conforme a queima

        self.LimiteInsercao = 2.58 * (self.Pot) - 85

        # Ajuste da Carga Programada

        if self.TaxaTurbina != 0:
            while self.t >= self.ty:
                self.ty = self.ty + 1
                if self.ModuloTref > (self.ModuloTaxa * 0.0173846):
                    self.Tref = self.Tref + (self.TaxaTurbina * 0.0173846)
                    self.PotAlvo = (self.Tref - 291.7) / 0.113
                    self.ModuloTref = (self.AlvoTref - self.Tref)
                    if self.AlvoTref < self.Tref:
                        self.ModuloTref = -(self.AlvoTref - self.Tref)
                    printf("\nModuloTref=%.2f\n", self.ModuloTref)
                if self.ModuloTref <= (self.ModuloTaxa * 0.0173846):
                    self.Tref = self.AlvoTref
                    self.TaxaTurbina = 0
                    self.PotAlvo = (self.Tref - 291.7) / 0.113
        while (self.t >= self.y
               and (self.Pot > (self.PotAlvo + 0.015) or (self.Pot < (self.PotAlvo - 0.015)))):
            self.y = self.y + 1
            self.i = 0
            while self.i < 500:
                # printf("\n\ni:%d",i);
                if self.Pot > self.PotAlvo:
                    self.Pot = self.Pot - 0.01
                    self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
                    self.Pbase = (2 * self.Pot - self.DeltaI) / 2
                    self.PbaseAntes = self.Pot
                    # tXe=0;
                    if self.Pot != 0:
                        self.erro = self.DeltaI * ((1 / self.PotAntes) - (1 / self.Pot))
                    # printf("\n\nErro corrigido: %f",erro);
                    printf("\n\nPOTENCIA DO REATOR: %f%c", self.Pot, 37)
                    if self.TaxaTurbina != 0:
                        self.PotTurbina = 6.5 * self.Pot
                        printf("\nPOTENCIA DA TURBINA: %f", self.PotTurbina)
                if self.Pot < self.PotAlvo:
                    self.Pot = self.Pot + 0.01
                    self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
                    self.Pbase = (2 * self.Pot - self.DeltaI) / 2
                    self.PbaseAntes = self.Pot
                    # tXe=0;
                    printf("\n\nPOTENCIA DO REATOR: %f%c", self.Pot, 37)
                    if self.TaxaTurbina != 0:
                        self.PotTurbina = 6.5 * self.Pot
                        printf("\nPOTENCIA DA TURBINA: %f", self.PotTurbina)
                if (self.Pot <= (self.PotAlvo + 0.015)) and (self.Pot >= (self.PotAlvo - 0.015)):
                    break
                self.i = self.i + 1
        self.CalculaAlvoDeltaI()
        self.CalculaDeltaI()

        printf("\n\n\nt=%.0f", self.t)
        # sleep(1);
        printf("\nZ=%d", self.z)
        printf("\nPot=%.2f", self.Pot)
        if (self.Pot <= (self.PotAlvo + 0.015)) and (self.Pot >= (self.PotAlvo - 0.015)):
            self.PotTurbina = 6.5 * self.Pot
            printf("\nPotTurbina=%.1f", self.PotTurbina)
        self.PotTurbinaTemp = 6.5 * self.Pot
        printf("\nPotTurbinaTemp=%.1f", self.PotTurbinaTemp)
        printf("\nAlvoTref=%.2f", self.AlvoTref)
        printf("\nTmed=%.1f", self.Tmed)
        printf("\nTref=%.1f", self.Tref)
        printf("\nAlvo DeltaI=%f", self.AlvoDeltaI)
        printf("\nDeltaI=%f", self.DeltaI)
        printf("\nDesvioDeltaI=%f", self.DesvioDeltaI)
        printf("\nVariacaoDeltaI=%f", self.VariacaoDeltaI)
        printf("\nPosicao Barra=%d", self.PosicaoBarra)
        printf("\nPosicao de referencia BD=%d", self.BD)
        printf("\nCboro=%f\n\n\n", self.Cboro)

        self.GravaDados()

        # Injecao automatica do transiente, no mesmo ponto do laco em que o
        # operador digitaria "v" no programa original.
        if (self.transienteTipo != TR_NENHUM and self.transienteAplicado == 0
                and self.t >= self.tTransiente):
            self.transienteAplicado = 1
            printf("\n\nTRANSIENTE APLICADO EM t=%.0f\n", self.t)
            self.AplicaTransienteAuto()


        # CALCULA DELTA I NO LOOP DO MAIN

        self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
        self.Pbase = (2 * self.Pot - self.DeltaI) / 2
        if self.Ptopo < 0:
            self.Ptopo = 0
        if self.win_original:
            if self.Pbase < 0:
                self.Ptopo = 0   # semantica literal do original .txt (aparente troca de variavel)
        else:
            if self.Pbase < 0:
                self.Pbase = 0   # corrigido: era "Ptopo=0" (aparente troca de variavel)

        self.BD = 0.73 * self.Pot + 144
        printf("BD: %d", self.BD)
        return

    def pode_continuar(self):
        """Metade da condicao do laco que cabe a planta. A outra metade
        (`termino != "fim"`, posta por R19) e do expert."""
        return self.t < self.tmax

    # =======================================================================
    # Interface do servico — as tres alavancas de reatividade
    # =======================================================================

    def diluir(self, vazao):
        """Efeito de uma diluicao. Consequente de R1, R3 e R5.

        O expert escolheu a vazao (faixa de DeltaT: v1, v2 ou a rampa -a.DeltaT+b,
        dobrada em R5) e ja imprimiu o seu proprio "Iniciada a Diluicao...".
        A planta comeca em "Diluicao Encerrada".

        `tempo = t` e fixado aqui. No fonte ele e atribuido dentro de cada um dos
        tres ramos de selecao de vazao (L722, 727, 732), que sao exaustivos para
        qualquer t1 > t2 — logo equivale a fixa-lo no instante da atuacao.
        """
        self.Vazao = vazao
        self.tempo = self.t
        self.t = self.t + self.tempodilute
        self.z = self.z + self.tempodilute
        self.tXe = self.tXe + self.tempodilute
        printf("\n\nDiluicao Encerrada")
        self.Vagua = self.Vazao * (self.t - self.tempo)
        self.Vazao = 0
        self.VaguaTemp = self.Vagua + self.VaguaTemp
        self.CorrigeTmedDiluicao()
        self.CorrigeDeltaIDiluicao()
        return

    def borar(self, vazao_boro, vboro):
        """Efeito de uma boracao. Consequente de R8, R10, R11 e R12.

        As quatro regras calculam VazaoBoro e Vboro por formulas diferentes; o
        calculo e do expert. So Vboro entra na fisica — VazaoBoro vem junto
        porque e variavel de estado do modelo e o arredondamento a 32 bits do
        produto VazaoBoro*k tem de acontecer do lado de quem o calcula.
        """
        self.VazaoBoro = vazao_boro
        self.Vboro = vboro
        self.CorrigeTmedBoracao()
        self.CorrigeDeltaIBoracao()
        return

    def mover_barra(self, passos):
        """Efeito de mover o banco D. Consequente de R2, R4, R6, R7, R9, R13-R16.

        O expert ja imprimiu "Posicao Anterior" e "Posicao Atual" — e por isso
        que ele calcula a posicao nova por conta propria; aqui ela e refeita com
        a mesma soma inteira, e as duas coincidem.

        R6 escreve `DeltaBarra = DeltaBarra + 1` em vez de `= 1` (steps/03 §5.3).
        E equivalente porque CorrigeTmedDeltaBarra zera DeltaBarra depois de
        consumi-lo, entao ele vale 0 na entrada de toda regra.
        """
        self.PosicaoBarra = self.PosicaoBarra + passos
        self.DeltaBarra = passos
        self.CorrigeTmedDeltaBarra()
        self.CorrigeDeltaIDeltaBarra()
        return

    # =======================================================================
    # Observacao
    # =======================================================================

    # O que o controlador enxerga. As oito primeiras sao as grandezas
    # levantadas em steps/03-regras-controle.md §2 a partir das condicoes das
    # 19 regras; as sete seguintes sao as "grandezas de apoio" que parametrizam
    # os consequentes (alvo de DeltaI e selecao de vazao). O resto e relogio,
    # potencia e horizonte — nao entra em nenhuma condicao, serve a relatorio e
    # a condicao do laco.
    OBSERVADAS = (
        "DeltaT", "DesvioDeltaI", "VariacaoDeltaI", "DeltaI",
        "PosicaoBarra", "LimiteInsercao", "BD", "Cboro",
        "AlvoDeltaI", "v1", "v2", "a", "b", "t1", "t2", "tempodilute",
        "t", "z", "tXe", "Pot", "PotTurbina", "PotTurbinaTemp", "PotAlvo",
        "Tmed", "Tref", "AlvoTref", "Ptopo", "Pbase", "VaguaTemp", "tmax",
    )

    def estado(self):
        """A observacao que o expert recebe. Nada aqui e decisao."""
        return {n: self._valor(n) for n in self.OBSERVADAS}

    def interno(self):
        """Estado interno completo — todas as variaveis globais do .c.

        Nao e para o expert: e para a validacao. Permite comparar a planta com
        simulador.py variavel a variavel, e nao so pelo arquivo de amostras.
        """
        nomes = sorted(self._FLOAT | self._INT | self._DOUBLE)
        return {n: self._valor(n) for n in nomes}

    def _valor(self, nome):
        v = getattr(self, nome)
        return v if isinstance(v, int) else float(v)

    def tipos(self):
        """O tipo C de cada grandeza observada: 'float' (32 bits), 'int' ou
        'double'.

        Existe porque a fidelidade nao sobrevive ao JSON sozinha. O expert
        recebe numeros e faz contas com eles (a vazao da rampa, o volume de
        boro), e essas contas tem de arredondar a 32 bits nos mesmos pontos que
        o C. Sem saber o tipo de cada grandeza, o cliente nao consegue
        reproduzir o arredondamento — e +-0,001 desloca um evento.
        """
        return {n: ('int' if n in self._INT else
                    'double' if n in self._DOUBLE else 'float')
                for n in self.OBSERVADAS}

    # --- inicio do bloco copiado de simulador.py (linhas 331-384) ----------

    def AplicaRunback(self, trefNovo, alvoTrefNovo):
        trefNovo, alvoTrefNovo = F(trefNovo), F(alvoTrefNovo)   # parametros float
        self.Tref = trefNovo
        self.AlvoTref = alvoTrefNovo
        self.PotAlvo = (self.Tref - 291.7) / 0.113
        self.y = self.t
        self.ty = self.t
        self.tXe = 0
        self.RoAntes = self.Ro
        self.Nig0 = self.Nig
        self.Nxeg0 = self.Nxeg
        return

    def AplicaRampa(self, alvoTurbina, taxa):
        alvoTurbina, taxa = F(alvoTurbina), F(taxa)             # parametros float
        self.AlvoTurbina = alvoTurbina
        self.TaxaTurbina = taxa
        self.AlvoTref = 291.7 + (0.0173846 * self.AlvoTurbina)
        self.ModuloTref = (self.AlvoTref - self.Tref)
        self.ModuloTaxa = self.TaxaTurbina
        if self.AlvoTref < self.Tref:

            self.TaxaTurbina = -self.TaxaTurbina

            self.ModuloTref = -(self.AlvoTref - self.Tref)
        self.y = self.t
        self.ty = self.t
        self.tXe = 0
        self.RoAntes = self.Ro
        self.Nig0 = self.Nig
        self.Nxeg0 = self.Nxeg
        return

    # Aplica o transiente escolhido por linha de comando, com as mesmas
    # guardas de potencia usadas no menu interativo.
    def AplicaTransienteAuto(self):
        if self.transienteTipo == TR_RUNBACK_BAP:
            if self.PotTurbina > 301:
                self.AplicaRunback(296.92, 296.92)
        elif self.transienteTipo == TR_RUNBACK_CIRC:
            if self.PotTurbina > 401:
                self.AplicaRunback(298.65, 298.65)
        elif self.transienteTipo == TR_RUNBACK_400:
            if self.PotTurbina > 401:
                self.AplicaRunback(298.65, 298.5)
        elif self.transienteTipo == TR_RUNBACK_300:
            if self.PotTurbina > 301:
                self.AplicaRunback(296.92, 296.92)
        elif self.transienteTipo == TR_RUNBACK_150:
            if self.PotTurbina > 150:
                self.AplicaRunback(294.31, 294.31)
        elif self.transienteTipo == TR_RAMPA:
            self.AplicaRampa(self.argAlvo, self.argTaxa)
        return

    # --- fim do bloco copiado ---------------------------------------------

    # --- inicio do bloco copiado de simulador.py (linhas 460-848) ----------

    def CalculaAlvoDeltaI(self):

        # if (Cboro>=1440) {
        # AlvoDeltaI= (71.43-Pot)/28.57; }

        if self.Cboro >= 1080:
            self.AlvoDeltaI = self.Pot / 100          # (71.43-Pot)/28.57;

        # if (Cboro<1440 && Cboro>=1080) {
        # AlvoDeltaI= (57.14-Pot)/28.57; }

        if self.Cboro < 1080 and self.Cboro >= 720:
            self.AlvoDeltaI = (57.14 - self.Pot) / 28.57

        # if (Cboro<1080 && Cboro>=720) {
        # AlvoDeltaI= (42.86-Pot)/28.57; }

        # if (Cboro<720 && Cboro>=360) {
        # AlvoDeltaI= (28.57-Pot)/28.57; }

        # if (Cboro<360) {
        # AlvoDeltaI= (14.29-Pot)/28.57; }

        if self.Cboro < 720:
            self.AlvoDeltaI = (42.86 - self.Pot) / 28.57

        return

    def CalculaDeltaI(self):

        self.DeltaI = self.Ptopo - self.Pbase
        self.DesvioDeltaI = self.DeltaI - self.AlvoDeltaI
        self.DeltaIantes = self.DeltaI
        printf("\n\nPbase: %f", self.Pbase)
        printf("\n\nPtopo: %f", self.Ptopo)
        # printf("\n\nPbaseAntes: %f", PbaseAntes);
        printf("\n\nPbase/PbaseAntes: %f", self.Pbase / self.PbaseAntes)
        printf("\n\nerro: %f", self.erro)
        self.Fnb = self.Fnb0 * (self.Pbase / self.PbaseAntes)  # ((Pbase/PbaseAntes)-erro)
        printf("\n\nFnb: %f", self.Fnb)

        # printf("\nPotencia na Base do Reator Antes da Oscilacao do Xe: %f%c",Pbase,37);
        # printf("\nPotencia no Topo do Reator Antes da Oscilacao do Xe: %f%c",Ptopo,37);
        printf("\nDelta I Antes da Oscilacao do Xe: %f", self.DeltaI)

        # EQUAÇÃO DO XENONIO E IODO- BASE

        self.NxeAntes = self.Nxeb

        self.Nib = (self.Ni0 * math.pow(2.7182818282, ((-self.lambdaI) * (self.z * 60)))
                    + (self.gamaI * self.Sigmaf * self.Fnb)
                    * (1 - math.pow(2.7182818282, ((-self.lambdaI) * (self.z * 60)))) / self.lambdaI)

        self.Nxeb = ((self.Nxe0 * (math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fnb) * (self.z * 60)))))
                     + ((self.gamaI + self.gamaXe) * self.Sigmaf * self.Fnb
                        * (1 - (math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fnb) * (self.z * 60)))))
                        / (self.lambdaXe + self.sigmaXe * self.Fnb))
                     + ((self.gamaI * self.Sigmaf * self.Fnb - self.lambdaI * self.Ni0)
                        * ((math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fnb) * (self.z * 60))))
                           - (math.pow(2.7182818282, (-(self.lambdaI * (self.z * 60))))))
                        / (self.lambdaXe - self.lambdaI + self.sigmaXe * self.Fnb)))

        # printf("\n\nValor da concentracao do Iodo: %f", Nib);
        # printf("\n\nValor da concentracao do Xe: %f", Nxeb);

        # REGRA DE CONVERSÃO DA CONCENTRAÇÃO DE Xe PARA REATIVIDADE - BASE

        self.RoAntes = self.NxeAntes * self.ConvertXe_Ro
        self.Ro = self.Nxeb * self.ConvertXe_Ro
        printf("\n\nRoAntes: %f", self.RoAntes)
        printf("\n\nRo: %f", self.Ro)
        self.Deltaro = self.Ro - self.RoAntes
        if self.Deltaro > 400:
            self.Deltaro = 400
        if (self.Deltaro < 0.0001 and self.Deltaro > -0.0001) or self.DeltaI == 0:
            self.Deltaro = 0

        # printf("\nValor de Reatividade Devido ao Xe: %f", Ro);
        printf("\nValor do Delta de Reatividade Devido ao Xe: %f\n", self.Deltaro)

        # ALTERAÇÃO Pbase

        if self.Deltaro != 0:
            self.Trx = (self.betaeff - self.Deltaro) / (self.lambda_ * self.Deltaro)
            printf("\nTrx: %f\n", self.Trx)
            self.Pbase0 = self.Pbase
            self.inversoTrx = 1 / self.Trx
            self.Pbase = self.Pbase * math.pow(2.72, self.inversoTrx)
            if self.Pbase < 0:
                self.Pbase = 0
            self.DeltaPbase = self.Pbase - self.Pbase0
            self.Ptopo = self.Ptopo - self.DeltaPbase
            if self.Ptopo < 0:
                self.Ptopo = 0

        # NOVO DELTA I

        self.DeltaI = self.Ptopo - self.Pbase
        self.DesvioDeltaI = self.DeltaI - self.AlvoDeltaI
        self.VariacaoDeltaI = self.DeltaI - self.DeltaIantes

        printf("\nPotencia na Base do Reator Apos a Oscilacao do Xe: %f%c", self.Pbase, 37)
        printf("\nPotencia no Topo do Reator Apos a Oscilacao do Xe: %f%c", self.Ptopo, 37)
        # printf("\nPotencia no Topo do Reator Apos a Oscilacao do Xe: %f%c",Ptopo,37);
        printf("\nDelta I Apos a Oscilacao do Xe: %f\n", self.DeltaI)

        # printf("\nNxeAntes: %f\n",NxeAntes);
        # printf("\nNxeb: %f\n",Nxeb);

        if (self.Nxeb - self.NxeAntes) < 1000 and (self.Nxeb - self.NxeAntes) > -1000:

            self.atualizadadosXe()

        # ALTERA A POTENCIA DO REATOR DEVIDO AO EFEITO GLOBAL DO XE DEVIDO A TRANSIENTES DE CARGA
        # if (tXe<4320) {
        printf("\n\nFngAntes: %f", self.Fng)
        self.Fng = self.Fng0 * (self.Pot / self.PotAntes)
        printf("\n\nPot/PotAntes: %f", self.Pot / self.PotAntes)
        printf("\n\nFng: %f", self.Fng)
        printf("\n\ntXe: %d", self.tXe)

        self.NxeAntes = self.Nxeg

        self.Nig = (self.Nig0 * math.pow(2.7182818282, ((-self.lambdaI) * (self.tXe * 60)))
                    + (self.gamaI * self.Sigmaf * self.Fng)
                    * (1 - math.pow(2.7182818282, ((-self.lambdaI) * (self.tXe * 60)))) / self.lambdaI)

        self.Nxeg = ((self.Nxeg0 * (math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fng) * (self.tXe * 60)))))
                     + ((self.gamaI + self.gamaXe) * self.Sigmaf * self.Fng
                        * (1 - (math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fng) * (self.tXe * 60)))))
                        / (self.lambdaXe + self.sigmaXe * self.Fng))
                     + ((self.gamaI * self.Sigmaf * self.Fng - self.lambdaI * self.Nig0)
                        * ((math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fng) * (self.tXe * 60))))
                           - (math.pow(2.7182818282, (-(self.lambdaI * (self.tXe * 60))))))
                        / (self.lambdaXe - self.lambdaI + self.sigmaXe * self.Fng)))

        self.RoAntes = self.NxeAntes * self.ConvertXe_Ro
        self.Ro = self.Nxeg * self.ConvertXe_Ro
        printf("\n\nRoAntes: %f", self.RoAntes)
        printf("\n\nRo: %f", self.Ro)
        self.Deltaro = self.Ro - self.RoAntes
        if self.Deltaro > 400:
            self.Deltaro = 400
        if (self.Deltaro < 0.0001 and self.Deltaro > -0.0001) or self.DeltaI == 0:
            self.Deltaro = 0
        # Defeito de Potência Antes da Variação Devido ao Xe
        self.DefPotAntes = (self.Cboro - 3806.7024) * self.Pot / 150.88

        # printf("\nValor de Reatividade Devido ao Xe: %f", Ro);
        printf("\nValor do Delta de Reatividade Devido ao Xe: %f\n", self.Deltaro)
        if self.Deltaro != 0:
            self.Trx = (self.betaeff - self.Deltaro) / (self.lambda_ * self.Deltaro)
            printf("\nTrxPot: %f\n", self.Trx)
            printf("\nPotencia do Reator Antes do Variacao do Xe: %f\n", self.Pot)
            self.inversoTrx = 1 / self.Trx
            self.Pot = self.Pot * math.pow(2.72, self.inversoTrx)
            if self.Pot < 0:
                self.Pot = 0
            self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
            self.Pbase = (2 * self.Pot - self.DeltaI) / 2
            self.PbaseAntes = self.Pot
            if self.Pot != 0:
                self.erro = self.DeltaI * ((1 / self.PotAntes) - (1 / self.Pot))
            printf("\nPotencia variando devido ao Xe: %f\n", self.Pot)
            self.DefPot = (self.Cboro - 3806.7024) * self.Pot / 150.88
            printf("\nTemperatura Media Antes da Variacao do Xe: %.1f\n", self.Tmed)
            self.Tmed = self.Tmed + ((self.DefPot - self.DefPotAntes) / self.alfamoderador)
            printf("\nTemperatura Media Apos da Variacao de Potencia Devido ao Xe: %.1f\n", self.Tmed)
            # getch();
        if (((self.Nxeb - self.NxeAntes) < 1000 and (self.Nxeb - self.NxeAntes) > -1000)
                or self.tXe >= 4320):

            self.atualizadadosXeg()

        return

    def atualizadadosXe(self):

        printf("\n\nATUALIZA DADOS")
        self.z = 0
        self.RoAntes = self.Ro
        self.Ni0 = self.Nib
        self.Nxe0 = self.Nxeb
        return

    def atualizadadosXeg(self):

        printf("\n\nATUALIZA DADOS GLOBAIS")
        self.tXe = 0
        self.RoAntes = self.Ro
        self.Nig0 = self.Nig
        self.Nxeg0 = self.Nxeg
        return

    # Funcoes Diluicao

    def CorrigeTmedDiluicao(self):
        printf("\n\nVolume de agua pura adicionado: %.0f", self.Vagua)
        self.Cboro1 = self.Cboro
        printf("\n\nConcentracao de Boro do SRR Antes da Diluicao: %f ppm", self.Cboro1)
        self.razao = self.Vagua / self.Msrr
        self.erazao = math.pow(2.72, self.razao)
        self.Cboro = self.Cboro / (self.erazao)
        printf("\nConcentracao de Boro do SRR Apos a Diluicao: %f ppm", self.Cboro)
        # ATUALIZACAO DOS PARAMETROS QUE VARIAM COM A CONCENTRACAO DE BORO
        printf("\nTaxa de Reducao de 0,1°C na Temperatura do SRR Devido a Queima: %d\n", self.taxatemp)
        self.alfamoderador = 0.02849 * self.Cboro - 75.02849
        printf("\nCoeficiente de Temperatura do Moderador: %f pcm/°C", self.alfamoderador)
        self.alfaboro = 0.0005363 * self.Cboro - 7.285363
        printf("\nValor do Coeficiente de Reatividade do Boro: %f pcm/ppm\n", self.alfaboro)
        self.v1 = -0.05307 * self.Cboro + 100.5307
        if self.v1 <= 0:
            self.v1 = 5
        printf("\nValor da Vazao de Diluicao Minima: %.0f lpm", self.v1)
        self.v2 = -0.24022 * self.Cboro + 452.24022
        if self.v2 <= 0:
            self.v2 = 10
        printf("\nValor da Vazao de Diluicao Maxima: %.0f lpm", self.v2)
        self.a = 2 * self.v1
        printf("\nValor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f", self.a)
        self.b = self.v1
        printf("\nValor do Coeficiente B da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f\n", self.b)
        printf("\nPosicao do Banco de Controle D: %d\n", self.PosicaoBarra)
        # FIM DA ATUALIZACAO CBORO

        self.Deltaro = (self.Cboro - self.Cboro1) * self.alfaboro
        printf("\n\nVariacao de Reatividade Devido a Diluicao: %f pcm", self.Deltaro)
        printf("\n\n\nATENCAO: O SRR ESTA AQUECENDO DEVIDO A DILUICAO\n\n")
        self.i = _para_int(self.thom)
        while self.i > 0:
            self.Tmedantes = self.Tmed
            self.Tmed = (-(self.Deltaro / self.thom) / self.alfamoderador) + self.Tmed
            self.aux = self.thom + 1 - self.i
            printf("\nTmed%d: %f °C", self.aux, self.Tmed)
            self.DeltaT = self.Tmed - self.Tref
            self.VariacaoTmed = self.Tmed - self.Tmedantes
            # sleep(1);
            self.t = self.t + 1
            self.z = self.z + 1
            self.tXe = self.tXe + 1
            self.i = self.i - 1
        printf("\n\n\nA ESTABILIZACAO DA TEMPERATURA DO SRR FOI ATINGIDA\n\n")
        printf("\n\nTemperatura Media do SRR: %.2f °C  // Diferenca Tmed - Tref (DeltaT): %f °C \n\n",
               self.Tmed, self.DeltaT)
        return

    def CorrigeDeltaIDiluicao(self):
        self.Trx = (self.betaeff - self.Deltaro) / (self.lambda_ * self.Deltaro)
        printf("\nPeriodo do Reator Devido a Insercao de Reatividade: %f", self.Trx)
        self.Pbase0 = self.Pbase
        printf("\nPotencia na Base do Reator Antes da Diluicao: %f%c", self.Pbase, 37)
        self.inversoTrx = 1 / self.Trx
        self.Pbase1 = self.Pbase * math.pow(2.72, self.inversoTrx)
        self.DeltaPbase = (self.Pbase1 - self.Pbase0) * 0.9
        self.Pbase = self.Pbase + self.DeltaPbase
        if self.Pbase < 0:
            self.Pbase = 0
        printf("\nPotencia na Base do Reator Apos da Diluicao: %f%c", self.Pbase, 37)
        self.Ptopo = self.Ptopo - self.DeltaPbase
        if self.Ptopo < 0:
            self.Ptopo = 0
        self.DeltaI = self.Ptopo - self.Pbase
        self.DesvioDeltaI = self.DeltaI - self.AlvoDeltaI

        # CALCULA DELTA I Xe APÓS DILUIÇÃO

        self.CalculaDeltaI()

        return

    # Funcões Boração

    def CorrigeTmedBoracao(self):
        printf("\n\nVolume de Boro adicionado: %.0f", self.Vboro)
        self.Cboro1 = self.Cboro
        printf("\n\nConcentracao de Boro do SRR Antes da Boracao: %f ppm", self.Cboro1)
        self.razao = -self.Vboro / self.Msrr
        self.erazao = math.pow(2.72, self.razao)
        self.Cboro = 7200 - (7200 - self.Cboro) * self.erazao
        printf("\nConcentracao de Boro do SRR Apos a Boracao: %f ppm", self.Cboro)

        # ATUALIZACAO DOS PARAMETROS QUE VARIAM COM A CONCENTRACAO DE BORO
        self.taxatempreal = (2601 - self.Cboro) / 6.31   # (2619-Cboro)/6.16;
        self.taxatemp = self.taxatempreal                # tempo de redução de 0,1ºC
        printf("\nTaxa de Reducao de 0,1°C na Temperatura do SRR Devido a Queima: %d\n", self.taxatemp)
        self.alfamoderador = 0.02849 * self.Cboro - 75.02849
        printf("\nCoeficiente de Temperatura do Moderador: %f pcm/°C", self.alfamoderador)
        self.alfaboro = 0.0005363 * self.Cboro - 7.285363
        printf("\nValor do Coeficiente de Reatividade do Boro: %f pcm/ppm\n", self.alfaboro)
        self.v1 = -0.05307 * self.Cboro + 100.5307
        if self.v1 <= 0:
            self.v1 = 5
        printf("\nValor da Vazao de Diluicao Minima: %.0f lpm", self.v1)
        self.v2 = -0.24022 * self.Cboro + 452.24022
        if self.v2 <= 0:
            self.v2 = 10
        printf("\nValor da Vazao de Diluicao Maxima: %.0f lpm", self.v2)
        self.a = 2 * self.v1
        printf("\nValor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f", self.a)
        self.b = self.v1
        printf("\nValor do Coeficiente B da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f\n", self.b)
        printf("\nPosicao do Banco de Controle D: %d\n", self.PosicaoBarra)
        # FIM DA ATUALIZACAO CBORO

        self.Deltaro = (self.Cboro - self.Cboro1) * self.alfaboro
        printf("\n\nVariacao de Reatividade Devido a Boracao: %f pcm", self.Deltaro)
        printf("\n\n\nATENCAO: O SRR ESTA RESFRIANDO DEVIDO A BORACAO\n\n")
        self.i = _para_int(self.thom)
        while self.i > 0:
            self.Tmedantes = self.Tmed
            self.Tmed = (-(self.Deltaro / self.thom) / self.alfamoderador) + self.Tmed
            self.aux = self.thom + 1 - self.i
            printf("\nTmed%d: %f °C", self.aux, self.Tmed)
            self.DeltaT = self.Tmed - self.Tref
            self.VariacaoTmed = self.Tmed - self.Tmedantes
            # sleep(1);
            self.t = self.t + 1
            self.z = self.z + 1
            self.tXe = self.tXe + 1
            self.i = self.i - 1
        printf("\n\n\nA ESTABILIZACAO DA TEMPERATURA DO SRR FOI ATINGIDA\n\n")
        printf("\n\nTemperatura Media do SRR: %.2f °C  // Diferenca Tmed - Tref (DeltaT): %f °C \n\n",
               self.Tmed, self.DeltaT)
        return

    def CorrigeDeltaIBoracao(self):
        self.Trx = (self.betaeff - self.Deltaro) / (self.lambda_ * self.Deltaro)
        printf("\nPeriodo do Reator Devido a Insercao de Reatividade: %f", self.Trx)
        self.Pbase0 = self.Pbase
        printf("\nPotencia na Base do Reator Antes da Boracao: %f%c", self.Pbase, 37)
        self.inversoTrx = 1 / self.Trx
        self.Pbase1 = self.Pbase * math.pow(2.72, self.inversoTrx)
        self.DeltaPbase = (self.Pbase1 - self.Pbase0) * 1.6
        self.Pbase = self.Pbase + self.DeltaPbase
        if self.Pbase < 0:
            self.Pbase = 0
        printf("\nPotencia na Base do Reator Apos da Boracao: %f%c", self.Pbase, 37)
        self.Ptopo = self.Ptopo - self.DeltaPbase
        if self.Ptopo < 0:
            self.Ptopo = 0
        self.DeltaI = self.Ptopo - self.Pbase
        self.DesvioDeltaI = self.DeltaI - self.AlvoDeltaI

        # CALCULA DELTA I Xe APÓS BORAÇÃO

        self.CalculaDeltaI()

        return

    # Funcoes DeltaBarra

    def CorrigeTmedDeltaBarra(self):

        if self.PosicaoBarra >= 100:
            self.Deltaro = 6.5 * self.DeltaBarra
        else:
            self.Deltaro = 20 * self.DeltaBarra
        self.DeltaBarra = 0
        printf("\n\nVARIACAO DE REATIVIDADE DEVIDO A MOVIMENTACAO DE BARRA: %f pcm", self.Deltaro)
        self.Tmedantes = self.Tmed
        printf("\nTemperatura Media antes da Movimentacao de Barra: %f °C", self.Tmed)
        self.Tmed = (-(self.Deltaro / self.alfamoderador)) + self.Tmed
        self.DeltaT = self.Tmed - self.Tref
        self.VariacaoTmed = self.Tmed - self.Tmedantes
        # sleep(1);
        self.t = self.t + 2
        self.z = self.z + 2
        self.tXe = self.tXe + 2
        printf("\n\nTemperatura Media do SRR: %.2f °C  // Diferenca Tmed - Tref (DeltaT): %f °C \n\n",
               self.Tmed, self.DeltaT)
        return

    def CorrigeDeltaIDeltaBarra(self):
        self.Trx = (self.betaeff - self.Deltaro) / (self.lambda_ * self.Deltaro)
        printf("\nPeriodo do Reator Devido a Insercao de Reatividade: %f", self.Trx)
        self.Ptopo0 = self.Ptopo
        printf("\nPotencia no Topo do Reator Antes da Movimentacao de Barra: %f%c", self.Ptopo, 37)
        self.inversoTrx = 1 / self.Trx
        self.Ptopo = self.Ptopo * math.pow(2, self.inversoTrx)
        self.DeltaPtopo = self.Ptopo - self.Ptopo0
        printf("\nPotencia no Topo do Reator Apos da Movimentacao de Barra: %f%c", self.Ptopo, 37)
        self.Pbase = self.Pbase - self.DeltaPtopo
        self.DeltaI = self.Ptopo - self.Pbase
        self.DesvioDeltaI = self.DeltaI - self.AlvoDeltaI
        # CALCULA DELTA I Xe APÓS DILUIÇÃO

        self.CalculaDeltaI()

        return

    # --- fim do bloco copiado ---------------------------------------------
