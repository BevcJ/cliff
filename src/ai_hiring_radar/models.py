from __future__ import annotations

from enum import StrEnum


class RoleGroup(StrEnum):
    AI_EXECUTION = "AI Execution Role"
    AI_PRODUCT = "AI Product Role"
    BOTH_EXECUTION_AND_PRODUCT = "Both Execution + Product"
    UNCLEAR = "Unclear AI Role"


class EvidenceQuality(StrEnum):
    TITLE_ONLY_SEARCH_RESULT = "title_only_search_result"
    TITLE_ONLY_ATS_LISTING = "title_only_ats_listing"


class SourceName(StrEnum):
    SERPER_GOOGLE = "serper_google"
    ASHBY = "ashby"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    PERSONIO = "personio"
    SMARTRECRUITERS = "smartrecruiters"
    WORKABLE = "workable"


class SourceMode(StrEnum):
    LINKEDIN_SAFE_SEARCH = "linkedin_safe_search"
    ATS_BOARD_DISCOVERY_SEARCH = "ats_board_discovery_search"
    PUBLIC_JOB_BOARD_ENDPOINT = "public_job_board_endpoint"
