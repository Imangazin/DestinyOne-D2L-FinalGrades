from typing import Union

from brightspace_api import (
    BRIGHTSPACE_API_VERSION,
    DEFAULT_PAGE_SIZE,
    get_all_object_pages,
)


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
