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
    require_serper_api_key,
)
from ai_hiring_radar.export import export_company_review_files
from ai_hiring_radar.inspection import export_company_inspection_artifact
from ai_hiring_radar.job_description_extraction import (
    PydanticAIJobDescriptionExtractor,
    run_job_description_extraction,
)
from ai_hiring_radar.llm_usage import format_usage_summary, format_usd
from ai_hiring_radar.normalize import process_collection
from ai_hiring_radar.query_builder import (
    LocationDepth,
    SearchQuery,
    generate_search_queries,
)
from ai_hiring_radar.sources.ashby import (
    AshbyClient,
    AshbyDiscoveryDepth,
    DEFAULT_ASHBY_DISCOVERY_PAGES,
    DEFAULT_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
    MAX_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
    collect_ashby_boards,
    discover_ashby_boards,
    generate_ashby_discovery_queries,
    normalize_ashby_board,
)
from ai_hiring_radar.sources.greenhouse import (
    DEFAULT_GREENHOUSE_DISCOVERY_PAGES,
    DEFAULT_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
    GreenhouseClient,
    GreenhouseDiscoveryDepth,
    MAX_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
    collect_greenhouse_boards,
    discover_greenhouse_boards,
    generate_greenhouse_discovery_queries,
    normalize_greenhouse_board,
)
from ai_hiring_radar.sources.lever import (
    DEFAULT_LEVER_DISCOVERY_PAGES,
    DEFAULT_LEVER_DISCOVERY_RESULTS_PER_QUERY,
    LeverClient,
    LeverDiscoveryDepth,
    MAX_LEVER_DISCOVERY_RESULTS_PER_QUERY,
    collect_lever_boards,
    discover_lever_boards,
    generate_lever_discovery_queries,
    normalize_lever_board,
)
from ai_hiring_radar.sources.personio import (
    DEFAULT_PERSONIO_DISCOVERY_PAGES,
    DEFAULT_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
    DEFAULT_PERSONIO_LANGUAGE,
    MAX_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
    PersonioClient,
    PersonioDiscoveryDepth,
    collect_personio_boards,
    discover_personio_boards,
    generate_personio_discovery_queries,
    normalize_personio_board,
)
from ai_hiring_radar.sources.teamtailor import (
    DEFAULT_TEAMTAILOR_DISCOVERY_PAGES,
    DEFAULT_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
    MAX_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
    TeamtailorClient,
    TeamtailorDiscoveryDepth,
    collect_teamtailor_boards,
    discover_teamtailor_boards,
    generate_teamtailor_discovery_queries,
    normalize_teamtailor_board,
)
from ai_hiring_radar.sources.smartrecruiters import (
    DEFAULT_SMARTRECRUITERS_DISCOVERY_PAGES,
    DEFAULT_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY,
    MAX_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY,
    SmartRecruitersClient,
    SmartRecruitersDiscoveryDepth,
    collect_smartrecruiters_boards,
    discover_smartrecruiters_boards,
    generate_smartrecruiters_discovery_queries,
    normalize_smartrecruiters_board,
)
from ai_hiring_radar.sources.serper_google import SerperGoogleClient, collect_searches
from ai_hiring_radar.storage_json import DEFAULT_DATA_DIR, ats_discovery_dir, read_json


app = typer.Typer(help="European AI hiring radar MVP.")
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
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise typer.BadParameter("Date must use YYYY-MM-DD format.") from exc


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


def _parse_ats_discovery_depth(value: str) -> AshbyDiscoveryDepth:
    try:
        return AshbyDiscoveryDepth(value.strip().lower())
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


def _build_ashby_discovery_queries(
    *,
    country_codes: list[str],
    limit: int | None = None,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: AshbyDiscoveryDepth = AshbyDiscoveryDepth.EXHAUSTIVE,
    results_per_query: int = DEFAULT_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_ASHBY_DISCOVERY_PAGES,
):
    return generate_ashby_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=country_codes,
        limit=limit,
        num=results_per_query,
        pages=pages,
        location_depth=location_depth,
        discovery_depth=discovery_depth,
        role_terms=load_taxonomy_config().all_roles,
    )


