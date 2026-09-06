#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
observacao.py — o estado da planta com o tipo C restaurado.

O reator entrega JSON, e JSON so tem um tipo numerico. Mas o controlador calcula
com esses numeros — `LimiteInsercao+11`, `(-DesvioDeltaI)*6`, `-a*DeltaT+b` — e
no C essas contas arredondam a 32 bits a cada operacao.

GET /reactor/tipos diz, para cada grandeza, se ela e `float` de 32 bits, `int`
ou `double`. Aqui cada valor volta para o seu tipo, e a aritmetica das regras
passa a arredondar nos mesmos pontos que o C. Sem isto o expert decidiria igual
quase sempre — e "quase sempre" desloca um evento de diluicao e desfaz a fase do
resto da corrida (steps/01-porte-linux-simulador.md).
"""

from f32 import F


def espaco(estado, tipos):
    """Dicionario pronto para servir de espaco de nomes das expressoes."""
    ns = {}
    for nome, valor in estado.items():
        tipo = tipos.get(nome, "float")
        if tipo == "int":
            ns[nome] = int(valor)
        elif tipo == "double":
            ns[nome] = float(valor)
        else:
            ns[nome] = F(valor)
    return ns
