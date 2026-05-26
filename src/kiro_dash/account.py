"""Wrapper enriquecido do ``kiro-cli whoami``.

Roda ``kiro-cli whoami --format json-pretty``, parseia o output (que é um
JSON seguido de blocos textuais) e renderiza um sumário da identidade
AWS / billing tier / profile.

Sem credenciais, sem rede — apenas leitura local de saída do CLI.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WhoAmI:
    """Identidade atual reportada pelo Kiro CLI."""

    account_type: str  # "IamIdentityCenter" | "BuilderId" | etc
    email: str | None
    region: str | None
    start_url: str | None
    profile_name: str | None
    profile_arn: str | None

    @property
    def aws_account_id(self) -> str | None:
        """Extrai a conta AWS do ARN (``arn:aws:codewhisperer:region:ACCT:...``)."""
        if not self.profile_arn:
            return None
        parts = self.profile_arn.split(":")
        return parts[4] if len(parts) >= 5 else None

    @property
    def profile_region(self) -> str | None:
        """Extrai a região do ARN."""
        if not self.profile_arn:
            return None
        parts = self.profile_arn.split(":")
        return parts[3] if len(parts) >= 4 else None

    @property
    def is_enterprise(self) -> bool:
        """``True`` quando o tipo de conta é IAM Identity Center."""
        return self.account_type == "IamIdentityCenter"


def _split_json_and_tail(output: str) -> tuple[dict, str]:
    """Separa o bloco JSON inicial dos blocos textuais subsequentes."""
    output = output.strip()
    if not output.startswith("{"):
        return {}, output

    depth = 0
    end_idx = -1
    in_string = False
    escape = False
    for i, ch in enumerate(output):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i
                break

    if end_idx < 0:
        return {}, output

    head = output[: end_idx + 1]
    tail = output[end_idx + 1 :].strip()
    try:
        return json.loads(head), tail
    except json.JSONDecodeError:
        return {}, output


_PROFILE_BLOCK_RE = re.compile(
    r"Profile:\s*\n([^\n]+)\n([^\n]+)",
    re.MULTILINE,
)


def parse_whoami_output(output: str) -> WhoAmI:
    """Parseia o output completo do ``kiro-cli whoami --format json-pretty``.

    O output tem dois pedaços: um JSON com identidade base e um bloco de
    texto livre (``Profile:\\n<nome>\\n<arn>``) com o profile do Kiro.
    """
    head, tail = _split_json_and_tail(output)

    profile_name = None
    profile_arn = None
    m = _PROFILE_BLOCK_RE.search(tail)
    if m:
        profile_name = m.group(1).strip() or None
        profile_arn = m.group(2).strip() or None

    return WhoAmI(
        account_type=str(head.get("accountType", "") or ""),
        email=head.get("email"),
        region=head.get("region"),
        start_url=head.get("startUrl"),
        profile_name=profile_name,
        profile_arn=profile_arn,
    )


def run_whoami(timeout: float = 5.0) -> WhoAmI | None:
    """Invoca ``kiro-cli whoami --format json-pretty`` e devolve ``WhoAmI``.

    Retorna ``None`` se o binário não estiver no ``PATH`` ou o comando
    falhar.
    """
    if shutil.which("kiro-cli") is None:
        return None

    try:
        proc = subprocess.run(
            ["kiro-cli", "whoami", "--format", "json-pretty"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if proc.returncode != 0:
        return None

    return parse_whoami_output(proc.stdout)
