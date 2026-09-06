#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_c_vs_python.py — o braco procedural: as 19 regras, fora da planta.

O QUE ISTO E

    O Passo 4 tirou toda a decisao de dentro do simulador: reactor/physics.py so
    tem efeitos. Faltava alguem para decidir — senao nao ha o que validar. Este
    arquivo e esse alguem, na forma mais conservadora possivel: os 19 blocos `if`
    de steps/03-regras-controle.md transcritos na ordem do fonte, chamando a
    planta pelas tres alavancas (diluir / borar / mover_barra).

    Ele NAO e o sistema especialista. E o instrumento que prova que a fronteira
    esta no lugar certo: se a planta ficou completa e as regras sairam inteiras,
    esta transcricao dirigindo reactor/physics.py tem de produzir os MESMOS bytes
    que simulador.py — nas amostras e na saida padrao. Se um `if` tivesse ficado
    para tras na planta, ou um efeito tivesse vindo junto com uma regra, a
    comparacao byte a byte acusaria.

    No Passo 5 ele vira a referencia do expert: a base de regras declarativa sera
    conferida contra esta transcricao (tests/test_equivalencia_braco_python.py),
    que por sua vez ja foi conferida contra o .c.

COMO AS REGRAS LEEM O ESTADO

    Pela API de observacao da planta — estado() e tipos() — e nao pelos atributos
    do objeto. Isso e de proposito: e exatamente o que um cliente HTTP recebe.
    Observacao() reembrulha cada numero no tipo C declarado, para que as contas
    do lado do controle (a rampa de vazao, o volume de boro) arredondem a 32 bits
    nos mesmos pontos que o C. Sem isso o braco decidiria igual quase sempre, e
    +-0,001 num ponto deslocaria um evento de diluicao e desfaria a fase do
    resto da corrida.

    O estado e RELIDO depois de cada atuacao. steps/03 §5.1: as regras nao sao
    atomicas — varias disparam no mesmo minuto e cada uma ve o que a anterior
    deixou.

USO — a mesma linha de comando de simulador.py

    echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' \
        | python3 scripts/validate_c_vs_python.py --tmax=1440 > /dev/null

    --arquivo=NOME    arquivo de amostras (padrao Modelagem_Reator_api.txt)
    --capturar        passa a saida pelo buffer de captura do servico, em vez
                      de escrever direto no stdout. Prova que o caminho que a
                      API usa para devolver texto produz os mesmos bytes.
    --api=URL         fala com o servico por HTTP em vez de importar a planta.
                      As 19 regras sao as MESMAS nos dois modos: so muda quem
                      responde a estado() e a diluir/borar/mover_barra. E o
                      teste de que a fronteira e a API.

                          podman run -d --name reactor-teste -p 8008:8008 \
                              -v ./runs:/runs reactor-simulator:latest
                          echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' \
                            | python3 scripts/validate_c_vs_python.py \
                                  --api=http://localhost:8008 --tmax=1440 > /dev/null
