from __future__ import annotations

from collections import Counter
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from typing import Annotated

import typer
from rich.console import Console

from ai_hiring_radar.company_enrichment import (
    PydanticAICompanyEnrichmentExtractor,
    run_company_enrichment,
)
from ai_hiring_radar.config import (
    load_countries_config,
    load_settings,
    load_taxonomy_config,
    require_inspection_database_url,
    require_serper_api_key,
)
from ai_hiring_radar.export import export_company_review_files
from ai_hiring_radar.inspection import export_company_inspection_artifact
from ai_hiring_radar.inspection_db import sync_inspection_database
from ai_hiring_radar.job_description_extraction import (
    PydanticAIJobDescriptionExtractor,
    run_job_description_extraction,
)
from ai_hiring_radar.llm_usage import format_usage_summary, format_usd
from ai_hiring_radar.processing import process_collection
from ai_hiring_radar.search_locations import LocationDepth
from ai_hiring_radar.sources.collection_resilience import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_DELAY_SECONDS,
    read_ats_board_file,
)
from ai_hiring_radar.sources.ats_discovery import (
    AtsDiscoveryDepth,
    AtsDiscoveryQuery,
    AtsDiscoveryResult,
)
from ai_hiring_radar.sources.ats_providers import (
    AtsClientOptions,
    AtsProvider,
    AtsProviderSpec,
    get_ats_provider_spec,
)
from ai_hiring_radar.sources.serper_google import SerperGoogleClient
from ai_hiring_radar.storage_json import DEFAULT_DATA_DIR, ats_discovery_dir, read_json


app = typer.Typer(help="European AI hiring radar MVP.")
ats_app = typer.Typer(help="Discover and collect public ATS job boards.")
app.add_typer(ats_app, name="ats")
console = Console()


def _parse_country_codes(countries: str) -> list[str]:
    config = load_countries_config()
    codes = [code.strip().lower() for code in countries.split(",") if code.strip()]

    if not codes:
        raise typer.BadParameter("At least one country code is required.")

    unknown_codes = sorted(set(codes) - set(config.countries))
    if unknown_codes:
        available_codes = ",".join(sorted(config.countries))
        raise typer.BadParameter(
            f"Unknown country code(s): {','.join(unknown_codes)}. "
            f"Available country codes: {available_codes}."
        )

    return codes


def _parse_iso_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("Date must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value:
        raise typer.BadParameter("Date must use YYYY-MM-DD format.")
    return value


def _resolve_explicit_board_values(
    board_urls: list[str] | None,
    boards_file: Path | None,
    normalize_board,  # noqa: ANN001 - provider normalizers return distinct board types.
) -> tuple[bool, list[str]]:
    explicit_input = board_urls is not None or boards_file is not None
    if not explicit_input:
        return False, []

    values = list(board_urls or [])
    if boards_file is not None:
        try:
            values.extend(read_ats_board_file(boards_file))
        except (OSError, ValueError, RecursionError) as exc:
            console.print(f"[red]Could not read boards file: {exc}[/red]")
            raise typer.Exit(code=1) from exc

    board_values: list[str] = []
    seen_slugs: set[str] = set()
    for value in values:
        board = normalize_board(value)
        if board.platform_company_slug in seen_slugs:
            continue
        seen_slugs.add(board.platform_company_slug)
        board_values.append(board.board_url)
    return True, board_values


def _launch_inspection_app(collection_date: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(Path(__file__).with_name("inspection_app.py")),
            "--",
            "--date",
            collection_date,
        ],
        check=True,
    )


def _parse_location_depth(value: str) -> LocationDepth:
    try:
        return LocationDepth(value.strip().lower())
    except ValueError as exc:
        raise typer.BadParameter("Location depth must be 'country' or 'cities'.") from exc


def _parse_ats_discovery_depth(value: str) -> AtsDiscoveryDepth:
    try:
        return AtsDiscoveryDepth(value.strip().lower())
    except ValueError as exc:
        raise typer.BadParameter(
            "ATS discovery depth must be 'standard', 'broad', or 'exhaustive'."
        ) from exc


