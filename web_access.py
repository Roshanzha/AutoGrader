"""Local, email-only access for the AutoGrader web app."""
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

import gradio as gr
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import HTTPConnection
from starlette.responses import Response

COOKIE = "autograder_session"
LIFETIME = 8 * 3600
ADDRESS = re.compile(r"[a-z0-9_+%-]+(?:\.[a-z0-9_+%-]+)*@iitp\.ac\.in", re.ASCII)


def form_page(register=False, message="", status=200):
    action, other = ("Register", "Sign in") if register else ("Sign in", "Register")
    path, alternate = ("/register", "/login") if register else ("/login", "/register")
    return HTMLResponse(f"""<!doctype html><html lang="en"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{action} · AutoGrader</title><style>
    :root{{color-scheme:light dark}}*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;
    place-items:center;background:Canvas;color:CanvasText;font:16px/1.5 system-ui,sans-serif}}
    main{{width:min(92vw,390px);padding:24px}}h1{{font-size:2.3rem;margin:0}}h2{{margin:.6em 0}}
    label,input,button{{display:block;width:100%}}input,button{{font:inherit;border:1px solid #78918e;
    border-radius:6px;padding:10px;margin:6px 0 16px}}button{{background:#195f57;color:white;cursor:pointer}}
    </style><main><h1>AutoGrader</h1><h2>{action}</h2><form method="post" action="{path}">
    <label for="email">IIT Patna email address</label><input type="email" id="email" name="email"
    autocomplete="email" maxlength="254" required placeholder="name@iitp.ac.in">
    <p role="status">{message}</p><button>{action}</button></form>
    <a href="{alternate}">{other}</a></main></html>""", status_code=status,
    headers={"Cache-Control": "no-store"})


def create_app(demo, data_dir=None):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    directory = Path(data_dir or Path.home() / ".local/share/autograder")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    database = directory / "accounts.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS accounts(email TEXT PRIMARY KEY)")
        db.commit()
    sessions = {}

    def identity(request: Request):
        record = sessions.get(request.cookies.get(COOKIE))
        return record[0] if record and record[1] > time.monotonic() else None

    class AccessGate:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] in ("http", "websocket"):
                conn = HTTPConnection(scope)
                path = scope["path"]
                if path not in ("/", "/login", "/register") and not identity(conn):
                    if scope["type"] == "websocket":
                        await send({"type": "websocket.close", "code": 1008})
                        return
                    response = RedirectResponse("/login", 303) if "text/html" in conn.headers.get("accept", "") else Response(status_code=401)
                    await response(scope, receive, send)
                    return
                origin = conn.headers.get("origin")
                if scope.get("method") == "POST" and origin and urlsplit(origin).netloc != conn.headers.get("host"):
                    await Response(status_code=403)(scope, receive, send)
                    return
            await self.app(scope, receive, send)

    app.add_middleware(AccessGate)

    @app.get("/")
    async def home(request: Request):
        return RedirectResponse("/grader/" if identity(request) else "/login", 303)

    @app.get("/login")
    @app.get("/register")
    async def entry(request: Request):
        return form_page(request.url.path == "/register")

    @app.post("/register")
    @app.post("/login")
    async def enter(request: Request, email: str = Form(...)):
        register = request.url.path == "/register"
        address = email.strip().lower()
        if len(address) > 254 or not ADDRESS.fullmatch(address):
            return form_page(register, "Enter an @iitp.ac.in email address.", 400)
        with closing(sqlite3.connect(database)) as db:
            if register:
                inserted = db.execute("INSERT OR IGNORE INTO accounts VALUES (?)", (address,)).rowcount
                db.commit()
                return form_page(False, "Account registered. Sign in to continue." if inserted else
                                 "This address is already registered. Sign in to continue.")
            if not db.execute("SELECT 1 FROM accounts WHERE email=?", (address,)).fetchone():
                return form_page(False, "Register this email address first.", 403)
        now = time.monotonic()
        for token in [key for key, (_, expiry) in sessions.items() if expiry <= now]:
            sessions.pop(token, None)
        sessions.pop(request.cookies.get(COOKIE), None)
        token = secrets.token_urlsafe(32)
        sessions[token] = (address, now + LIFETIME)
        response = RedirectResponse("/grader/", 303)
        response.set_cookie(COOKIE, token, max_age=LIFETIME, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https")
        return response

    @app.post("/logout")
    async def logout(request: Request):
        sessions.pop(request.cookies.get(COOKIE), None)
        response = RedirectResponse("/login", 303)
        response.delete_cookie(COOKIE)
        return response

    return gr.mount_gradio_app(app, demo, path="/grader", auth_dependency=identity)