def _print_ashby_discovery_queries(search_queries) -> None:  # noqa: ANN001
    console.print(f"Generated {len(search_queries)} Ashby discovery queries.")
    for index, search_query in enumerate(search_queries, start=1):
        console.print(
            f"{index}. "
            f"[{search_query.country_code}/{search_query.search_location_label}] "
            f"{search_query.discovery_query_type} "
            f"page={search_query.page} "
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


def _build_greenhouse_discovery_queries(
    *,
    country_codes: list[str],
    limit: int | None = None,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: GreenhouseDiscoveryDepth = GreenhouseDiscoveryDepth.EXHAUSTIVE,
    results_per_query: int = DEFAULT_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_GREENHOUSE_DISCOVERY_PAGES,
):
    return generate_greenhouse_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=country_codes,
        limit=limit,
        num=results_per_query,
        pages=pages,
        location_depth=location_depth,
        discovery_depth=discovery_depth,
        role_terms=load_taxonomy_config().all_roles,
    )


def _print_greenhouse_discovery_queries(search_queries) -> None:  # noqa: ANN001
    console.print(f"Generated {len(search_queries)} Greenhouse discovery queries.")
    for index, search_query in enumerate(search_queries, start=1):
        console.print(
            f"{index}. "
            f"[{search_query.country_code}/{search_query.search_location_label}] "
            f"{search_query.discovery_query_type} "
            f"page={search_query.page} "
            f"{search_query.search_query}",
            markup=False,
        )


def _build_lever_discovery_queries(
    *,
    country_codes: list[str],
    limit: int | None = None,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: LeverDiscoveryDepth = LeverDiscoveryDepth.EXHAUSTIVE,
    results_per_query: int = DEFAULT_LEVER_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_LEVER_DISCOVERY_PAGES,
):
    return generate_lever_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=country_codes,
        limit=limit,
        num=results_per_query,
        pages=pages,
        location_depth=location_depth,
        discovery_depth=discovery_depth,
        role_terms=load_taxonomy_config().all_roles,
    )


def _print_lever_discovery_queries(search_queries) -> None:  # noqa: ANN001
    console.print(f"Generated {len(search_queries)} Lever discovery queries.")
    for index, search_query in enumerate(search_queries, start=1):
        console.print(
            f"{index}. "
            f"[{search_query.country_code}/{search_query.search_location_label}] "
            f"{search_query.discovery_query_type} "
            f"page={search_query.page} "
            f"{search_query.search_query}",
            markup=False,
        )


def _build_personio_discovery_queries(
    *,
    country_codes: list[str],
    limit: int | None = None,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: PersonioDiscoveryDepth = PersonioDiscoveryDepth.EXHAUSTIVE,
    results_per_query: int = DEFAULT_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_PERSONIO_DISCOVERY_PAGES,
):
    return generate_personio_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=country_codes,
        limit=limit,
        num=results_per_query,
        pages=pages,
        location_depth=location_depth,
        discovery_depth=discovery_depth,
        role_terms=load_taxonomy_config().all_roles,
    )


def _print_personio_discovery_queries(search_queries) -> None:  # noqa: ANN001
    console.print(f"Generated {len(search_queries)} Personio discovery queries.")
    for index, search_query in enumerate(search_queries, start=1):
        console.print(
            f"{index}. "
            f"[{search_query.country_code}/{search_query.search_location_label}] "
            f"{search_query.discovery_query_type} "
            f"page={search_query.page} "
            f"{search_query.search_query}",
            markup=False,
        )


def _build_teamtailor_discovery_queries(
    *,
    country_codes: list[str],
    limit: int | None = None,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: TeamtailorDiscoveryDepth = TeamtailorDiscoveryDepth.EXHAUSTIVE,
    results_per_query: int = DEFAULT_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_TEAMTAILOR_DISCOVERY_PAGES,
):
    return generate_teamtailor_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=country_codes,
        limit=limit,
        num=results_per_query,
        pages=pages,
        location_depth=location_depth,
        discovery_depth=discovery_depth,
        role_terms=load_taxonomy_config().all_roles,
    )


def _print_teamtailor_discovery_queries(search_queries) -> None:  # noqa: ANN001
    console.print(f"Generated {len(search_queries)} Teamtailor discovery queries.")
    for index, search_query in enumerate(search_queries, start=1):
        console.print(
            f"{index}. "
            f"[{search_query.country_code}/{search_query.search_location_label}] "
            f"{search_query.discovery_query_type} "
            f"page={search_query.page} "
            f"{search_query.search_query}",
            markup=False,
        )


def _build_smartrecruiters_discovery_queries(
    *,
    country_codes: list[str],
    limit: int | None = None,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: SmartRecruitersDiscoveryDepth = SmartRecruitersDiscoveryDepth.EXHAUSTIVE,
    results_per_query: int = DEFAULT_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_SMARTRECRUITERS_DISCOVERY_PAGES,
):
    return generate_smartrecruiters_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=country_codes,
        limit=limit,
        num=results_per_query,
        pages=pages,
        location_depth=location_depth,
        discovery_depth=discovery_depth,
        role_terms=load_taxonomy_config().all_roles,
    )


