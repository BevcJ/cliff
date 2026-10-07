from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.static_review.comments import resolve_thread
from tools.static_review.service.core import handle_direct_invocation, handle_http_request
from tools.static_review.service.repository import (
    DynamoDbCommentRepository,
    MemoryCommentRepository,
    _to_item,
    reply_key,
    thread_key,
)
from tools.static_review.stack_outputs import StaticReviewStackOutputs


def _thread_payload(body: str = "Please clarify this.") -> str:
    return json.dumps(
        {
            "reviewer_name": "Ada",
            "body": body,
            "anchor": {
                "section_id": "overview",
                "quote": "canonical HTML",
                "prefix": "The ",
                "suffix": " file",
                "start_offset": 4,
                "end_offset": 18,
                "revision_hash": "abc123",
            },
        }
    )


def _body(response: dict[str, Any]) -> dict[str, Any]:
    return json.loads(response["body"])


def test_public_responses_do_not_emit_cors_headers() -> None:
    repository = MemoryCommentRepository()

    result = handle_http_request(
        method="GET",
        path="/v1/documents/doc-1/threads",
        body=None,
        repository=repository,
    )

    assert result["headers"] == {"content-type": "application/json; charset=utf-8"}


def test_public_requests_create_threads_and_replies() -> None:
    repository = MemoryCommentRepository()

    created = handle_http_request(
        method="POST",
        path="/v1/documents/doc-1/threads",
        body=_thread_payload(),
        repository=repository,
        now="2026-07-13T10:00:00.000Z",
    )
    thread = _body(created)["thread"]

    reply = handle_http_request(
        method="POST",
        path=f"/v1/documents/doc-1/threads/{thread['thread_id']}/replies",
        body=json.dumps({"reviewer_name": "Grace", "body": "Reply text"}),
        repository=repository,
        now="2026-07-13T10:01:00.000Z",
    )
    listed = handle_http_request(
        method="GET",
        path="/v1/documents/doc-1/threads",
        body=None,
        repository=repository,
    )

    assert created["statusCode"] == 201
    assert reply["statusCode"] == 201
    assert _body(listed)["threads"][0]["body"] == "Please clarify this."
    assert _body(listed)["threads"][0]["replies"][0]["body"] == "Reply text"


def test_public_requests_validate_field_limits() -> None:
    repository = MemoryCommentRepository()

    response = handle_http_request(
        method="POST",
        path="/v1/documents/doc-1/threads",
        body=_thread_payload(body="x" * 5001),
        repository=repository,
    )

    assert response["statusCode"] == 400
    assert "body exceeds" in _body(response)["message"]


def test_public_requests_can_resolve_reopen_and_soft_delete_threads() -> None:
    repository = MemoryCommentRepository()
    created = handle_http_request(
        method="POST",
        path="/v1/documents/doc-1/threads",
        body=_thread_payload(),
        repository=repository,
        now="2026-07-13T10:00:00.000Z",
    )
    thread_id = _body(created)["thread"]["thread_id"]

    resolve_response = handle_http_request(
        method="PATCH",
        path=f"/v1/documents/doc-1/threads/{thread_id}",
        body=json.dumps({"resolved": True}),
        repository=repository,
        now="2026-07-13T10:02:00.000Z",
    )
    reopen_response = handle_http_request(
        method="PATCH",
        path=f"/v1/documents/doc-1/threads/{thread_id}",
        body=json.dumps({"resolved": False}),
        repository=repository,
        now="2026-07-13T10:03:00.000Z",
    )
    delete_response = handle_http_request(
        method="DELETE",
        path=f"/v1/documents/doc-1/threads/{thread_id}",
        body=None,
        repository=repository,
        now="2026-07-13T10:04:00.000Z",
    )
    listed = handle_http_request(
        method="GET",
        path="/v1/documents/doc-1/threads",
        body=None,
        repository=repository,
    )

    assert resolve_response["statusCode"] == 200
    assert _body(resolve_response)["thread"]["resolved_at"] == "2026-07-13T10:02:00.000Z"
    assert reopen_response["statusCode"] == 200
    assert _body(reopen_response)["thread"]["resolved_at"] is None
    assert delete_response["statusCode"] == 200
    assert _body(delete_response)["thread"]["deleted_at"] == "2026-07-13T10:04:00.000Z"
    assert _body(delete_response)["thread"]["body"] == ""
    assert _body(delete_response)["thread"]["reviewer_name"] == ""
    assert _body(listed)["threads"] == []


