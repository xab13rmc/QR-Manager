# QR-Manager

Aplicación web para gestionar códigos QR dinámicos con URL de destino editable.

**Estado actual:** prototipo de un único dominio y administrador. La compatibilidad multidominio (`dominio/QR/slug`) y el acceso privado opcional por negocio todavía no están implementados. No usar para códigos impresos definitivos.

## Ejecutar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export QR_ADMIN_PASSWORD='elige-una-clave-segura'
export QR_BASE_URL='http://localhost:8000'
uvicorn app:app --reload
```

Panel: `/admin`. Redirecciones: `/QR/{slug}`.

## Pendiente

- Uno o varios dominios por negocio.
- Resolución y enrutamiento `https://dominio/QR/slug` sin interferir con las webs actuales.
- Administración central y usuarios con permisos por negocio.
- Persistencia y seguridad de producción.
- Despliegue y DNS.
