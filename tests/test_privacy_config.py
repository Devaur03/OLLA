"""Unit tests for Phase 3 privacy-mode config enforcement."""

from app.config import Settings


def test_local_only_forces_local_embeddings_and_clears_keys():
    s = Settings(
        local_only=True,
        use_local_embeddings=False,
        openai_api_key="sk-secret",
        brave_api_key="brave-secret",
    )
    assert s.use_local_embeddings is True
    assert s.openai_api_key is None
    assert s.brave_api_key == ""
    assert s.privacy_mode is True


def test_disable_external_llm_blocks_openai_only():
    s = Settings(
        disable_external_llm=True,
        use_local_embeddings=False,
        openai_api_key="sk-secret",
    )
    assert s.use_local_embeddings is True
    assert s.openai_api_key is None
    assert s.privacy_mode is True


def test_disable_external_llm_keeps_brave():
    # disable_external_llm targets the embedding provider; it does not, on its
    # own, clear the web-search provider key (only full local_only does).
    s = Settings(disable_external_llm=True, brave_api_key="brave-secret")
    assert s.brave_api_key == "brave-secret"


def test_no_privacy_flags_leaves_config_untouched():
    s = Settings(
        local_only=False,
        disable_external_llm=False,
        use_local_embeddings=False,
        openai_api_key="sk-secret",
    )
    assert s.use_local_embeddings is False
    assert s.openai_api_key == "sk-secret"
    assert s.privacy_mode is False


def test_retention_days_default_is_disabled():
    s = Settings()
    assert s.retention_days == 0
