"""Páginas legales públicas (privacidad) para verificación OAuth de Google."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["legal"])

PRIVACY_URL = "https://ia.irrigacionmalargue.net/politicas-privacidad"
APP_URL = "https://ia.irrigacionmalargue.net"
CONTACT_EMAIL = "ia@irrigacionmalargue.net"
LAST_UPDATED = "13 de agosto de 2026"

_PRIVACY_HTML = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Política de privacidad · Irrigación Bot</title>
  <meta name="description" content="Política de privacidad de Irrigación Bot, asistente institucional de la Jefatura de Zona de Riego de Malargüe. Describe el uso de datos de Google (identidad, Calendar, Gmail y Drive)." />
  <meta name="robots" content="index,follow" />
  <link rel="canonical" href="{PRIVACY_URL}" />
  <link rel="icon" type="image/png" href="/favicon-32x32.png" />
  <style>
    :root {{
      --bg: #faf7f2;
      --fg: #2d2520;
      --muted: #8a7a6e;
      --card: #fffcf8;
      --primary: #b5714e;
      --border: rgba(180, 150, 120, 0.28);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--fg);
      line-height: 1.65;
    }}
    header {{
      border-bottom: 1px solid var(--border);
      background: #f2ebe3;
      padding: 1.1rem 1.25rem;
    }}
    header .wrap, main, footer .wrap {{
      max-width: 46rem;
      margin: 0 auto;
    }}
    .brand {{
      font-weight: 650;
      font-size: 0.95rem;
      letter-spacing: 0.01em;
    }}
    .sub {{
      color: var(--muted);
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      margin-top: 0.15rem;
    }}
    main {{ padding: 2rem 1.25rem 3.5rem; }}
    h1 {{ font-size: 1.7rem; line-height: 1.25; margin: 0 0 0.4rem; }}
    .meta {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 1.75rem; }}
    h2 {{ font-size: 1.12rem; margin: 1.85rem 0 0.55rem; }}
    p, li {{ font-size: 0.98rem; }}
    ul {{ padding-left: 1.2rem; }}
    li {{ margin: 0.35rem 0; }}
    a {{ color: var(--primary); }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1rem 1.1rem;
      margin: 1rem 0 1.4rem;
    }}
    footer {{
      border-top: 1px solid var(--border);
      padding: 1.1rem 1.25rem 1.6rem;
      color: var(--muted);
      font-size: 0.82rem;
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <div class="brand">Irrigación Bot</div>
      <div class="sub">Malargüe · Jefatura de Zona de Riego</div>
    </div>
  </header>
  <main>
    <p><a href="/">← Volver al asistente</a></p>
    <h1>Política de privacidad</h1>
    <p class="meta">Última actualización: {LAST_UPDATED} · URL canónica: <a href="{PRIVACY_URL}">{PRIVACY_URL}</a></p>

    <p>
      Esta política describe cómo <strong>Irrigación Bot</strong> (el asistente virtual
      institucional de la Jefatura de Zona de Riego de Malargüe, Mendoza, Argentina)
      trata datos personales cuando usás
      <a href="{APP_URL}">{APP_URL}</a>, incluida la conexión con tu cuenta de Google.
    </p>

    <h2>1. Responsable</h2>
    <p>
      El servicio es operado por la Jefatura de Zona de Riego de Malargüe
      (Irrigación Malargüe) con fines internos de gestión hídrica e institucional.
      Contacto: <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.
    </p>

    <h2>2. Qué datos recabamos</h2>
    <div class="card">
      <p><strong>Cuenta e identidad (Google Sign-In)</strong></p>
      <ul>
        <li>Identificador de Google (<code>sub</code>), correo electrónico, nombre y foto de perfil.</li>
      </ul>
      <p><strong>Servicios de Google que autorizás (solo si iniciás sesión y otorgás permiso)</strong></p>
      <ul>
        <li><strong>Calendar:</strong> lectura de eventos próximos y creación de eventos que vos pidas.</li>
        <li><strong>Gmail:</strong> lectura de mensajes recientes para listarlos o resumirlos, y envío de correos solo cuando lo pedís y confirmás.</li>
        <li><strong>Drive:</strong> búsqueda y lectura de archivos que indiques, para mostrar contenido o indexarlo como contexto del asistente si lo pedís.</li>
      </ul>
      <p><strong>Uso del asistente</strong></p>
      <ul>
        <li>Mensajes del chat, documentos que subís y notas que pedís guardar como contexto (personal o de irrigación).</li>
        <li>Registros técnicos mínimos (fecha, sesión) para operar y auditar el servicio.</li>
      </ul>
    </div>

    <h2>3. Para qué los usamos</h2>
    <ul>
      <li>Identificarte y mantener tu sesión en el asistente.</li>
      <li>Ejecutar las acciones que pedís sobre tu Calendar, Gmail o Drive.</li>
      <li>Recordar contexto institucional (compartido de oficina) o personal (solo tu usuario), según indiques.</li>
      <li>Mejorar la seguridad y el funcionamiento del sistema (p. ej. confirmación humana antes de enviar un mail o crear un evento).</li>
    </ul>
    <p>
      <strong>No vendemos datos.</strong> No usamos el contenido de Gmail, Calendar ni Drive
      para publicidad, ni para entrenar modelos de inteligencia artificial de terceros
      con fines comerciales.
    </p>

    <h2>4. Uso limitado de datos de Google (Limited Use)</h2>
    <p>
      El acceso a APIs de Google cumple la
      <a href="https://developers.google.com/terms/api-services-user-data-policy" rel="noopener noreferrer">
        política de datos de usuario de los servicios de Google API
      </a>, incluida la política de uso limitado para Gmail:
    </p>
    <ul>
      <li>Solo usamos esos datos para brindar y mejorar las funciones visibles del asistente que vos activás.</li>
      <li>No transferimos datos de Google a terceros, salvo si es necesario para operar el servicio (p. ej. infraestructura propia), por obligación legal, o con tu instrucción explícita (enviar un correo).</li>
      <li>No permitimos que humanos lean el contenido de Gmail/Drive/Calendar salvo: (a) tu consentimiento puntual, (b) investigación de seguridad / abuso, (c) cumplimiento legal, o (d) el dato está ya agregado y no identifica a una persona.</li>
    </ul>

    <h2>5. Cómo los guardamos</h2>
    <ul>
      <li>Los tokens de acceso y actualización de Google se almacenan <strong>cifrados</strong> en nuestra base de datos.</li>
      <li>La sesión de la aplicación usa una cookie o token firmado (JWT), con vencimiento configurable (por defecto 7 días).</li>
      <li>El contexto “de irrigación” puede ser consultado por el asistente para personal de la oficina; el contexto “personal” queda asociado a tu usuario.</li>
    </ul>

    <h2>6. Con quién se comparte</h2>
    <p>
      No compartimos tus datos de Google con otras organizaciones. Pueden procesarlos
      proveedores estrictamente necesarios para hospedar el servicio (servidor y base
      de datos bajo control de Irrigación Malargüe). Google procesa el inicio de sesión
      y las APIs según sus propias políticas.
    </p>

    <h2>7. Conservación y baja</h2>
    <ul>
      <li>Podés cerrar sesión en el asistente en cualquier momento.</li>
      <li>Podés revocar el acceso de la aplicación desde
        <a href="https://myaccount.google.com/permissions" rel="noopener noreferrer">tu cuenta de Google → Permisos de terceros</a>.</li>
      <li>Para pedir la eliminación de tu usuario, tokens y contexto personal, escribinos a
        <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</li>
    </ul>

    <h2>8. Confirmaciones y seguridad</h2>
    <p>
      Las acciones de escritura (crear un evento, enviar un correo) requieren tu
      autorización en la interfaz (Autorizar / Cancelar), salvo que hayas reutilizado
      una autorización previa de esa misma herramienta. El acceso al servicio está
      destinado a personal autorizado de la Jefatura de Zona de Riego.
    </p>

    <h2>9. Derechos</h2>
    <p>
      Podés solicitar acceso, corrección o eliminación de tus datos personales
      asociados al asistente contactando a <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.
      También aplican los derechos previstos en la Ley 25.326 de Protección de Datos
      Personales de la República Argentina.
    </p>

    <h2>10. Cambios</h2>
    <p>
      Si actualizamos esta política, publicaremos la nueva versión en esta misma URL
      y cambiaremos la fecha de “última actualización”. El uso continuado del servicio
      después de un cambio sustancial implica que tomaste conocimiento de la nueva versión.
    </p>

    <h2>11. Contacto</h2>
    <p>
      Jefatura de Zona de Riego de Malargüe · Irrigación Bot<br />
      Sitio: <a href="{APP_URL}">{APP_URL}</a><br />
      Correo: <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>
    </p>
  </main>
  <footer>
    <div class="wrap">
      Irrigación Bot · Malargüe · Documento público para usuarios y para la verificación OAuth de Google.
    </div>
  </footer>
</body>
</html>
"""


_PRIVACY_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "X-Robots-Tag": "index,follow",
}


def _privacy_response() -> HTMLResponse:
    return HTMLResponse(content=_PRIVACY_HTML, status_code=200, headers=_PRIVACY_HEADERS)


@router.get("/politicas-privacidad", response_class=HTMLResponse)
def privacy_policy_es() -> HTMLResponse:
    return _privacy_response()


@router.get("/api/legal/privacidad", response_class=HTMLResponse)
def privacy_policy_api_alias() -> HTMLResponse:
    """Alias que el service worker de la PWA no intercepta (denylist /api/)."""
    return _privacy_response()


@router.get("/privacy-policy")
def privacy_policy_en_alias() -> RedirectResponse:
    return RedirectResponse(url="/politicas-privacidad", status_code=302)


@router.get("/privacy")
def privacy_short_alias() -> RedirectResponse:
    return RedirectResponse(url="/politicas-privacidad", status_code=302)
