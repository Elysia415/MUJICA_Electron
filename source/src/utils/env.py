from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_LOADED = False


def load_env(override: bool = False, env_path: Optional[str] = None) -> None:
    """
    在项目内统一加载环境变量。

    - 优先加载用户配置目录的 `.env` (%APPDATA%/MUJICA/.env on Windows)
    - 然后加载项目根目录的 `.env`
    - 允许通过 env_path 指定自定义路径
    - 该函数幂等，多次调用不会重复加载
    """
    import os
    global _LOADED
    if _LOADED:
        return

    if env_path:
        load_dotenv(env_path, override=override)
        _LOADED = True
        return

    # 1. Load from user config directory first (for packaged app)
    if os.name == 'nt':
        user_config_dir = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'MUJICA'
    else:
        user_config_dir = Path.home() / '.mujica'
    
    user_env = user_config_dir / '.env'
    if user_env.exists():
        load_dotenv(user_env, override=override)

    # 2. Then load from project root (dev mode fallback)
    project_root = Path(__file__).resolve().parents[2]  # .../src/utils/env.py -> 项目根
    default_env = project_root / ".env"
    if default_env.exists():
        load_dotenv(default_env, override=override)
    else:
        # 兜底：dotenv 自己搜索
        load_dotenv(override=override)

    _LOADED = True


