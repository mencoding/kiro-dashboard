"""Backend de sessões do Kiro IDE (Wave 6 frente Q).

Lê ``~/.config/Kiro/User/globalStorage/kiro.kiroagent/`` em modo
read-only forte, expondo sessões, turns e tool calls do IDE para o
domínio interno do kiro-dash.

Ref: ADR-0001 §"Decisão", plano Wave 6 frente Q.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from kiro_dash.backends import Backend, Capability
from kiro_dash.backends.workspace_codec import decode

from kiro_dash._platform_paths import kiro_ide_kiroagent_dir

# ── Constantes (caminhos default) ───────────────────────────────────

DEFAULT_IDE_SESSIONS_ROOT = kiro_ide_kiroagent_dir()
"""Cross-platform via :mod:`kiro_dash._platform_paths`:
- Linux: ``~/.config/Kiro/User/globalStorage/kiro.kiroagent``
- Windows: ``%APPDATA%/Kiro/User/globalStorage/kiro.kiroagent``
- macOS: ``~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent``
"""
WORKSPACE_SESSIONS_SUBDIR = "workspace-sessions"
EXECUTIONS_CATALOG_FILENAME = "f62de366d0006e17ea00a01f6624aabf"
SESSIONS_INDEX_FILENAME = "sessions.json"

# Env vars (decisão #5 do plano Q)
ENV_OVERRIDE_ROOT = "KIRO_DASH_IDE_SESSIONS_ROOT"
ENV_DISABLE = "KIRO_DASH_NO_IDE_SESSIONS"

# Regex para reconhecer arquivos de execution.
#
# I7 do code review (Wave 6/Q): filtrar arquivos não-execution dentro
# do profile_hash dir para evitar I/O wasteful em arquivos auxiliares.
#
# Wave 9 (v0.7.3): aceitar dois formatos de filename:
#   - UUID com hífens (8-4-4-4-12): formato observado em versões
#     anteriores do Kiro IDE
#   - 32 hex chars sem hífens: formato atual (storage-key opaca,
#     NÃO é hash do executionId interno; o JSON dentro mantém o
#     executionId em UUID format)
#
# read_execution() valida schema internamente, então a regex é só
# pré-filtro de I/O para descartar arquivos auxiliares (catalog
# index, profile.json, etc.) que não têm formato de UUID/hex32.
_EXECUTION_ID_RE = re.compile(
    r"^([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$"
)


# ── Erros estruturados ──────────────────────────────────────────────


class IdeSessionError(Exception):
    """Erro genérico ao ler sessões IDE."""


class IdeWorkspaceDecodeError(IdeSessionError):
    """Nome de diretório de workspace base64url inválido."""

    def __init__(self, encoded: str, reason: str):
        super().__init__(f"workspace dir inválido {encoded!r}: {reason}")
        self.encoded = encoded
        self.reason = reason


# ── Workspace dataclass ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Workspace:
    """Um workspace conhecido pelo IDE.

    :param path: caminho lógico decodificado
    :param encoded_dir: nome do diretório base64url (no fs)
    :param fs_dir: ``Path`` filesystem completo
    """

    path: str
    encoded_dir: str
    fs_dir: Path


# ── Modelos tipados de leitura (T4-T6) ──────────────────────────────


def _ms_to_dt(ms: int) -> datetime:
    """Converte epoch-ms para datetime UTC."""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class IdeSessionMetadata:
    """Resumo de sessão lido de ``workspace-sessions/<b64>/sessions.json``."""

    session_id: str
    title: str
    date_created: datetime
    workspace_directory: str


@dataclass(frozen=True, slots=True)
class IdeHistoryItem:
    """Item de history sem conteúdo (privacidade preservada).

    Apenas presença/ausência de campos — nunca o texto da mensagem.
    """

    has_message: bool
    has_context_items: bool
    has_editor_state: bool
    context_items_count: int


@dataclass(frozen=True, slots=True)
class IdeSession:
    """Sessão IDE completa, lida de ``workspace-sessions/<b64>/<uuid>.json``."""

    session_id: str
    title: str
    workspace_path: str
    date_created: datetime
    session_type: str
    autonomy_mode: str
    selected_model: str
    default_model_title: str | None
    history: list[IdeHistoryItem]
    context_usage_percentage: float
    mtime: datetime

    @property
    def history_length(self) -> int:
        return len(self.history)


@dataclass(frozen=True, slots=True)
class IdeExecutionIndexEntry:
    """Entry de catálogo de executions (``f62de366d0006e17ea00a01f6624aabf``).

    O catálogo tem campos resumidos; ``read_execution`` carrega o
    arquivo completo com actions e usage_summary.
    """

    execution_id: str
    workflow_type: str  # "chat-agent" ou "spec-generation"
    status: str  # "succeed" / "failed" / "aborted" / "running"
    start_time: datetime
    end_time: datetime | None  # None se ``running`` (raw endTime == 0)
    chat_session_id: str

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def duration_ms(self) -> int | None:
        if self.end_time is None:
            return None
        delta = (self.end_time - self.start_time).total_seconds() * 1000
        return int(delta)


@dataclass(frozen=True, slots=True)
class IdeUsageEntry:
    """Fase do ``usageSummary`` da execution.

    Cada entry corresponde a uma chamada de model + opcionalmente
    tools usadas naquela fase.
    """

    usage: float
    unit: str
    unit_plural: str
    used_tools: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IdeIntent:
    """Resultado do action ``intentClassification``.

    Em executions ``spec-generation`` (sub-execução) o classifier não
    é invocado — para essas, ``intent_result`` da execution é ``None``.
    """

    classification: str  # "chat" / "do" / "spec"
    final_intent: dict
    llm_intent: dict
    local_intent: dict


@dataclass(frozen=True, slots=True)
class IdeAction:
    """Ação genérica em ``actions[]`` da execution.

    Mantém o ``raw`` para casos não cobertos pelo vocabulário
    documentado na decisão #6 do plano Q. Conteúdo de input/output
    é redatado para preservar privacidade.
    """

    action_id: str
    action_type: str
    action_state: str
    emitted_at: datetime
    end_time: datetime | None  # presente em ``model``
    has_input: bool
    has_output: bool
    tool_origin: str | None  # ``acp`` em tools


@dataclass(frozen=True, slots=True)
class IdeExecution:
    """Execution completa lida do arquivo no profile_hash dir."""

    execution_id: str
    chat_session_id: str
    workflow_type: str
    status: str
    start_time: datetime
    end_time: datetime | None
    autonomy_mode: str
    actions: list[IdeAction]
    usage_summary: list[IdeUsageEntry]
    intent_result: IdeIntent | None
    context_usage_percentage: float
    mtime: datetime

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def total_credits(self) -> float:
        return sum(u.usage for u in self.usage_summary)

    @property
    def all_used_tools(self) -> list[str]:
        """União dos ``usedTools`` de todas as fases (preservando ordem)."""
        seen: set[str] = set()
        out: list[str] = []
        for u in self.usage_summary:
            for t in u.used_tools:
                if t not in seen:
                    seen.add(t)
                    out.append(t)
        return out


# ── Readers (free functions, testáveis isoladamente) ────────────────


def read_sessions_index(workspace_dir: Path) -> list[IdeSessionMetadata]:
    """Lê ``workspace-sessions/<b64>/sessions.json``.

    Retorna lista vazia se o arquivo não existe ou é malformado.
    """
    sj = workspace_dir / SESSIONS_INDEX_FILENAME
    if not sj.is_file():
        return []
    try:
        data = json.loads(sj.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    out: list[IdeSessionMetadata] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("sessionId")
        if not isinstance(sid, str):
            continue
        try:
            date_ms = int(entry.get("dateCreated", 0))
        except (TypeError, ValueError):
            date_ms = 0
        out.append(
            IdeSessionMetadata(
                session_id=sid,
                title=entry.get("title", ""),
                date_created=_ms_to_dt(date_ms),
                workspace_directory=entry.get("workspaceDirectory", ""),
            )
        )
    return out


def _read_history(raw_history: Any) -> list[IdeHistoryItem]:
    """Extrai apenas presença de campos do history; nunca o conteúdo."""
    if not isinstance(raw_history, list):
        return []
    out: list[IdeHistoryItem] = []
    for item in raw_history:
        if not isinstance(item, dict):
            continue
        ctx_items = item.get("contextItems") or []
        out.append(
            IdeHistoryItem(
                has_message="message" in item and bool(item.get("message")),
                has_context_items=bool(ctx_items),
                has_editor_state="editorState" in item,
                context_items_count=len(ctx_items) if isinstance(ctx_items, list) else 0,
            )
        )
    return out


def read_session(session_id: str, workspace_dir: Path) -> IdeSession | None:
    """Lê ``workspace-sessions/<b64>/<session_id>.json`` completo.

    Retorna ``None`` se o arquivo não existe ou tem schema inesperado.
    Nunca retorna conteúdo de mensagens — apenas metadata.
    """
    sess_path = workspace_dir / f"{session_id}.json"
    if not sess_path.is_file():
        return None
    try:
        data = json.loads(sess_path.read_text(encoding="utf-8"))
        mtime = datetime.fromtimestamp(sess_path.stat().st_mtime, tz=timezone.utc)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    sid = data.get("sessionId")
    if not isinstance(sid, str):
        return None
    try:
        date_ms = int(data.get("dateCreated", 0))
    except (TypeError, ValueError):
        date_ms = 0
    try:
        ctx_pct = float(data.get("contextUsagePercentage", 0.0))
    except (TypeError, ValueError):
        ctx_pct = 0.0
    return IdeSession(
        session_id=sid,
        title=data.get("title", ""),
        workspace_path=data.get("workspaceDirectory", ""),
        date_created=_ms_to_dt(date_ms),
        session_type=data.get("sessionType", ""),
        autonomy_mode=data.get("autonomyMode", ""),
        selected_model=data.get("selectedModel", ""),
        default_model_title=data.get("defaultModelTitle"),
        history=_read_history(data.get("history")),
        context_usage_percentage=ctx_pct,
        mtime=mtime,
    )


def read_executions_catalog(profile_hash_dir: Path) -> list[IdeExecutionIndexEntry]:
    """Lê ``<profile_hash>/f62de366d0006e17ea00a01f6624aabf``.

    Retorna lista vazia se ausente ou malformado.
    """
    cat_path = profile_hash_dir / EXECUTIONS_CATALOG_FILENAME
    if not cat_path.is_file():
        return []
    try:
        data = json.loads(cat_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    raw_execs = data.get("executions", [])
    if not isinstance(raw_execs, list):
        return []
    out: list[IdeExecutionIndexEntry] = []
    for e in raw_execs:
        if not isinstance(e, dict):
            continue
        eid = e.get("executionId")
        if not isinstance(eid, str):
            continue
        try:
            start_ms = int(e.get("startTime", 0))
        except (TypeError, ValueError):
            start_ms = 0
        try:
            end_ms = int(e.get("endTime", 0))
        except (TypeError, ValueError):
            end_ms = 0
        end_dt = _ms_to_dt(end_ms) if end_ms != 0 else None
        out.append(
            IdeExecutionIndexEntry(
                execution_id=eid,
                workflow_type=e.get("type", ""),
                status=e.get("status", ""),
                start_time=_ms_to_dt(start_ms),
                end_time=end_dt,
                chat_session_id=e.get("chatSessionId", ""),
            )
        )
    return out


def _read_usage_summary(raw: Any) -> list[IdeUsageEntry]:
    if not isinstance(raw, list):
        return []
    out: list[IdeUsageEntry] = []
    for u in raw:
        if not isinstance(u, dict):
            continue
        try:
            usage_val = float(u.get("usage", 0.0))
        except (TypeError, ValueError):
            usage_val = 0.0
        used_tools_raw = u.get("usedTools", []) or []
        if isinstance(used_tools_raw, list):
            used_tools = [t for t in used_tools_raw if isinstance(t, str)]
        else:
            used_tools = []
        out.append(
            IdeUsageEntry(
                usage=usage_val,
                unit=u.get("unit", "credit"),
                unit_plural=u.get("unitPlural", "credits"),
                used_tools=used_tools,
            )
        )
    return out


def _read_actions(raw: Any) -> tuple[list[IdeAction], IdeIntent | None]:
    """Lê actions[] + extrai intent_result quando presente."""
    if not isinstance(raw, list):
        return [], None
    actions: list[IdeAction] = []
    intent: IdeIntent | None = None
    for a in raw:
        if not isinstance(a, dict):
            continue
        action_type = a.get("actionType", "")
        try:
            emitted_ms = int(a.get("emittedAt", 0))
        except (TypeError, ValueError):
            emitted_ms = 0
        end_t: datetime | None = None
        if "endTime" in a:
            try:
                end_t = _ms_to_dt(int(a["endTime"]))
            except (TypeError, ValueError):
                end_t = None
        actions.append(
            IdeAction(
                action_id=a.get("actionId", ""),
                action_type=action_type,
                action_state=a.get("actionState", ""),
                emitted_at=_ms_to_dt(emitted_ms),
                end_time=end_t,
                has_input="input" in a,
                has_output="output" in a,
                tool_origin=a.get("toolOrigin"),
            )
        )
        if action_type == "intentClassification" and isinstance(a.get("intentResult"), dict):
            ir = a["intentResult"]
            cls = ir.get("classification", "")
            if isinstance(cls, str) and cls:
                intent = IdeIntent(
                    classification=cls,
                    final_intent=ir.get("finalIntent", {}) or {},
                    llm_intent=ir.get("llmIntent", {}) or {},
                    local_intent=ir.get("localIntent", {}) or {},
                )
    return actions, intent


def read_execution(execution_path: Path) -> IdeExecution | None:
    """Lê arquivo completo de execution (``<profile>/<inner>/<execution_id>``).

    Retorna ``None`` se ausente ou schema inválido.
    """
    if not execution_path.is_file():
        return None
    try:
        data = json.loads(execution_path.read_text(encoding="utf-8"))
        mtime = datetime.fromtimestamp(execution_path.stat().st_mtime, tz=timezone.utc)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    eid = data.get("executionId")
    if not isinstance(eid, str):
        return None
    try:
        start_ms = int(data.get("startTime", 0))
    except (TypeError, ValueError):
        start_ms = 0
    try:
        end_ms = int(data.get("endTime", 0))
    except (TypeError, ValueError):
        end_ms = 0
    end_dt = _ms_to_dt(end_ms) if end_ms != 0 else None
    actions, intent = _read_actions(data.get("actions"))
    try:
        ctx_pct = float(data.get("contextUsagePercentage", 0.0))
    except (TypeError, ValueError):
        ctx_pct = 0.0
    return IdeExecution(
        execution_id=eid,
        chat_session_id=data.get("chatSessionId", ""),
        workflow_type=data.get("workflowType", ""),
        status=data.get("status", ""),
        start_time=_ms_to_dt(start_ms),
        end_time=end_dt,
        autonomy_mode=data.get("autonomyMode", ""),
        actions=actions,
        usage_summary=_read_usage_summary(data.get("usageSummary")),
        intent_result=intent,
        context_usage_percentage=ctx_pct,
        mtime=mtime,
    )


# ── Backend ─────────────────────────────────────────────────────────


class IdeSessionBackend(Backend):
    """Backend para sessões do Kiro IDE.

    O slug ``ide-sessions`` distingue do ``IdeStateBackend`` (slug
    ``ide``) que cobre apenas USAGE_STATE.

    Capabilities expostas: :data:`Capability.SESSIONS`,
    :data:`Capability.TURNS`, :data:`Capability.TOOL_CALLS`,
    :data:`Capability.RUNNING`.
    """

    slug = "ide-sessions"

    def __init__(self, root: Path | None = None):
        if root is not None:
            self._root = Path(root)
        else:
            self._root = self._resolve_default_root()
        # I1 do code review: cache instance-level do índice de
        # executions. Lazy (preenchido na 1ª chamada) e invalidável
        # via :meth:`invalidate_cache`. Trade-off: aceitável dentro de
        # uma única invocação CLI; em TUI live o caller deve chamar
        # ``invalidate_cache()`` periodicamente para refresh.
        self._exec_index_cache: dict[str, list["IdeExecution"]] | None = None

    # -- resolution --

    @staticmethod
    def _resolve_default_root() -> Path:
        env = os.environ.get(ENV_OVERRIDE_ROOT)
        if env:
            return Path(env).expanduser()
        return DEFAULT_IDE_SESSIONS_ROOT

    @property
    def root(self) -> Path:
        """Diretório-raiz da kiro.kiroagent."""
        return self._root

    @property
    def workspace_sessions_dir(self) -> Path:
        return self._root / WORKSPACE_SESSIONS_SUBDIR

    # -- Backend protocol --

    def is_available(self) -> bool:
        """Retorna True se há ao menos 1 workspace com sessions.json válido.

        Curto-circuita em ``KIRO_DASH_NO_IDE_SESSIONS`` truthy.
        """
        if os.environ.get(ENV_DISABLE):
            return False
        ws_root = self.workspace_sessions_dir
        if not ws_root.is_dir():
            return False
        for ws_dir in ws_root.iterdir():
            if not ws_dir.is_dir():
                continue
            sj = ws_dir / SESSIONS_INDEX_FILENAME
            if not sj.is_file():
                continue
            try:
                data = json.loads(sj.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, list) and data:
                return True
        return False

    def capabilities(self) -> set[Capability]:
        return {
            Capability.SESSIONS,
            Capability.TURNS,
            Capability.TOOL_CALLS,
            Capability.RUNNING,
        }

    def data_age(self) -> float | None:
        """Idade em segundos do ``sessions.json`` mais recente.

        Retorna ``None`` quando não há nenhum workspace.
        """
        latest_mtime: float | None = None
        ws_root = self.workspace_sessions_dir
        if not ws_root.is_dir():
            return None
        for ws_dir in ws_root.iterdir():
            if not ws_dir.is_dir():
                continue
            sj = ws_dir / SESSIONS_INDEX_FILENAME
            if not sj.is_file():
                continue
            try:
                m = sj.stat().st_mtime
            except OSError:
                continue
            if latest_mtime is None or m > latest_mtime:
                latest_mtime = m
        if latest_mtime is None:
            return None
        return time.time() - latest_mtime

    # -- IDE-specific API --

    def iter_workspaces(self) -> Iterator[Workspace]:
        """Itera sobre todos os workspaces conhecidos pelo IDE.

        Diretórios cujo nome falha na decodificação base64url são
        silenciosamente ignorados (best-effort tolerance).
        """
        ws_root = self.workspace_sessions_dir
        if not ws_root.is_dir():
            return
        for ws_dir in sorted(ws_root.iterdir()):
            if not ws_dir.is_dir():
                continue
            try:
                path = decode(ws_dir.name)
            except (ValueError, TypeError):
                continue
            yield Workspace(
                path=path,
                encoded_dir=ws_dir.name,
                fs_dir=ws_dir,
            )

    def list_workspaces(self) -> list[Workspace]:
        """Versão list-eager de :meth:`iter_workspaces`."""
        return list(self.iter_workspaces())

    def iter_profile_hash_dirs(self) -> Iterator[Path]:
        """Itera sobre diretórios de profile_hash que contêm catálogo.

        Cada profile dir tem o arquivo ``f62de366d0006e17ea00a01f6624aabf``
        como catálogo de executions. ``default/`` (symlink) é ignorado.
        """
        if not self._root.is_dir():
            return
        for entry in sorted(self._root.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name == "default":
                continue  # symlink — coberto pelo profile real
            if entry.name == WORKSPACE_SESSIONS_SUBDIR:
                continue
            catalog = entry / EXECUTIONS_CATALOG_FILENAME
            if catalog.is_file():
                yield entry

    # -- T8/T9: API completa (list_sessions, iter_turns, ...) -----------

    def invalidate_cache(self) -> None:
        """Limpa cache do índice de executions (I1 do code review).

        Chamar antes de re-leituras quando arquivos no disco podem
        ter mudado (TUI live, watchdog em loop). Em CLI invocação
        única o cache é sempre fresh por construção.
        """
        self._exec_index_cache = None

    def _scan_all_executions(self) -> Iterator["IdeExecution"]:
        """Itera todas as executions encontradas em todos os profile_hashes.

        Filtra arquivos por nome (UUID) — I7 do code review: evita
        tentar parser arquivos auxiliares (catálogo, profile.json,
        etc.) como JSON de execution.

        Faz I/O completo. Resultado é cacheado em
        ``_exec_index_cache`` via :meth:`_executions_by_session_id`.
        """
        for ph_dir in self.iter_profile_hash_dirs():
            for entry in sorted(ph_dir.iterdir()):
                if not entry.is_dir():
                    continue
                for f in sorted(entry.iterdir()):
                    if not f.is_file():
                        continue
                    if not _EXECUTION_ID_RE.match(f.name):
                        continue  # I7: pular arquivos não-execution
                    ex = read_execution(f)
                    if ex is not None:
                        yield ex

    def _executions_by_session_id(self) -> dict[str, list["IdeExecution"]]:
        """Indexa executions por ``chat_session_id``.

        Cacheado em instance state (I1 do code review). Use
        :meth:`invalidate_cache` para forçar re-leitura.
        """
        if self._exec_index_cache is not None:
            return self._exec_index_cache
        index: dict[str, list[IdeExecution]] = {}
        for ex in self._scan_all_executions():
            index.setdefault(ex.chat_session_id, []).append(ex)
        for sid in index:
            index[sid].sort(key=lambda e: e.start_time)
        self._exec_index_cache = index
        return index

    def _strip_prefix(self, session_id: str) -> str:
        """Aceita ``ide-sessions:<uuid>`` ou ``<uuid>`` raw."""
        prefix = f"{self.slug}:"
        if session_id.startswith(prefix):
            return session_id[len(prefix):]
        return session_id

    def list_sessions(self) -> list:
        """Lista todas as sessões IDE como ``Session`` do domínio interno.

        Faz I/O completo: enumera workspaces, lê catálogos e arquivos de
        sessão, indexa executions por ``chat_session_id`` e mapeia para
        ``Session`` via :mod:`kiro_dash.backends.ide_mapper`.

        Sessões cuja leitura falha (arquivo corrompido, schema inválido)
        são silenciosamente ignoradas.
        """
        if not self.is_available():
            return []
        # Import lazy para evitar ciclo (ide_mapper importa ide_sessions)
        from kiro_dash.backends.ide_mapper import to_session

        exec_index = self._executions_by_session_id()
        out: list = []
        for ws in self.iter_workspaces():
            for meta in read_sessions_index(ws.fs_dir):
                ide_sess = read_session(meta.session_id, ws.fs_dir)
                if ide_sess is None:
                    continue
                execs = exec_index.get(meta.session_id, [])
                out.append(to_session(ide_sess, execs))
        return out

    def iter_turns(self, session_id: str) -> Iterator:
        """Itera ``Turn`` de uma sessão IDE.

        Aceita session_id raw (UUID) ou composto (``ide-sessions:<uuid>``).
        Retorna iterador vazio se a sessão não tem executions ou não
        existe.
        """
        from kiro_dash.backends.ide_mapper import to_turn

        raw = self._strip_prefix(session_id)
        exec_index = self._executions_by_session_id()
        for ex in exec_index.get(raw, []):
            yield to_turn(ex)

    def iter_tool_calls(self, session_id: str) -> Iterator:
        """Itera ``ToolCall`` de uma sessão IDE."""
        from kiro_dash.backends.ide_mapper import to_tool_calls

        raw = self._strip_prefix(session_id)
        exec_index = self._executions_by_session_id()
        for ex in exec_index.get(raw, []):
            yield from to_tool_calls(ex)

    def running_sessions(self) -> list:
        """Sessões com ao menos uma execution ``status=running``.

        Heurística primária (decisão #10 do plano Q): catálogo de
        executions traz status. Quando o catálogo está ausente
        (improvável em IDEs reais), retorna lista vazia — o fallback
        de active+mtime fica para casos extremos e é exposto via
        :meth:`running_sessions_fallback`.
        """
        return [s for s in self.list_sessions() if s.is_active]

    def running_sessions_fallback(
        self,
        *,
        threshold_seconds: float = 60.0,
    ) -> list:
        """Fallback: sessões com ``mtime`` recente, mesmo sem catálogo.

        Best-effort para casos onde o catálogo de executions está
        ausente ou todas as executions running são antigas. Usa o
        mtime do arquivo da sessão como proxy para "atividade
        recente".
        """
        if not self.is_available():
            return []
        from kiro_dash.backends.ide_mapper import to_session

        now = time.time()
        out: list = []
        exec_index = self._executions_by_session_id()
        for ws in self.iter_workspaces():
            for meta in read_sessions_index(ws.fs_dir):
                sess_path = ws.fs_dir / f"{meta.session_id}.json"
                try:
                    age = now - sess_path.stat().st_mtime
                except OSError:
                    continue
                if age > threshold_seconds:
                    continue
                ide_sess = read_session(meta.session_id, ws.fs_dir)
                if ide_sess is None:
                    continue
                execs = exec_index.get(meta.session_id, [])
                out.append(to_session(ide_sess, execs))
        return out
