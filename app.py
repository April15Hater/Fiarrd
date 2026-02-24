"""
web/app.py — Local Flask dashboard (127.0.0.1:5001). No auth needed.
"""
from flask import Flask
from web.routes import register_routes

app = Flask(__name__, template_folder="templates")
app.secret_key = "jobsearch-local-only-no-auth-needed"

register_routes(app)


def run():
    app.run(host="127.0.0.1", port=5001, debug=False)