def _parse_role_terms(role: str | None) -> list[str]:
    taxonomy_config = load_taxonomy_config()
    all_roles = taxonomy_config.all_roles

    if role is None:
        return all_roles

    normalized_role = " ".join(role.split()).casefold()
    roles_by_normalized_name = {item.casefold(): item for item in all_roles}
    selected_role = roles_by_normalized_name.get(normalized_role)
    if selected_role is None:
        raise typer.BadParameter(
            "Unknown role term. Available role terms: " + ", ".join(all_roles)
        )

    return [selected_role]


def _build_search_queries(
    *,
    country_codes: list[str],
    role: str | None = None,
    limit: int | None = None,
    location_depth: LocationDepth = LocationDepth.COUNTRY,
) -> list[SearchQuery]:
    countries_config = load_countries_config()
    role_terms = _parse_role_terms(role)
    return generate_search_queries(
        countries_config=countries_config,
        country_codes=country_codes,
        role_terms=role_terms,
        limit=limit,
        location_depth=location_depth,
    )


def _print_collection_plan(
    country_codes: list[str],
    *,
    location_depth: LocationDepth = LocationDepth.COUNTRY,
) -> None:
    countries_config = load_countries_config()
    search_queries = _build_search_queries(
        country_codes=country_codes,
        location_depth=location_depth,
    )
    country_names = [countries_config.countries[code].name for code in country_codes]

    console.print(f"Countries: {', '.join(country_names)}")
    console.print(f"Location depth: {location_depth.value}")
    console.print(f"Queries: {len(search_queries)}")


def _print_dry_run_queries(search_queries: list[SearchQuery]) -> None:
    console.print(
        f"Generated {len(search_queries)} LinkedIn-safe Serper Google queries."
    )
    for index, search_query in enumerate(search_queries, start=1):
        console.print(
            f"{index}. "
            f"[{search_query.country_code}/{search_query.search_location_label}] "
            f"{search_query.search_query}",
            markup=False,
        )


def _latest_ashby_discovery_manifest_path():  # noqa: ANN201
    root = DEFAULT_DATA_DIR / "raw" / "ats_discovery"
    if not root.exists():
        raise FileNotFoundError(f"No ATS discovery directory exists: {root}")

    candidates = sorted(root.glob("*/ashby/manifest.json"))
    if not candidates:
        raise FileNotFoundError(f"No Ashby discovery manifest found under: {root}")
    return candidates[-1]


def _ashby_discovery_manifest_path(date_value: str | None):  # noqa: ANN201
    if date_value is None:
        return _latest_ashby_discovery_manifest_path()
    return ats_discovery_dir(_parse_iso_date(date_value), platform="ashby") / "manifest.json"


def _resolve_ats_discovery_options(
    spec: AtsProviderSpec,
    *,
    results_per_query: int | None,
    pages: int | None,
) -> tuple[int, int]:
    resolved_results = (
        spec.default_results_per_query
        if results_per_query is None
        else results_per_query
    )
    if resolved_results > spec.max_results_per_query:
        raise typer.BadParameter(
            f"{spec.display_name} accepts at most "
            f"{spec.max_results_per_query} results per query.",
            param_hint="--results-per-query",
        )
    return resolved_results, spec.default_pages if pages is None else pages


def _build_ats_discovery_queries(
    spec: AtsProviderSpec,
    *,
    country_codes: list[str],
    limit: int | None,
    location_depth: LocationDepth,
    discovery_depth: AtsDiscoveryDepth,
    results_per_query: int,
    pages: int,
) -> list[AtsDiscoveryQuery]:
    return spec.generate_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=country_codes,
        limit=limit,
        num=results_per_query,
        pages=pages,
        location_depth=location_depth,
        discovery_depth=discovery_depth,
        role_terms=load_taxonomy_config().all_roles,
    )


def _print_ats_discovery_queries(
    spec: AtsProviderSpec,
    search_queries: list[AtsDiscoveryQuery],
) -> None:
    console.print(
        f"Generated {len(search_queries)} {spec.display_name} discovery queries."
    )
    for index, search_query in enumerate(search_queries, start=1):
        console.print(
            f"{index}. "
            f"[{search_query.country_code}/{search_query.search_location_label}] "
            f"{search_query.discovery_query_type} "
            f"page={search_query.page} "
            f"{search_query.search_query}",
            markup=False,
        )


