"""Adapter discovery stays consistent for direct builds and workbench preflight."""
from pathlib import Path

import pytest

from protocol_pipeline.cad_runtime import ADAPTER_RELATIVE_PATH, cad_adapter_path
from protocol_pipeline.machines import forma_runtime


def test_forma_root_is_used_by_preflight_and_native_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured checkout works even when the installed package has no skill files."""
    root = tmp_path / 'custom-forma'
    adapter = root / ADAPTER_RELATIVE_PATH
    adapter.parent.mkdir(parents=True)
    adapter.write_text('# discovery fixture, never executed')
    monkeypatch.delenv('FORMA_CAD_ADAPTER_PATH', raising=False)
    monkeypatch.setenv('FORMA_ROOT', str(root))
    assert cad_adapter_path() == adapter.resolve()
    assert forma_runtime()['cad_adapter'] == str(adapter.resolve())


def test_explicit_bad_adapter_path_does_not_silently_fall_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Report a typo in explicit configuration rather than choosing another checkout."""
    monkeypatch.setenv('FORMA_CAD_ADAPTER_PATH', str(tmp_path / 'missing.py'))
    with pytest.raises(ValueError, match='does not name an existing'):
        cad_adapter_path()
    assert forma_runtime()['available'] is False
