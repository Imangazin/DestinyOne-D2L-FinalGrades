import os
import uuid
from dotenv import load_dotenv
from tempfile import mkdtemp

from flask import Flask, render_template, request, session
from flask_caching import Cache
from pylti1p3.contrib.flask import FlaskOIDCLogin, FlaskMessageLaunch
from pylti1p3.contrib.flask.request import FlaskRequest
from pylti1p3.contrib.flask import FlaskCacheDataStorage
from pylti1p3.tool_config import ToolConfJsonFile

from werkzeug.middleware.proxy_fix import ProxyFix
from auth2 import get_access_token
from brightspace_grades import (
    BrightspaceParentLookupError,
    get_course_template_code,
    get_final_grade_values,
    get_section_name_code_pairs,
)
from destinyone import (
    create_or_update_student_final_grade,
    get_course_section_profile_object_id,
    login as destinyone_login,
)

load_dotenv()

SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
APP_FOLDER = os.getenv("APP_FOLDER")
APP_URL_PREFIX = os.getenv("APP_URL_PREFIX") or (f"/{APP_FOLDER}" if APP_FOLDER else "")
CACHE_DIR = os.getenv("FLASK_CACHE_DIR") or f"/tmp/{APP_FOLDER}-flask-cache"
os.makedirs(CACHE_DIR, exist_ok=True)


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = SECRET_KEY

app.config.from_mapping(
    DEBUG=True,
    CACHE_TYPE="FileSystemCache",
    CACHE_DEFAULT_TIMEOUT=600,
    CACHE_DIR=CACHE_DIR,
    SECRET_KEY=SECRET_KEY,
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=mkdtemp(),
    SESSION_COOKIE_NAME=f"{APP_FOLDER}-lti13-sessionid",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="None",
)

