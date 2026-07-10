from __future__ import annotations

from ai_hiring_radar.classify import match_known_role


def ats_role_search_term(job_title_raw: str) -> str:
    known_role = match_known_role(job_title_raw)
    if known_role is not None:
        return known_role.role
    return "title contains AI"
