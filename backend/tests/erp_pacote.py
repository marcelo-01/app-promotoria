"""Um pacote de sincronização de exemplo, no formato que o `sync/sincronizar.py` manda.

Os números vêm de notas reais de out/2026 (venda 746308, brinde 77246), com
cliente e CNPJ trocados.
"""
import copy
import gzip
import json

CHAVE = "k" * 43

PACOTE = {
    "copy_at": "2026-11-16T08:43:18-03:00",
    "first_day": "2026-07-20",
    "last_day": "2026-11-16",
    "customers": [
        {"erp_id": 501, "code": "900001", "document": "11222333000181", "name": "MERCADO A"},
        {"erp_id": 502, "code": "900002", "document": "44555666000199", "name": "MERCADO B"},
    ],
    "products": [
        {"erp_id": 26, "code": "A51001", "name": "MANTEIGA 500G"},
        {"erp_id": 9616, "code": "A170003", "name": "QUEIJO DE COALHO 370G PALITO"},
        {"erp_id": 9776, "code": "A191", "name": "REQUEIJAO CREMOSO 200G"},
    ],
    "sales": [
        {
            "number": 746308, "issued_on": "2026-10-16", "invoice": "642862",
            "company": "LEITE MAIS VIDA - MATRIZ", "customer": 501,
            "items": [
                {"product": 26, "cfop": "5101", "pieces": 24},
                {"product": 9616, "cfop": "5101", "pieces": 16},
            ],
        },
    ],
    "gifts": [
        {
            "number": 77246, "issued_on": "2026-10-16", "invoice": "642802",
            "company": "LEITE MAIS VIDA - MATRIZ", "customer": 502,
            "reason": "BRINDE - DANIFICADO NO CLIENTE",
            "items": [
                {"product": 9616, "cfop": "5910", "pieces": 5},
                {"product": 9776, "cfop": "5910", "pieces": 7},
            ],
        },
    ],
}


def pacote(**mudancas) -> dict:
    dados = copy.deepcopy(PACOTE)
    dados.update(mudancas)
    return dados


def compactado(dados: dict) -> bytes:
    return gzip.compress(json.dumps(dados).encode("utf-8"))
