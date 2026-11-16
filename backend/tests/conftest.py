"""O mínimo para importar o app nos testes sem um Postgres de verdade.

O `Settings` exige a DATABASE_URL, e a sessão cria o engine na importação. Os
testes daqui não abrem conexão: o que fala com o banco é trocado por dublê.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