def _run_ats_discovery(
    spec: AtsProviderSpec,
    discovery_queries: list[AtsDiscoveryQuery],
) -> AtsDiscoveryResult:
    try:
        api_key = require_serper_api_key()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    client = SerperGoogleClient(api_key=api_key)
    try:
        result = spec.discover_boards(discovery_queries, client=client)
    finally:
        client.close()

    console.print(
        f"{spec.display_name} discovery complete: "
        f"{result.board_count} board(s), "
        f"{result.query_count} querie(s), "
        f"{result.error_count} error(s)."
    )
    console.print(f"Boards: {result.boards_path.as_posix()}")
    console.print(f"Manifest: {result.manifest_path.as_posix()}")
    return result


@app.command()
def collect(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes, for example: nl,uk,dk.",
        ),
    ] = "nl,uk,dk",
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            min=1,
            help="Limit the number of generated queries.",
        ),
    ] = None,
    role: Annotated[
        str | None,
        typer.Option(
            "--role",
            help="Run one known role term, for example: AI Product Manager.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Print generated queries without calling Serper.",
        ),
    ] = False,
    location_depth: Annotated[
        str,
        typer.Option(
            "--location-depth",
            help="Search location depth: country or cities.",
        ),
    ] = LocationDepth.COUNTRY.value,
) -> None:
    """Collect raw Serper Google Search responses."""
    country_codes = _parse_country_codes(countries)
    parsed_location_depth = _parse_location_depth(location_depth)
    search_queries = _build_search_queries(
        country_codes=country_codes,
        role=role,
        limit=limit,
        location_depth=parsed_location_depth,
    )

    if dry_run:
        _print_dry_run_queries(search_queries)
        return

    try:
        api_key = require_serper_api_key()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    client = SerperGoogleClient(api_key=api_key)
    try:
        result = collect_searches(search_queries, client=client)
    finally:
        client.close()

    console.print(
        "Collection complete: "
        f"{result.successful_count}/{result.query_count} raw file(s) written; "
        f"{result.error_count} error(s)."
    )
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@ats_app.command("discover")
def ats_discover(
    provider: Annotated[
        AtsProvider,
        typer.Argument(help="ATS provider to discover."),
    ],
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for ATS board discovery.",
        ),
    ] = "nl,uk,dk",
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            min=1,
            help="Limit the number of generated discovery queries.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Print generated discovery queries without calling Serper.",
        ),
    ] = False,
    location_depth: Annotated[
        str,
        typer.Option(
            "--location-depth",
            help="Search location depth: country or cities.",
        ),
    ] = LocationDepth.CITIES.value,
    discovery_depth: Annotated[
        str,
        typer.Option(
            "--discovery-depth",
            help="ATS discovery depth: standard, broad, or exhaustive.",
        ),
    ] = AtsDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int | None,
        typer.Option(
            "--results-per-query",
            min=1,
            help=(
                "Serper results requested per discovery query. "
                "Defaults to the selected provider setting (currently 10)."
            ),
        ),
    ] = None,
    pages: Annotated[
        int | None,
        typer.Option(
            "--pages",
            min=1,
            help=(
                "Serper result pages requested per discovery query. "
                "Defaults to the selected provider setting (currently 2)."
            ),
        ),
    ] = None,
) -> None:
    """Discover public ATS board URLs through search-index queries."""
    spec = get_ats_provider_spec(provider)
    resolved_results, resolved_pages = _resolve_ats_discovery_options(
        spec,
        results_per_query=results_per_query,
        pages=pages,
    )
    discovery_queries = _build_ats_discovery_queries(
        spec,
        country_codes=_parse_country_codes(countries),
        limit=limit,
        location_depth=_parse_location_depth(location_depth),
        discovery_depth=_parse_ats_discovery_depth(discovery_depth),
        results_per_query=resolved_results,
        pages=resolved_pages,
    )

    if dry_run:
        _print_ats_discovery_queries(spec, discovery_queries)
        return

    _run_ats_discovery(spec, discovery_queries)


