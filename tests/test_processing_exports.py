from ai_hiring_radar.export import export_company_review_files
from ai_hiring_radar.processing import process_collection
from ai_hiring_radar.sources.ashby import ashby_board_from_slug, build_raw_ashby_response_record
from ai_hiring_radar.storage_json import read_jsonl, write_raw_ats_response


def test_process_collection_and_export_files(tmp_path) -> None:
    raw_record = build_raw_ashby_response_record(
        board=ashby_board_from_slug("example-ai"),
        collected_at="2026-06-13T10:30:00Z",
        response={
            "data": {
                "jobBoard": {
                    "teams": [
                        {
                            "id": "team-ai",
                            "name": "AI",
                            "externalName": None,
                            "parentTeamId": None,
                        }
                    ],
                    "jobPostings": [
                        {
                            "id": "job-ai-product-manager",
                            "title": "AI Product Manager",
                            "teamId": "team-ai",
                            "locationName": "Netherlands",
                            "workplaceType": "Remote",
                            "employmentType": "FullTime",
                            "secondaryLocations": [],
                            "compensationTierSummary": None,
                        }
                    ],
                }
            }
        },
    )
    write_raw_ats_response(
        raw_record,
        platform_company_slug="example-ai",
        collection_date="2026-06-13",
        data_dir=tmp_path,
    )

    processing_result = process_collection("2026-06-13", data_dir=tmp_path)

    assert processing_result.raw_file_count == 1
    assert processing_result.candidate_count == 1
    assert processing_result.deduped_candidate_count == 1
    assert processing_result.company_count == 1

    candidates = read_jsonl(processing_result.job_candidates_path)
    assert candidates[0]["company_normalized"] == "Example Ai"
    assert candidates[0]["job_title_normalized"] == "AI Product Manager"
    assert candidates[0]["role_group"] == "AI Product Role"

    companies = read_jsonl(processing_result.companies_path)
    assert companies[0]["company"] == "Example Ai"
    assert companies[0]["matched_search_terms"] == ["AI Product Manager"]
    assert companies[0]["evidence_urls"] == ["https://jobs.ashbyhq.com/example-ai"]
    assert companies[0]["ai_role_title_counts"] == [
        {"title": "AI Product Manager", "count": 1}
    ]
    assert companies[0]["review_status"] == "new"

    export_result = export_company_review_files("2026-06-13", data_dir=tmp_path)

    assert export_result.company_count == 1
    csv_content = export_result.csv_path.read_text(encoding="utf-8")
    markdown_content = export_result.markdown_path.read_text(encoding="utf-8")
    assert "Company,Countries,Role Classification" in csv_content
    assert "AI Role Title Counts" in csv_content
    assert "AI Product Manager (1)" in csv_content
    assert "Example Ai" in csv_content
    assert "## AI Product Role" in markdown_content
    assert "| Company | Countries | Titles | Role Title Counts |" in markdown_content
    assert "AI Product Manager (1)" in markdown_content
