"""O pacote com o faturamento e os brindes do ERP, mandado pelo computador da empresa.

O ERP (Firebird) roda na empresa, e a cópia do banco dele fica num computador de
lá — o mesmo de onde o BI Mais Vida e o EFFEX Trade tiram os dados. O
`sync/sincronizar.py` lê as notas de venda e de brinde dos últimos 120 dias e
manda tudo para cá num pacote só: JSON compactado em gzip e assinado com
HMAC-SHA256 da hora do envio e do hash do conteúdo, o mesmo esquema do BI e do
EFFEX. A chave fica no `sync/config.ini` e na ERP_SYNC_KEY do servidor e nunca
trafega.

Este módulo é o lado de cá do transporte: confere a hora, a assinatura e o
tamanho, descompacta com teto e confere a integridade do pacote. Não fala com o
banco — quem casa com o cadastro e grava é o serviço.

A ORDEM DAS CONFERÊNCIAS NÃO É DETALHE
--------------------------------------
A assinatura é conferida sobre os bytes recebidos, antes de descompactar: quem
não tem a chave não consegue mandar um pacote que explode na memória (um gzip
de 1 MB pode virar 1 GB). Só depois dela vêm a descompressão, com teto, o JSON
e o formato.
"""
import hashlib
import hmac
import json
import re
import zlib
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from app.merchandising.schemas import ErpSyncPackage

CABECALHO_DATA = "X-Estoque-Data"
CABECALHO_ASSINATURA = "X-Estoque-Assinatura"

# Diferença aceita entre o relógio do computador que envia e o do servidor.
TOLERANCIA_RELOGIO = 15 * 60
# 120 dias de notas dão uns 2 MB compactados (110 mil itens em nov/2026).
LIMITE_PACOTE = 20 * 1024 * 1024
LIMITE_JSON = 200 * 1024 * 1024
# `secrets.token_urlsafe(32)` dá 43 caracteres; menos que isto é chave fraca.
MIN_CHAVE = 32
# O computador manda 120 dias: um período muito maior é erro no envio.
MAX_DIAS_PERIODO = 400


