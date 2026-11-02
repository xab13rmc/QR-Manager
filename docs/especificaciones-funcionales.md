# QR-Manager · Especificaciones funcionales aprobadas
Versión 1.1 · 2026-11-02

## Objetivo
Aplicación web profesional para generar, editar y administrar muchos códigos QR dinámicos organizados por negocios. Un panel de administración central con acceso privado opcional para usuarios de cada negocio.

> **Estado:** documento de requisitos. La aplicación actual desplegada es un prototipo monodominio y NO implementa todavía estas funciones.

## Organización
- Cada negocio tiene **un único dominio maestro principal**.
- Un dominio maestro tiene múltiples QR: `https://dominio-del-negocio/QR/slug`.
- El identificador `slug` debe ser único **dentro de su dominio**, no necesariamente globalmente.
- El sistema resuelve cada petición por **hostname + slug**, no solo por slug.
- La ruta `/QR/` debe configurarse sin romper las páginas existentes del dominio.
- El administrador central administra todos los negocios. Los usuarios invitados solo acceden a los negocios autorizados.
- El dominio maestro se registra, verifica y configura antes de activar sus QR públicos. Evitar enlaces no operativos.

## Editor visual de QR
- Visualización en tiempo real y validación de que el QR es escaneable.
- Personalizar formas de módulos, ojos/marcadores, colores de módulos y fondo, degradados, marcos, texto y logotipo.
- Selector de color visual con cuentagotas cuando esté disponible en el navegador, e introducción directa de HEX.
- Guardar colores favoritos, paletas y estilos en **dos niveles**: biblioteca general y bibliotecas por negocio.
- Guardar plantillas con nombre, duplicarlas, modificarlas y usarlas para crear otros QR.
- Al crear un QR, cargar por defecto **el último estilo utilizado en ese negocio**. Se pueden ajustar todos los parámetros antes de guardar.
- Logo: permitir subir uno para un QR concreto y elegir otro desde una biblioteca de logos reutilizables del negocio.
- Exportación de códigos en SVG y PNG de alta resolución. Preservar la zona de silencio y corrección de errores.
- Cambiar el diseño del QR NO cambia su URL pública. Si se modifica el estilo tras imprimir el QR, la impresión anterior conserva su aspecto y sigue siendo válida.

## Destinos y experiencias
Cada QR puede tener un modo configurado:
1. Redirección directa a URL destino editable.
2. Página intermedia con pop-up configurable antes de redirigir (con condiciones para cerrarlo o continuar).
3. Página de destino personalizada con imágenes, textos, botones y pop-ups opcionales.

Un pop-up se muestra dentro de la página web a la que lleva el QR, no de manera nativa encima de la cámara.

## Guardado, publicación y versiones
- Borradores editables, publicación explícita e historial de versiones de cada QR.
- Guardar una edición no cambia automáticamente la versión pública. Publicar aplica los cambios.
- Historial de diseños y de configuración de URL/experiencia, con fecha, autor y posibilidad de restauración.
- Diferenciar claramente cambios de *diseño impreso* frente a cambios de *comportamiento online*.
- La URL estable del QR no debe cambiar cuando se modifica el destino, el diseño o el contenido de la página.
- Aplicar una nueva versión visual no modifica los QR ya impresos.

## Modelos de datos previstos
- Business(id, name, master_domain, status)
- Membership(user_id, business_id, role)
- QrCode(id, business_id, slug, current_published_version_id, created_at)
- QrVersion(id, qr_id, version, style_json, experience_json, destination_url, created_by, status, published_at)
- ColorPalette(id, scope_global_or_business, business_id?, name, colors)
- StylePreset(id, scope_global_or_business, business_id?, name, style_json)
- LogoAsset(id, business_id, storage_ref, filename)
- ScanEvent(id, qr_id, timestamp, metadata_minimized)

## Seguridad y operación
- Autenticación robusta y control de acceso por negocio en backend; no basta filtrar la interfaz.
- Validar dominios y destinos HTTP(S); proteger rutas administrativas; medidas contra abuso de redirecciones.
- Archivos alojados en almacenamiento persistente; datos en base de datos persistente con copias de seguridad.
- HTTPS, control de caché de las redirecciones y configuración DNS o proxy por cada dominio.
- Mínimos de privacidad para estadísticas y gestión de consentimiento cuando proceda.
- No publicar para QR definitivos hasta completar estas garantías.

## Decisiones confirmadas por el usuario
1. Colores y estilos: biblioteca general **y** bibliotecas propias por negocio.
2. Estilo predeterminado de un nuevo QR: último diseño utilizado **en ese negocio**.
3. Experiencias: tanto ventana previa como páginas personalizadas con pop-up.
4. Dominios: **un dominio principal por negocio**.
5. Logos: biblioteca reutilizable **y** carga individual por QR.
6. Ediciones: guardar, publicar y mantener **historial de versiones**.