@ats_app.command("collect")
def ats_collect(
    provider: Annotated[
        AtsProvider,
        typer.Argument(help="ATS provider to collect."),
    ],
    board_url: Annotated[
        list[str] | None,
        typer.Option(
            "--board-url",
            help="ATS board URL or identifier. Can be repeated to skip discovery.",
        ),
    ] = None,
    boards_file: Annotated[
        Path | None,
        typer.Option(
            "--boards-file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="JSONL or plain-text file containing ATS board values.",
        ),
    ] = None,
    collection_date: Annotated[
        str | None,
        typer.Option("--collection-date", help="Collection date in YYYY-MM-DD format."),
    ] = None,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume/--no-resume",
            help="Reuse successful board results already collected for this date.",
        ),
    ] = True,
    request_delay_seconds: Annotated[
        float,
        typer.Option(
            "--request-delay",
            min=0,
            help="Delay in seconds between provider requests.",
        ),
    ] = DEFAULT_REQUEST_DELAY_SECONDS,
    max_retries: Annotated[
        int,
        typer.Option(
            "--max-retries",
            min=0,
            help="Maximum retries for transient provider request failures.",
        ),
    ] = DEFAULT_MAX_RETRIES,
    language: Annotated[
        str | None,
        typer.Option(
            "--language",
            help=(
                "Personio feed language (default: en). "
                "Accepted but ignored by other providers."
            ),
        ),
    ] = None,
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for ATS board discovery.",
        ),
    ] = "nl,uk,dk",
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            min=1,
            help="Limit the number of generated discovery queries.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Print discovery queries or normalized boards without fetching jobs.",
        ),
    ] = False,
    location_depth: Annotated[
        str,
        typer.Option(
            "--location-depth",
            help="Search location depth: country or cities.",
        ),
    ] = LocationDepth.CITIES.value,
    discovery_depth: Annotated[
        str,
        typer.Option(
            "--discovery-depth",
            help="ATS discovery depth: standard, broad, or exhaustive.",
        ),
    ] = AtsDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int | None,
        typer.Option(
            "--results-per-query",
            min=1,
            help=(
                "Serper results requested per discovery query. "
                "Defaults to the selected provider setting (currently 10)."
            ),
        ),
    ] = None,
    pages: Annotated[
        int | None,
        typer.Option(
            "--pages",
            min=1,
            help=(
                "Serper result pages requested per discovery query. "
                "Defaults to the selected provider setting (currently 2)."
            ),
        ),
    ] = None,
) -> None:
    """Discover ATS boards and collect their public job data."""
    spec = get_ats_provider_spec(provider)
    parsed_collection_date = (
        _parse_iso_date(collection_date) if collection_date is not None else None
    )
    resolved_results, resolved_pages = _resolve_ats_discovery_options(
        spec,
        results_per_query=results_per_query,
        pages=pages,
    )
    explicit_input, board_values = _resolve_explicit_board_values(
        board_url,
        boards_file,
        spec.normalize_board,
    )

    if explicit_input:
        if dry_run:
            console.print(
                f"Normalized {len(board_values)} {spec.display_name} board URL(s)."
            )
            for value in board_values:
                console.print(value, markup=False)
            return
    else:
        discovery_queries = _build_ats_discovery_queries(
            spec,
            country_codes=_parse_country_codes(countries),
            limit=limit,
            location_depth=_parse_location_depth(location_depth),
            discovery_depth=_parse_ats_discovery_depth(discovery_depth),
            results_per_query=resolved_results,
            pages=resolved_pages,
        )
        if dry_run:
            _print_ats_discovery_queries(spec, discovery_queries)
            return

        discovery_result = _run_ats_discovery(spec, discovery_queries)
        board_values = [str(record["board_url"]) for record in discovery_result.boards]

    if not board_values:
        console.print(f"No {spec.display_name} boards to collect.")
        return

    client = spec.make_client(
        AtsClientOptions(
            request_delay_seconds=request_delay_seconds,
            max_retries=max_retries,
            language=language,
        )
    )
    try:
        result = spec.collect_boards(
            board_values,
            client=client,
            collection_date=parsed_collection_date,
            resume=resume,
        )
    finally:
        client.close()

    console.print(
        f"{spec.display_name} collection complete: "
        f"{result.board_count} board(s), "
        f"{len(result.result_files)} result file(s) available, "
        f"{result.written_count} written, "
        f"{result.resumed_count} resumed, "
        f"{result.error_count} error(s)."
    )
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("debug-ashby-discovery")
def debug_ashby_discovery(
    date_value: Annotated[
        str | None,
        typer.Option("--date", help="Discovery date in YYYY-MM-DD format."),
    ] = None,
    sample: Annotated[
        int,
        typer.Option(
            "--sample",
            min=1,
            help="Number of individual error records to print.",
        ),
    ] = 5,
    as_json: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print machine-readable JSON for easy pasting or redirection.",
        ),
    ] = False,
) -> None:
    """Print a paste-friendly Ashby discovery error summary."""
    manifest_path = _ashby_discovery_manifest_path(date_value)
    try:
        manifest = read_json(manifest_path)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not isinstance(manifest, dict):
        console.print(f"[red]Expected JSON object in {manifest_path}[/red]")
        raise typer.Exit(code=1)

    errors = manifest.get("errors")
    if not isinstance(errors, list):
        errors = []

    status_counts = Counter(
        str(error.get("status_code") or "unknown")
        for error in errors
        if isinstance(error, dict)
    )
    type_counts = Counter(
        str(error.get("error_type") or "unknown")
        for error in errors
        if isinstance(error, dict)
    )

    if as_json:
        print(
            json.dumps(
                {
                    "manifest": manifest_path.as_posix(),
                    "query_count": manifest.get("query_count"),
                    "board_count": manifest.get("board_count"),
                    "error_count": len(errors),
                    "status_counts": dict(status_counts),
                    "error_type_counts": dict(type_counts),
                    "errors": [
                        error for error in errors[:sample] if isinstance(error, dict)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    console.print(f"Manifest: {manifest_path.as_posix()}")
    console.print(f"Queries: {manifest.get('query_count')}")
    console.print(f"Boards: {manifest.get('board_count')}")
    console.print(f"Errors: {len(errors)}")

    if status_counts:
        console.print(
            "Status counts: "
            + ", ".join(f"{key}={value}" for key, value in status_counts.items())
        )
    if type_counts:
        console.print(
            "Error type counts: "
            + ", ".join(f"{key}={value}" for key, value in type_counts.items())
        )

    for index, error in enumerate(errors[:sample], start=1):
        if not isinstance(error, dict):
            continue
        console.print(f"\nError {index}:")
        console.print(f"  type: {error.get('error_type')}")
        console.print(f"  status: {error.get('status_code')}")
        console.print(f"  query_type: {error.get('discovery_query_type')}")
        console.print(f"  page: {error.get('search_page')}")
        console.print(f"  query: {error.get('search_query')}", markup=False)
        console.print(f"  request_params: {error.get('request_params')}", markup=False)
        console.print(f"  error: {error.get('error')}", markup=False)
        response_body = error.get("response_body")
        if response_body:
            console.print(f"  response_body: {response_body}", markup=False)


@app.command()
def process(
    date_value: Annotated[
        str,
        typer.Option("--date", help="Collection date in YYYY-MM-DD format."),
    ],
) -> None:
    """Process raw search responses into candidates and company records."""
    collection_date = _parse_iso_date(date_value)
    try:
        result = process_collection(collection_date)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        "Processing complete: "
        f"{result.raw_file_count} raw file(s), "
        f"{result.candidate_count} candidate(s), "
        f"{result.deduped_candidate_count} deduped candidate(s), "
        f"{result.company_count} company record(s)."
    )
    console.print(f"Candidates: {result.job_candidates_path.as_posix()}")
    console.print(f"Companies: {result.companies_path.as_posix()}")


@app.command("extract-job-descriptions")
def extract_job_descriptions(
    date_value: Annotated[
        str,
        typer.Option("--date", help="Processed collection date in YYYY-MM-DD format."),
    ],
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            min=1,
            help="Limit candidates examined for a small extraction run.",
        ),
    ] = None,
    countries: Annotated[
        str | None,
        typer.Option(
            "--countries",
            help="Only extract jobs matching any comma-separated country code, for example: nl,dk.",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Override JOB_DESCRIPTION_EXTRACTION_MODEL for this run.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Count processable candidates without model calls or output writes.",
        ),
    ] = False,
    show_progress: Annotated[
        bool,
        typer.Option(
            "--progress/--no-progress",
            help="Show a tqdm progress bar while iterating candidates.",
        ),
    ] = True,
    restart: Annotated[
        bool,
        typer.Option(
            "--restart",
            help="Clear existing job description extracts for this date before running.",
        ),
    ] = False,
) -> None:
    """Extract structured datapoints from processed job descriptions."""
    collection_date = _parse_iso_date(date_value)
    country_codes = None
    country_names = None
    if countries is not None:
        countries_config = load_countries_config()
        country_codes = _parse_country_codes(countries)
        country_names = [
            countries_config.countries[country_code].name for country_code in country_codes
        ]

    settings = load_settings()
    model_name = (
        model
        or settings.azure_openai_deployment_name
        or settings.job_description_extraction_model
    )
    try:
        extractor = (
            None
            if dry_run
            else PydanticAIJobDescriptionExtractor(
                model=model_name,
                provider=settings.job_description_extraction_provider,
                azure_endpoint=settings.azure_openai_endpoint,
                azure_api_key=settings.azure_openai_api_key,
                azure_api_version=settings.azure_openai_api_version,
            )
        )
    except Exception as exc:  # noqa: BLE001 - provider config errors should be readable.
        console.print(f"[red]Failed to initialize extraction model: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        result = run_job_description_extraction(
            collection_date,
            extractor=extractor,
            model=model_name,
            limit=limit,
            country_codes=country_codes,
            country_names=country_names,
            dry_run=dry_run,
            show_progress=show_progress,
            restart=restart,
        )
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        "Job description extraction "
        + ("dry run" if result.dry_run else "complete")
        + ": "
        f"{result.candidates_read} candidate(s) read, "
        f"{result.processable_count} processable, "
        f"{result.extracted_count} extracted, "
        f"{result.already_processed_count} already completed, "
        f"{result.skipped_count} skipped, "
        f"{result.validation_error_count} validation error(s), "
        f"{result.llm_error_count} LLM error(s)."
    )
    console.print(f"Collection date: {result.collection_date}")
    console.print(f"Model: {result.model}")
    console.print(f"Candidates: {result.input_path.as_posix()}")
    console.print(f"Extracts: {result.output_path.as_posix()}")
    _print_llm_usage_summary(result)


