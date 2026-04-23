import os
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

load_dotenv()

BRIGHTSPACE_BASE_URL = os.getenv("BRIGHTSPACE_BASE_URL")
BRIGHTSPACE_API_VERSION = os.getenv("BRIGHTSPACE_API_VERSION", "1.82")
DEFAULT_PAGE_SIZE = 200


class BrightspaceApiError(Exception):
    """Raised when Brightspace returns an unsuccessful API response."""


def base_url() -> str:
    if not BRIGHTSPACE_BASE_URL:
        raise ValueError("BRIGHTSPACE_BASE_URL is not configured.")
    return BRIGHTSPACE_BASE_URL.rstrip("/") + "/"


def api_url(path: str) -> str:
    return urljoin(base_url(), path.lstrip("/"))


def api_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def request(method: str, path_or_url: str, access_token: str, **kwargs) -> dict:
    url = path_or_url if path_or_url.startswith("http") else api_url(path_or_url)

    response = requests.request(
        method,
        url,
        headers=api_headers(access_token),
        timeout=30,
        **kwargs,
    )

    if not response.ok:
        raise BrightspaceApiError(
            f"Brightspace API returned {response.status_code}: {response.text}"
        )

    if not response.content:
        return {}

    return response.json()


def get_all_object_pages(
    path: str,
    access_token: str,
    params: dict | None = None,
) -> list:
    objects = []
    next_url = path
    next_params = params

    while next_url:
        page = request("GET", next_url, access_token, params=next_params)
        objects.extend(page.get("Objects", []))
        next_url = page.get("Next")
        next_params = None

    return objects
