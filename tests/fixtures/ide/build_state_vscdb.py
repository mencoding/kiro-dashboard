"""Builder de fixtures sqlite para `state.vscdb` do Kiro IDE.

Reproduz a estrutura mínima do storage do VS Code/Kiro IDE:
- Tabela ``ItemTable(key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)``
- Chave ``kiro.kiroAgent`` com JSON serializado como BLOB

Uso em testes::

    from tests.fixtures.ide.build_state_vscdb import build_state_vscdb

    def test_something(tmp_path):
        db = build_state_vscdb(tmp_path)
        # db é o Path do state.vscdb pronto pra IdeStateBackend ler

Permite override do JSON via parâmetro ``kiro_agent_data`` para variantes
(schema desconhecido, ausência da chave, etc.).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent
DEFAULT_KIRO_AGENT_FIXTURE = FIXTURE_DIR / "state_vscdb_kiroagent.json"


def load_default_kiro_agent_data() -> dict:
    """Carrega o JSON canônico de ``kiro.kiroAgent`` para uso default."""
    return json.loads(DEFAULT_KIRO_AGENT_FIXTURE.read_text(encoding="utf-8"))


def build_state_vscdb(
    target_dir: Path,
    *,
    kiro_agent_data: dict | None = None,
    extra_keys: dict[str, str | bytes] | None = None,
    omit_kiro_agent: bool = False,
) -> Path:
    """Constrói um ``state.vscdb`` mínimo em ``target_dir``.

    Parâmetros
    ----------
    target_dir
        Diretório onde criar o ``state.vscdb`` (em fixtures, costuma ser
        ``tmp_path``).
    kiro_agent_data
        JSON a serializar como BLOB da chave ``kiro.kiroAgent``. Se
        ``None``, usa o default em ``state_vscdb_kiroagent.json``.
    extra_keys
        Outras entradas a inserir em ``ItemTable``. Útil para testar
        leitura tolerante a chaves desconhecidas.
    omit_kiro_agent
        Quando ``True``, não insere ``kiro.kiroAgent`` (útil para testar
        ``IdeStateBackend.is_available() == False``).

    Retorno
    -------
    Path
        Caminho do ``state.vscdb`` criado.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    db_path = target_dir / "state.vscdb"

    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute(
            "CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)"
        )
        if not omit_kiro_agent:
            data = kiro_agent_data if kiro_agent_data is not None else load_default_kiro_agent_data()
            cur.execute(
                "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
                ("kiro.kiroAgent", json.dumps(data).encode("utf-8")),
            )
        if extra_keys:
            for k, v in extra_keys.items():
                if isinstance(v, str):
                    v_blob: str | bytes = v.encode("utf-8")
                else:
                    v_blob = v
                cur.execute(
                    "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
                    (k, v_blob),
                )
        con.commit()
    finally:
        con.close()

    return db_path