@app.command("enrich-companies")
def enrich_companies(
    date_value: Annotated[
        str,
        typer.Option("--date", help="Processed collection date in YYYY-MM-DD format."),
    ],
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            min=1,
            help="Limit companies examined for a small enrichment run.",
        ),
    ] = None,
    countries: Annotated[
        str | None,
        typer.Option(
            "--countries",
            help="Only enrich companies matching any comma-separated country code, for example: nl,dk.",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Override COMPANY_ENRICHMENT_MODEL for this run.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Count processable companies without model calls or output writes.",
        ),
    ] = False,
    show_progress: Annotated[
        bool,
        typer.Option(
            "--progress/--no-progress",
            help="Show a tqdm progress bar while iterating companies.",
        ),
    ] = True,
    restart: Annotated[
        bool,
        typer.Option(
            "--restart",
            help="Clear existing company enrichment extracts for this date before running.",
        ),
    ] = False,
) -> None:
    """Enrich processed company records with web-researched company facts."""
    collection_date = _parse_iso_date(date_value)
    country_names = None
    if countries is not None:
        countries_config = load_countries_config()
        country_codes = _parse_country_codes(countries)
        country_names = [
            countries_config.countries[country_code].name for country_code in country_codes
        ]

    settings = load_settings()
    model_name = model or settings.company_enrichment_model
    try:
        extractor = (
            None
            if dry_run
            else PydanticAICompanyEnrichmentExtractor(
                model=model_name,
                azure_endpoint=settings.azure_openai_endpoint,
                azure_api_key=settings.azure_openai_api_key,
                azure_api_version=settings.azure_openai_api_version,
            )
        )
    except Exception as exc:  # noqa: BLE001 - provider config errors should be readable.
        console.print(f"[red]Failed to initialize company enrichment model: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        result = run_company_enrichment(
            collection_date,
            extractor=extractor,
            model=model_name,
            limit=limit,
            country_names=country_names,
            dry_run=dry_run,
            show_progress=show_progress,
            restart=restart,
        )
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        "Company enrichment "
        + ("dry run" if result.dry_run else "complete")
        + ": "
        f"{result.companies_read} company record(s) read, "
        f"{result.processable_count} processable, "
        f"{result.enriched_count} enriched, "
        f"{result.already_processed_count} already completed, "
        f"{result.skipped_count} skipped, "
        f"{result.validation_error_count} validation error(s), "
        f"{result.llm_error_count} LLM error(s), "
        f"{result.quality_error_count} quality error(s)."
    )
    console.print(f"Collection date: {result.collection_date}")
    console.print(f"Model: {result.model}")
    console.print(f"Companies: {result.company_input_path.as_posix()}")
    console.print(f"Candidates: {result.candidate_input_path.as_posix()}")
    console.print(f"Extracts: {result.output_path.as_posix()}")
    _print_llm_usage_summary(result)
    _print_company_enrichment_issue_samples(result)