def _print_smartrecruiters_discovery_queries(search_queries) -> None:  # noqa: ANN001
    console.print(f"Generated {len(search_queries)} SmartRecruiters discovery queries.")
    for index, search_query in enumerate(search_queries, start=1):
        console.print(
            f"{index}. "
            f"[{search_query.country_code}/{search_query.search_location_label}] "
            f"{search_query.discovery_query_type} "
            f"page={search_query.page} "
            f"{search_query.search_query}",
            markup=False,
        )


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


@app.command("discover-ashby")
def discover_ashby(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for Ashby board discovery.",
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
            help="Print generated Ashby discovery queries without calling Serper.",
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
            help="Ashby discovery depth: standard, broad, or exhaustive.",
        ),
    ] = AshbyDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per Ashby discovery query.",
        ),
    ] = DEFAULT_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per Ashby discovery query.",
        ),
    ] = DEFAULT_ASHBY_DISCOVERY_PAGES,
) -> None:
    """Discover public Ashby board URLs through search-index queries."""
    country_codes = _parse_country_codes(countries)
    parsed_location_depth = _parse_location_depth(location_depth)
    parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
    discovery_queries = _build_ashby_discovery_queries(
        country_codes=country_codes,
        limit=limit,
        location_depth=parsed_location_depth,
        discovery_depth=parsed_discovery_depth,
        results_per_query=results_per_query,
        pages=pages,
    )

    if dry_run:
        _print_ashby_discovery_queries(discovery_queries)
        return

    try:
        api_key = require_serper_api_key()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    client = SerperGoogleClient(api_key=api_key)
    try:
        result = discover_ashby_boards(discovery_queries, client=client)
    finally:
        client.close()

    console.print(
        "Ashby discovery complete: "
        f"{result.board_count} board(s), "
        f"{result.query_count} querie(s), "
        f"{result.error_count} error(s)."
    )
    console.print(f"Boards: {result.boards_path.as_posix()}")
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("collect-ashby")
def collect_ashby(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for Ashby board discovery.",
        ),
    ] = "nl,uk,dk",
    board_url: Annotated[
        list[str] | None,
        typer.Option(
            "--board-url",
            help="Ashby board URL or slug. Can be repeated to skip discovery.",
        ),
    ] = None,
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
            help="Print discovery queries or board URLs without fetching Ashby.",
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
            help="Ashby discovery depth: standard, broad, or exhaustive.",
        ),
    ] = AshbyDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per Ashby discovery query.",
        ),
    ] = DEFAULT_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per Ashby discovery query.",
        ),
    ] = DEFAULT_ASHBY_DISCOVERY_PAGES,
) -> None:
    """Discover Ashby boards and collect public ATS job data."""
    manual_board_values = board_url or []
    parsed_boards = [normalize_ashby_board(value) for value in manual_board_values]

    if parsed_boards:
        board_values = [board.board_url for board in parsed_boards]
        if dry_run:
            console.print(f"Normalized {len(board_values)} Ashby board URL(s).")
            for value in board_values:
                console.print(value, markup=False)
            return
    else:
        country_codes = _parse_country_codes(countries)
        parsed_location_depth = _parse_location_depth(location_depth)
        parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
        discovery_queries = _build_ashby_discovery_queries(
            country_codes=country_codes,
            limit=limit,
            location_depth=parsed_location_depth,
            discovery_depth=parsed_discovery_depth,
            results_per_query=results_per_query,
            pages=pages,
        )

        if dry_run:
            _print_ashby_discovery_queries(discovery_queries)
            return

        try:
            api_key = require_serper_api_key()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        search_client = SerperGoogleClient(api_key=api_key)
        try:
            discovery_result = discover_ashby_boards(
                discovery_queries,
                client=search_client,
            )
        finally:
            search_client.close()

        board_values = [str(record["board_url"]) for record in discovery_result.boards]
        console.print(
            "Ashby discovery complete: "
            f"{discovery_result.board_count} board(s), "
            f"{discovery_result.error_count} error(s)."
        )
        console.print(f"Boards: {discovery_result.boards_path.as_posix()}")

    if not board_values:
        console.print("No Ashby boards to collect.")
        return

    ashby_client = AshbyClient()
    try:
        result = collect_ashby_boards(board_values, client=ashby_client)
    finally:
        ashby_client.close()

    console.print(
        "Ashby collection complete: "
        f"{result.successful_count}/{result.board_count} raw board file(s) written; "
        f"{result.error_count} error(s)."
    )
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("discover-greenhouse")
def discover_greenhouse(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for Greenhouse board discovery.",
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
            help="Print generated Greenhouse discovery queries without calling Serper.",
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
            help="Greenhouse discovery depth: standard, broad, or exhaustive.",
        ),
    ] = GreenhouseDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per Greenhouse discovery query.",
        ),
    ] = DEFAULT_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per Greenhouse discovery query.",
        ),
    ] = DEFAULT_GREENHOUSE_DISCOVERY_PAGES,
) -> None:
    """Discover public Greenhouse board URLs through search-index queries."""
    country_codes = _parse_country_codes(countries)
    parsed_location_depth = _parse_location_depth(location_depth)
    parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
    discovery_queries = _build_greenhouse_discovery_queries(
        country_codes=country_codes,
        limit=limit,
        location_depth=parsed_location_depth,
        discovery_depth=parsed_discovery_depth,
        results_per_query=results_per_query,
        pages=pages,
    )

    if dry_run:
        _print_greenhouse_discovery_queries(discovery_queries)
        return

    try:
        api_key = require_serper_api_key()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    client = SerperGoogleClient(api_key=api_key)
    try:
        result = discover_greenhouse_boards(discovery_queries, client=client)
    finally:
        client.close()

    console.print(
        "Greenhouse discovery complete: "
        f"{result.board_count} board(s), "
        f"{result.query_count} querie(s), "
        f"{result.error_count} error(s)."
    )
    console.print(f"Boards: {result.boards_path.as_posix()}")
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("collect-greenhouse")
def collect_greenhouse(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for Greenhouse board discovery.",
        ),
    ] = "nl,uk,dk",
    board_url: Annotated[
        list[str] | None,
        typer.Option(
            "--board-url",
            help="Greenhouse board URL or token. Can be repeated to skip discovery.",
        ),
    ] = None,
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
            help="Print discovery queries or board URLs without fetching Greenhouse.",
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
            help="Greenhouse discovery depth: standard, broad, or exhaustive.",
        ),
    ] = GreenhouseDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per Greenhouse discovery query.",
        ),
    ] = DEFAULT_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per Greenhouse discovery query.",
        ),
    ] = DEFAULT_GREENHOUSE_DISCOVERY_PAGES,
) -> None:
    """Discover Greenhouse boards and collect public ATS job data."""
    manual_board_values = board_url or []
    parsed_boards = [normalize_greenhouse_board(value) for value in manual_board_values]

    if parsed_boards:
        board_values = [board.board_url for board in parsed_boards]
        if dry_run:
            console.print(f"Normalized {len(board_values)} Greenhouse board URL(s).")
            for value in board_values:
                console.print(value, markup=False)
            return
    else:
        country_codes = _parse_country_codes(countries)
        parsed_location_depth = _parse_location_depth(location_depth)
        parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
        discovery_queries = _build_greenhouse_discovery_queries(
            country_codes=country_codes,
            limit=limit,
            location_depth=parsed_location_depth,
            discovery_depth=parsed_discovery_depth,
            results_per_query=results_per_query,
            pages=pages,
        )

        if dry_run:
            _print_greenhouse_discovery_queries(discovery_queries)
            return

        try:
            api_key = require_serper_api_key()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        search_client = SerperGoogleClient(api_key=api_key)
        try:
            discovery_result = discover_greenhouse_boards(
                discovery_queries,
                client=search_client,
            )
        finally:
            search_client.close()

        board_values = [str(record["board_url"]) for record in discovery_result.boards]
        console.print(
            "Greenhouse discovery complete: "
            f"{discovery_result.board_count} board(s), "
            f"{discovery_result.error_count} error(s)."
        )
        console.print(f"Boards: {discovery_result.boards_path.as_posix()}")

    if not board_values:
        console.print("No Greenhouse boards to collect.")
        return

    greenhouse_client = GreenhouseClient()
    try:
        result = collect_greenhouse_boards(board_values, client=greenhouse_client)
    finally:
        greenhouse_client.close()

    console.print(
        "Greenhouse collection complete: "
        f"{result.successful_count}/{result.board_count} raw board file(s) written; "
        f"{result.error_count} error(s)."
    )
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("discover-lever")
def discover_lever(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for Lever board discovery.",
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
            help="Print generated Lever discovery queries without calling Serper.",
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
            help="Lever discovery depth: standard, broad, or exhaustive.",
        ),
    ] = LeverDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_LEVER_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per Lever discovery query.",
        ),
    ] = DEFAULT_LEVER_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per Lever discovery query.",
        ),
    ] = DEFAULT_LEVER_DISCOVERY_PAGES,
) -> None:
    """Discover public Lever board URLs through search-index queries."""
    country_codes = _parse_country_codes(countries)
    parsed_location_depth = _parse_location_depth(location_depth)
    parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
    discovery_queries = _build_lever_discovery_queries(
        country_codes=country_codes,
        limit=limit,
        location_depth=parsed_location_depth,
        discovery_depth=parsed_discovery_depth,
        results_per_query=results_per_query,
        pages=pages,
    )

    if dry_run:
        _print_lever_discovery_queries(discovery_queries)
        return

    try:
        api_key = require_serper_api_key()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    client = SerperGoogleClient(api_key=api_key)
    try:
        result = discover_lever_boards(discovery_queries, client=client)
    finally:
        client.close()

    console.print(
        "Lever discovery complete: "
        f"{result.board_count} board(s), "
        f"{result.query_count} querie(s), "
        f"{result.error_count} error(s)."
    )
    console.print(f"Boards: {result.boards_path.as_posix()}")
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("collect-lever")
def collect_lever(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for Lever board discovery.",
        ),
    ] = "nl,uk,dk",
    board_url: Annotated[
        list[str] | None,
        typer.Option(
            "--board-url",
            help="Lever board URL or site slug. Can be repeated to skip discovery.",
        ),
    ] = None,
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
            help="Print discovery queries or board URLs without fetching Lever.",
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
            help="Lever discovery depth: standard, broad, or exhaustive.",
        ),
    ] = LeverDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_LEVER_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per Lever discovery query.",
        ),
    ] = DEFAULT_LEVER_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per Lever discovery query.",
        ),
    ] = DEFAULT_LEVER_DISCOVERY_PAGES,
) -> None:
    """Discover Lever boards and collect public ATS job data."""
    manual_board_values = board_url or []
    parsed_boards = [normalize_lever_board(value) for value in manual_board_values]

    if parsed_boards:
        board_values = [board.board_url for board in parsed_boards]
        if dry_run:
            console.print(f"Normalized {len(board_values)} Lever board URL(s).")
            for value in board_values:
                console.print(value, markup=False)
            return
    else:
        country_codes = _parse_country_codes(countries)
        parsed_location_depth = _parse_location_depth(location_depth)
        parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
        discovery_queries = _build_lever_discovery_queries(
            country_codes=country_codes,
            limit=limit,
            location_depth=parsed_location_depth,
            discovery_depth=parsed_discovery_depth,
            results_per_query=results_per_query,
            pages=pages,
        )

        if dry_run:
            _print_lever_discovery_queries(discovery_queries)
            return

        try:
            api_key = require_serper_api_key()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        search_client = SerperGoogleClient(api_key=api_key)
        try:
            discovery_result = discover_lever_boards(
                discovery_queries,
                client=search_client,
            )
        finally:
            search_client.close()

        board_values = [str(record["board_url"]) for record in discovery_result.boards]
        console.print(
            "Lever discovery complete: "
            f"{discovery_result.board_count} board(s), "
            f"{discovery_result.error_count} error(s)."
        )
        console.print(f"Boards: {discovery_result.boards_path.as_posix()}")

    if not board_values:
        console.print("No Lever boards to collect.")
        return

    lever_client = LeverClient()
    try:
        result = collect_lever_boards(board_values, client=lever_client)
    finally:
        lever_client.close()

    console.print(
        "Lever collection complete: "
        f"{result.successful_count}/{result.board_count} raw board file(s) written; "
        f"{result.error_count} error(s)."
    )
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("discover-personio")
def discover_personio(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for Personio board discovery.",
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
            help="Print generated Personio discovery queries without calling Serper.",
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
            help="Personio discovery depth: standard, broad, or exhaustive.",
        ),
    ] = PersonioDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per Personio discovery query.",
        ),
    ] = DEFAULT_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per Personio discovery query.",
        ),
    ] = DEFAULT_PERSONIO_DISCOVERY_PAGES,
) -> None:
    """Discover public Personio board URLs through search-index queries."""
    country_codes = _parse_country_codes(countries)
    parsed_location_depth = _parse_location_depth(location_depth)
    parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
    discovery_queries = _build_personio_discovery_queries(
        country_codes=country_codes,
        limit=limit,
        location_depth=parsed_location_depth,
        discovery_depth=parsed_discovery_depth,
        results_per_query=results_per_query,
        pages=pages,
    )

    if dry_run:
        _print_personio_discovery_queries(discovery_queries)
        return

    try:
        api_key = require_serper_api_key()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    client = SerperGoogleClient(api_key=api_key)
    try:
        result = discover_personio_boards(discovery_queries, client=client)
    finally:
        client.close()

    console.print(
        "Personio discovery complete: "
        f"{result.board_count} board(s), "
        f"{result.query_count} querie(s), "
        f"{result.error_count} error(s)."
    )
    console.print(f"Boards: {result.boards_path.as_posix()}")
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("collect-personio")
def collect_personio(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for Personio board discovery.",
        ),
    ] = "nl,uk,dk",
    board_url: Annotated[
        list[str] | None,
        typer.Option(
            "--board-url",
            help="Personio board URL or company slug. Can be repeated to skip discovery.",
        ),
    ] = None,
    language: Annotated[
        str,
        typer.Option(
            "--language",
            help="Personio XML feed language, for example: en, de, nl.",
        ),
    ] = DEFAULT_PERSONIO_LANGUAGE,
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
            help="Print discovery queries or board URLs without fetching Personio.",
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
            help="Personio discovery depth: standard, broad, or exhaustive.",
        ),
    ] = PersonioDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per Personio discovery query.",
        ),
    ] = DEFAULT_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per Personio discovery query.",
        ),
    ] = DEFAULT_PERSONIO_DISCOVERY_PAGES,
) -> None:
    """Discover Personio boards and collect public ATS job data."""
    manual_board_values = board_url or []
    parsed_boards = [normalize_personio_board(value) for value in manual_board_values]

    if parsed_boards:
        board_values = [board.board_url for board in parsed_boards]
        if dry_run:
            console.print(f"Normalized {len(board_values)} Personio board URL(s).")
            for value in board_values:
                console.print(value, markup=False)
            return
    else:
        country_codes = _parse_country_codes(countries)
        parsed_location_depth = _parse_location_depth(location_depth)
        parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
        discovery_queries = _build_personio_discovery_queries(
            country_codes=country_codes,
            limit=limit,
            location_depth=parsed_location_depth,
            discovery_depth=parsed_discovery_depth,
            results_per_query=results_per_query,
            pages=pages,
        )

        if dry_run:
            _print_personio_discovery_queries(discovery_queries)
            return

        try:
            api_key = require_serper_api_key()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        search_client = SerperGoogleClient(api_key=api_key)
        try:
            discovery_result = discover_personio_boards(
                discovery_queries,
                client=search_client,
            )
        finally:
            search_client.close()

        board_values = [str(record["board_url"]) for record in discovery_result.boards]
        console.print(
            "Personio discovery complete: "
            f"{discovery_result.board_count} board(s), "
            f"{discovery_result.error_count} error(s)."
        )
        console.print(f"Boards: {discovery_result.boards_path.as_posix()}")

    if not board_values:
        console.print("No Personio boards to collect.")
        return

    personio_client = PersonioClient(language=language)
    try:
        result = collect_personio_boards(board_values, client=personio_client)
    finally:
        personio_client.close()

    console.print(
        "Personio collection complete: "
        f"{result.successful_count}/{result.board_count} raw board file(s) written; "
        f"{result.error_count} error(s)."
    )
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("discover-teamtailor")
def discover_teamtailor(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for Teamtailor board discovery.",
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
            help="Print generated Teamtailor discovery queries without calling Serper.",
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
            help="Teamtailor discovery depth: standard, broad, or exhaustive.",
        ),
    ] = TeamtailorDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per Teamtailor discovery query.",
        ),
    ] = DEFAULT_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per Teamtailor discovery query.",
        ),
    ] = DEFAULT_TEAMTAILOR_DISCOVERY_PAGES,
) -> None:
    """Discover public Teamtailor board URLs through search-index queries."""
    country_codes = _parse_country_codes(countries)
    parsed_location_depth = _parse_location_depth(location_depth)
    parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
    discovery_queries = _build_teamtailor_discovery_queries(
        country_codes=country_codes,
        limit=limit,
        location_depth=parsed_location_depth,
        discovery_depth=parsed_discovery_depth,
        results_per_query=results_per_query,
        pages=pages,
    )

    if dry_run:
        _print_teamtailor_discovery_queries(discovery_queries)
        return

    try:
        api_key = require_serper_api_key()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    client = SerperGoogleClient(api_key=api_key)
    try:
        result = discover_teamtailor_boards(discovery_queries, client=client)
    finally:
        client.close()

    console.print(
        "Teamtailor discovery complete: "
        f"{result.board_count} board(s), "
        f"{result.query_count} querie(s), "
        f"{result.error_count} error(s)."
    )
    console.print(f"Boards: {result.boards_path.as_posix()}")
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("collect-teamtailor")
def collect_teamtailor(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for Teamtailor board discovery.",
        ),
    ] = "nl,uk,dk",
    board_url: Annotated[
        list[str] | None,
        typer.Option(
            "--board-url",
            help=(
                "Teamtailor board URL or company slug. "
                "Can be repeated to skip discovery."
            ),
        ),
    ] = None,
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
            help="Print discovery queries or board URLs without fetching Teamtailor.",
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
            help="Teamtailor discovery depth: standard, broad, or exhaustive.",
        ),
    ] = TeamtailorDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per Teamtailor discovery query.",
        ),
    ] = DEFAULT_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per Teamtailor discovery query.",
        ),
    ] = DEFAULT_TEAMTAILOR_DISCOVERY_PAGES,
) -> None:
    """Discover Teamtailor boards and collect public RSS job data."""
    manual_board_values = board_url or []
    parsed_boards = [normalize_teamtailor_board(value) for value in manual_board_values]

    if parsed_boards:
        board_values = [board.board_url for board in parsed_boards]
        if dry_run:
            console.print(f"Normalized {len(board_values)} Teamtailor board URL(s).")
            for value in board_values:
                console.print(value, markup=False)
            return
    else:
        country_codes = _parse_country_codes(countries)
        parsed_location_depth = _parse_location_depth(location_depth)
        parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
        discovery_queries = _build_teamtailor_discovery_queries(
            country_codes=country_codes,
            limit=limit,
            location_depth=parsed_location_depth,
            discovery_depth=parsed_discovery_depth,
            results_per_query=results_per_query,
            pages=pages,
        )

        if dry_run:
            _print_teamtailor_discovery_queries(discovery_queries)
            return

        try:
            api_key = require_serper_api_key()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        search_client = SerperGoogleClient(api_key=api_key)
        try:
            discovery_result = discover_teamtailor_boards(
                discovery_queries,
                client=search_client,
            )
        finally:
            search_client.close()

        board_values = [str(record["board_url"]) for record in discovery_result.boards]
        console.print(
            "Teamtailor discovery complete: "
            f"{discovery_result.board_count} board(s), "
            f"{discovery_result.error_count} error(s)."
        )
        console.print(f"Boards: {discovery_result.boards_path.as_posix()}")

    if not board_values:
        console.print("No Teamtailor boards to collect.")
        return

    teamtailor_client = TeamtailorClient()
    try:
        result = collect_teamtailor_boards(board_values, client=teamtailor_client)
    finally:
        teamtailor_client.close()

    console.print(
        "Teamtailor collection complete: "
        f"{result.successful_count}/{result.board_count} raw board file(s) written; "
        f"{result.error_count} error(s)."
    )
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("discover-smartrecruiters")
def discover_smartrecruiters(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for SmartRecruiters board discovery.",
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
            help="Print generated SmartRecruiters discovery queries without calling Serper.",
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
            help="SmartRecruiters discovery depth: standard, broad, or exhaustive.",
        ),
    ] = SmartRecruitersDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per SmartRecruiters discovery query.",
        ),
    ] = DEFAULT_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per SmartRecruiters discovery query.",
        ),
    ] = DEFAULT_SMARTRECRUITERS_DISCOVERY_PAGES,
) -> None:
    """Discover public SmartRecruiters board URLs through search-index queries."""
    country_codes = _parse_country_codes(countries)
    parsed_location_depth = _parse_location_depth(location_depth)
    parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
    discovery_queries = _build_smartrecruiters_discovery_queries(
        country_codes=country_codes,
        limit=limit,
        location_depth=parsed_location_depth,
        discovery_depth=parsed_discovery_depth,
        results_per_query=results_per_query,
        pages=pages,
    )

    if dry_run:
        _print_smartrecruiters_discovery_queries(discovery_queries)
        return

    try:
        api_key = require_serper_api_key()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    client = SerperGoogleClient(api_key=api_key)
    try:
        result = discover_smartrecruiters_boards(discovery_queries, client=client)
    finally:
        client.close()

    console.print(
        "SmartRecruiters discovery complete: "
        f"{result.board_count} board(s), "
        f"{result.query_count} querie(s), "
        f"{result.error_count} error(s)."
    )
    console.print(f"Boards: {result.boards_path.as_posix()}")
    console.print(f"Manifest: {result.manifest_path.as_posix()}")


