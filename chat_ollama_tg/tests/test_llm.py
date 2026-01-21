"""Tests for LLM adapters."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from chat_ollama_tg.llm.base import Message
from chat_ollama_tg.llm.ollama import OllamaAdapter
from chat_ollama_tg.llm.factory import create_llm_adapter
from chat_ollama_tg.config import Config


class TestOllamaAdapter:
    """Tests for Ollama adapter."""

    @pytest.fixture
    def adapter(self):
        """Create Ollama adapter for testing."""
        return OllamaAdapter(
            base_url="http://localhost:11434",
            model="test-model",
            timeout=30,
            retries=1,
        )

    def test_engine_name(self, adapter: OllamaAdapter):
        """Test engine name property."""
        assert adapter.engine_name == "ollama"

    def test_model_name(self, adapter: OllamaAdapter):
        """Test model name property."""
        assert adapter.model_name == "test-model"

    @pytest.mark.asyncio
    async def test_generate_success(self, adapter: OllamaAdapter):
        """Test successful generation with mocked HTTP client."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Hello! How can I help you?"}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            messages = [
                Message(role="user", content="Hi!")
            ]

            result = await adapter.generate(messages)

            assert result == "Hello! How can I help you?"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self, adapter: OllamaAdapter):
        """Test health check with mocked response."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await adapter.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, adapter: OllamaAdapter):
        """Test health check when service is unavailable."""
        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_get_client.return_value = mock_client

            result = await adapter.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_list_models(self, adapter: OllamaAdapter):
        """Test listing models."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2"},
                {"name": "mistral"},
                {"name": "gemma2"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            models = await adapter.list_models()

            assert len(models) == 3
            assert "llama3.2" in models
            assert "mistral" in models


class TestLLMFactory:
    """Tests for LLM factory."""

    def test_create_ollama_adapter(self):
        """Test creating Ollama adapter from config."""
        config = Config()
        config.llm_engine = "ollama"
        config.ollama_base_url = "http://localhost:11434"
        config.ollama_model = "llama3.2"

        adapter = create_llm_adapter(config)

        assert adapter.engine_name == "ollama"
        assert adapter.model_name == "llama3.2"

    def test_create_llamacpp_adapter(self):
        """Test creating llama.cpp adapter from config."""
        config = Config()
        config.llm_engine = "llamacpp"
        config.llamacpp_model_path = "/path/to/model.gguf"
        config.llamacpp_cli_path = "llama-cli"

        adapter = create_llm_adapter(config)

        assert adapter.engine_name == "llamacpp"

    def test_invalid_engine(self):
        """Test that invalid engine raises error."""
        config = Config()
        config.llm_engine = "invalid"  # type: ignore

        with pytest.raises(ValueError, match="Unknown LLM engine"):
            create_llm_adapter(config)
