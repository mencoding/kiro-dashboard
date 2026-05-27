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


# ── T4-W7: Sync de sessões IDE com redação ──────────────────────────


def _redact_and_stage_ide_sessions(
    ide_root: Path, stage_root: Path
) -> int:
    """Cria árvore espelhada em ``stage_root`` com sessões IDE redatadas.

    Para cada ``workspace-sessions/<b64>/<sid>.json`` em ``ide_root``,
    redata via :func:`sync_redactor.redact_session_dict` e escreve em
    ``stage_root/<b64>/<sid>.json``. Retorna contagem de arquivos
    escritos.

    Privacidade: nada de ``history[].message``, ``editorState``,
    ``actions[].input/output``, ``rawInput``, ``input.data.messages``
    sai do redator. Ver ``sync_redactor.py`` para vocabulário completo.
    """
    import json as _json

    from kiro_dash.sync_redactor import redact_session_dict

    ws_root = ide_root / "workspace-sessions"
    if not ws_root.is_dir():
        return 0

    count = 0
    for ws_dir in ws_root.iterdir():
        if not ws_dir.is_dir():
            continue
        target_ws = stage_root / ws_dir.name
        target_ws.mkdir(parents=True, exist_ok=True)
        for jf in ws_dir.glob("*.json"):
            try:
                payload = _json.loads(jf.read_text(encoding="utf-8"))
            except (OSError, _json.JSONDecodeError):
                continue
            # sessions.json é catálogo (lista de metadata) — sem
            # message/content. Pode passar inalterado.
            if jf.name == "sessions.json":
                redacted = payload
            else:
                redacted = redact_session_dict(payload)
            target_path = target_ws / jf.name
            target_path.write_text(_json.dumps(redacted), encoding="utf-8")
            count += 1
    return count


def sync_push_ide(
    cfg: SyncConfig,
    ide_root: Path,
) -> tuple[bool, str]:
    """Envia sessões IDE redatadas para ``cfg.remote_uri/ide-sessions/``.

    Executa em três passos: stage local (redação) → rclone copy →
    cleanup. A árvore staged é descartada após o push, garantindo que
    redação aplicada não pode ser revertida lendo do disk local
    posteriormente.

    Retorna ``(ok, error_msg)``. ``ok=True`` em sucesso (mesmo se zero
    arquivos foram enviados — diretório IDE pode estar vazio).
    """
    import shutil as _sh
    import tempfile as _tmp

    if not ide_root.is_dir():
        return False, f"IDE root não é diretório: {ide_root}"

    with _tmp.TemporaryDirectory(prefix="kiro-dash-ide-sync-") as tmpdir:
        stage = Path(tmpdir)
        try:
            count = _redact_and_stage_ide_sessions(ide_root, stage)
        except Exception as exc:
            return False, f"falha redatando sessões IDE: {exc}"

        if count == 0:
            return True, ""  # vazio — não é falha

        remote_uri_ide = f"{cfg.remote_uri}/ide-sessions"
        args = [
            "rclone", "copy",
            str(stage),
            remote_uri_ide,
            *_FILTERS,
            "--update",
            "--quiet",
            "--drive-acknowledge-abuse",
        ]
        ok, err = _run_rclone(args)
        # tmpdir é limpo automaticamente pelo context manager
        return ok, err


def main() -> int:  # pragma: no cover
    """Entry point do binário ``kiro-dash-sync``."""
    import sys
    from kiro_dash.cli import main as cli_main
    sys.argv = ["kiro-dash", "sync", *sys.argv[1:]]
    return cli_main()
