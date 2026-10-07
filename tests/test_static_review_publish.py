from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.static_review.models import (
    DocumentSidecar,
    StaticReviewConfig,
    StaticReviewError,
    load_static_review_config,
    save_sidecar,
    sha256_file,
    sidecar_path_for,
    stable_json,
)
from tools.static_review.publish import StaticReviewPublisher
from tools.static_review.stack_outputs import StaticReviewStackOutputs


def _config() -> StaticReviewConfig:
    return StaticReviewConfig(
        schema_version=1,
        site_id="11111111-1111-4111-8111-111111111111",
        site_name="static-review",
        project_id="22222222-2222-4222-8222-222222222222",
        project_slug="pareto",
        project_title="Pareto",
        aws_region="eu-central-1",
    )


def _outputs() -> StaticReviewStackOutputs:
    return StaticReviewStackOutputs(
        stack_name="static-review-test",
        bucket_name="static-review-test-bucket",
        amplify_app_id="app123",
        amplify_branch_name="main",
        amplify_default_domain="app123.amplifyapp.com",
        public_base_url="https://main.app123.amplifyapp.com/",
        comments_table_name="static-review-comments",
        comments_function_name="static-review-comments",
        comments_function_url="https://lambda-url.example",
    )


def _source(tmp_path: Path) -> Path:
    source_dir = tmp_path / "architecture-design-documents" / "10-example"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "DOC.html"
    source_path.write_text(
        "<!doctype html><html><head><title>Example Doc</title></head><body><h1 id=\"top\">Example</h1><p>Review me.</p></body></html>",
        encoding="utf-8",
    )
    return source_path


def _sidecar(source_path: Path) -> DocumentSidecar:
    return DocumentSidecar(
        schema_version=1,
        document_id="33333333-3333-4333-8333-333333333333",
        document_slug=source_path.parent.name,
        title="Example Doc",
        description="Example description.",
        published_path=f"/projects/pareto/{source_path.parent.name}/",
        last_deployed_hash=None,
        last_deployed_at=None,
    )


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def read_json(self, key: str) -> dict[str, Any] | None:
        if key not in self.objects:
            return None
        return json.loads(self.objects[key][0].decode("utf-8"))

    def list_json(self, prefix: str) -> list[dict[str, Any]]:
        return [
            json.loads(content.decode("utf-8"))
            for key, (content, _content_type) in sorted(self.objects.items())
            if key.startswith(prefix) and key.endswith(".json")
        ]

    def write_json(self, key: str, data: dict[str, Any]) -> None:
        self.objects[key] = (stable_json(data).encode("utf-8"), "application/json")

    def write_text(self, key: str, text: str, content_type: str) -> None:
        self.objects[key] = (text.encode("utf-8"), content_type)

    def write_file(self, key: str, path: Path, content_type: str) -> None:
        self.objects[key] = (path.read_bytes(), content_type)

    def text(self, key: str) -> str:
        return self.objects[key][0].decode("utf-8")


class FakeAws:
    def __init__(self, statuses: list[str] | None = None) -> None:
        self.statuses = statuses or ["SUCCEED"]
        self.calls: list[tuple[str, ...]] = []

    def run_json(
        self,
        args: list[str] | tuple[str, ...],
        *,
        input_json: dict[str, Any] | list[Any] | None = None,
    ) -> dict[str, Any]:
        call = tuple(args)
        self.calls.append(call)
        if call[:2] == ("amplify", "start-deployment"):
            return {"jobSummary": {"jobId": "job-1", "status": "PENDING"}}
        if call[:2] == ("amplify", "get-job"):
            status = self.statuses.pop(0) if self.statuses else "SUCCEED"
            return {"job": {"summary": {"jobId": "job-1", "status": status}}}
        return {}


def test_missing_static_review_config_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(StaticReviewError, match="Static review config not found"):
        load_static_review_config(tmp_path / ".static-review.json")


