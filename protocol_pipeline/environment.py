# SPDX-License-Identifier: MPL-2.0
"""Load local configuration without replacing the launching process's settings."""
from pathlib import Path

from dotenv import load_dotenv


def load_environment() -> None:
    """Read .env in the working directory; exported variables take precedence."""
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
