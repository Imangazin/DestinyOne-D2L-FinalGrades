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

        user = launch_data.get("name")
        course = launch_data.get("context", {}).get("title")
        return f"Hello {user}, welcome to {course}"

    except Exception as e:
        print("LAUNCH ERROR:", str(e))
        return {"error": str(e)}, 400


@app.route("/jwks/", methods=["GET"])
def jwks():
    return tool_conf.get_jwks()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5060, debug=True)
