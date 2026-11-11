"""Prova de vida por desafio de piscada.

Uma foto impressa ou exibida em um celular tem o rosto certo, mas não pisca.
O desafio pede ao usuário que mantenha os olhos abertos, pisque e abra de
novo. O detector de olhos de Haar encontra apenas olhos ABERTOS; portanto uma
piscada aparece como: olhos detectados -> não detectados -> detectados.

Limitações assumidas (discutidas no relatório): (1) um vídeo gravado do
usuário piscando poderia, em tese, passar; (2) o detector de Haar falha de
forma intermitente, de modo que uma foto em movimento poderia, por acaso,
simular "olhos não detectados". Por isso a piscada exige DOIS quadros
consecutivos sem os dois olhos, e a autenticação só se conclui depois que a
identidade é reconfirmada nos quadros finais (ver autenticacao.py). A prova de
vida é uma camada que encarece o ataque, não uma garantia absoluta
(ISO/IEC 30107-1:2016).
"""

ABERTOS_INICIAIS = 3     # quadros consecutivos com os dois olhos abertos
FECHADOS_MINIMOS = 2     # quadros CONSECUTIVOS com menos de dois olhos detectados
ABERTOS_FINAIS = 2       # quadros consecutivos reabertos


class DesafioPiscada:
    AGUARDA_ABERTOS = 0
    AGUARDA_PISCADA = 1
    AGUARDA_REABERTURA = 2
    CONCLUIDO = 3

    def __init__(self):
        self.reiniciar()

    def reiniciar(self):
        self.estado = self.AGUARDA_ABERTOS
        self._contador = 0

    @property
    def concluido(self):
        return self.estado == self.CONCLUIDO

    @property
    def instrucao(self):
        return {
            self.AGUARDA_ABERTOS: "Olhe para a camera com os olhos abertos",
            self.AGUARDA_PISCADA: "Agora PISQUE",
            self.AGUARDA_REABERTURA: "Abra os olhos",
            self.CONCLUIDO: "Prova de vida concluida",
        }[self.estado]

    def registrar(self, olhos_detectados):
        """Alimenta o desafio com o nº de olhos abertos do quadro.

        Passe None quando não houve rosto: o desafio recomeça, pois a pessoa
        saiu de cena e não se pode juntar partes de pessoas diferentes.
        """
        if olhos_detectados is None:
            self.reiniciar()
            return self.estado

        abertos = olhos_detectados >= 2
        if self.estado == self.AGUARDA_ABERTOS:
            self._contador = self._contador + 1 if abertos else 0
            if self._contador >= ABERTOS_INICIAIS:
                self.estado, self._contador = self.AGUARDA_PISCADA, 0
        elif self.estado == self.AGUARDA_PISCADA:
            self._contador = self._contador + 1 if not abertos else 0
            if self._contador >= FECHADOS_MINIMOS:
                self.estado, self._contador = self.AGUARDA_REABERTURA, 0
        elif self.estado == self.AGUARDA_REABERTURA:
            self._contador = self._contador + 1 if abertos else 0
            if self._contador >= ABERTOS_FINAIS:
                self.estado = self.CONCLUIDO
        return self.estado
