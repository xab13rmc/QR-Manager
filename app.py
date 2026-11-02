import os, re, io, sqlite3, secrets, json, hashlib, hmac
from datetime import datetime, timezone
from urllib.parse import urlparse
from html import escape as esc
from fastapi import FastAPI, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import qrcode
import qrcode.image.svg
from PIL import Image
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader

app=FastAPI(title="QR-Manager",docs_url=None,redoc_url=None)
security=HTTPBasic()
DB=os.getenv("QR_DB_PATH","qr.sqlite3")
BASE=os.getenv("QR_BASE_URL","https://qr-manager-xabier.onrender.com").rstrip("/")
ADMIN=os.getenv("QR_ADMIN_USER","admin")
PASSWORD=os.getenv("QR_ADMIN_PASSWORD","")
BRANDS=["Bella Ciao","La Fabrica","Estrella Andorra","ArtLab","Andorra Aviation Group","Maison Beauvert","Maison Beauvert Catering","Peregrinus"]
def timestamp(): return datetime.now(timezone.utc).isoformat()
def conn():
 c=sqlite3.connect(DB,timeout=20)
 c.row_factory=sqlite3.Row
 c.execute("PRAGMA busy_timeout=10000")
 c.executescript("""CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,domain TEXT DEFAULT '',active INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS codes(id INTEGER PRIMARY KEY,business_id INTEGER NOT NULL,slug TEXT NOT NULL,label TEXT NOT NULL,target TEXT NOT NULL,enabled INTEGER DEFAULT 1,visits INTEGER DEFAULT 0,updated TEXT,style TEXT DEFAULT '{}',popup INTEGER DEFAULT 0,popup_title TEXT DEFAULT '',popup_text TEXT DEFAULT '',popup_image BLOB,popup_mime TEXT,UNIQUE(business_id,slug));
 CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY,code_id INTEGER,created TEXT,editor TEXT,body TEXT);
 CREATE TABLE IF NOT EXISTS palettes(id INTEGER PRIMARY KEY,business_id INTEGER,name TEXT,color TEXT);
 CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY,business_id INTEGER,username TEXT UNIQUE,salt TEXT,hash TEXT);
 """)
 for name in BRANDS:
  domain="bellaciao-andorra.com" if name=="Bella Ciao" else ""
  c.execute("INSERT OR IGNORE INTO businesses(name,domain) VALUES(?,?)",(name,domain))
 c.commit()
 return c
def auth(credentials:HTTPBasicCredentials=Depends(security)):
 if not PASSWORD:raise HTTPException(503,"Configure QR_ADMIN_PASSWORD")
 if secrets.compare_digest(credentials.username,ADMIN) and secrets.compare_digest(credentials.password,PASSWORD): return None
 c=conn();u=c.execute("SELECT * FROM members WHERE username=?",(credentials.username,)).fetchone();c.close()
 if u and hmac.compare_digest(hashlib.pbkdf2_hmac("sha256",credentials.password.encode(),bytes.fromhex(u["salt"]),240000).hex(),u["hash"]):return u["business_id"]
 raise HTTPException(401,"Acceso denegado",headers={"WWW-Authenticate":'Basic realm="QR-Manager"'})
def check(scope,business_id):
 if scope is not None and scope!=business_id:raise HTTPException(403)
def page(body):
 return HTMLResponse("""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>QR-Manager</title><style>
 body{font:15px system-ui;background:#f3f5f8;color:#202b39;margin:0}main{max-width:1100px;margin:32px auto;padding:18px}
 section{background:white;border:1px solid #dfe4eb;border-radius:14px;padding:22px;margin:18px 0}
 h1{letter-spacing:-.04em}input,textarea,select{width:100%;max-width:100%;box-sizing:border-box;margin:6px 0 14px;padding:10px;border:1px solid #cbd3dc;border-radius:7px}input[type=checkbox],input[type=color]{width:auto}
 label{display:block;font-weight:600}button,.btn{background:#214a8a;color:#fff;border:0;border-radius:7px;padding:10px 15px;text-decoration:none;cursor:pointer}
 table{width:100%;border-collapse:collapse}td,th{padding:11px 5px;text-align:left;border-bottom:1px solid #e8eaf0}
 a{color:#2154c9;overflow-wrap:anywhere}.muted{color:#627184}.notice{background:#fff3d8;padding:12px;border-radius:8px}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
 </style></head><body><main><header><h1>QR-Manager</h1><a href="/admin">Todos los negocios</a></header>"""+body+"</main></body></html>")
