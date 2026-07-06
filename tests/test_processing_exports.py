from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.export import export_company_review_files
from ai_hiring_radar.normalize import process_collection
from ai_hiring_radar.query_builder import generate_search_queries
from ai_hiring_radar.sources.serper_google import build_raw_search_record
from ai_hiring_radar.storage_json import read_jsonl, write_raw_search_response


def test_process_collection_and_export_files(tmp_path) -> None:
    search_query = generate_search_queries(
        countries_config=load_countries_config(),
        country_codes=["nl"],
        role_terms=["AI Product Manager"],
    )[0]
    raw_record = build_raw_search_record(
        search_query=search_query,
        collected_at="2026-06-13T10:30:00Z",
        response={
            "organic": [
                {
                    "position": 1,
                    "title": "2,000+ Product Manager jobs in Netherlands - LinkedIn",
                    "link": "https://www.linkedin.com/jobs/search?keywords=Product+Manager",
                    "snippet": "AI Product Manager. Example Company. Amsterdam.",
                },
                {
                    "position": 2,
                    "title": "Senior AI Product Manager - Example Company",
                    "link": "https://www.linkedin.com/jobs/view/123",
                    "displayed_link": "linkedin.com/jobs/view/123",
                    "snippet": "Example Company is hiring in Amsterdam.",
                }
            ]
        },
    )
    write_raw_search_response(
        raw_record,
        country_code="nl",
        role_term="AI Product Manager",
        search_location="Netherlands",
        collection_date="2026-06-13",
        data_dir=tmp_path,
    )

    processing_result = process_collection("2026-06-13", data_dir=tmp_path)

    assert processing_result.raw_file_count == 1
    assert processing_result.candidate_count == 1
    assert processing_result.deduped_candidate_count == 1
    assert processing_result.company_count == 1

    candidates = read_jsonl(processing_result.job_candidates_path)
    assert candidates[0]["company_normalized"] == "Example Company"
    assert candidates[0]["job_title_normalized"] == "AI Product Manager"
    assert candidates[0]["role_group"] == "AI Product Role"

    companies = read_jsonl(processing_result.companies_path)
    assert companies[0]["company"] == "Example Company"
    assert companies[0]["matched_search_terms"] == ["AI Product Manager"]
    assert companies[0]["evidence_urls"] == [
        "https://www.linkedin.com/jobs/view/123"
    ]
    assert companies[0]["ai_role_title_counts"] == [
        {"title": "Senior AI Product Manager - Example Company", "count": 1}
    ]
    assert companies[0]["review_status"] == "new"

    export_result = export_company_review_files("2026-06-13", data_dir=tmp_path)

    assert export_result.company_count == 1
    csv_content = export_result.csv_path.read_text(encoding="utf-8")
    markdown_content = export_result.markdown_path.read_text(encoding="utf-8")
    assert "Company,Countries,Role Classification" in csv_content
    assert "AI Role Title Counts" in csv_content
    assert "Senior AI Product Manager - Example Company (1)" in csv_content
    assert "Example Company" in csv_content
    assert "## AI Product Role" in markdown_content
    assert "| Company | Countries | Titles | Role Title Counts |" in markdown_content
    assert "Senior AI Product Manager - Example Company (1)" in markdown_content
