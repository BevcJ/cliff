from datetime import date

from ai_hiring_radar.storage_json import (
    read_json,
    stable_board_filename,
    write_processed_jsonl,
    write_raw_ats_response,
)


def test_stable_board_filename() -> None:
    assert stable_board_filename(platform_company_slug="Acme AI") == "acme-ai.json"
    assert stable_board_filename(platform_company_slug="") == "unknown.json"


def test_raw_ats_json_can_be_written_and_read_back(tmp_path) -> None:
    path = write_raw_ats_response(
        {"record_type": "raw_ats_response", "response": {"jobs": []}},
        platform_company_slug="acme-ai",
        collection_date=date(2026, 6, 13),
        data_dir=tmp_path,
        platform="greenhouse",
    )

    assert path == (
        tmp_path / "raw" / "ats" / "2026-06-13" / "greenhouse" / "acme-ai.json"
    )
    assert read_json(path) == {"record_type": "raw_ats_response", "response": {"jobs": []}}


def test_processed_jsonl_is_written_under_processed_dir(tmp_path) -> None:
    path = write_processed_jsonl(
        "job_candidates_2026-06-13.jsonl",
        [{"record_type": "job_candidate", "job_id": "123"}],
        data_dir=tmp_path,
    )

    assert path == tmp_path / "processed" / "job_candidates_2026-06-13.jsonl"
    assert path.read_text(encoding="utf-8") == (
        '{"job_id": "123", "record_type": "job_candidate"}\n'
    )
