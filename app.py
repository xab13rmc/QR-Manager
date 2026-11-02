"""QR-Manager: prototipo monodominio (no apto aún para despliegue multidominio)."""
import io, os, re, secrets, sqlite3
from datetime import datetime, timezone
from html import escape
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import qrcode
import qrcode.image.svg

app = FastAPI(title="QR-Manager", docs_url=None, redoc_url=None)
security = HTTPBasic()
DB = os.getenv("QR_DB_PATH", "qr.sqlite3")
BASE_URL = os.getenv("QR_BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_USER = os.getenv("QR_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("QR_ADMIN_PASSWORD", "")

def conn():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS codes (
        slug TEXT PRIMARY KEY, label TEXT NOT NULL, target TEXT NOT NULL,
        enabled INTEGER DEFAULT 1, visits INTEGER DEFAULT 0, updated TEXT NOT NULL)""")
    db.commit()
    return db

def auth(creds: HTTPBasicCredentials = Depends(security)):
    if not ADMIN_PASSWORD:
        raise HTTPException(503, "Configura QR_ADMIN_PASSWORD")
    if not (secrets.compare_digest(creds.username, ADMIN_USER)
            and secrets.compare_digest(creds.password, ADMIN_PASSWORD)):
        raise HTTPException(401, "Acceso denegado",
                            headers={"WWW-Authenticate": 'Basic realm="QR-Manager"'})

def valid_target(value):
    value = value.strip()
    p = urlparse(value)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise HTTPException(400, "Introduce una URL HTTP(S) válida")
    return value

def valid_slug(value):
    value = value.lower().strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,49}", value):
        raise HTTPException(400, "El identificador debe tener entre 3 y 50 caracteres")
    return value

def page(content):
    return HTMLResponse("""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QR-Manager</title><style>
body{font:15px system-ui;margin:0;background:#f4f6f8;color:#182536}
main{max-width:1000px;margin:40px auto;padding:20px}
section{background:white;border:1px solid #dfe3e9;border-radius:14px;padding:22px;margin:20px 0}
input{padding:11px;margin:6px 0 14px;border:1px solid #cbd2db;border-radius:7px;width:100%;box-sizing:border-box}
label{display:block;font-weight:600}button,a.btn{border:0;border-radius:7px;background:#2154c9;color:white;padding:10px 14px;text-decoration:none;cursor:pointer}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px 8px;border-bottom:1px solid #ddd}
small{color:#606976}a{word-break:break-word}
</style></head><body><main><h1>QR-Manager</h1><p>Gestión de códigos QR dinámicos</p>"""
    + content + "</main></body></html>")

@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/admin")

@app.get("/admin", dependencies=[Depends(auth)])
def dashboard():
    db = conn()
    codes = db.execute("SELECT * FROM codes ORDER BY updated DESC").fetchall()
    db.close()
    items = ""
    for c in codes:
        slug = escape(c["slug"], quote=True)
        url = escape(BASE_URL + "/QR/" + c["slug"], quote=True)
        target = escape(c["target"], quote=True)
        label = escape(c["label"], quote=True)
        items += (f'<tr><td><strong>{label}</strong><br><small>{slug}</small></td>'
                  f'<td><a href="{url}">{url}</a><br><small>{target}</small></td>'
                  f'<td>{c["visits"]}</td><td>'
                  f'<a href="/admin/edit/{slug}">Editar</a> · '
                  f'<a href="/admin/qr/{slug}.png">PNG</a> · '
                  f'<a href="/admin/qr/{slug}.svg">SVG</a></td></tr>')
    return page("""<section><h2>Crear QR</h2><form method="post" action="/admin/create">
<label>Nombre interno</label><input name="label" required maxlength="100">
<label>Identificador</label><input name="slug" required minlength="3" maxlength="50">
<label>URL destino</label><input name="target" type="url" required>
<button>Crear QR</button></form></section>"""
    + f'<section><h2>Códigos ({len(codes)})</h2><div style="overflow:auto"><table>'
      '<tr><th>Nombre</th><th>URL pública / destino</th><th>Visitas</th><th>Acciones</th></tr>'
      + items + "</table></div></section>")

@app.post("/admin/create", dependencies=[Depends(auth)])
def create(label: str = Form(...), slug: str = Form(...), target: str = Form(...)):
    slug, target = valid_slug(slug), valid_target(target)
    db = conn()
    try:
        db.execute("INSERT INTO codes(slug,label,target,updated) VALUES(?,?,?,?)",
                   (slug, label.strip()[:100], target, datetime.now(timezone.utc).isoformat()))
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "El identificador ya existe")
    finally:
        db.close()
    return RedirectResponse("/admin", status_code=303)

@app.get("/admin/edit/{slug}", dependencies=[Depends(auth)])
def edit(slug: str):
    db = conn()
    c = db.execute("SELECT * FROM codes WHERE slug=?", (slug,)).fetchone()
    db.close()
    if not c:
        raise HTTPException(404)
    label, target, slug = [escape(c[k], quote=True) for k in ("label", "target", "slug")]
    checked = "checked" if c["enabled"] else ""
    return page(f"""<section><h2>Editar {label}</h2>
<p>La URL pública permanece fija cuando cambias el destino.</p>
<form method="post" action="/admin/edit/{slug}">
<label>Nombre</label><input name="label" value="{label}" required>
<label>Destino</label><input type="url" name="target" value="{target}" required>
<label><input type="checkbox" style="width:auto" name="enabled" value="1" {checked}> Activo</label>
<button>Guardar</button> <a href="/admin">Volver</a></form></section>""")

@app.post("/admin/edit/{slug}", dependencies=[Depends(auth)])
def update(slug: str, label: str = Form(...), target: str = Form(...),
           enabled: str | None = Form(None)):
    target = valid_target(target)
    db = conn()
    cur = db.execute("UPDATE codes SET label=?,target=?,enabled=?,updated=? WHERE slug=?",
        (label.strip()[:100], target, int(enabled == "1"),
         datetime.now(timezone.utc).isoformat(), slug))
    db.commit()
    db.close()
    if not cur.rowcount:
        raise HTTPException(404)
    return RedirectResponse("/admin", status_code=303)

@app.get("/admin/qr/{slug}.{fmt}", dependencies=[Depends(auth)])
def qr(slug: str, fmt: str):
    db = conn()
    exists = db.execute("SELECT 1 FROM codes WHERE slug=?", (slug,)).fetchone()
    db.close()
    if not exists or fmt not in ("png", "svg"):
        raise HTTPException(404)
    url = BASE_URL + "/QR/" + slug
    buffer = io.BytesIO()
    if fmt == "svg":
        image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
        image.save(buffer)
        media = "image/svg+xml"
    else:
        image = qrcode.make(url, error_correction=qrcode.constants.ERROR_CORRECT_H)
        image.save(buffer, format="PNG")
        media = "image/png"
    buffer.seek(0)
    return StreamingResponse(buffer, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{slug}.{fmt}"'})

@app.get("/QR/{slug}")
def follow(slug: str):
    db = conn()
    c = db.execute("SELECT target,enabled FROM codes WHERE slug=?", (slug,)).fetchone()
    if c is None:
        db.close()
        raise HTTPException(404)
    if not c["enabled"]:
        db.close()
        raise HTTPException(410, "Código pausado")
    db.execute("UPDATE codes SET visits=visits+1 WHERE slug=?", (slug,))
    db.commit()
    db.close()
    return RedirectResponse(c["target"], status_code=302,
                            headers={"Cache-Control": "no-store, private"})
