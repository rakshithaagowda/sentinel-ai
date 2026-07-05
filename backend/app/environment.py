import os
from pathlib import Path

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    _load_dotenv = None


BACKEND_ROOT = Path(__file__).resolve().parent.parent


def load_environment(dotenv_path: str | Path | None = None) -> bool:
    path = Path(dotenv_path) if dotenv_path else BACKEND_ROOT / ".env"
    if _load_dotenv:
        return _load_dotenv(dotenv_path=path)
    return _load_dotenv_file(path)


def _load_dotenv_file(path: Path) -> bool:
    if not path.exists():
        return False
    for line in _read_dotenv_text(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    return True


def _read_dotenv_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-16", "utf-8"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeError:
            continue
    return path.read_text()
