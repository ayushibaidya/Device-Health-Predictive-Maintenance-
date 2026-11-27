import pytest
from psycopg.conninfo import conninfo_to_dict

from device_health_ingestion.store import database_dsn


def test_password_characters_are_preserved(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PGHOST", "postgres")
    monkeypatch.setenv("PGDATABASE", "device_health")
    monkeypatch.setenv("PGUSER", "device_health")
    password = "space ' quote @ : $ \\"
    monkeypatch.setenv("PGPASSWORD", password)
    assert conninfo_to_dict(database_dsn())["password"] == password


def test_explicit_database_url_is_supported(monkeypatch):
    value = "postgresql://example.invalid/device_health"
    monkeypatch.setenv("DATABASE_URL", value)
    assert database_dsn() == value


def test_missing_database_configuration_fails_early(monkeypatch):
    for name in ("DATABASE_URL", "PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError):
        database_dsn()
