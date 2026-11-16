"""O recebimento da sincronização: os freios e a gravação, com o banco trocado por dublê."""
import time
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.infrastructure.persistence.session import get_db_session
from app.merchandising import erp_sync
from app.merchandising import service as svc
from app.merchandising.schemas import ErpSyncPackage, ErpSyncResponse
from erp_pacote import CHAVE, compactado, pacote

TENANT = uuid4()
MANTEIGA, QUEIJO, MERCADO_A, MERCADO_B = uuid4(), uuid4(), uuid4(), uuid4()
AGORA = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class Banco:
    """O que o serviço pede ao repositório, com o que ele gravou."""

    def __init__(self, ultimo_envio=None, antes=0):
        self.ultimo_envio = ultimo_envio
        self.antes = antes
        self.trocas = []
        self.recibos = []

    def instalar(self, monkeypatch):
        repo = svc.Repo

        async def tenant(session):
            return TENANT

        async def ultimo(session, tenant_id):
            return self.ultimo_envio

        async def produtos(session, tenant_id):
            return {"A51001": MANTEIGA, "A170003": QUEIJO}

        async def clientes(session, tenant_id):
            return {"11222333000181": MERCADO_A, "44555666000199": MERCADO_B}

        async def contar(session, tenant_id, kind, de, ate):
            return self.antes

        async def trocar(session, tenant_id, kind, de, ate, entradas):
            self.trocas.append((kind, de, ate, entradas))

        async def recibos(session, tenant_id, lista):
            self.recibos.extend(lista)

        monkeypatch.setattr(repo, "single_active_tenant_id", tenant)
        monkeypatch.setattr(repo, "last_erp_sent_at", ultimo)
        monkeypatch.setattr(repo, "products_by_sku", produtos)
        monkeypatch.setattr(repo, "customers_by_document", clientes)
        monkeypatch.setattr(repo, "count_deliveries_in_period", contar)
        monkeypatch.setattr(repo, "replace_deliveries_in_period", trocar)
        monkeypatch.setattr(repo, "save_erp_receipts", recibos)
        return self


def _pacote(**mudancas) -> ErpSyncPackage:
    return ErpSyncPackage.model_validate(pacote(**mudancas))


@pytest.mark.asyncio
async def test_grava_as_duas_origens_no_periodo_e_deixa_um_recibo_com_relato(monkeypatch):
    banco = Banco(antes=3).instalar(monkeypatch)
    resposta = await svc.MerchandisingService.receive_erp_sync(None, _pacote(), AGORA)

    assert [(k, de, ate, len(e)) for k, de, ate, e in banco.trocas] == [
        ("venda", date(2026, 7, 20), date(2026, 11, 16), 2),
        ("brinde", date(2026, 7, 20), date(2026, 11, 16), 1),
    ]
    assert [(r.kind, r.source, r.sent_at, r.matched_lines) for r in banco.recibos] == [
        ("venda", "erp", AGORA, 2), ("brinde", "erp", AGORA, 1),
    ]
    assert banco.recibos[0].report["previous_lines"] == 3
    assert resposta.sales.matched_lines == 2
    assert resposta.gifts.unknown_products_total == 1  # o requeijão
    assert resposta.copy_at is not None


@pytest.mark.asyncio
async def test_origem_que_nao_veio_fica_como_estava(monkeypatch):
    banco = Banco().instalar(monkeypatch)
    resposta = await svc.MerchandisingService.receive_erp_sync(None, _pacote(gifts=None), AGORA)
    assert [k for k, *_ in banco.trocas] == ["venda"]
    assert resposta.gifts is None


@pytest.mark.asyncio
async def test_pacote_igual_ou_mais_velho_que_o_ultimo_e_recusado(monkeypatch):
    banco = Banco(ultimo_envio=AGORA).instalar(monkeypatch)
    with pytest.raises(erp_sync.Recusado) as recusa:
        await svc.MerchandisingService.receive_erp_sync(None, _pacote(), AGORA)
    assert recusa.value.codigo == "REENVIO"
    assert banco.trocas == [] and banco.recibos == []

    banco.ultimo_envio = AGORA - timedelta(seconds=1)
    await svc.MerchandisingService.receive_erp_sync(None, _pacote(), AGORA)
    assert len(banco.recibos) == 2


