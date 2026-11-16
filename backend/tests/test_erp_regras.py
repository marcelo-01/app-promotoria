"""As regras do que entra como mercadoria no cliente, e o casamento com o cadastro."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.merchandising import invoices
from app.merchandising import service as svc
from app.merchandising.schemas import ErpSyncPackage
from erp_pacote import pacote

DE, ATE = date(2026, 7, 20), date(2026, 11, 16)


def _lido(dados: dict, origem: str = "sales", kind: str = "venda") -> invoices.Parsed:
    p = ErpSyncPackage.model_validate(dados)
    return invoices.from_package(
        getattr(p, origem),
        {c.erp_id: c for c in p.customers},
        {x.erp_id: x for x in p.products},
        kind, p.first_day, p.last_day,
    )


def _item(product: int, cfop: str, pieces: float) -> dict:
    return {"product": product, "cfop": cfop, "pieces": pieces}


def test_faturamento_aceita_so_cfop_de_saida():
    dados = pacote()
    dados["sales"][0]["items"] = [
        _item(26, "5101", 1), _item(26, "6102", 2), _item(9616, "1202", 3), _item(9776, "", 4),
    ]
    lido = _lido(dados)
    assert [r.cfop for r in lido.rows] == ["5101", "6102"]
    assert (lido.total, lido.ignored_cfop, lido.ignored_incomplete) == (4, 2, 0)


def test_brinde_aceita_so_remessa_ao_cliente():
    dados = pacote()
    dados["gifts"][0]["items"] = [
        _item(9616, "5910", 1), _item(9616, "6910", 2), _item(26, "6209", 3), _item(26, "5927", 4),
    ]
    lido = _lido(dados, "gifts", "brinde")
    assert [r.cfop for r in lido.rows] == ["5910", "6910"]
    assert lido.ignored_cfop == 2
    assert lido.rows[0].reason == "BRINDE - DANIFICADO NO CLIENTE"


def test_item_sem_pecas_ou_produto_sem_codigo_fica_de_fora():
    dados = pacote()
    dados["products"][2]["code"] = None
    dados["sales"][0]["items"] = [_item(26, "5101", 0), _item(9776, "5101", 5), _item(9616, "5101", 16)]
    lido = _lido(dados)
    assert [r.product_code for r in lido.rows] == ["A170003"]
    assert lido.ignored_incomplete == 2


def test_linha_limpa_traz_a_chave_e_o_casamento():
    dados = pacote()
    dados["customers"][0]["document"] = "11.222.333/0001-81"
    dados["sales"][0]["company"] = None
    linha = _lido(dados).rows[0]
    assert linha.customer_document == "11222333000181"
    assert (linha.company, linha.sale_number, linha.invoice) == ("—", "746308", "642862")
    assert (linha.customer_code, linha.product_code, linha.quantity) == ("900001", "A51001", 24.0)
    assert linha.issued_on == date(2026, 10, 16)


def test_casar_por_cnpj_e_codigo_soma_o_mesmo_produto_e_relata_o_que_faltou():
    dados = pacote()
    # O mesmo produto em dois CFOPs na mesma nota soma numa entrada só; o requeijão
    # não está no cadastro do app e o segundo cliente também não.
    dados["sales"][0]["items"] = [_item(26, "5101", 24), _item(26, "5102", 6), _item(9776, "5101", 10)]
    dados["sales"].append({
        "number": 746620, "issued_on": "2026-10-19", "invoice": "054568",
        "company": "LEITE MAIS VIDA - FILIAL ES", "customer": 502,
        "items": [_item(26, "5102", 12)],
    })
    mercado_a, manteiga = uuid4(), uuid4()
    relato, entradas = svc._casar(
        _lido(dados), "venda", {"A51001": manteiga}, {"11222333000181": mercado_a}
    )

    assert len(entradas) == 1
    entrada = entradas[0]
    assert (entrada["customer_id"], entrada["product_id"]) == (mercado_a, manteiga)
    assert entrada["quantity"] == Decimal("30")
    assert (entrada["company"], entrada["sale_number"], entrada["cfop"]) == (
        "LEITE MAIS VIDA - MATRIZ", "746308", "5101"
    )
    assert relato.matched_lines == 2
    assert relato.matched_quantity == Decimal("30")
    assert relato.matched_customers == 1
    assert [(u.code, u.lines) for u in relato.unknown_products] == [("A191", 1)]
    assert [(u.code, u.document) for u in relato.unknown_customers] == [
        ("900002", "44555666000199")
    ]
    assert (relato.unknown_products_total, relato.unknown_customers_total) == (1, 1)
    assert (relato.first_day, relato.last_day) == (DE, ATE)


def test_quebra_por_motivo_conta_so_o_que_entrou():
    dados = pacote()
    lido = _lido(dados, "gifts", "brinde")
    queijo, mercado_b = uuid4(), uuid4()
    relato, entradas = svc._casar(lido, "brinde", {"A170003": queijo}, {"44555666000199": mercado_b})
    assert len(entradas) == 1
    assert [(m.code, m.lines, m.quantity) for m in relato.by_reason] == [
        ("BRINDE - DANIFICADO NO CLIENTE", 1, Decimal("5"))
    ]


def test_lista_de_clientes_sem_cadastro_vem_cortada_com_o_total():
    dados = pacote(gifts=[])
    dados["customers"] = [
        {"erp_id": i, "code": str(i), "document": f"{i:014d}", "name": f"C{i}"} for i in range(1, 251)
    ]
    dados["sales"] = [
        {"number": 1000 + i, "issued_on": "2026-10-01", "customer": i, "items": [_item(26, "5101", 1)]}
        for i in range(1, 251)
    ]
    relato, entradas = svc._casar(_lido(dados), "venda", {"A51001": uuid4()}, {})
    assert entradas == []
    assert relato.unknown_customers_total == 250
    assert len(relato.unknown_customers) == svc._LISTA_MAX
