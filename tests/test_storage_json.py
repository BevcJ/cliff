from datetime import date

from ai_hiring_radar.storage_json import (
    read_json,
    stable_search_filename,
    write_processed_jsonl,
    write_raw_search_response,
)


def test_stable_search_filename() -> None:
    assert (
        stable_search_filename(
            country_code="nl",
            role_term="AI Product Manager",
            search_location="Netherlands",
        )
        == "nl_ai-product-manager_netherlands.json"
    )

    assert (
        stable_search_filename(
            country_code="nl",
            role_term="AI Product Manager",
            search_location="Amsterdam",
        )
        == "nl_ai-product-manager_amsterdam.json"
    )


def test_raw_json_can_be_written_and_read_back(tmp_path) -> None:
    path = write_raw_search_response(
        {"organic_results": [{"title": "AI Product Manager"}]},
        country_code="nl",
        role_term="AI Product Manager",
        search_location="Netherlands",
        collection_date=date(2026, 6, 13),
        data_dir=tmp_path,
    )

    assert path == (
        tmp_path
        / "raw"
        / "searches"
        / "2026-06-13"
        / "serper_google"
        / "nl_ai-product-manager_netherlands.json"
    )
    assert read_json(path) == {"organic_results": [{"title": "AI Product Manager"}]}


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