def test_public_requests_soft_delete_replies_and_preserve_thread_context() -> None:
    repository = MemoryCommentRepository()
    created = handle_http_request(
        method="POST",
        path="/v1/documents/doc-1/threads",
        body=_thread_payload(),
        repository=repository,
        now="2026-07-13T10:00:00.000Z",
    )
    thread_id = _body(created)["thread"]["thread_id"]
    first_reply = handle_http_request(
        method="POST",
        path=f"/v1/documents/doc-1/threads/{thread_id}/replies",
        body=json.dumps({"reviewer_name": "Grace", "body": "First reply"}),
        repository=repository,
        now="2026-07-13T10:01:00.000Z",
    )
    second_reply = handle_http_request(
        method="POST",
        path=f"/v1/documents/doc-1/threads/{thread_id}/replies",
        body=json.dumps({"reviewer_name": "Linus", "body": "Second reply"}),
        repository=repository,
        now="2026-07-13T10:02:00.000Z",
    )
    first_reply_id = _body(first_reply)["reply"]["reply_id"]
    second_reply_id = _body(second_reply)["reply"]["reply_id"]

    delete_first_reply = handle_http_request(
        method="DELETE",
        path=f"/v1/documents/doc-1/threads/{thread_id}/replies/{first_reply_id}",
        body=None,
        repository=repository,
        now="2026-07-13T10:03:00.000Z",
    )
    delete_thread = handle_http_request(
        method="DELETE",
        path=f"/v1/documents/doc-1/threads/{thread_id}",
        body=None,
        repository=repository,
        now="2026-07-13T10:04:00.000Z",
    )
    listed = handle_http_request(
        method="GET",
        path="/v1/documents/doc-1/threads",
        body=None,
        repository=repository,
    )
    reply_to_deleted_thread = handle_http_request(
        method="POST",
        path=f"/v1/documents/doc-1/threads/{thread_id}/replies",
        body=json.dumps({"reviewer_name": "Ada", "body": "Late reply"}),
        repository=repository,
        now="2026-07-13T10:05:00.000Z",
    )
    delete_second_reply = handle_http_request(
        method="DELETE",
        path=f"/v1/documents/doc-1/threads/{thread_id}/replies/{second_reply_id}",
        body=None,
        repository=repository,
        now="2026-07-13T10:06:00.000Z",
    )
    listed_after_all_content_deleted = handle_http_request(
        method="GET",
        path="/v1/documents/doc-1/threads",
        body=None,
        repository=repository,
    )

    listed_thread = _body(listed)["threads"][0]
    assert delete_first_reply["statusCode"] == 200
    assert _body(delete_first_reply)["reply"]["deleted_at"] == "2026-07-13T10:03:00.000Z"
    assert _body(delete_first_reply)["reply"]["body"] == ""
    assert delete_thread["statusCode"] == 200
    assert listed_thread["deleted_at"] == "2026-07-13T10:04:00.000Z"
    assert listed_thread["body"] == ""
    assert listed_thread["replies"][0]["body"] == ""
    assert listed_thread["replies"][0]["deleted_at"] == "2026-07-13T10:03:00.000Z"
    assert listed_thread["replies"][1]["body"] == "Second reply"
    assert reply_to_deleted_thread["statusCode"] == 404
    assert delete_second_reply["statusCode"] == 200
    assert _body(listed_after_all_content_deleted)["threads"] == []


def test_public_status_update_validates_boolean() -> None:
    repository = MemoryCommentRepository()

    response = handle_http_request(
        method="PATCH",
        path="/v1/documents/doc-1/threads/thread-1",
        body=json.dumps({"resolved": "yes"}),
        repository=repository,
    )

    assert response["statusCode"] == 400
    assert "resolved must be a boolean" in _body(response)["message"]


def test_operator_direct_invocation_can_resolve_thread() -> None:
    repository = MemoryCommentRepository()
    created = handle_http_request(
        method="POST",
        path="/v1/documents/doc-1/threads",
        body=_thread_payload(),
        repository=repository,
        now="2026-07-13T10:00:00.000Z",
    )
    thread_id = _body(created)["thread"]["thread_id"]

    result = handle_direct_invocation(
        {"operator_action": "resolve_thread", "document_id": "doc-1", "thread_id": thread_id},
        repository,
        now="2026-07-13T10:02:00.000Z",
    )

    assert result["thread"]["resolved_at"] == "2026-07-13T10:02:00.000Z"


