from typing import Union

from brightspace_api import (
    BRIGHTSPACE_API_VERSION,
    BRIGHTSPACE_LP_API_VERSION,
    DEFAULT_PAGE_SIZE,
    get_all_object_pages,
    request,
)


class BrightspaceParentLookupError(Exception):
    """Raised when a course parent template lookup returns an unexpected result."""


class BrightspaceSectionLookupError(Exception):
    """Raised when a course section lookup returns an unexpected result."""


def get_final_grade_values(
    org_unit_id: Union[int, str],
    access_token: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list:
    """Retrieve final grade values for all users in a Brightspace course."""
    params = {
        "pageSize": page_size,
    }

    path = (
        f"/d2l/api/le/{BRIGHTSPACE_API_VERSION}/"
        f"{org_unit_id}/grades/final/values/"
    )
    return get_all_object_pages(path, access_token, params=params)


def get_course_template_code(
    org_unit_id: Union[int, str],
    access_token: str,
    *,
    ou_type_id: int = 2,
) -> str:
    """Return the single parent course template code for a Brightspace org unit."""
    params = {
        "ouTypeId": ou_type_id,
    }
    path = (
        f"/d2l/api/lp/{BRIGHTSPACE_LP_API_VERSION}/"
        f"orgstructure/{org_unit_id}/parents/"
    )
    parents = request("GET", path, access_token, params=params)

    if not isinstance(parents, list) or len(parents) != 1:
        raise BrightspaceParentLookupError(
            "Expected exactly one course template parent for org unit {org_unit_id}; "
            "received {count}.".format(
                org_unit_id=org_unit_id,
                count=len(parents) if isinstance(parents, list) else "non-list response",
            )
        )

    code = parents[0].get("Code")
    if not code:
        raise BrightspaceParentLookupError(
            "Course template parent for org unit {org_unit_id} did not include Code.".format(
                org_unit_id=org_unit_id,
            )
        )

    return code


def get_section_name_code_pairs(
    org_unit_id: Union[int, str],
    access_token: str,
) -> list:
    """Return Brightspace course section Name/Code pairs for an org unit."""
    path = f"/d2l/api/lp/{BRIGHTSPACE_LP_API_VERSION}/{org_unit_id}/sections/"
    sections = request("GET", path, access_token)

    if not isinstance(sections, list):
        raise BrightspaceSectionLookupError(
            "Expected section list for org unit {org_unit_id}; received non-list response.".format(
                org_unit_id=org_unit_id,
            )
        )

    pairs = []
    for section in sections:
        if not isinstance(section, dict):
            raise BrightspaceSectionLookupError(
                "Expected section object for org unit {org_unit_id}; received {section}.".format(
                    org_unit_id=org_unit_id,
                    section=section,
                )
            )

        name = section.get("Name")
        code = section.get("Code")
        section_id = section.get("SectionId")
        if not name or not code or section_id is None:
            raise BrightspaceSectionLookupError(
                "Section for org unit {org_unit_id} did not include SectionId, Name, and Code.".format(
                    org_unit_id=org_unit_id,
                )
            )

        pairs.append({
            "SectionId": section_id,
            "Name": name,
            "Code": code,
        })

    return pairs