def test_publisher_creates_sidecar_preserves_source_and_deploys_staged_html(tmp_path: Path) -> None:
    config = _config()
    source_path = _source(tmp_path)
    source_before = source_path.read_bytes()
    storage = MemoryStorage()
    aws = FakeAws()

    result = StaticReviewPublisher(
        config=config,
        aws=aws,
        storage=storage,
        stack_outputs=_outputs(),
        now=lambda: "2026-07-13T10:00:00Z",
        sleeper=lambda _seconds: None,
    ).publish(source_path)

    sidecar = json.loads(sidecar_path_for(source_path).read_text(encoding="utf-8"))
    assert source_path.read_bytes() == source_before
    assert sidecar["document_slug"] == "10-example"
    assert sidecar["last_deployed_hash"] == sha256_file(source_path)
    assert sidecar["last_deployed_at"] == "2026-07-13T10:00:00Z"
    assert result.stable_url == "https://main.app123.amplifyapp.com/projects/pareto/10-example/"
    staged = storage.text("site/projects/pareto/10-example/index.html")
    assert "window.StaticReviewConfig" in staged
    assert "review-client.js" in staged
    assert "Example Doc" in storage.text("site/projects/pareto/index.html")
    assert "Pareto" in storage.text("site/index.html")
    assert "site/_review/review-client.js" in storage.objects
    deployment_call = next(call for call in aws.calls if call[:2] == ("amplify", "start-deployment"))
    assert "--source-url-type" in deployment_call
    assert deployment_call[deployment_call.index("--source-url-type") + 1] == "BUCKET_PREFIX"
    assert deployment_call[deployment_call.index("--source-url") + 1].endswith("/site/")


def test_publisher_rejects_document_slug_conflict_without_uploading(tmp_path: Path) -> None:
    config = _config()
    source_path = _source(tmp_path)
    storage = MemoryStorage()
    storage.write_json(
        "registry/documents/other.json",
        {
            "document_id": "other-document",
            "document_slug": "10-example",
            "project_id": config.project_id,
        },
    )

    with pytest.raises(StaticReviewError, match="Document slug is already owned"):
        StaticReviewPublisher(
            config=config,
            aws=FakeAws(),
            storage=storage,
            stack_outputs=_outputs(),
            now=lambda: "2026-07-13T10:00:00Z",
            sleeper=lambda _seconds: None,
        ).publish(source_path)

    assert "site/projects/pareto/10-example/index.html" not in storage.objects


def test_publisher_writes_deterministic_registry_documents(tmp_path: Path) -> None:
    config = _config()
    source_path = _source(tmp_path)
    save_sidecar(sidecar_path_for(source_path), _sidecar(source_path))
    storage = MemoryStorage()

    StaticReviewPublisher(
        config=config,
        aws=FakeAws(),
        storage=storage,
        stack_outputs=_outputs(),
        now=lambda: "2026-07-13T10:00:00Z",
        sleeper=lambda _seconds: None,
    ).publish(source_path)

    document_registry_text = storage.text("registry/documents/33333333-3333-4333-8333-333333333333.json")
    assert document_registry_text == stable_json(json.loads(document_registry_text))
    assert '"document_slug": "10-example"' in document_registry_text
    assert '"source_hash":' in document_registry_text


def test_failed_amplify_deployment_does_not_update_sidecar_metadata(tmp_path: Path) -> None:
    config = _config()
    source_path = _source(tmp_path)
    save_sidecar(sidecar_path_for(source_path), _sidecar(source_path))
    storage = MemoryStorage()

    with pytest.raises(StaticReviewError, match="Amplify deployment job-1 failed"):
        StaticReviewPublisher(
            config=config,
            aws=FakeAws(statuses=["FAILED"]),
            storage=storage,
            stack_outputs=_outputs(),
            now=lambda: "2026-07-13T10:00:00Z",
            sleeper=lambda _seconds: None,
        ).publish(source_path)

    sidecar = json.loads(sidecar_path_for(source_path).read_text(encoding="utf-8"))
    assert sidecar["last_deployed_hash"] is None
    assert sidecar["last_deployed_at"] is None