@pytest.mark.asyncio
async def test_envio_que_apagaria_mais_da_metade_pede_confirmacao(monkeypatch):
    banco = Banco(antes=500).instalar(monkeypatch)
    with pytest.raises(erp_sync.Recusado) as recusa:
        await svc.MerchandisingService.receive_erp_sync(None, _pacote(), AGORA)
    assert recusa.value.codigo == "MUITAS_REMOCOES"
    assert "500" in recusa.value.mensagem
    # Nada foi gravado: o freio vem antes da primeira troca
    assert banco.trocas == [] and banco.recibos == []

    await svc.MerchandisingService.receive_erp_sync(None, _pacote(force=True), AGORA)
    assert len(banco.trocas) == 2


@pytest.mark.asyncio
async def test_sem_uma_empresa_ativa_nao_ha_de_quem_seja_o_pacote(monkeypatch):
    Banco().instalar(monkeypatch)

    async def nenhum(session):
        return None

    monkeypatch.setattr(svc.Repo, "single_active_tenant_id", nenhum)
    with pytest.raises(erp_sync.Recusado) as recusa:
        await svc.MerchandisingService.receive_erp_sync(None, _pacote(), AGORA)
    assert recusa.value.codigo == "SEM_EMPRESA"


# ── A rota ──────────────────────────────────────────────────────────────────


@pytest.fixture
def cliente(monkeypatch):
    from app.main import app

    async def sem_banco():
        yield None

    app.dependency_overrides[get_db_session] = sem_banco
    monkeypatch.setattr(settings, "erp_sync_key", CHAVE)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _enviar(cliente, corpo: bytes, chave: str = CHAVE, data: str | None = None):
    data = data or str(int(time.time()))
    return cliente.post(
        "/merchandising/erp/sync",
        content=corpo,
        headers={
            "Content-Type": "application/gzip",
            erp_sync.CABECALHO_DATA: data,
            erp_sync.CABECALHO_ASSINATURA: erp_sync.assinar(chave, data, corpo),
        },
    )


def test_rota_sem_chave_no_servidor_fica_desligada(cliente, monkeypatch):
    monkeypatch.setattr(settings, "erp_sync_key", "")
    r = _enviar(cliente, compactado(pacote()))
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "SINCRONIZACAO_DESLIGADA"

    monkeypatch.setattr(settings, "erp_sync_key", "curta")
    assert _enviar(cliente, compactado(pacote()), chave="curta").json()["detail"]["code"] == (
        "CHAVE_FRACA"
    )


def test_rota_recusa_assinatura_de_outra_chave(cliente):
    r = _enviar(cliente, compactado(pacote()), chave="z" * 43)
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "ASSINATURA_INVALIDA"


def test_rota_entrega_o_pacote_conferido_ao_servico(cliente, monkeypatch):
    recebido = {}

    async def receber(session, package, sent_at):
        recebido.update(package=package, sent_at=sent_at)
        return ErpSyncResponse(
            received_at=AGORA, first_day=package.first_day, last_day=package.last_day
        )

    monkeypatch.setattr(svc.MerchandisingService, "receive_erp_sync", receber)
    r = _enviar(cliente, compactado(pacote()))
    assert r.status_code == 200, r.text
    assert r.json()["first_day"] == "2026-07-20"
    assert recebido["package"].sales[0].number == 746308
    assert recebido["sent_at"].tzinfo is not None


def test_rota_devolve_o_motivo_do_pacote_quebrado(cliente):
    dados = pacote()
    dados["sales"][0]["issued_on"] = "2026-12-01"
    r = _enviar(cliente, compactado(dados))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "NOTA_FORA_DO_PERIODO"
