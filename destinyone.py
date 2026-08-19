import os
from typing import Any, Dict, List, Optional
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


class DestinyOneCourseSectionLookupError(DestinyOneError):
    """Raised when a course section lookup returns an unexpected result."""


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


def _as_list(value: Any) -> List[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    return [value]


def _course_section_profiles(response: Dict[str, Any]) -> List[Any]:
    result = response.get("SearchCourseSectionProfileResult", {})
    profiles = result.get("courseSectionProfiles", {})
    return _as_list(profiles.get("courseSectionProfile"))


def _pagination(response: Dict[str, Any]) -> Dict[str, Any]:
    result = response.get("SearchCourseSectionProfileResult", {})
    pagination = result.get("paginationResponse", {})
    return pagination if isinstance(pagination, dict) else {}


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _search_course_sections_page(
    session_id: str,
    brightspace_template_code: str,
    page_number: int,
    page_size: int,
) -> Dict[str, Any]:
    payload = {
        "searchCourseSectionProfileRequestDetail": {
            "paginationConstruct": {
                "pageNumber": page_number,
                "pageSize": page_size,
            },
            "courseSectionSearchCriteria": {
                "courseCode": brightspace_template_code,
            },
        }
    }
    url = _service_url(INTERNAL_REST_PATH, "searchCourseSection")
    params = {
        "informationLevel": "full",
        "_type": "json",
    }
    return _request("POST", url, session_id=session_id, params=params, json=payload)


def get_course_section_profile_object_id(
    session_id: str,
    brightspace_template_code: str,
    brightspace_section_code: str,
    page_size: int = 25,
) -> int:
    """Return the Destiny One section profile objectId matching a Brightspace section."""
    matches = []
    page_number = 1
    total_count = None

    while True:
        response = _search_course_sections_page(
            session_id,
            brightspace_template_code,
            page_number,
            page_size,
        )

        for profile in _course_section_profiles(response):
            if not isinstance(profile, dict):
                continue

            lms_info = profile.get("sectionLMSInfo")
            if not isinstance(lms_info, dict):
                continue

            if lms_info.get("lmsSectionId") == brightspace_section_code:
                matches.append(profile)

        pagination = _pagination(response)
        if total_count is None:
            total_count = _to_int(pagination.get("totalCount"), len(matches))

        response_page_size = _to_int(pagination.get("pageSize"), page_size)
        if page_number * response_page_size >= total_count:
            break

        page_number += 1

    if len(matches) != 1:
        raise DestinyOneCourseSectionLookupError(
            "Expected exactly one Destiny One course section for courseCode "
            "{course_code} and lmsSectionId {section_code}; received {count}.".format(
                course_code=brightspace_template_code,
                section_code=brightspace_section_code,
                count=len(matches),
            )
        )

    object_id = matches[0].get("objectId")
    if object_id is None:
        raise DestinyOneCourseSectionLookupError(
            "Matched Destiny One course section did not include objectId."
        )

    return int(object_id)


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
                "isInstructorApproved": "true",
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
