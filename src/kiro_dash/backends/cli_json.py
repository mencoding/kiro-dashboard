"""``CliJsonBackend`` — backend para sessões do Kiro CLI.

Lê arquivos ``~/.kiro/sessions/cli/<sid>.{json,jsonl,lock}`` via wrapper
sobre :mod:`kiro_dash.parser` (que permanece como módulo de baixo nível
com toda a lógica de parsing de schema do CLI).

Slug: ``"cli"``. Capabilities: ``SESSIONS``, ``TURNS``, ``TOOL_CALLS``,
``RUNNING``.
"""
from __future__ import annotations

from pathlib import Path

from kiro_dash.backends import Backend, Capability
from kiro_dash.models import LockInfo, Session
from kiro_dash.parser import (
    DEFAULT_SESSIONS_DIR,
    discover_sessions,
    find_session_by_prefix,
    load_all_sessions,
    load_session_file,
    read_lock,
)


class CliJsonBackend(Backend):
    """Backend de sessões do Kiro CLI.

    Parâmetros
    ----------
    sessions_dir
        Override do diretório de sessões. Default: ``~/.kiro/sessions/cli/``.
    """

    def __init__(self, sessions_dir: Path | None = None):
        self._sessions_dir = sessions_dir or DEFAULT_SESSIONS_DIR

    @property
    def slug(self) -> str:
        return "cli"

    def is_available(self) -> bool:
        """``True`` se o diretório existir e tiver ao menos um arquivo lido.

        Não exige sessões dentro — diretório vazio também conta como
        "Kiro CLI instalado, sem uso ainda".
        """
        return self._sessions_dir.is_dir()

    def capabilities(self) -> set[Capability]:
        return {
            Capability.SESSIONS,
            Capability.TURNS,
            Capability.TOOL_CALLS,
            Capability.RUNNING,
        }

    @property
    def sessions_dir(self) -> Path:
        return self._sessions_dir

    # --- API de leitura (delegação ao parser) ---

    def list_session_paths(self) -> list[Path]:
        """Lista caminhos de ``.json`` em ordem de mtime (mais recente primeiro)."""
        return discover_sessions(self._sessions_dir)

    def load_all_sessions(self) -> list[Session]:
        """Carrega todas as sessões do diretório, mais recente primeiro."""
        return load_all_sessions(self._sessions_dir)

    def load_session(self, path: Path) -> Session | None:
        """Carrega uma sessão a partir do caminho do ``.json``."""
        return load_session_file(path)

    def find_by_prefix(self, prefix: str) -> Path | None:
        """Resolve um prefixo de UUID em caminho de ``.json``."""
        return find_session_by_prefix(prefix, self._sessions_dir)

    def read_lock(self, session_id: str) -> LockInfo | None:
        """Lê ``.lock`` da sessão; ``None`` se ausente."""
        return read_lock(session_id, self._sessions_dir)

    def running_session_ids(self) -> list[str]:
        """Lista session_ids que possuem ``.lock`` válido."""
        if not self._sessions_dir.is_dir():
            return []
        result: list[str] = []
        for lock_path in self._sessions_dir.glob("*.lock"):
            sid = lock_path.stem
            info = read_lock(sid, self._sessions_dir)
            if info is not None:
                result.append(sid)
        return result