def clean_url(s):
 s=s.strip();p=urlparse(s)
 if p.scheme not in ("http","https") or not p.hostname or p.username or p.password:raise HTTPException(400,"URL HTTP(S) no válida")
 return s
def clean_slug(s):
 s=s.lower().strip()
 if not re.fullmatch("[a-z0-9][a-z0-9-]{2,49}",s):raise HTTPException(400,"Identificador inválido")
 return s
def hexcolor(s):
 if not re.fullmatch(r"#[a-fA-F0-9]{6}",s):raise HTTPException(400,"Color HEX inválido")
 return s
def business(c,b):
 r=c.execute("SELECT * FROM businesses WHERE id=?",(b,)).fetchone()
 if not r:raise HTTPException(404)
 return r
def qrrow(c,i):
 r=c.execute("SELECT * FROM codes WHERE id=?",(i,)).fetchone()
 if not r:raise HTTPException(404)
 return r
def test_url(b,slug):return BASE+"/p/"+str(b)+"/QR/"+slug
def final_url(b,slug):
 return "https://"+b["domain"]+"/QR/"+slug if b["domain"] else test_url(b["id"],slug)
@app.get("/")
def index():return RedirectResponse("/admin")
@app.get("/admin")
def dashboard(scope=Depends(auth)):
 c=conn();rows=c.execute("SELECT b.*,count(q.id) AS total FROM businesses b LEFT JOIN codes q ON q.business_id=b.id GROUP BY b.id ORDER BY b.name").fetchall()
 t='<section><h2>Empresas</h2><p class="notice">Los dominios maestros se muestran como proyecto. Hasta configurar el proxy /QR/ en cada dominio, utiliza únicamente las URL de prueba de Render.</p><table><tr><th>Negocio</th><th>Dominio maestro</th><th>Códigos</th></tr>'
 for b in rows:
  if scope is None or scope==b["id"]:t+=f'<tr><td><a href="/admin/business/{b["id"]}">{esc(b["name"])}</a></td><td>{esc(b["domain"] or "Por configurar")}</td><td>{b["total"]}</td></tr>'
 t+="</table></section>"
 if scope is None:t+='''<section><h3>Añadir otra empresa</h3><form method="post" action="/admin/business"><label>Nombre</label><input name="name" required maxlength="100"><label>Dominio maestro (opcional)</label><input name="domain" placeholder="empresa.com"><button>Crear empresa</button></form></section>'''
 c.close();return page(t)
@app.post("/admin/business")
def new_business(name:str=Form(...),domain:str=Form(""),scope=Depends(auth)):
 if scope is not None:raise HTTPException(403)
 domain=domain.lower().strip()
 if domain and not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+",domain):raise HTTPException(400,"Dominio inválido")
 c=conn()
 try:c.execute("INSERT INTO businesses(name,domain) VALUES(?,?)",(name.strip()[:100],domain));c.commit()
 except sqlite3.IntegrityError:raise HTTPException(409,"Ya existe esa empresa")
 finally:c.close()
 return RedirectResponse("/admin",303)
