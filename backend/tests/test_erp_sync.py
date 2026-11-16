"""O transporte da sincronização com o ERP: assinatura, relógio, tamanho e integridade."""
import gzip
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

from app.merchandising import erp_sync
from app.merchandising.erp_sync import Recusado
from erp_pacote import CHAVE, compactado, pacote


def _codigo(funcao, *args, **kwargs) -> str:
    with pytest.raises(Recusado) as recusa:
        funcao(*args, **kwargs)
    return recusa.value.codigo


# ── Assinatura e relógio ─────────────────────────────────────────────────────


def test_assinatura_certa_devolve_a_hora_do_envio():
    corpo = compactado(pacote())
    data = str(int(time.time()))
    enviado = erp_sync.conferir_assinatura(
        CHAVE, data, erp_sync.assinar(CHAVE, data, corpo), corpo, int(data) + 30
    )
    assert int(enviado.timestamp()) == int(data)


def test_chave_errada_e_pacote_alterado_nao_passam():
    corpo = compactado(pacote())
    data = str(int(time.time()))
    assinatura = erp_sync.assinar(CHAVE, data, corpo)
    agora = int(data)

    errada = erp_sync.assinar("x" * 43, data, corpo)
    assert _codigo(erp_sync.conferir_assinatura, CHAVE, data, errada, corpo, agora) == (
        "ASSINATURA_INVALIDA"
    )
    alterado = corpo + b"\x00"
    assert _codigo(
        erp_sync.conferir_assinatura, CHAVE, data, assinatura, alterado, agora
    ) == "ASSINATURA_INVALIDA"
    assert _codigo(erp_sync.conferir_assinatura, CHAVE, data, None, corpo, agora) == (
        "ASSINATURA_INVALIDA"
    )


def test_relogio_fora_da_tolerancia_e_hora_ausente_sao_recusados():
    corpo = b"corpo"
    data = str(int(time.time()))
    assinatura = erp_sync.assinar(CHAVE, data, corpo)
    atrasado = int(data) + erp_sync.TOLERANCIA_RELOGIO + 1
    assert _codigo(
        erp_sync.conferir_assinatura, CHAVE, data, assinatura, corpo, atrasado
    ) == "RELOGIO"
    assert _codigo(erp_sync.conferir_assinatura, CHAVE, "", assinatura, corpo, 0) == "SEM_DATA"
    assert _codigo(erp_sync.conferir_assinatura, CHAVE, "abc", assinatura, corpo, 0) == "SEM_DATA"


# ── Descompressão ───────────────────────────────────────────────────────────


def test_gzip_que_passa_do_teto_para_antes_de_ocupar_a_memoria():
    bomba = gzip.compress(b"0" * 10_000)
    with pytest.raises(Recusado) as recusa:
        erp_sync.descompactar(bomba, limite=1000)
    assert recusa.value.codigo == "PACOTE_GRANDE"
    assert recusa.value.status == 413