def test_dynamodb_key_construction_matches_static_review_format() -> None:
    assert thread_key("doc-1", "thread-1") == {
        "PK": "DOC#doc-1",
        "SK": "THREAD#thread-1",
    }
    assert reply_key("doc-1", "thread-1", "2026-07-13T10:01:00.000Z", "reply-1") == {
        "PK": "DOC#doc-1",
        "SK": "THREAD#thread-1#REPLY#2026-07-13T10:01:00.000Z#reply-1",
    }


class FakeDynamoDb:
    def __init__(self) -> None:
        self.update_calls: list[dict[str, Any]] = []
        self.reply_item = {
            **reply_key("doc-1", "thread-1", "2026-07-13T10:01:00.000Z", "reply-1"),
            "entity_type": "REPLY",
            "document_id": "doc-1",
            "thread_id": "thread-1",
            "reply_id": "reply-1",
            "reviewer_name": "Grace",
            "body": "Reply text",
            "created_at": "2026-07-13T10:01:00.000Z",
        }

    def query(self, **request: Any) -> dict[str, Any]:
        return {"Items": [_to_item(self.reply_item)]}

    def update_item(self, **request: Any) -> dict[str, Any]:
        self.update_calls.append(request)
        if request.get("ReturnValues") != "ALL_NEW":
            return {}
        updated = {**self.reply_item, "deleted_at": "2026-07-13T10:02:00.000Z"}
        return {"Attributes": _to_item(updated)}


def test_dynamodb_reply_delete_uses_prefix_query_and_redacts_response() -> None:
    client = FakeDynamoDb()
    repository = DynamoDbCommentRepository("comments", dynamodb_client=client)

    deleted = repository.delete_reply(
        "doc-1",
        "thread-1",
        "reply-1",
        "2026-07-13T10:02:00.000Z",
    )

    assert deleted["deleted_at"] == "2026-07-13T10:02:00.000Z"
    assert deleted["body"] == ""
    assert deleted["reviewer_name"] == ""
    assert any(call["UpdateExpression"] == "SET updated_at = :updated_at" for call in client.update_calls)
    assert any(call["UpdateExpression"] == "SET deleted_at = :deleted_at" for call in client.update_calls)


class FakeAws:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run_json(
        self,
        args: list[str] | tuple[str, ...],
        *,
        input_json: dict[str, Any] | list[Any] | None = None,
    ) -> dict[str, Any]:
        call = tuple(args)
        self.calls.append(call)
        if call == ("sts", "get-caller-identity"):
            return {"Account": "123456789012"}
        if call[:2] == ("lambda", "invoke"):
            return {"StatusCode": 200}
        return {}


def test_operator_helper_invokes_lambda_with_document_namespace(tmp_path: Path) -> None:
    config_path = tmp_path / ".static-review.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "site_id": "stable-site-uuid",
                "site_name": "static-review",
                "project_id": "stable-project-uuid",
                "project_slug": "pareto",
                "project_title": "Pareto",
                "aws_region": "eu-central-1",
            }
        ),
        encoding="utf-8",
    )
    sidecar_path = tmp_path / "DOC.publish.json"
    sidecar_path.write_text(json.dumps({"document_id": "doc-1"}), encoding="utf-8")
    fake = FakeAws()

    resolve_thread(
        sidecar_path,
        "thread-1",
        config_path=config_path,
        aws=fake,  # type: ignore[arg-type]
        stack_outputs=StaticReviewStackOutputs(
            stack_name="static-review-test",
            bucket_name="bucket",
            amplify_app_id="app123",
            amplify_branch_name="main",
            amplify_default_domain="app123.amplifyapp.com",
            public_base_url="https://main.app123.amplifyapp.com/",
            comments_table_name="comments",
            comments_function_name="static-review-comments",
            comments_function_url="https://lambda-url.example",
        ),
    )

    invoke_call = next(call for call in fake.calls if call[:2] == ("lambda", "invoke"))
    assert "static-review-comments" in invoke_call
    payload = json.loads(invoke_call[invoke_call.index("--payload") + 1])
    assert payload == {
        "operator_action": "resolve_thread",
        "document_id": "doc-1",
        "thread_id": "thread-1",
    }