@app.get("/admin/business/{b}")
def business_page(b:int,scope=Depends(auth)):
 check(scope,b);c=conn();biz=business(c,b)
 rows=c.execute("SELECT * FROM codes WHERE business_id=? ORDER BY id DESC",(b,)).fetchall()
 t=f'<section><h2>{esc(biz["name"])}</h2><p>Dominio maestro: {esc(biz["domain"] or "Sin configurar")}</p>'
 if scope is None:t+=f'<form method="post" action="/admin/business/{b}/domain"><label>Configurar dominio principal</label><input name="domain" value="{esc(biz["domain"],quote=True)}" placeholder="ejemplo.com"><button>Guardar dominio</button></form>'
 t+='<h3>QR del negocio</h3><table><tr><th>Nombre</th><th>Estado</th><th>Visitas</th></tr>'
 for x in rows:t+=f'<tr><td><a href="/admin/code/{x["id"]}">{esc(x["label"])}</a><br><small>/QR/{esc(x["slug"])}</small></td><td>{"Activo" if x["enabled"] else "Inactivo"}</td><td>{x["visits"]}</td></tr>'
 t+='</table></section>'
 t+=f'<section><h3>Crear código</h3><form method="post" action="/admin/business/{b}/new"><label>Nombre</label><input name="label" required><label>Identificador</label><input name="slug" required placeholder="carta"><label>URL destino</label><input type="url" name="target" required><button>Crear QR</button></form></section>'
 if scope is None:t+=f'<section><h3>Acceso privado opcional</h3><form method="post" action="/admin/business/{b}/member"><label>Usuario único</label><input name="username" required><label>Contraseña</label><input name="password" type="password" minlength="12" required><button>Crear acceso</button></form></section>'
 c.close();return page(t)
@app.post("/admin/business/{b}/domain")
def update_domain(b:int,domain:str=Form(""),scope=Depends(auth)):
 if scope is not None:raise HTTPException(403)
 domain=domain.lower().strip()
 if domain and not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+",domain):raise HTTPException(400,"Dominio inválido")
 c=conn();business(c,b);c.execute("UPDATE businesses SET domain=? WHERE id=?",(domain,b));c.commit();c.close()
 return RedirectResponse(f"/admin/business/{b}",303)
@app.post("/admin/business/{b}/member")
def add_member(b:int,username:str=Form(...),password:str=Form(...),scope=Depends(auth)):
 if scope is not None:raise HTTPException(403)
 if len(password)<12:raise HTTPException(400,"Contraseña demasiado corta")
 salt=secrets.token_bytes(16);hashed=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,240000).hex()
 c=conn();business(c,b)
 try:c.execute("INSERT INTO members(business_id,username,salt,hash) VALUES(?,?,?,?)",(b,username.strip(),salt.hex(),hashed));c.commit()
 except sqlite3.IntegrityError:raise HTTPException(409,"Usuario existente")
 finally:c.close()
 return RedirectResponse(f"/admin/business/{b}",303)
@app.post("/admin/business/{b}/new")
def create_qr(b:int,label:str=Form(...),slug:str=Form(...),target:str=Form(...),scope=Depends(auth)):
 check(scope,b);c=conn();business(c,b)
 other=c.execute("SELECT style FROM codes WHERE business_id=? ORDER BY updated DESC LIMIT 1",(b,)).fetchone()
 style=other["style"] if other else json.dumps({"color":"#214a8a","background":"#ffffff","shape":"rounded"})
 try:
  cur=c.execute("INSERT INTO codes(business_id,slug,label,target,updated,style) VALUES(?,?,?,?,?,?)",(b,clean_slug(slug),label.strip()[:100],clean_url(target),timestamp(),style));c.commit();newid=cur.lastrowid
 except sqlite3.IntegrityError:raise HTTPException(409,"Identificador existente en este negocio")
 finally:c.close()
 return RedirectResponse(f"/admin/code/{newid}",303)