"""

import base64
import json
import os
import re
import sys
import urllib.request

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# DIR_MODULOS existe para o caso de rodar DENTRO do conteiner, onde os modulos
# da planta estao em /api e nao ha raiz de repositorio. Fora dele, reactor/.
sys.path.insert(0, os.environ.get("DIR_MODULOS") or os.path.join(_RAIZ, "reactor"))

from f32 import F                                                # noqa: E402
import saida                                                     # noqa: E402

# Os nomes de transiente que a linha de comando aceita. Ficam aqui, e nao vindo
# de physics, porque este script tambem roda DENTRO do conteiner do expert, onde
# a planta nao existe — em modo --api o que se manda e o NOME, e o mapeamento
# para o codigo interno e da planta. tests/test_api.py confere que os dois
# conjuntos coincidem.
NOMES_TRANSIENTE = ("runback-bap", "runback-circ", "runback-400",
                    "runback-300", "runback-150", "rampa")

from saida import printf, putc_raw                               # noqa: E402


class Observacao:
    """O estado da planta como o controlador o ve, com o tipo C restaurado."""

    def __init__(self, planta, tipos):
        self._d = planta.estado()
        self._t = tipos

    def __getattr__(self, nome):
        v = self._d[nome]
        tipo = self._t[nome]
        if tipo == "int":
            return v
        if tipo == "double":
            return float(v)
        return F(v)


class PlantaRemota:
    """A planta do outro lado do HTTP, com a mesma interface de physics.Planta.

    As 19 regras nao mudam uma linha entre os dois transportes — e essa a prova
    de que a fronteira e a API, e nao um detalhe da implementacao. O que este
    adaptador faz de diferente e uma coisa so: cada resposta traz o texto que a
    planta imprimiu, e ele e reemitido AQUI, no instante da chamada. E o que
    mantem a ordem da saida remontada igual a do monolito.
    """

    def __init__(self, base, params):
        self.base = base.rstrip("/")
        r = self._post("/reactor/initialize", params)
        self.sid = r["sessao"]
        self._estado = r["estado"]
        self._pode = r["pode_continuar"]
        self._tipos = self._get("/reactor/tipos")
        putc_raw(base64.b64decode(r["saida_b64"]))

    # -- transporte ------------------------------------------------------
    def _get(self, rota):
        req = urllib.request.Request(self.base + rota)
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)

    def _post(self, rota, corpo):
        dados = json.dumps(corpo).encode("utf-8")
        req = urllib.request.Request(self.base + rota, data=dados,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.load(resp)

    def _aplica(self, r):
        self._estado = r["estado"]
        self._pode = r["pode_continuar"]
        # putc_raw, e nao printf: sao bytes, e printf codificaria em UTF-8.
        putc_raw(base64.b64decode(r["saida_b64"]))

    # -- interface da planta ---------------------------------------------
    def tipos(self):
        return self._tipos

    def estado(self):
        return self._estado

    def pode_continuar(self):
        return self._pode

    def passo(self):
        self._aplica(self._post("/reactor/%s/passo" % self.sid, None))

    def diluir(self, vazao):
        self._aplica(self._post("/reactor/%s/acao" % self.sid,
                                {"acao": {"tipo": "diluir", "vazao": float(vazao)}}))

    def borar(self, vazao_boro, vboro):
        self._aplica(self._post("/reactor/%s/acao" % self.sid,
                                {"acao": {"tipo": "borar",
                                          "vazao_boro": float(vazao_boro),
                                          "vboro": float(vboro)}}))

    def mover_barra(self, passos):
        self._aplica(self._post("/reactor/%s/acao" % self.sid,
                                {"acao": {"tipo": "barra", "passos": int(passos)}}))

    def encerra(self):
        req = urllib.request.Request(self.base + "/reactor/" + self.sid, method="DELETE")
        try:
            urllib.request.urlopen(req, timeout=60).read()
        except Exception:
            pass


class BracoProcedural:
    """As 19 regras, na ordem do fonte, com prioridade = ordem e disparo
    multiplo por ciclo (a estrategia de resolucao de conflito que steps/03 §5.1
    identificou como a unica compativel com o simulador original)."""

    def __init__(self, planta):
        self.p = planta
        self.tipos = planta.tipos()
        self.termino = ""
        # Globais do .c que pertencem ao lado do controle: sobrevivem entre
        # regras e entre ciclos, como no fonte.
        self.Vazao = F(0)
        self.VazaoBoro = F(0)
        self.Vboro = F(0)

    def ve(self):
        return Observacao(self.p, self.tipos)

    # =======================================================================
    # Bloco I — CompensacaoQueima · guarda DeltaT < -0,1        R1 a R4
    # =======================================================================

    def CompensacaoQueima(self):
        e = self.ve()
        if e.DeltaT < -0.1:

            # ---- R1: diluir ------------------------------------------------
            if ((e.VariacaoDeltaI >= 0 or e.DeltaT < -0.3)
                    or (e.PosicaoBarra >= 222 or e.DesvioDeltaI > -3)):

                if e.DeltaT >= e.t1:
                    self.Vazao = e.v1
                    printf("\n\nDeltaT: %f\n\n", e.DeltaT)
                    printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm", self.Vazao)
                if e.DeltaT <= e.t2:
                    self.Vazao = e.v2
                    printf("\n\nDeltaT: %f\n\n", e.DeltaT)
                    printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm", self.Vazao)
                if e.DeltaT > e.t2 and e.DeltaT < e.t1:
                    self.Vazao = (-e.a * e.DeltaT) + e.b
                    printf("\n\nDeltaT: %f\n\n", e.DeltaT)
                    printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm", self.Vazao)
                self.p.diluir(self.Vazao)
                e = self.ve()

            # ---- R2: barra +1 ----------------------------------------------
            if (e.DesvioDeltaI < 0
                    and (e.VariacaoDeltaI <= 0 or e.DeltaT < -0.3)
                    and e.PosicaoBarra < 222):
                printf("\n\nCOMPENSACAO DA QUEIMA POR RETIRADA DE BARRA\n\n")
                printf("\n\nPosicao Anterior do Banco D: %d passos", e.PosicaoBarra)
                printf("\n\nPosicao Atual do Banco D: %d passos\n", e.PosicaoBarra + 1)
                self.p.mover_barra(1)
                e = self.ve()

            # ---- R3: diluir a v2 -------------------------------------------
            if (e.DeltaT < -0.8) and (e.DesvioDeltaI >= 0 or e.PosicaoBarra >= 222):
                self.Vazao = e.v2
                printf("\n\nDeltaT: %f\n\n", e.DeltaT)
                printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm", self.Vazao)
                self.p.diluir(self.Vazao)
                e = self.ve()

            # ---- R4: barra +2 ----------------------------------------------
            if (e.DeltaT < -0.8) and (e.DesvioDeltaI < 4) and (e.PosicaoBarra < 222):
                printf("\n\nCORRECAO DA TEMPERATURA MEDIA POR RETIRADA DE BARRA\n\n")
                printf("\n\nPosicao Anterior do Banco D: %d passos", e.PosicaoBarra)
                printf("\n\nPosicao Atual do Banco D: %d passos\n", e.PosicaoBarra + 2)
                self.p.mover_barra(2)
        return

    # =======================================================================
    # Bloco II — Corrige_DeltaI · guarda |DesvioDeltaI| > 2     R5 a R8
    # =======================================================================

    def Corrige_DeltaI(self):
        e = self.ve()

        # ---- R5: diluir com vazao dobrada ----------------------------------
        if ((e.DesvioDeltaI >= 0 and e.DeltaT <= 0.4)
                or (e.DesvioDeltaI > 4.5 and e.DeltaT < 2)):
            if e.DeltaT >= e.t1:
                self.Vazao = 2 * e.v1
                printf("\n\nDeltaT: %f\n\n", e.DeltaT)
                printf("\n\nIniciada a Correcao do Delta I por Diluicao na Vazao de %.0f lpm", self.Vazao)
            if e.DeltaT <= e.t2:
                self.Vazao = 2 * e.v2
                printf("\n\nDeltaT: %f\n\n", e.DeltaT)
                printf("\n\nIniciada a Correcao do Delta I por Diluicao na Vazao de %.0f lpm", self.Vazao)
            if e.DeltaT > e.t2 and e.DeltaT < e.t1:
                self.Vazao = 2 * ((-e.a * e.DeltaT) + e.b)
                printf("\n\nDeltaT: %f\n\n", e.DeltaT)
                printf("\n\nIniciada a Correcao do Delta I por Diluicao na Vazao de %.0f lpm", self.Vazao)
            self.p.diluir(self.Vazao)
            e = self.ve()

        # ---- R6: barra +1 ---------------------------------------------------
        if e.DesvioDeltaI < 0 and e.DeltaT < 0.8 and e.PosicaoBarra < 222:
            printf("\n\nCORRECAO DO DELTA I POR RETIRADA DE BARRA\n\n")
            printf("\n\nPosicao Anterior do Banco D: %d passos", e.PosicaoBarra)
            printf("\n\nPosicao Atual do Banco D: %d passos\n", e.PosicaoBarra + 1)
            self.p.mover_barra(1)
            e = self.ve()

        # ---- R7: barra -1 ---------------------------------------------------
        if ((e.DeltaT > -0.6) and (e.DesvioDeltaI > 4.5)
                and (e.PosicaoBarra > (e.LimiteInsercao + 11) or e.DesvioDeltaI > 5)):
            printf("\n\nCORRECAO DA DELTA I POR INSERCAO DE BARRA\n\n")
            printf("\n\nPosicao Anterior do Banco D: %d passos", e.PosicaoBarra)
            printf("\n\nPosicao Atual do Banco D: %d passos\n", e.PosicaoBarra - 1)
            self.p.mover_barra(-1)
            e = self.ve()

        # ---- R8: borar ------------------------------------------------------
        if (((e.DesvioDeltaI < -4 and e.PosicaoBarra >= 222) and e.DeltaT > -1)
                or (e.DesvioDeltaI < -10 and e.DeltaT > -3)):

            # Cálculo do Volume de Boro
            self.VazaoBoro = (-e.DesvioDeltaI) * 6
            if self.VazaoBoro > 20:
                self.VazaoBoro = F(20)
            self.Vboro = self.VazaoBoro * 2

            printf("\n\nCORRECAO DO DELTA I POR BORACAO\n\n")
            self.p.borar(self.VazaoBoro, self.Vboro)
        return

    # =======================================================================
    # Bloco III — laco do main · sem guarda                    R9 a R19
    # =======================================================================

    def regras_do_laco(self):
        e = self.ve()

        # ---- R9: barra -1 ou -2 ---------------------------------------------
        if ((e.DeltaT > 0.6) and (e.DesvioDeltaI >= -2.2)
                and (e.PosicaoBarra > (e.LimiteInsercao + 11) or e.DeltaT > 1.5)):
            printf("\n\nCORRECAO DA TEMPERATURA MEDIA POR INSERCAO DE BARRA\n\n")
            printf("\n\nPosicao Anterior do Banco D: %d passos", e.PosicaoBarra)
            passos = -1 if e.DeltaT < 1 else -2
            printf("\n\nPosicao Atual do Banco D: %d passos\n", e.PosicaoBarra + passos)
            self.p.mover_barra(passos)
            e = self.ve()

        # ---- R10: borar ------------------------------------------------------
        if (e.DeltaT > 0.8) and (e.DesvioDeltaI < 0):
            # Volume de Boro
            self.VazaoBoro = e.DeltaT * 10
            self.Vboro = self.VazaoBoro * 4
            printf("\n\nCORRECAO DO DELTA T POR BORACAO\n\n")
            self.p.borar(self.VazaoBoro, self.Vboro)
            e = self.ve()

        # ---- R11: alarme limite baixo (+ boracao normal) ---------------------
        if e.PosicaoBarra <= (e.LimiteInsercao + 10) and e.PosicaoBarra > e.LimiteInsercao:
            printf("\n\nALARME ATIVADO: LIMITE DE INSERCAO BAIXO\n\n")
            if e.DeltaI < 0:
                # Volume de Boro
                self.VazaoBoro = (e.LimiteInsercao - e.PosicaoBarra + 11) * 2
                self.Vboro = self.VazaoBoro * 2
                printf("\n\nLIMITE DE INSERCAO BAIXO ATINGIDO - BORACAO NORMAL\n\n")
                self.p.borar(self.VazaoBoro, self.Vboro)
                e = self.ve()

        # ---- R12: alarme limite muito baixo (+ boracao de emergencia) --------
        if e.PosicaoBarra <= e.LimiteInsercao:
            printf("\n\nALARME ATIVADO: LIMITE DE INSERCAO MUITO BAIXO\n\n")
            if e.DeltaI < 0:
                # Volume de Boro
                self.VazaoBoro = (e.LimiteInsercao + 1 - e.PosicaoBarra) * 5
                self.Vboro = self.VazaoBoro * 2
                printf("\n\nLIMITE DE INSERCAO MUITO BAIXO ATINGIDO - BORACAO DE EMERGENCIA\n\n")
                self.p.borar(self.VazaoBoro, self.Vboro)
                e = self.ve()

        # ---- R13: barra +1 ---------------------------------------------------
        if ((e.PosicaoBarra < (e.BD - 3)) and (e.DesvioDeltaI < 4.2)
                and (e.DeltaT < 0.8)):
            printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n")
            printf("\n\nPosicao Anterior do Banco D: %d passos", e.PosicaoBarra)
            printf("\n\nPosicao Atual do Banco D: %d passos\n", e.PosicaoBarra + 1)
            self.p.mover_barra(1)
            e = self.ve()

        # ---- R14: barra -1 ---------------------------------------------------
        if ((e.PosicaoBarra > (e.BD + 10)) and (e.DesvioDeltaI >= -3)
                and (e.DeltaT > -0.4)):
            printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n")
            printf("\n\nPosicao Anterior do Banco D: %d passos", e.PosicaoBarra)
            printf("\n\nPosicao Atual do Banco D: %d passos\n", e.PosicaoBarra - 1)
            self.p.mover_barra(-1)
            e = self.ve()

        # ---- R15: barra +1 ---------------------------------------------------
        if ((e.PosicaoBarra < (e.LimiteInsercao + 11)) and (e.DesvioDeltaI < 4)
                and (e.DeltaT < 0.5)):
            printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n")
            printf("\n\nPosicao Anterior do Banco D: %d passos", e.PosicaoBarra)
            printf("\n\nPosicao Atual do Banco D: %d passos\n", e.PosicaoBarra + 1)
            self.p.mover_barra(1)
            e = self.ve()

        # ---- R16: barra -1 ---------------------------------------------------
        if ((e.PosicaoBarra > 220) and (e.DesvioDeltaI >= -1.5)
                and (e.DeltaT > -0.25)):
            printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n")
            printf("\n\nPosicao Anterior do Banco D: %d passos", e.PosicaoBarra)
            printf("\n\nPosicao Atual do Banco D: %d passos\n", e.PosicaoBarra - 1)
            self.p.mover_barra(-1)
            e = self.ve()

        # ---- R17: alarme de Delta I fora da banda alvo ------------------------
        if e.DesvioDeltaI > 5 or e.DesvioDeltaI < -5:
            printf("\n\n\n\t\t\t\t\tDELTA I: %f\n", e.DeltaI)
            printf("\n\n\n\t\t\t\t\tALARME DE DELTA I FORA DA BANDA ALVO 5%c \n", 37)
            printf("t\t\t\t\t****************************************\n")
            printf("\t\t\t\t\t")
            self._despejo(e)

        # ---- R18: alarme de desvio de temperatura 1,67 °C ---------------------
        if e.DeltaT > 1.67 or e.DeltaT < -1.67:
            printf("\n\n\n\t\t\t\t  TEMPERATURA MEDIA DO SRR: %.1f\n", e.Tmed)
            printf("\n\n\n\t\t\t\tO ALARME DESVIO DE TEMPERATURA 1,67°C\n")
            printf("t\t\t\t\t****************************************\n")
            printf("\t\t\t\t")
            i = 0
            while i < 37:
                putc_raw(b'\xb1')     # printf("%c",177): UM byte, nao UTF-8
                i = i + 1
            self._despejo(e)

        # ---- R19: fim do ciclo ------------------------------------------------
        if e.Cboro < 8:
            printf("\n\n\n\t\t\t\t\tO FIM DO CICLO - PARABENS!!!!!\n")
            printf("\t\t\t\t\t")
            i = 0
            while i < 30:
                putc_raw(b'\xb1')     # printf("%c",177): UM byte, nao UTF-8
                i = i + 1
            self._despejo(e)
            self.termino = "fim"   # Força o fim para o caso de sair por aqui
        return

    def _despejo(self, e):
        """O bloco de estado que R17, R18 e R19 imprimem, identico nos tres."""
        printf("\n\n\nt=%.0f", e.t)
        printf("\nZ=%d", e.z)
        printf("\nPot=%.2f", e.Pot)
        printf("\nTmed=%.1f", e.Tmed)
        printf("\nTref=%.1f", e.Tref)
        printf("\nAlvo DeltaI=%f", e.AlvoDeltaI)
        printf("\nDeltaI=%f", e.DeltaI)
        printf("\nDesvioDeltaI=%f", e.DesvioDeltaI)
        printf("\nVariacaoDeltaI=%f", e.VariacaoDeltaI)
        printf("\nPosicao Barra=%d", e.PosicaoBarra)
        printf("\nCboro=%f\n\n\n", e.Cboro)

    # =======================================================================

    def ciclo(self):
        """Um minuto: a planta avanca, depois as 19 regras na ordem do fonte.

        As duas guardas de despacho (L1168 e L1173 do .c) sao reavaliadas sobre
        o estado corrente, e nao sobre o do inicio do ciclo — CompensacaoQueima
        pode ter mudado DesvioDeltaI antes de Corrige_DeltaI ser consultada.
        """
        self.p.passo()

        e = self.ve()
        if e.DeltaT < -0.1:
            self.CompensacaoQueima()

        e = self.ve()
        if e.DesvioDeltaI > 2 or e.DesvioDeltaI < -2:
            self.Corrige_DeltaI()

        self.regras_do_laco()

    def executa(self):
        while self.termino != "fim" and self.p.pode_continuar():
            self.ciclo()
        printf("\n\nFim do Programa\n\n")


# ---------------------------------------------------------------------------
# Linha de comando — a mesma de simulador.py, para a comparacao ser direta
# ---------------------------------------------------------------------------

_RE_FLOAT = re.compile(r'\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')
_RE_INT = re.compile(r'\s*[+-]?\d+')


def atof(s):
    m = _RE_FLOAT.match(s)
    return float(m.group(0)) if m else 0.0


def atoi(s):
    m = _RE_INT.match(s)
    return int(m.group(0)) if m else 0


def main(argv):
    transiente = None
    alvo = taxa = 0.0
    t_transiente = 10
    tmax = 700000.0
    arquivo = "Modelagem_Reator_api.txt"
    capturar = False
    api = None

    for arg in argv[1:]:
        if arg.startswith("--transiente="):
            val = arg[13:]
            if val not in NOMES_TRANSIENTE:
                sys.stderr.write("Transiente desconhecido: %s\n" % val)
                return 1
            transiente = val
        elif arg.startswith("--alvo="):
            alvo = atof(arg[7:])
        elif arg.startswith("--taxa="):
            taxa = atof(arg[7:])
        elif arg.startswith("--t-transiente="):
            t_transiente = atoi(arg[15:])
        elif arg.startswith("--tmax="):
            tmax = atof(arg[7:])
        elif arg.startswith("--arquivo="):
            arquivo = arg[10:]
        elif arg == "--capturar":
            capturar = True
        elif arg.startswith("--api="):
            api = arg[6:]
        else:
            sys.stderr.write("Argumento desconhecido: %s\n" % arg)
            return 1
    if transiente == "rampa" and taxa <= 0:
        sys.stderr.write("--transiente=rampa exige --alvo=<MW> e --taxa=<MW/min> positiva\n")
        return 1

    # Os 7 valores que o operador digitaria, na ordem dos prompts.
    tokens = sys.stdin.read().split()
    v = [atof(x) for x in tokens] + [0.0] * 7
    pot_turbina, cboro, posicao_barra, tempodilute, t1, t2, delta_i = v[:7]

    win = os.environ.get('WIN_ORIGINAL', '') not in ('', '0')
    nome_transiente = transiente

    def corrida():
        if api:
            # No modo remoto a partida ja acontece no construtor: e o
            # POST /reactor/initialize que cria a sessao e imprime o prologo.
            planta = PlantaRemota(api, {
                "pot_turbina": pot_turbina, "cboro": cboro,
                "posicao_barra": int(posicao_barra), "tempodilute": int(tempodilute),
                "t1": t1, "t2": t2, "delta_i": delta_i, "tmax": tmax,
                "transiente": nome_transiente, "t_transiente": t_transiente,
                "alvo": alvo, "taxa": taxa, "win_original": win,
                "arquivo": os.path.basename(arquivo),
            })
            try:
                BracoProcedural(planta).executa()
            finally:
                planta.encerra()
        else:
            # So aqui a planta e necessaria — e so aqui ela e importada.
            from physics import Planta, TRANSIENTES, TR_NENHUM
            planta = Planta(arquivo=arquivo, win_original=win)
            planta.inicializa(pot_turbina, cboro, int(posicao_barra), int(tempodilute),
                              t1, t2, delta_i, tmax=tmax,
                              transiente=TRANSIENTES.get(transiente, TR_NENHUM),
                              t_transiente=t_transiente, alvo=alvo, taxa=taxa)
            BracoProcedural(planta).executa()

    if capturar:
        # Caminho do servico: cada trecho volta num buffer e e remontado.
        with saida.captura() as buf:
            corrida()
        sys.stdout.buffer.write(bytes(buf))
    else:
        corrida()
    sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    try:
        codigo = main(sys.argv)
    except BrokenPipeError:
        codigo = 0
    sys.exit(codigo)