def _print_llm_usage_summary(result) -> None:  # noqa: ANN001 - shared CLI helper.
    usage = getattr(result, "llm_usage", None)
    if usage is None or not any(
        (
            usage.requests,
            usage.tool_calls,
            usage.input_tokens,
            usage.cache_read_tokens,
            usage.output_tokens,
        )
    ):
        return

    console.print(f"LLM usage: {format_usage_summary(usage)}")
    estimated_cost = getattr(result, "llm_estimated_cost_usd", None)
    if estimated_cost is not None:
        console.print(f"Estimated LLM cost: {format_usd(estimated_cost)}")
        return

    missing_models = getattr(result, "llm_pricing_missing_models", ())
    missing = ", ".join(missing_models) if missing_models else "unknown model"
    console.print(f"Estimated LLM cost: unavailable; missing pricing for {missing}")


def _print_company_enrichment_issue_samples(
    result,  # noqa: ANN001 - small CLI formatting helper for the run result object.
) -> None:
    sample_groups = (
        ("Validation error samples", result.validation_error_samples),
        ("LLM error samples", result.llm_error_samples),
        ("Quality error samples", result.quality_error_samples),
    )
    for label, samples in sample_groups:
        if not samples:
            continue
        console.print(f"{label}:")
        for issue in samples:
            company = issue.company or "unknown company"
            console.print(
                f"- {company}: {issue.error_type}: {issue.message}",
                markup=False,
            )


