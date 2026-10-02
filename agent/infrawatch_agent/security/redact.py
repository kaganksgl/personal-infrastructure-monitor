"""Keep secrets out of what the agent sends and logs.

Process command lines regularly contain credentials (``--password=hunter2``,
``postgres://user:pass@host``). They are masked before leaving the machine.
"""

import os
import re
import stat
from pathlib import Path

_SECRET_FLAG = re.compile(
    r"(?i)(--?[\w-]*(?:pass(?:word|wd)?|secret|token|api[_-]?key|auth|credential)[\w-]*)"
    r"(=|\s+)(\S+)"
)
_URL_CREDENTIALS = re.compile(r"(\w+://[^:/\s@]+:)[^@\s]+@")
_SECRET_ENV = re.compile(r"(?i)\b([A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY)[A-Z0-9_]*=)\S+")
MASK = "***"


def redact_cmdline(cmdline: str) -> str:
    cmdline = _SECRET_FLAG.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", cmdline)
    cmdline = _URL_CREDENTIALS.sub(rf"\g<1>{MASK}@", cmdline)
    return _SECRET_ENV.sub(rf"\g<1>{MASK}", cmdline)


def mask_secret(value: str, visible: int = 8) -> str:
    if not value:
        return "(not set)"
    return value[:visible] + "…" if len(value) > visible else MASK


def insecure_permissions(path: Path) -> bool:
    """True if a file holding the API key is readable by group/others."""
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    return bool(mode & (stat.S_IRWXG | stat.S_IRWXO))
