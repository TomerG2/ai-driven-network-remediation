"""Tests for the auto-ingest startup hook and related logic."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# We need to set env vars BEFORE importing app module (config is read at import time)
os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-secret")
os.environ.setdefault("MINIO_BUCKET", "test-bucket")
os.environ.setdefault("VECTOR_STORE_NAME", "noc_runbooks")
os.environ.setdefault("LLAMASTACK_HOST", "llamastack")
os.environ.setdefault("LLAMASTACK_PORT", "8321")


class TestAutoIngestFunction:
    """Tests for _auto_ingest() logic."""

    @patch("ingestion_pipeline.app.LlamaStackVectorStoreClient")
    @patch("ingestion_pipeline.app.MinioDocumentClient")
    def test_auto_ingest_syncs_and_ingests(self, mock_minio_cls, mock_vector_cls, tmp_path):
        from ingestion_pipeline.app import _auto_ingest

        runbook = tmp_path / "nginx-crashloop.md"
        runbook.write_text("# Nginx CrashLoop Runbook\nRestart the pod.")

        mock_minio = MagicMock()
        mock_minio_cls.return_value = mock_minio
        mock_minio.load_prefix_text_objects.return_value = [
            MagicMock(object_name="runbooks/nginx-crashloop.md", content="# Nginx CrashLoop Runbook"),
        ]

        mock_vector = MagicMock()
        mock_vector_cls.return_value = mock_vector

        with patch("ingestion_pipeline.app.settings") as mock_settings:
            mock_settings.minio_is_configured = True
            mock_settings.vector_store_name = "noc_runbooks"
            mock_settings.minio_endpoint = "minio:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "bucket"
            mock_settings.minio_secure = False
            mock_settings.minio_runbook_prefix = "runbooks/"
            mock_settings.llamastack_base_url = "http://llamastack:8321"
            mock_settings.embedding_model = "sentence-transformers/nomic-ai/nomic-embed-text-v1.5"
            mock_settings.chunk_size_tokens = 800
            mock_settings.chunk_overlap_tokens = 80
            mock_settings.runbooks_dir = tmp_path

            _auto_ingest()

        mock_minio.ensure_bucket.assert_called_once()
        mock_vector.ensure_vector_store.assert_called_once()
        mock_vector.ingest_text.assert_called_once_with(
            filename="nginx-crashloop.md",
            content="# Nginx CrashLoop Runbook",
            attributes={"source_type": "runbook", "source_name": "runbooks/nginx-crashloop.md"},
        )

    @patch("ingestion_pipeline.app.MinioDocumentClient")
    def test_auto_ingest_skips_when_minio_not_configured(self, mock_minio_cls):
        from ingestion_pipeline.app import _auto_ingest

        with patch("ingestion_pipeline.app.settings") as mock_settings:
            mock_settings.minio_is_configured = False
            _auto_ingest()

        mock_minio_cls.assert_not_called()

    @patch("ingestion_pipeline.app.MinioDocumentClient")
    def test_auto_ingest_skips_when_vector_store_name_empty(self, mock_minio_cls):
        from ingestion_pipeline.app import _auto_ingest

        with patch("ingestion_pipeline.app.settings") as mock_settings:
            mock_settings.minio_is_configured = True
            mock_settings.vector_store_name = ""
            _auto_ingest()

        mock_minio_cls.assert_not_called()

    @patch("ingestion_pipeline.app.LlamaStackVectorStoreClient")
    @patch("ingestion_pipeline.app.MinioDocumentClient")
    def test_auto_ingest_handles_multiple_runbooks(self, mock_minio_cls, mock_vector_cls, tmp_path):
        from ingestion_pipeline.app import _auto_ingest

        for name in ["runbook-a.md", "runbook-b.md", "runbook-c.md"]:
            (tmp_path / name).write_text(f"# {name}")

        mock_minio = MagicMock()
        mock_minio_cls.return_value = mock_minio
        mock_minio.load_prefix_text_objects.return_value = [
            MagicMock(object_name=f"runbooks/{name}", content=f"# {name}")
            for name in ["runbook-a.md", "runbook-b.md", "runbook-c.md"]
        ]

        mock_vector = MagicMock()
        mock_vector_cls.return_value = mock_vector

        with patch("ingestion_pipeline.app.settings") as mock_settings:
            mock_settings.minio_is_configured = True
            mock_settings.vector_store_name = "noc_runbooks"
            mock_settings.minio_endpoint = "minio:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "bucket"
            mock_settings.minio_secure = False
            mock_settings.minio_runbook_prefix = "runbooks/"
            mock_settings.llamastack_base_url = "http://llamastack:8321"
            mock_settings.embedding_model = "sentence-transformers/nomic-ai/nomic-embed-text-v1.5"
            mock_settings.chunk_size_tokens = 800
            mock_settings.chunk_overlap_tokens = 80
            mock_settings.runbooks_dir = tmp_path

            _auto_ingest()

        assert mock_vector.ingest_text.call_count == 3


class TestLifespan:
    """Tests for the FastAPI lifespan that triggers auto-ingest."""

    @patch("ingestion_pipeline.app._auto_ingest")
    @pytest.mark.anyio
    async def test_lifespan_calls_auto_ingest_when_enabled(self, mock_ingest):
        from ingestion_pipeline.app import lifespan

        mock_app = MagicMock()
        with patch("ingestion_pipeline.app._AUTO_INGEST", True):
            async with lifespan(mock_app):
                pass

        mock_ingest.assert_called_once()

    @patch("ingestion_pipeline.app._auto_ingest")
    @pytest.mark.anyio
    async def test_lifespan_skips_auto_ingest_when_disabled(self, mock_ingest):
        from ingestion_pipeline.app import lifespan

        mock_app = MagicMock()
        with patch("ingestion_pipeline.app._AUTO_INGEST", False):
            async with lifespan(mock_app):
                pass

        mock_ingest.assert_not_called()

    @patch("ingestion_pipeline.app._auto_ingest", side_effect=RuntimeError("connection refused"))
    @pytest.mark.anyio
    async def test_lifespan_does_not_crash_on_ingest_failure(self, mock_ingest):
        from ingestion_pipeline.app import lifespan

        mock_app = MagicMock()
        with patch("ingestion_pipeline.app._AUTO_INGEST", True):
            async with lifespan(mock_app):
                pass  # should not raise


class TestSyncPackagedRunbooks:
    """Tests for _sync_packaged_runbooks_to_minio."""

    def test_sync_uploads_new_runbooks(self, tmp_path):
        from ingestion_pipeline.app import _sync_packaged_runbooks_to_minio

        (tmp_path / "runbook-1.md").write_text("content 1")
        (tmp_path / "runbook-2.md").write_text("content 2")

        mock_minio = MagicMock()
        mock_minio.put_text_object_if_missing.return_value = True

        with patch("ingestion_pipeline.app.settings") as mock_settings:
            mock_settings.runbooks_dir = tmp_path
            mock_settings.minio_runbook_prefix = "runbooks/"

            result = _sync_packaged_runbooks_to_minio(mock_minio)

        assert result["uploaded_count"] == 2
        assert result["skipped_count"] == 0
        mock_minio.ensure_bucket.assert_called_once()

    def test_sync_skips_existing_runbooks(self, tmp_path):
        from ingestion_pipeline.app import _sync_packaged_runbooks_to_minio

        (tmp_path / "existing.md").write_text("already there")

        mock_minio = MagicMock()
        mock_minio.put_text_object_if_missing.return_value = False

        with patch("ingestion_pipeline.app.settings") as mock_settings:
            mock_settings.runbooks_dir = tmp_path
            mock_settings.minio_runbook_prefix = "runbooks/"

            result = _sync_packaged_runbooks_to_minio(mock_minio)

        assert result["uploaded_count"] == 0
        assert result["skipped_count"] == 1

    def test_sync_handles_empty_runbooks_dir(self, tmp_path):
        from ingestion_pipeline.app import _sync_packaged_runbooks_to_minio

        mock_minio = MagicMock()

        with patch("ingestion_pipeline.app.settings") as mock_settings:
            mock_settings.runbooks_dir = tmp_path
            mock_settings.minio_runbook_prefix = "runbooks/"

            result = _sync_packaged_runbooks_to_minio(mock_minio)

        assert result["uploaded_count"] == 0
        assert result["skipped_count"] == 0


class TestConfigDefaults:
    """Tests for correct config defaults (the bug that caused the issue)."""

    def test_llamastack_host_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LLAMASTACK_HOST", None)
            from ingestion_pipeline.config import Settings

            s = Settings.from_env()
            assert s.llamastack_host == "llamastack"

    def test_embedding_model_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMBEDDING_MODEL", None)
            from ingestion_pipeline.config import Settings

            s = Settings.from_env()
            assert s.embedding_model == "sentence-transformers/nomic-ai/nomic-embed-text-v1.5"

    def test_llamastack_base_url_format(self):
        from ingestion_pipeline.config import Settings

        s = Settings.from_env()
        assert s.llamastack_base_url == f"http://{s.llamastack_host}:{s.llamastack_port}"

    def test_minio_is_configured_requires_all_fields(self):
        from ingestion_pipeline.config import Settings

        s = Settings(
            llamastack_host="h",
            llamastack_port=8321,
            vector_store_name="vs",
            embedding_model="m",
            chunk_size_tokens=800,
            chunk_overlap_tokens=80,
            runbooks_dir=Path("/tmp"),
            minio_endpoint="",
            minio_access_key="key",
            minio_secret_key="secret",
            minio_bucket="bucket",
            minio_secure=False,
            minio_runbook_prefix="runbooks/",
        )
        assert s.minio_is_configured is False

    def test_minio_is_configured_true_when_all_set(self):
        from ingestion_pipeline.config import Settings

        s = Settings(
            llamastack_host="h",
            llamastack_port=8321,
            vector_store_name="vs",
            embedding_model="m",
            chunk_size_tokens=800,
            chunk_overlap_tokens=80,
            runbooks_dir=Path("/tmp"),
            minio_endpoint="minio:9000",
            minio_access_key="key",
            minio_secret_key="secret",
            minio_bucket="bucket",
            minio_secure=False,
            minio_runbook_prefix="runbooks/",
        )
        assert s.minio_is_configured is True