def test_gzip_corrompido_ou_cortado_e_recusado():
    assert _codigo(erp_sync.descompactar, b"isto nao e gzip") == "PACOTE_INVALIDO"
    inteiro = gzip.compress(b"x" * 5000)
    assert _codigo(erp_sync.descompactar, inteiro[: len(inteiro) // 2]) == "PACOTE_INVALIDO"


# ── Formato e integridade do pacote ─────────────────────────────────────────


def test_pacote_bom_passa_inteiro():
    lido = erp_sync.ler_pacote(compactado(pacote()))
    assert [n.number for n in lido.sales] == [746308]
    assert [n.number for n in lido.gifts] == [77246]
    assert lido.gifts[0].reason == "BRINDE - DANIFICADO NO CLIENTE"
    assert lido.force is False


def test_origem_ausente_fica_nula_e_as_duas_ausentes_sao_recusadas():
    dados = pacote()
    del dados["gifts"]
    assert erp_sync.ler_pacote(compactado(dados)).gifts is None

    del dados["sales"]
    assert _codigo(erp_sync.ler_pacote, compactado(dados)) == "PACOTE_VAZIO"


def test_nota_fora_do_periodo_repetida_ou_sem_cadastro_derruba_o_pacote():
    fora = pacote()
    fora["sales"][0]["issued_on"] = "2026-07-19"
    assert _codigo(erp_sync.ler_pacote, compactado(fora)) == "NOTA_FORA_DO_PERIODO"

    repetida = pacote()
    repetida["gifts"].append(dict(repetida["gifts"][0]))
    assert _codigo(erp_sync.ler_pacote, compactado(repetida)) == "NOTA_REPETIDA"

    sem_cliente = pacote()
    sem_cliente["sales"][0]["customer"] = 1
    assert _codigo(erp_sync.ler_pacote, compactado(sem_cliente)) == "CLIENTE_AUSENTE"

    sem_produto = pacote()
    sem_produto["sales"][0]["items"][0]["product"] = 1
    assert _codigo(erp_sync.ler_pacote, compactado(sem_produto)) == "PRODUTO_AUSENTE"


def test_periodo_invertido_ou_longo_demais_e_recusado():
    invertido = pacote(first_day="2026-11-17", last_day="2026-11-16", sales=[], gifts=[])
    assert _codigo(erp_sync.ler_pacote, compactado(invertido)) == "PERIODO_INVALIDO"
    longo = pacote(first_day="2025-01-01", last_day="2026-11-16", sales=[], gifts=[])
    assert _codigo(erp_sync.ler_pacote, compactado(longo)) == "PERIODO_INVALIDO"


def test_conteudo_que_nao_e_o_pacote_e_recusado_com_o_campo():
    with pytest.raises(Recusado) as recusa:
        erp_sync.ler_pacote(gzip.compress(b"[1, 2"))
    assert recusa.value.codigo == "PACOTE_INVALIDO"

    errado = pacote()
    errado["sales"][0]["items"][0]["pieces"] = "vinte"
    with pytest.raises(Recusado) as recusa:
        erp_sync.ler_pacote(compactado(errado))
    assert recusa.value.codigo == "PACOTE_INVALIDO"
    assert "pieces" in recusa.value.mensagem


# ── O contrato com o computador da empresa ──────────────────────────────────

_SINCRONIZAR = Path(__file__).resolve().parents[2] / "sync" / "sincronizar.py"


@pytest.mark.skipif(not _SINCRONIZAR.exists(), reason="sync/ fora do contêiner da API")
def test_o_envio_do_sincronizar_py_passa_na_conferencia_do_servidor(monkeypatch):
    """O script do computador e a API assinam do mesmo jeito: se um mudar sem o
    outro, toda sincronização passa a voltar 'assinatura inválida'."""
    spec = importlib.util.spec_from_file_location("sincronizar", _SINCRONIZAR)
    sincronizar = importlib.util.module_from_spec(spec)
    sys.modules["sincronizar"] = sincronizar
    spec.loader.exec_module(sincronizar)

    capturado = {}

    class Resposta:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode()

    def urlopen(req, timeout):
        capturado["req"] = req
        return Resposta()

    monkeypatch.setattr(sincronizar.urllib.request, "urlopen", urlopen)
    corpo = compactado(pacote())
    sincronizar.enviar("https://estoque.exemplo/api", CHAVE, corpo)

    req = capturado["req"]
    assert req.full_url == "https://estoque.exemplo/api/merchandising/erp/sync"
    cabecalhos = {k.lower(): v for k, v in req.header_items()}
    enviado = erp_sync.conferir_assinatura(
        CHAVE,
        cabecalhos[erp_sync.CABECALHO_DATA.lower()],
        cabecalhos[erp_sync.CABECALHO_ASSINATURA.lower()],
        req.data,
        time.time(),
    )
    assert enviado is not None
    assert erp_sync.ler_pacote(req.data).sales[0].number == 746308
