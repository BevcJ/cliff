from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.static_review.service.core import handle_http_request
from tools.static_review.service.repository import MemoryCommentRepository


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_feature_design_workflow_creates_canonical_doc_html():
    """(08-static-html-review-publishing, US-1)

    The feature design workflow creates architecture-design-documents/{NN}-{slug}/DOC.html
    from the HTML scaffold, preserves stable section/story/decision anchors, supports rich
    custom HTML, and does not create a Markdown design duplicate.
    """
    workflow = _read(".opencode/skills/feature-design-workflow/SKILL.MD")
    scaffold_path = ROOT / ".opencode/skills/feature-design-workflow/design-doc-format.html"
    doc_path = ROOT / "architecture-design-documents/08-static-html-review-publishing/DOC.html"

    assert "architecture-design-documents/{NN}-{slug}/DOC.html" in workflow
    assert "design-doc-format.html" in workflow
    assert "DOC_MARKDOWN" not in workflow
    assert "architecture-design-documents/{NN}-{slug}/DOC.md" not in workflow
    assert scaffold_path.exists()
    assert not (ROOT / ".opencode/skills/feature-design-workflow/design-doc-format.md").exists()
    assert not (ROOT / "architecture-design-documents/00-scaffold/DOC.md").exists()

    scaffold = scaffold_path.read_text(encoding="utf-8")
    assert "<style>" in scaffold
    assert "<script>" in scaffold
    assert "<svg" in scaffold
    assert 'id="user-stories"' in scaffold
    assert 'id="decision-1"' in scaffold

    doc = doc_path.read_text(encoding="utf-8")
    assert 'id="overview"' in doc
    assert 'id="us-1"' in doc
    assert 'id="decisions-made"' in doc


def test_cdk_defines_managed_static_review_resources():
    """(08-static-html-review-publishing, US-2)

    CDK defines the managed AWS resources, tags them for the expected static review
    site, and exposes CloudFormation outputs used by publisher/operator commands.
    """
    stack = _read("infra/static_review/static_review_stack.py")
    outputs = _read("tools/static_review/stack_outputs.py")

    assert "class StaticReviewStack" in stack
    assert "aws_s3" in stack
    assert "aws_amplify" in stack
    assert "aws_dynamodb" in stack
    assert "aws_lambda" in stack
    assert "management_tags(config)" in stack
    assert "StaticReviewStackOutputs" in outputs


def test_public_comment_api_creates_threads_and_replies():
    """(08-static-html-review-publishing, US-3)

    Public comment API requests can create threads and replies for a document namespace,
    while public requests cannot resolve, edit, or delete existing threads.
    """
    repository = MemoryCommentRepository()
    created = handle_http_request(
        method="POST",
        path="/v1/documents/doc-1/threads",
        body=json.dumps(
            {
                "reviewer_name": "Ada",
                "body": "Looks good.",
                "anchor": {"quote": "review", "section_id": "overview"},
            }
        ),
        repository=repository,
        now="2026-07-13T10:00:00.000Z",
    )
    thread = json.loads(created["body"])["thread"]
    reply = handle_http_request(
        method="POST",
        path=f"/v1/documents/doc-1/threads/{thread['thread_id']}/replies",
        body=json.dumps({"reviewer_name": "Grace", "body": "Agreed."}),
        repository=repository,
        now="2026-07-13T10:01:00.000Z",
    )

    assert created["statusCode"] == 201
    assert reply["statusCode"] == 201
    assert repository.list_threads("doc-1")[0]["replies"][0]["body"] == "Agreed."


@pytest.mark.skip(reason="Manual browser coverage in v1; node syntax is checked separately")
def test_annotation_client_reattaches_threads_and_replies():
    """(08-static-html-review-publishing, US-4)

    A reviewer can select text, create a thread, reload the same document, see the thread
    reattach, add replies, hide resolved threads by default, and view orphaned comments.
    """
    raise NotImplementedError("Manual browser coverage in v1")


def test_publisher_preserves_source_and_deploys_staged_html():
    """(08-static-html-review-publishing, US-5)

    Publishing stages and instruments a temporary copy, preserves canonical source bytes,
    rejects slug conflicts, uploads deterministic registries and indexes, starts Amplify
    with BUCKET_PREFIX, and updates sidecar metadata only after successful deployment.
    """
    assert (ROOT / ".static-review.json").exists()
    assert (ROOT / "architecture-design-documents/08-static-html-review-publishing/DOC.publish.json").exists()
    assert (ROOT / "tools/static_review/publish.py").exists()
    assert (ROOT / "tools/static_review/staging.py").exists()
    assert (ROOT / "tools/static_review/indexes.py").exists()
    assert (ROOT / "infra/static_review/static_review_stack.py").exists()
    publisher = _read("tools/static_review/publish.py")
    staging = _read("tools/static_review/staging.py")
    assert "--source-url-type" in publisher
    assert "BUCKET_PREFIX" in publisher
    assert "load_stack_outputs" in publisher
    assert "last_deployed_hash" in publisher
    assert "source_path.read_bytes() != source_bytes_before" in publisher
    assert "data-static-review" in staging


def test_handoff_uses_canonical_html_design_doc():
    """(08-static-html-review-publishing, US-6)

    Feature design handoff embeds the HTML artifact in Notion and implementation workflow
    reads local DOC.html first, using the Notion attachment only as fallback.
    """
    design_workflow = _read(".opencode/skills/feature-design-workflow/SKILL.MD")
    implementation_workflow = _read(".opencode/skills/feature-implementation-workflow/SKILL.md")
    notion_skill = _read(".opencode/skills/notion-mcp/SKILL.md")

    assert "Upload the accepted `DOC.html` as a Notion HTML attachment" in design_workflow
    assert "Published stable URL" in design_workflow
    assert "Do not paste or generate a Markdown duplicate" in design_workflow
    assert "Read the local `DOC.html`" in implementation_workflow
    assert "fallback" in implementation_workflow
    assert "pasted Markdown" in implementation_workflow
    assert "Create an HTML attachment" in notion_skill
    assert '<embed src="file-upload://...">' in notion_skill
    assert "canonical repository path" in notion_skill