class Recusado(Exception):
    """Pacote que não entra, com o motivo para quem rodou a sincronização.

    `codigo` é o que o `sincronizar.py` lê para sugerir o que fazer (o
    `MUITAS_REMOCOES`, por exemplo, pede para rodar de novo com --forcar).
    """

    def __init__(self, status: int, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem


def assinar(chave: str, data: str, corpo: bytes) -> str:
    """HMAC-SHA256 de "<hora do envio>\\n<sha256 do corpo>", em hexadecimal."""
    hash_corpo = hashlib.sha256(corpo).hexdigest()
    return hmac.new(
        chave.encode(), f"{data}\n{hash_corpo}".encode(), hashlib.sha256
    ).hexdigest()


def conferir_assinatura(
    chave: str, data: Optional[str], assinatura: Optional[str], corpo: bytes,
    agora: float,
) -> datetime:
    """A hora do envio, se o relógio está dentro da tolerância e a assinatura
    confere. `agora` em segundos (time.time())."""
    data = (data or "").strip()
    if not re.fullmatch(r"\d{9,11}", data):
        raise Recusado(401, "SEM_DATA", "O pedido veio sem a hora do envio.")
    if abs(agora - int(data)) > TOLERANCIA_RELOGIO:
        raise Recusado(
            401, "RELOGIO",
            "O relógio do computador que envia está mais de 15 minutos diferente "
            "do servidor (acerte a hora do Windows).",
        )
    esperada = assinar(chave, data, corpo).encode()
    recebida = (assinatura or "").strip().encode("utf-8", "replace")
    if not hmac.compare_digest(esperada, recebida):
        raise Recusado(
            401, "ASSINATURA_INVALIDA",
            "Assinatura inválida: a chave do sync/config.ini não é a mesma "
            "ERP_SYNC_KEY do servidor (ou o pacote foi alterado no caminho).",
        )
    return datetime.fromtimestamp(int(data), tz=timezone.utc)


def descompactar(corpo: bytes, limite: int = LIMITE_JSON) -> bytes:
    """gzip → bytes, sem passar de `limite` (a bomba de gzip para aqui)."""
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        saida = d.decompress(corpo, limite)
    except zlib.error:
        raise Recusado(
            400, "PACOTE_INVALIDO", "Pacote corrompido: não foi possível descompactar."
        ) from None
    if d.unconsumed_tail:
        raise Recusado(
            413, "PACOTE_GRANDE",
            f"O pacote descompactado passa de {limite // (1024 * 1024)} MB.",
        )
    if not d.eof:
        raise Recusado(
            400, "PACOTE_INVALIDO", "Pacote incompleto: o envio foi cortado no caminho."
        )
    return saida


def ler_pacote(corpo: bytes) -> ErpSyncPackage:
    """Bytes já assinados → pacote validado e íntegro.

    É CPU pura (descompactar, ler o JSON e validar 100 mil itens): chame fora do
    event loop, senão a API inteira — a contagem do promotor, o login — espera.
    """
    texto = descompactar(corpo)
    try:
        dados = json.loads(texto)
    except ValueError:
        raise Recusado(
            400, "PACOTE_INVALIDO", "Pacote corrompido: o conteúdo não é JSON."
        ) from None
    try:
        pacote = ErpSyncPackage.model_validate(dados)
    except ValidationError as erro:
        primeiro = erro.errors()[0]
        onde = ".".join(str(p) for p in primeiro.get("loc", ()))
        raise Recusado(
            400, "PACOTE_INVALIDO",
            f"Pacote fora do formato esperado ({onde}: {primeiro.get('msg')}).",
        ) from None
    conferir_pacote(pacote)
    return pacote


_ROTULO = {"sales": "A venda", "gifts": "O brinde"}


def conferir_pacote(pacote: ErpSyncPackage) -> None:
    """O que o formato sozinho não garante: o período, as notas dentro dele e
    as referências de cada nota.

    O envio troca o período inteiro, então uma nota fora dele ficaria gravada
    sem nunca ser trocada — e uma nota repetida entraria em dobro.
    """
    if pacote.sales is None and pacote.gifts is None:
        raise Recusado(400, "PACOTE_VAZIO", "O pacote veio sem as vendas e sem os brindes.")

    de, ate = pacote.first_day, pacote.last_day
    if de > ate or (ate - de).days > MAX_DIAS_PERIODO:
        raise Recusado(
            400, "PERIODO_INVALIDO",
            f"Período inválido no pacote: {de:%d/%m/%Y} a {ate:%d/%m/%Y}.",
        )

    clientes = {c.erp_id for c in pacote.customers}
    produtos = {p.erp_id for p in pacote.products}
    for origem in ("sales", "gifts"):
        notas = getattr(pacote, origem)
        if notas is None:
            continue
        rotulo = _ROTULO[origem]
        vistas: set[int] = set()
        for nota in notas:
            if nota.number in vistas:
                raise Recusado(
                    400, "NOTA_REPETIDA",
                    f"{rotulo} {nota.number} aparece duas vezes no pacote.",
                )
            vistas.add(nota.number)
            if not de <= nota.issued_on <= ate:
                raise Recusado(
                    400, "NOTA_FORA_DO_PERIODO",
                    f"{rotulo} {nota.number} é de {nota.issued_on:%d/%m/%Y}, fora do "
                    f"período do pacote ({de:%d/%m/%Y} a {ate:%d/%m/%Y}).",
                )
            if nota.customer not in clientes:
                raise Recusado(
                    400, "CLIENTE_AUSENTE",
                    f"{rotulo} {nota.number} aponta para o cliente {nota.customer}, "
                    "que não veio no pacote.",
                )
            for item in nota.items:
                if item.product not in produtos:
                    raise Recusado(
                        400, "PRODUTO_AUSENTE",
                        f"{rotulo} {nota.number} aponta para o produto {item.product}, "
                        "que não veio no pacote.",
                    )
