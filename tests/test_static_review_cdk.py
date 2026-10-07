from __future__ import annotations

import json

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infra.static_review.static_review_stack import StaticReviewStack
from tools.static_review.models import StaticReviewConfig, static_review_stack_name
from tools.static_review.stack_outputs import OUTPUT_KEYS


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


def _template() -> Template:
    app = cdk.App()
    config = _config()
    stack = StaticReviewStack(
        app,
        static_review_stack_name(config),
        config=config,
        env=cdk.Environment(account="123456789012", region="eu-central-1"),
    )
    return Template.from_stack(stack)


def test_static_review_stack_defines_core_resources() -> None:
    template = _template()

    template.resource_count_is("AWS::S3::Bucket", 1)
    template.resource_count_is("AWS::Amplify::App", 1)
    template.resource_count_is("AWS::Amplify::Branch", 1)
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.resource_count_is("AWS::Lambda::Url", 1)
    template.resource_count_is("AWS::Logs::LogGroup", 1)


def test_static_review_stack_hardens_storage_and_comments_table() -> None:
    template = _template()

    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
            "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
            "VersioningConfiguration": {"Status": "Enabled"},
        },
    )
    bucket = next(iter(template.find_resources("AWS::S3::Bucket").values()))["Properties"]
    assert "eu-central-1" in json.dumps(bucket["BucketName"])
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "BillingMode": "PAY_PER_REQUEST",
            "DeletionProtectionEnabled": True,
            "KeySchema": [
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
        },
    )


def test_static_review_lambda_asset_uses_tools_package_only() -> None:
    template = _template()

    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "static_review.service.handler.lambda_handler",
            "Runtime": "python3.13",
            "ReservedConcurrentExecutions": 10,
        },
    )


def test_static_review_function_url_cors_uses_amplify_origin() -> None:
    template = _template()

    template.has_resource_properties(
        "AWS::Lambda::Url",
        {
            "AuthType": "NONE",
            "Cors": {
                "AllowHeaders": ["content-type"],
                "AllowMethods": ["DELETE", "GET", "PATCH", "POST"],
                "AllowOrigins": [Match.any_value()],
                "MaxAge": 300,
            },
        },
    )
    resources = template.find_resources("AWS::Lambda::Url")
    origin = next(iter(resources.values()))["Properties"]["Cors"]["AllowOrigins"][0]
    assert "https://main." in json.dumps(origin)


def test_static_review_lambda_policy_is_limited_to_comment_actions() -> None:
    policies = _template().find_resources("AWS::IAM::Policy")
    policy_text = json.dumps(policies)

    assert "dynamodb:GetItem" in policy_text
    assert "dynamodb:PutItem" in policy_text
    assert "dynamodb:Query" in policy_text
    assert "dynamodb:UpdateItem" in policy_text
    assert "dynamodb:DeleteItem" not in policy_text
    assert "dynamodb:Scan" not in policy_text
    assert "dynamodb:BatchWriteItem" not in policy_text


def test_static_review_stack_exports_publisher_contract_outputs() -> None:
    template = _template().to_json()
    outputs = template["Outputs"]

    for output_key in OUTPUT_KEYS.values():
        assert output_key in outputs


def test_static_review_stack_grants_public_function_url_invocation() -> None:
    resources = _template().find_resources("AWS::Lambda::Permission")
    actions = {resource["Properties"]["Action"] for resource in resources.values()}

    assert "lambda:InvokeFunctionUrl" in actions
    assert "lambda:InvokeFunction" in actions


def test_static_review_stack_limits_amplify_bucket_policy_to_site_prefix() -> None:
    template = _template()

    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Sid": "AllowAmplifyListSitePrefix",
                                "Action": "s3:ListBucket",
                                "Condition": Match.object_like(
                                    {"StringLike": {"s3:prefix": ["site", "site/", "site/*"]}}
                                ),
                            }
                        ),
                        Match.object_like(
                            {
                                "Sid": "AllowAmplifyReadSitePrefix",
                                "Action": "s3:GetObject",
                            }
                        ),
                    ]
                )
            }
        },
    )


def test_static_review_amplify_bucket_policy_allows_encoded_source_arn() -> None:
    resources = _template().find_resources("AWS::S3::BucketPolicy")
    policy = next(iter(resources.values()))["Properties"]["PolicyDocument"]
    policy_json = json.dumps(policy)

    assert "arn%3A" in policy_json
    assert "apps%2F" in policy_json
    assert "%2Fbranches%2Fmain" in policy_json
