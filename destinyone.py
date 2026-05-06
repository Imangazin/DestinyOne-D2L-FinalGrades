import os
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

load_dotenv()

DESTINYONE_BASE_URL = os.getenv("DESTINYONE_BASE_URL")
DESTINYONE_USERNAME = os.getenv("DESTINYONE_USERNAME")
DESTINYONE_PASSWORD = os.getenv("DESTINYONE_PASSWORD")

INTERNAL_REST_PATH = os.getenv("DESTINYONE_INTERNAL_REST_PATH", "InternalViewREST/")
INTERNAL_REST_V2_PATH = os.getenv(
    "DESTINYONE_INTERNAL_REST_V2_PATH",
    "InternalViewRESTV2/",
)
REQUEST_TIMEOUT = int(os.getenv("DESTINYONE_REQUEST_TIMEOUT", "30"))


class DestinyOneError(Exception):
    """Raised when Destiny One returns an unsuccessful response."""


class DestinyOneAuthError(DestinyOneError):
    """Raised when Destiny One login fails or no sessionId is returned."""


def _base_url() -> str:
    if not DESTINYONE_BASE_URL:
        raise ValueError("DESTINYONE_BASE_URL is not configured.")
    return DESTINYONE_BASE_URL.rstrip("/") + "/"


def _service_url(service_path: str, endpoint_path: str) -> str:
    service_base = urljoin(_base_url(), service_path.lstrip("/"))
    return urljoin(service_base, endpoint_path.lstrip("/"))


def _headers(session_id: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    if session_id:
        headers["sessionId"] = session_id

    return headers


def _request(
    method: str,
    url: str,
    *,
    session_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    response = requests.request(
        method,
        url,
        headers=_headers(session_id),
        timeout=REQUEST_TIMEOUT,
        **kwargs,
    )

    try:
        body = response.json() if response.content else {}
    except ValueError:
        body = {"raw": response.text}

    if not response.ok:
        raise DestinyOneError(
            "Destiny One API returned {status}: {body}".format(
                status=response.status_code,
                body=body,
            )
        )

    return body


def _extract_session_id(login_response: Dict[str, Any]) -> str:
    session_id = login_response.get("sessionId")
    if session_id:
        return str(session_id)

    login_result = login_response.get("loginResult")
    if isinstance(login_result, dict) and login_result.get("sessionId"):
        return str(login_result["sessionId"])

    response_detail = login_response.get("loginResponse")
    if isinstance(response_detail, dict) and response_detail.get("sessionId"):
        return str(response_detail["sessionId"])

    raw_response = login_response.get("raw")
    if raw_response:
        return str(raw_response)

    raise DestinyOneAuthError(
        "Destiny One login succeeded but no sessionId was found in the response: "
        "{response}".format(response=login_response)
    )


def login(
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """Authenticate with InternalViewREST/login and return the Destiny One sessionId."""
    username = username or DESTINYONE_USERNAME
    password = password or DESTINYONE_PASSWORD

    if not username or not password:
        raise DestinyOneAuthError(
            "DESTINYONE_USERNAME and DESTINYONE_PASSWORD must be configured."
        )

    params = {
        "username": username,
        "password": password,
        "_type": "json",
    }
    url = _service_url(INTERNAL_REST_PATH, "login")
    return _extract_session_id(_request("GET", url, params=params))


def create_or_update_student_final_grade(
    session_id: str,
    course_section_profile_object_id: str,
    student_login_id: str,
    grade: str,
) -> Dict[str, Any]:
    """Create or update one student final grade in Destiny One."""
    payload = {
        "createOrUpdateStudentFinalGradeRequestDetail": {
            "studentGrade": {
                "gradingSheet": {
                    "courseSectionProfile": {
                        "objectId": str(course_section_profile_object_id),
                    }
                },
                "student": {
                    "loginId": student_login_id,
                },
                "studentGradeItems": {
                    "studentGradeItem": {
                        "grade": grade,
                    }
                },
            }
        }
    }
    url = _service_url(
        INTERNAL_REST_V2_PATH,
        "createOrUpdateStudentFinalGrade?_type=json",
    )
    return _request("POST", url, session_id=session_id, json=payload)