cache = Cache(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
tool_conf = ToolConfJsonFile(os.path.join(BASE_DIR, "tool_config.json"))
WORKFLOW_CACHE_PREFIX = "final-grades-workflow:"


def get_launch_data_storage():
    return FlaskCacheDataStorage(cache)


def workflow_cache_key(workflow_id):
    return WORKFLOW_CACHE_PREFIX + workflow_id


def save_workflow(workflow_id, workflow):
    cache.set(workflow_cache_key(workflow_id), workflow, timeout=3600)


def get_workflow(workflow_id):
    if not workflow_id:
        return None
    if workflow_id not in session.get("workflow_ids", []):
        return None
    return cache.get(workflow_cache_key(workflow_id))


def allow_workflow_for_session(workflow_id):
    workflow_ids = session.get("workflow_ids", [])
    if workflow_id not in workflow_ids:
        workflow_ids.append(workflow_id)
    session["workflow_ids"] = workflow_ids


def render_workflow_template(workflow, **kwargs):
    app_url_prefix = APP_URL_PREFIX.rstrip("/")
    context = {
        "workflow_id": workflow.get("workflow_id"),
        "org_unit_id": workflow.get("org_unit_id"),
        "course_template_code": workflow.get("course_template_code"),
        "sections": workflow.get("sections", []),
        "selected_section_code": workflow.get("selected_section_code", ""),
        "mode": "validate",
        "message": None,
        "warning": None,
        "error_message": None,
        "transfer_result": None,
        "validate_url": app_url_prefix + "/validate/",
        "transfer_url": app_url_prefix + "/transfer/",
    }
    context.update(kwargs)
    return render_template("launch.html", **context)


def grade_has_displayed_grade(grade):
    if not isinstance(grade, dict):
        return False

    grade_value = grade.get("GradeValue")
    if not isinstance(grade_value, dict):
        return False

    displayed_grade = grade_value.get("DisplayedGrade")
    return displayed_grade not in (None, "")


def get_student_login_id(grade):
    user = grade.get("User") if isinstance(grade, dict) else None
    if not isinstance(user, dict):
        return None
    return user.get("UserName")


def get_displayed_grade(grade):
    grade_value = grade.get("GradeValue") if isinstance(grade, dict) else None
    if not isinstance(grade_value, dict):
        return None
    return grade_value.get("DisplayedGrade")


@app.route("/")
def index():
    return "Flask app is running."


@app.route("/login/", methods=["GET", "POST"])
def login():
    flask_request = FlaskRequest()

    target_link_uri = flask_request.get_param("target_link_uri")
    if not target_link_uri:
        return {
            "error": 'Missing "target_link_uri" param',
            "args": dict(request.args),
            "form": dict(request.form),
        }, 400

    oidc_login = FlaskOIDCLogin(
        flask_request,
        tool_conf,
        launch_data_storage=get_launch_data_storage(),
    )
    return oidc_login.enable_check_cookies().redirect(target_link_uri)


@app.route("/launch/", methods=["POST"])
def launch():

    flask_request = FlaskRequest()

    try:
        message_launch = FlaskMessageLaunch(
            flask_request,
            tool_conf,
            launch_data_storage=get_launch_data_storage(),
        )
        launch_data = message_launch.get_launch_data()


        context_data = launch_data.get(
            "https://purl.imsglobal.org/spec/lti/claim/context", {}
        )
        org_unit_id = context_data.get("id")

        if not org_unit_id:
            return render_template(
                "launch.html",
                workflow_id=None,
                org_unit_id=None,
                course_template_code=None,
                sections=[],
                selected_section_code="",
                mode="validate",
                message=None,
                warning=None,
                error_message="Error occured. Contact CPI for assistance.",
                transfer_result=None,
            ), 400

        token_response = get_access_token()
        access_token = token_response["access_token"]

        try:
            course_template_code = get_course_template_code(org_unit_id, access_token)
        except BrightspaceParentLookupError:
            return render_template(
                "launch.html",
                workflow_id=None,
                org_unit_id=org_unit_id,
                course_template_code=None,
                sections=[],
                selected_section_code="",
                mode="validate",
                message=None,
                warning=None,
                error_message=(
                    "Current course has multiple parent templates. "
                    "Please contact CPI for assisstance."
                ),
                transfer_result=None,
            )

        sections = get_section_name_code_pairs(org_unit_id, access_token)
        workflow_id = uuid.uuid4().hex
        workflow = {
            "workflow_id": workflow_id,
            "org_unit_id": org_unit_id,
            "access_token": access_token,
            "course_template_code": course_template_code,
            "sections": sections,
            "selected_section_code": "",
            "grade_values": [],
        }
        save_workflow(workflow_id, workflow)
        allow_workflow_for_session(workflow_id)

        return render_workflow_template(workflow)

    except Exception:
        app.logger.exception("Launch workflow failed.")
        return render_template(
            "launch.html",
            workflow_id=None,
            org_unit_id=None,
            course_template_code=None,
            sections=[],
            selected_section_code="",
            mode="validate",
            message=None,
            warning=None,
            error_message="Error occured. Contact CPI for assistance.",
            transfer_result=None,
        ), 400


@app.route("/validate/", methods=["POST"])
def validate_grades():
    workflow = get_workflow(request.form.get("workflow_id"))
    if not workflow:
        return render_template(
            "launch.html",
            workflow_id=None,
            org_unit_id=None,
            course_template_code=None,
            sections=[],
            selected_section_code="",
            mode="validate",
            message=None,
            warning=None,
            error_message="Error occured. Contact CPI for assistance.",
            transfer_result=None,
        ), 400

    selected_section_code = request.form.get("section_code", "")
    workflow["selected_section_code"] = selected_section_code

    if not selected_section_code:
        save_workflow(workflow["workflow_id"], workflow)
        return render_workflow_template(
            workflow,
            error_message="Please select a section.",
        )

    try:
        grade_values = get_final_grade_values(
            workflow["org_unit_id"],
            workflow["access_token"],
        )
    except Exception:
        app.logger.exception("Final grade validation failed.")
        save_workflow(workflow["workflow_id"], workflow)
        return render_workflow_template(
            workflow,
            error_message="Error occured. Contact CPI for assistance.",
        )

    workflow["grade_values"] = grade_values
    save_workflow(workflow["workflow_id"], workflow)

    warning = None
    if any(not grade_has_displayed_grade(grade) for grade in grade_values):
        warning = (
            "There is at least one student has no grade. "
            "Would you like to continue?"
        )

    return render_workflow_template(
        workflow,
        mode="transfer",
        warning=warning,
        message="Grades validated.",
    )


@app.route("/transfer/", methods=["POST"])
def transfer_grades():
    workflow = get_workflow(request.form.get("workflow_id"))
    if not workflow:
        return render_template(
            "launch.html",
            workflow_id=None,
            org_unit_id=None,
            course_template_code=None,
            sections=[],
            selected_section_code="",
            mode="validate",
            message=None,
            warning=None,
            error_message="Error occured. Contact CPI for assistance.",
            transfer_result=None,
        ), 400

    selected_section_code = request.form.get("section_code") or workflow.get(
        "selected_section_code",
        "",
    )
    workflow["selected_section_code"] = selected_section_code

    if not selected_section_code:
        save_workflow(workflow["workflow_id"], workflow)
        return render_workflow_template(
            workflow,
            error_message="Please select a section.",
        )

    try:
        grade_values = workflow.get("grade_values") or get_final_grade_values(
            workflow["org_unit_id"],
            workflow["access_token"],
        )
        workflow["grade_values"] = grade_values

        destinyone_session_id = destinyone_login()
        app.logger.info(
            "Looking up Destiny One course section objectId for courseCode=%s, lmsSectionId=%s.",
            workflow["course_template_code"],
            selected_section_code,
        )
        course_section_profile_object_id = get_course_section_profile_object_id(
            destinyone_session_id,
            workflow["course_template_code"],
            selected_section_code,
        )
        app.logger.info(
            "Resolved Destiny One course section objectId=%s.",
            course_section_profile_object_id,
        )

        transferred_count = 0
        skipped_count = 0
        for grade in grade_values:
            student_login_id = get_student_login_id(grade)
            final_grade = get_displayed_grade(grade)

            if not student_login_id or final_grade in (None, ""):
                skipped_count += 1
                continue

            create_or_update_student_final_grade(
                destinyone_session_id,
                course_section_profile_object_id,
                student_login_id,
                final_grade,
            )
            transferred_count += 1

        save_workflow(workflow["workflow_id"], workflow)

        return render_workflow_template(
            workflow,
            mode="transfer",
            transfer_result={
                "transferred_count": transferred_count,
                "skipped_count": skipped_count,
            },
            message="Grade transfer completed.",
        )

    except Exception:
        app.logger.exception("Final grade transfer failed.")
        save_workflow(workflow["workflow_id"], workflow)
        return render_workflow_template(
            workflow,
            mode="transfer",
            error_message="Error occured. Contact CPI for assistance.",
        )


@app.route("/jwks/", methods=["GET"])
def jwks():
    return tool_conf.get_jwks()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5060, debug=True)