@app.get("/admin/code/{i}")
def code_page(i:int,scope=Depends(auth)):
 c=conn();x=qrrow(c,i);check(scope,x["business_id"]);b=business(c,x["business_id"])
 s=json.loads(x["style"] or "{}");url=test_url(b["id"],x["slug"])
 prev=c.execute("SELECT * FROM revisions WHERE code_id=? ORDER BY id DESC LIMIT 12",(i,)).fetchall()
 rev="".join(f'<li>Versión {r["id"]} · {esc(r["created"][:19])}</li>' for r in prev)
 t=f'''<section><h2>{esc(x["label"])}</h2><p>URL de prueba: <a href="{esc(url)}">{esc(url)}</a></p><p>Dominio maestro previsto: <code>{esc(final_url(b,x["slug"]))}</code></p><p class="notice">No imprimas todavía QR con el dominio maestro: es necesario configurar su enrutamiento.</p>
 <p>Descargar: <a href="/admin/export/{i}/png">PNG transparente</a> · <a href="/admin/export/{i}/jpg">JPG</a> · <a href="/admin/export/{i}/svg">SVG</a> · <a href="/admin/export/{i}/pdf">PDF</a></p></section>
 <section><h3>Editar QR</h3><form method="post" action="/admin/code/{i}/save" enctype="multipart/form-data">
 <label>Nombre</label><input name="label" value="{esc(x["label"],quote=True)}" required>
 <label>URL de destino</label><input name="target" type="url" value="{esc(x["target"],quote=True)}" required>
 <label>Color de módulos (HEX)</label><input name="fg" type="color" value="{esc(s.get("color","#214a8a"))}"><input name="fg_hex" value="{esc(s.get("color","#214a8a"))}">
 <label>Color de fondo (HEX)</label><input name="bg" type="color" value="{esc(s.get("background","#ffffff"))}"><input name="bg_hex" value="{esc(s.get("background","#ffffff"))}">
 <label>Forma</label><select name="shape"><option value="{esc(s.get("shape","rounded"))}">Actual: {esc(s.get("shape","rounded"))}</option><option value="square">Cuadrados</option><option value="rounded">Redondeados</option><option value="dots">Puntos</option></select>
 <label><input name="enabled" type="checkbox" value="1" {"checked" if x["enabled"] else ""}> QR activo</label>
 <label><input name="popup" type="checkbox" value="1" {"checked" if x["popup"] else ""}> Mostrar página intermedia / pop-up</label>
 <label>Título del pop-up</label><input name="popup_title" value="{esc(x["popup_title"] or "",quote=True)}">
 <label>Texto del pop-up</label><textarea name="popup_text">{esc(x["popup_text"] or "")}</textarea>
 <label>Creatividad 1:1 o 5:4 (PNG/JPG/WebP)</label><input name="popup_image" type="file" accept="image/png,image/jpeg,image/webp">
 <button>Guardar nueva versión</button></form></section><section><h3>Historial de cambios</h3><ul>{rev or "Todavía sin cambios"}</ul></section>'''
 c.close();return page(t)
@app.post("/admin/code/{i}/save")
def save(i:int,label:str=Form(...),target:str=Form(...),fg_hex:str=Form("#214a8a"),bg_hex:str=Form("#ffffff"),shape:str=Form("square"),enabled:str|None=Form(None),popup:str|None=Form(None),popup_title:str=Form(""),popup_text:str=Form(""),popup_image:UploadFile|None=File(None),scope=Depends(auth)):
 c=conn();x=qrrow(c,i);check(scope,x["business_id"])
 style={"color":hexcolor(fg_hex),"background":hexcolor(bg_hex),"shape":shape if shape in ("square","rounded","dots") else "square"}
 asset=x["popup_image"];mime=x["popup_mime"]
 if popup_image and popup_image.filename:
  raw=popup_image.file.read(3_000_001)
  if len(raw)>3_000_000:raise HTTPException(400,"Imagen de más de 3 MB")
  try:
   im=Image.open(io.BytesIO(raw)); im.verify()
   im=Image.open(io.BytesIO(raw)); w,hh=im.size
   if im.format not in ("JPEG","PNG","WEBP") or min(abs(w/hh-1),abs(w/hh-1.25))>0.035:raise ValueError()
  except Exception:raise HTTPException(400,"Se requiere PNG/JPG/WebP 1:1 o 5:4")
  asset=raw;mime="image/jpeg" if im.format=="JPEG" else "image/"+im.format.lower()
 payload=json.dumps({"label":label,"target":target,"style":style,"enabled":bool(enabled),"popup":bool(popup)},ensure_ascii=False)
 c.execute("UPDATE codes SET label=?,target=?,style=?,enabled=?,popup=?,popup_title=?,popup_text=?,popup_image=?,popup_mime=?,updated=? WHERE id=?",(label.strip()[:100],clean_url(target),json.dumps(style),int(bool(enabled)),int(bool(popup)),popup_title[:150],popup_text[:2000],asset,mime,timestamp(),i))
 c.execute("INSERT INTO revisions(code_id,created,editor,body) VALUES(?,?,?,?)",(i,timestamp(),"administrador",payload));c.commit();c.close()
 return RedirectResponse(f"/admin/code/{i}",303)