@app.command("collect-smartrecruiters")
def collect_smartrecruiters(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes for SmartRecruiters board discovery.",
        ),
    ] = "nl,uk,dk",
    board_url: Annotated[
        list[str] | None,
        typer.Option(
            "--board-url",
            help=(
                "SmartRecruiters board URL or company identifier. "
                "Can be repeated to skip discovery."
            ),
        ),
    ] = None,
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
            help="Print discovery queries or board URLs without fetching SmartRecruiters.",
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
            help="SmartRecruiters discovery depth: standard, broad, or exhaustive.",
        ),
    ] = SmartRecruitersDiscoveryDepth.EXHAUSTIVE.value,
    results_per_query: Annotated[
        int,
        typer.Option(
            "--results-per-query",
            min=1,
            max=MAX_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY,
            help="Serper results requested per SmartRecruiters discovery query.",
        ),
    ] = DEFAULT_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY,
    pages: Annotated[
        int,
        typer.Option(
            "--pages",
            min=1,
            help="Serper result pages requested per SmartRecruiters discovery query.",
        ),
    ] = DEFAULT_SMARTRECRUITERS_DISCOVERY_PAGES,
) -> None:
    """Discover SmartRecruiters boards and collect public ATS job data."""
    manual_board_values = board_url or []
    parsed_boards = [
        normalize_smartrecruiters_board(value) for value in manual_board_values
    ]

    if parsed_boards:
        board_values = [board.board_url for board in parsed_boards]
        if dry_run:
            console.print(
                f"Normalized {len(board_values)} SmartRecruiters board URL(s)."
            )
            for value in board_values:
                console.print(value, markup=False)
            return
    else:
        country_codes = _parse_country_codes(countries)
        parsed_location_depth = _parse_location_depth(location_depth)
        parsed_discovery_depth = _parse_ats_discovery_depth(discovery_depth)
        discovery_queries = _build_smartrecruiters_discovery_queries(
            country_codes=country_codes,
            limit=limit,
            location_depth=parsed_location_depth,
            discovery_depth=parsed_discovery_depth,
            results_per_query=results_per_query,
            pages=pages,
        )

        if dry_run:
            _print_smartrecruiters_discovery_queries(discovery_queries)
            return

        try:
            api_key = require_serper_api_key()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        search_client = SerperGoogleClient(api_key=api_key)
        try:
            discovery_result = discover_smartrecruiters_boards(
                discovery_queries,
                client=search_client,
            )
        finally:
            search_client.close()

        board_values = [str(record["board_url"]) for record in discovery_result.boards]
        console.print(
            "SmartRecruiters discovery complete: "
            f"{discovery_result.board_count} board(s), "
            f"{discovery_result.error_count} error(s)."
        )
        console.print(f"Boards: {discovery_result.boards_path.as_posix()}")

    if not board_values:
        console.print("No SmartRecruiters boards to collect.")
        return

    smartrecruiters_client = SmartRecruitersClient()
    try:
        result = collect_smartrecruiters_boards(
            board_values,
            client=smartrecruiters_client,
        )
    finally:
        smartrecruiters_client.close()

    console.print(
        "SmartRecruiters collection complete: "
        f"{result.successful_count}/{result.board_count} raw board file(s) written; "
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


@app.command()
def run(
    countries: Annotated[
        str,
        typer.Option(
            "--countries",
            help="Comma-separated country codes, for example: nl,uk,dk.",
        ),
    ] = "nl,uk,dk",
    location_depth: Annotated[
        str,
        typer.Option(
            "--location-depth",
            help="Search location depth: country or cities.",
        ),
    ] = LocationDepth.COUNTRY.value,
) -> None:
    """Run collection, processing, and export for the selected countries."""
    country_codes = _parse_country_codes(countries)
    parsed_location_depth = _parse_location_depth(location_depth)
    _print_collection_plan(country_codes, location_depth=parsed_location_depth)
    try:
        api_key = require_serper_api_key()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    search_queries = _build_search_queries(
        country_codes=country_codes,
        location_depth=parsed_location_depth,
    )
    client = SerperGoogleClient(api_key=api_key)
    try:
        collection_result = collect_searches(search_queries, client=client)
    finally:
        client.close()

    collection_date = collection_result.manifest_path.parent.parent.name
    processing_result = process_collection(collection_date)
    export_result = export_company_review_files(collection_date)

    console.print(
        "Run complete: "
        f"{collection_result.successful_count}/{collection_result.query_count} "
        "raw file(s), "
        f"{processing_result.company_count} company record(s), "
        f"{export_result.company_count} exported company record(s)."
    )
    console.print(f"Manifest: {collection_result.manifest_path.as_posix()}")
    console.print(f"Candidates: {processing_result.job_candidates_path.as_posix()}")
    console.print(f"Companies: {processing_result.companies_path.as_posix()}")
    console.print(f"CSV: {export_result.csv_path.as_posix()}")
    console.print(f"Markdown: {export_result.markdown_path.as_posix()}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