@app.command("export")
def export_command(
    date_value: Annotated[
        str,
        typer.Option("--date", help="Collection date in YYYY-MM-DD format."),
    ],
) -> None:
    """Export company review CSV and Markdown files."""
    collection_date = _parse_iso_date(date_value)
    try:
        result = export_company_review_files(collection_date)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"Export complete: {result.company_count} company record(s).")
    console.print(f"CSV: {result.csv_path.as_posix()}")
    console.print(f"Markdown: {result.markdown_path.as_posix()}")


@app.command("export-inspection")
def export_inspection_command(
    date_value: Annotated[
        str,
        typer.Option("--date", help="Collection date in YYYY-MM-DD format."),
    ],
) -> None:
    """Export compact Streamlit inspection data for deployment."""
    collection_date = _parse_iso_date(date_value)
    try:
        result = export_company_inspection_artifact(collection_date)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        "Inspection artifact complete: "
        f"{result.company_count} company record(s), "
        f"{result.job_count} job record(s)."
    )
    console.print(f"Artifact: {result.path.as_posix()}")


@app.command("sync-inspection-db")
def sync_inspection_db_command(
    date_value: Annotated[
        str,
        typer.Option("--date", help="Collection date in YYYY-MM-DD format."),
    ],
) -> None:
    """Sync compact company inspection snapshots into Postgres."""
    collection_date = _parse_iso_date(date_value)
    try:
        database_url = require_inspection_database_url()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        result = sync_inspection_database(
            collection_date,
            database_url=database_url,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Inspection DB sync failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        "Inspection DB sync complete: "
        f"{result.snapshot_count} company snapshot(s), "
        f"{result.job_count} compact job(s)."
    )
    console.print(f"Collection date: {result.collection_date}")
    console.print("Source: data/processed")
    console.print(
        "Database: configured"
        if result.database_url_configured
        else "Database: not configured"
    )


@app.command("inspect")
def inspect_command(
    date_value: Annotated[
        str,
        typer.Option("--date", help="Collection date in YYYY-MM-DD format."),
    ],
) -> None:
    """Launch the local read-only company inspection UI."""
    collection_date = _parse_iso_date(date_value)
    console.print(f"Launching company inspection UI for {collection_date}.")
    try:
        _launch_inspection_app(collection_date)
    except subprocess.CalledProcessError as exc:
        raise typer.Exit(code=exc.returncode) from exc


def main() -> None:
    app()


if __name__ == "__main__":
    main()
