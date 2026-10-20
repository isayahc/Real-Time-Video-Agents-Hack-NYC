"""Verify local dotenv configuration reaches the server without exposing secrets."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from protocol_pipeline.environment import load_environment
from protocol_pipeline.extraction import create_provider
from protocol_pipeline.web import create_app


@pytest.mark.parametrize('key_name', ['NEBIUS_API_KEY', 'NEBIUS_TOKEN_FACTORY_KEY'])
def test_dotenv_reaches_readiness_and_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key_name: str,
) -> None:
    """Load either supported key before readiness checks and provider construction."""
    monkeypatch.chdir(tmp_path)
    for name in ('NEBIUS_API_KEY', 'NEBIUS_TOKEN_FACTORY_KEY', 'NEBIUS_VISION_MODEL'):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / '.env').write_text(f'{key_name}=dotenv-test-secret\nNEBIUS_VISION_MODEL=custom/vision\n')
    with TestClient(create_app(tmp_path / 'runs')) as client:
        response = client.get('/api/config')
        assert response.json()['credentials_available'] is True
        assert response.json()['vision_model'] == 'custom/vision'
        assert 'dotenv-test-secret' not in response.text
        provider = create_provider('nebius')
        assert provider.client.key == 'dotenv-test-secret'


def test_exported_environment_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not overwrite credentials already supplied by a shell or deployment."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NEBIUS_API_KEY', 'exported-test-key')
    (tmp_path / '.env').write_text('NEBIUS_API_KEY=file-test-key\n')
    load_environment()
    assert create_provider('nebius').client.key == 'exported-test-key'


def test_missing_dotenv_is_optional(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing file must not break deployments using exported credentials."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NEBIUS_API_KEY', 'exported-test-key')
    load_environment()
    assert create_provider('nebius').client.key == 'exported-test-key'
