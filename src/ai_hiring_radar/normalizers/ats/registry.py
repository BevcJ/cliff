from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ai_hiring_radar.classify import clean_text
from ai_hiring_radar.models import SourceName
from ai_hiring_radar.normalizers.ats.ashby.normalizer import (
    normalize_response as normalize_ashby_response,
)
from ai_hiring_radar.normalizers.ats.greenhouse.normalizer import (
    normalize_response as normalize_greenhouse_response,
)
from ai_hiring_radar.normalizers.ats.lever.normalizer import (
    normalize_response as normalize_lever_response,
)
from ai_hiring_radar.normalizers.ats.personio.normalizer import (
    normalize_response as normalize_personio_response,
)
from ai_hiring_radar.normalizers.ats.recruitee.normalizer import (
    normalize_response as normalize_recruitee_response,
)
from ai_hiring_radar.normalizers.ats.smartrecruiters.normalizer import (
    normalize_response as normalize_smartrecruiters_response,
)
from ai_hiring_radar.normalizers.ats.teamtailor.normalizer import (
    normalize_response as normalize_teamtailor_response,
)
from ai_hiring_radar.normalizers.ats.workable.normalizer import (
    normalize_response as normalize_workable_response,
)
from ai_hiring_radar.normalizers.common.raw import raw_ats_response_payload
from ai_hiring_radar.storage_json import read_json


class AtsNormalizer(Protocol):
    def __call__(
        self,
        *,
        metadata: dict[str, Any],
        response: Any,
        raw_file: Path,
    ) -> list[dict[str, Any]]: ...

ATS_NORMALIZER_PLATFORMS = (
    str(SourceName.ASHBY),
    str(SourceName.GREENHOUSE),
    str(SourceName.LEVER),
    str(SourceName.PERSONIO),
    str(SourceName.RECRUITEE),
    str(SourceName.TEAMTAILOR),
    str(SourceName.SMARTRECRUITERS),
    str(SourceName.WORKABLE),
)

ATS_NORMALIZERS: dict[str, AtsNormalizer] = {
    str(SourceName.ASHBY): normalize_ashby_response,
    str(SourceName.GREENHOUSE): normalize_greenhouse_response,
    str(SourceName.LEVER): normalize_lever_response,
    str(SourceName.PERSONIO): normalize_personio_response,
    str(SourceName.RECRUITEE): normalize_recruitee_response,
    str(SourceName.TEAMTAILOR): normalize_teamtailor_response,
    str(SourceName.SMARTRECRUITERS): normalize_smartrecruiters_response,
    str(SourceName.WORKABLE): normalize_workable_response,
}


def get_ats_normalizer(platform: str) -> AtsNormalizer | None:
    return ATS_NORMALIZERS.get(platform)


def normalize_raw_ats_file(raw_file: Path) -> list[dict[str, Any]]:
    raw_record = read_json(raw_file)
    if not isinstance(raw_record, dict):
        return []

    metadata, response = raw_ats_response_payload(raw_record)
    platform = clean_text(metadata.get("platform")) or str(SourceName.ASHBY)
    normalizer = get_ats_normalizer(platform)
    if normalizer is None:
        return []
    return normalizer(metadata=metadata, response=response, raw_file=raw_file)
