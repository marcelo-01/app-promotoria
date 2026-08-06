import re
from typing import Any, Optional


def only_digits(value: Any) -> Optional[str]:
    """CNPJ/CPF só dígitos (Âncora 4). Retorna None para vazio."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits or None