def raster(url,style):
 fg=style.get("color","#214a8a");bg=style.get("background","#ffffff");shape=style.get("shape","square")
 qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,box_size=16,border=4);qr.add_data(url);qr.make(fit=True)
 mat=qr.get_matrix(); n=len(mat);size=n*16
 image=Image.new("RGBA",(size,size),(0,0,0,0));from PIL import ImageDraw
 d=ImageDraw.Draw(image)
 for y,row in enumerate(mat):
  for x,on in enumerate(row):
   if not on:continue
   rect=(x*16,y*16,(x+1)*16-1,(y+1)*16-1)
   if shape=="dots":d.ellipse(rect,fill=fg)
   elif shape=="rounded":d.rounded_rectangle(rect,radius=4,fill=fg)
   else:d.rectangle(rect,fill=fg)
 return image
@app.get("/admin/export/{i}/{fmt}")
def export(i:int,fmt:str,scope=Depends(auth)):
 if fmt not in ("png","jpg","pdf","svg"):raise HTTPException(404)
 c=conn();x=qrrow(c,i);check(scope,x["business_id"]);b=business(c,x["business_id"]);c.close()
 url=test_url(b["id"],x["slug"]);style=json.loads(x["style"] or "{}");img=raster(url,style)
 bio=io.BytesIO()
 if fmt=="png":img.save(bio,"PNG");mime="image/png"
 elif fmt=="jpg":
  back=Image.new("RGB",img.size,style.get("background","#ffffff"));back.paste(img,mask=img.getchannel("A"));back.save(bio,"JPEG",quality=96);mime="image/jpeg"
 elif fmt=="pdf":
  back=Image.new("RGB",img.size,"white");back.paste(img,mask=img.getchannel("A"));pdf=Canvas(bio,pagesize=(400,400));pdf.drawImage(ImageReader(back),20,20,360,360);pdf.save();mime="application/pdf"
 else:
  qr=qrcode.make(url,image_factory=qrcode.image.svg.SvgPathImage);qr.save(bio);mime="image/svg+xml"
 return Response(bio.getvalue(),media_type=mime,headers={"Content-Disposition":f'attachment; filename="{x["slug"]}.{fmt}"'})
@app.get("/admin/image/{i}")
def popup_img(i:int,scope=Depends(auth)):
 c=conn();x=qrrow(c,i);check(scope,x["business_id"]);c.close()
 if not x["popup_image"]:raise HTTPException(404)
 return Response(x["popup_image"],media_type=x["popup_mime"])
def redirect(biz_id,slug,hostname=None):
 c=conn()
 q=c.execute("SELECT * FROM codes WHERE business_id=? AND slug=?",(biz_id,slug)).fetchone()
 if not q:raise HTTPException(404)
 if not q["enabled"]:raise HTTPException(410,"QR inactivo")
 c.execute("UPDATE codes SET visits=visits+1 WHERE id=?",(q["id"],));c.commit();c.close()
 if q["popup"]:
  image=f'<img style="max-width:100%;max-height:350px;object-fit:contain" src="/public/image/{q["id"]}">' if q["popup_image"] else ""
  return page(f'<section style="max-width:560px;margin:auto;text-align:center"><h2>{esc(q["popup_title"] or "Información")}</h2>{image}<p>{esc(q["popup_text"] or "")}</p><a class="btn" href="{esc(q["target"],quote=True)}">Continuar</a></section>')
 return RedirectResponse(q["target"],302,headers={"Cache-Control":"no-store"})
@app.get("/public/image/{i}")
def public_image(i:int):
 c=conn();q=qrrow(c,i);c.close()
 if not q["enabled"] or not q["popup"] or not q["popup_image"]:raise HTTPException(404)
 return Response(q["popup_image"],media_type=q["popup_mime"])
@app.get("/p/{business_id}/QR/{slug}")
def preview(business_id:int,slug:str):return redirect(business_id,slug)
@app.get("/QR/{slug}")
def domain_resolve(slug:str,request:__import__("fastapi").Request):
 host=request.headers.get("host","").split(":")[0].lower()
 c=conn();b=c.execute("SELECT * FROM businesses WHERE domain=?",(host,)).fetchone();c.close()
 if not b:raise HTTPException(404,"Dominio no configurado")
 return redirect(b["id"],slug)
