"""Sincronização de sessões do Kiro CLI com Google Drive via rclone.

Padrão herdado do ``iris/sync-drive.sh`` do Léo: rclone copy aditivo
(não-destrutivo no remote) com filtros explícitos pra evitar transferir
``.jsonl`` (transcripts grandes) e ``.lock`` (estado local).

Privacidade: o ``.json`` contém metadata + título; nunca prompts/respostas.
Estes ficam no ``.jsonl`` que é deliberadamente excluído do sync.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SyncConfig:
    """Configuração de sync.

    ``remote``: nome do remote rclone (ex.: ``gdrive-pessoal``).
    ``remote_path``: subpath no remote (ex.: ``kiro-dash/sessions``).
    """

    remote: str
    remote_path: str

    @property
    def remote_uri(self) -> str:
        return f"{self.remote}:{self.remote_path}"


_FILTERS = [
    "--include=*.json",
    "--exclude=*.jsonl",
    "--exclude=*.lock",
    "--exclude=*/",
]


def rclone_available() -> bool:
    """Retorna True se o binário rclone está no PATH."""
    return shutil.which("rclone") is not None


def rclone_remote_exists(remote: str) -> bool:
    """Verifica se ``remote`` está configurado em ``rclone listremotes``."""
    try:
        proc = subprocess.run(
            ["rclone", "listremotes"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    if proc.returncode != 0:
        return False
    target = f"{remote}:"
    return any(line.strip() == target for line in proc.stdout.splitlines())


def _run_rclone(args: list[str]) -> tuple[bool, str]:
    """Executa rclone e devolve (ok, stderr_se_falhou)."""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "rclone failed").strip()
    return True, ""


def sync_push(cfg: SyncConfig, sessions_dir: Path) -> tuple[bool, str]:
    """Envia ``sessions_dir/*.json`` para ``cfg.remote_uri`` (aditivo)."""
    args = [
        "rclone", "copy",
        str(sessions_dir),
        cfg.remote_uri,
        *_FILTERS,
        "--update",
        "--quiet",
        "--drive-acknowledge-abuse",
    ]
    return _run_rclone(args)


def sync_pull(cfg: SyncConfig, sessions_dir: Path) -> tuple[bool, str]:
    """Baixa ``cfg.remote_uri/*.json`` para ``sessions_dir`` (aditivo)."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    args = [
        "rclone", "copy",
        cfg.remote_uri,
        str(sessions_dir),
        *_FILTERS,
        "--update",
        "--quiet",
        "--drive-acknowledge-abuse",
    ]
    return _run_rclone(args)


def main() -> int:  # pragma: no cover
    """Entry point do binário ``kiro-dash-sync``."""
    import sys
    from kiro_dash.cli import main as cli_main
    sys.argv = ["kiro-dash", "sync", *sys.argv[1:]]
    return cli_main()
