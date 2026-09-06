"""
Simulador de Reatividade de Reatores Nucleares PWR — a planta.

Modelo fisico do reator exposto por API (porta 8008). NAO contem regras de
controle: as 19 regras levantadas em steps/03-regras-controle.md ficam no
servico expert. Ver steps/04-servico-reactor.md para onde passa a fronteira.
"""

__version__ = "0.1.0"
__author__ = "Leonardo loures"
__description__ = "API RESTful do modelo fisico de um reator PWR, sem controle"
