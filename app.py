import os
from dotenv import load_dotenv
from tempfile import mkdtemp

from flask import Flask, jsonify, render_template, request
from flask_caching import Cache
from pylti1p3.contrib.flask import FlaskOIDCLogin, FlaskMessageLaunch
from pylti1p3.contrib.flask.request import FlaskRequest
from pylti1p3.contrib.flask import FlaskCacheDataStorage
from pylti1p3.tool_config import ToolConfJsonFile

from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
APP_FOLDER = os.getenv("APP_FOLDER")
CACHE_DIR = os.getenv("FLASK_CACHE_DIR", f"/tmp/{APP_FOLDER}-flask-cache")
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


def get_launch_data_storage():
    return FlaskCacheDataStorage(cache)


def get_cached_message_launch():
    flask_request = FlaskRequest()
    message_launch = FlaskMessageLaunch(
        flask_request,
        tool_conf,
        launch_data_storage=get_launch_data_storage(),
    )
    return message_launch.from_cache()


@app.route("/")
def index():
    return "Flask app is running."


@app.route("/login/", methods=["GET", "POST"])
def login():
    flask_request = FlaskRequest()
    print("LOGIN METHOD:", request.method)
    print("LOGIN ARGS:", dict(request.args))
    print("LOGIN FORM:", dict(request.form))

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
    print("LAUNCH METHOD:", request.method)
    print("LAUNCH ARGS:", dict(request.args))
    print("LAUNCH FORM KEYS:", list(request.form.keys()))

    flask_request = FlaskRequest()

    try:
        message_launch = FlaskMessageLaunch(
            flask_request,
            tool_conf,
            launch_data_storage=get_launch_data_storage(),
        )
        launch_data = message_launch.get_launch_data()

        print("LAUNCH DATA:", launch_data)

        brightspace_data = launch_data.get("http://www.brightspace.com", {})
        context_data = launch_data.get(
            "https://purl.imsglobal.org/spec/lti/claim/context", {}
        )

        user = brightspace_data.get("username") or launch_data.get("sub")
        course = context_data.get("title")
        return jsonify({
            "message": f"Hello {user}, welcome to {course}",
            "user": user,
            "course": course,
            "launch_data": launch_data,
            "members_url": "/members/",
            "lineitems_url": "/lineitems/",
            "results_url": "/results/"
        })

    except Exception as e:
        print("LAUNCH ERROR:", str(e))
        return {"error": str(e)}, 400


@app.route("/members/", methods=["GET"])
def members():
    try:
        message_launch = get_cached_message_launch()
        nrps = message_launch.get_nrps()
        members_response = nrps.get_members()

        print("MEMBERS RESPONSE TYPE:", type(members_response).__name__)
        print("MEMBERS RESPONSE:", members_response)

        members_list = members_response
        if isinstance(members_response, dict):
            members_list = members_response.get("members", [])

        first_member = (
            members_list[0]
            if isinstance(members_list, list) and members_list
            else None
        )

        return jsonify({
            "members": members_list,
            "count": len(members_list) if isinstance(members_list, list) else None,
            "first_member": first_member,
            "raw_response": members_response if isinstance(members_response, dict) else None
        })

    except Exception as e:
        print("MEMBERS ERROR:", str(e))
        return jsonify({"error": str(e)}), 400


@app.route("/lineitems/", methods=["GET"])
def lineitems():
    try:
        message_launch = get_cached_message_launch()
        ags = message_launch.get_ags()
        lineitems = ags.get_lineitems()
        return jsonify({
            "lineitems": lineitems,
            "count": len(lineitems) if isinstance(lineitems, list) else None
        })
    except Exception as e:
        print("LINEITEMS ERROR:", str(e))
        return jsonify({"error": str(e)}), 400


@app.route("/results/", methods=["GET"])
def results():
    try:
        message_launch = get_cached_message_launch()
        ags = message_launch.get_ags()

        lineitem_id = request.args.get("lineitem_id")
        if not lineitem_id:
            lineitems = ags.get_lineitems()
            if not lineitems:
                return jsonify({
                    "message": "No line items found",
                    "results": []
                })
            lineitem_id = lineitems[0].get("id")

        results = ags.get_lineitem_results(lineitem_id)
        return jsonify({
            "lineitem_id": lineitem_id,
            "results": results,
            "count": len(results) if isinstance(results, list) else None
        })
    except Exception as e:
        print("RESULTS ERROR:", str(e))
        return jsonify({"error": str(e)}), 400


@app.route("/jwks/", methods=["GET"])
def jwks():
    return tool_conf.get_jwks()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5060, debug=True)
