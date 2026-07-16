from app.config import Settings, validate_production_config


def _settings(**overrides):
    base = {"JWT_SECRET_KEY": "a" * 40, "DEBUG": False}
    base.update(overrides)
    return Settings(**base)


def test_debug_mode_skips_validation():
    settings = _settings(DEBUG=True, JWT_SECRET_KEY="change-me-in-production")
    assert validate_production_config(settings) == []


def test_flags_default_placeholder_secret():
    settings = _settings(JWT_SECRET_KEY="change-me-in-production")
    warnings = validate_production_config(settings)
    assert any("JWT_SECRET_KEY" in w for w in warnings)


def test_flags_short_secret_even_if_not_exact_default():
    settings = _settings(JWT_SECRET_KEY="short")
    warnings = validate_production_config(settings)
    assert any("JWT_SECRET_KEY" in w for w in warnings)


def test_flags_secret_containing_change_word():
    settings = _settings(JWT_SECRET_KEY="production-secret-change-me-please-now")
    warnings = validate_production_config(settings)
    assert any("JWT_SECRET_KEY" in w for w in warnings)


def test_strong_secret_is_not_flagged():
    settings = _settings(JWT_SECRET_KEY="9f8e7d6c5b4a3928170615243342516071829384756afedcba0123456789ab")
    warnings = validate_production_config(settings)
    assert not any("JWT_SECRET_KEY" in w for w in warnings)


def test_flags_default_minio_credentials():
    settings = _settings()
    warnings = validate_production_config(settings)
    assert any("MinIO" in w for w in warnings)
