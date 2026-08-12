# Actualizaciones automáticas — Irrigación Bot (Tauri 2)

Las PCs de la oficina consultan `http://<SERVIDOR>:8000/updates/latest.json` al iniciar la app de escritorio. Si hay una versión más nueva firmada, aparece un modal para instalarla.

## Arquitectura

```
PC oficina (Tauri)  ──GET──▶  FastAPI :8000/updates/latest.json
                              └── descarga *.AppImage.tar.gz firmado
```

- **Manifiesto:** `updates/latest.json` (formato Tauri v2 con `platforms`)
- **Paquetes:** `.tar.gz` + `.sig` generados al compilar con `createUpdaterArtifacts: true`
- **Firma:** par de claves minisign (`tauri signer generate`)

## 1. Generar claves (una sola vez)

Desde `desktop-app/`:

```bash
npx tauri signer generate -w src-tauri/.tauri/irrigacion-bot.key --password ""
```

Se crean:

| Archivo | Uso |
|---------|-----|
| `src-tauri/.tauri/irrigacion-bot.key` | **Privada** — nunca commitear |
| `src-tauri/.tauri/irrigacion-bot.key.pub` | Pública — ya embebida en `tauri.conf.json` |

La clave pública en `tauri.conf.json` → `plugins.updater.pubkey` debe coincidir con la privada usada al firmar.

> Si perdés la clave privada, no podrás publicar updates a instalaciones existentes.

## 2. Compilar una versión firmada

```bash
# En la raíz del repo
export TAURI_SIGNING_PRIVATE_KEY="$PWD/desktop-app/src-tauri/.tauri/irrigacion-bot.key"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""   # si la clave no tiene password, dejalo vacío

# Opcional: URL del servidor para el cliente
export API_PUBLIC_URL=http://172.30.12.101:8000

./scripts/build_desktop.sh
```

Para que el updater genere paquetes en Linux, incluí **AppImage** (además del `.deb` si querés):

```bash
cd desktop-app
npm run tauri build -- --bundles deb,appimage
```

Artefactos relevantes:

```
desktop-app/src-tauri/target/release/bundle/appimage/
  Irrigacion Bot_0.2.0_amd64.AppImage
  Irrigacion Bot_0.2.0_amd64.AppImage.tar.gz      ← updater
  Irrigacion Bot_0.2.0_amd64.AppImage.tar.gz.sig   ← firma
```

## 3. Publicar en el servidor

```bash
# Subí la versión en tauri.conf.json antes de compilar (ej. 0.2.0)
export API_PUBLIC_URL=http://172.30.12.101:8000   # o Tailscale: http://100.68.57.77:8000
UPDATE_NOTES="Correcciones de skills y visor de archivos." ./scripts/publish_update.sh
```

Esto copia el `.tar.gz` a `updates/` y genera `updates/latest.json`.

### Despliegue con Docker

Montá la carpeta `updates/` en el contenedor API (ya configurado en `docker-compose.prod.yml`):

```yaml
- ${UPDATES_HOST_DIR:-./updates}:/app/static/updates:ro
```

En el servidor:

```bash
# Copiá updates/ al host del deploy
rsync -av updates/ usuario@servidor:/ruta/al/proyecto/updates/

# Redeploy
./scripts/deploy.sh
```

Verificá:

```bash
curl http://172.30.12.101:8000/updates/latest.json
```

## 4. Endpoints configurados en la app

En `desktop-app/src-tauri/tauri.conf.json`:

```json
"endpoints": [
  "http://172.30.12.101:8000/updates/latest.json",
  "http://100.68.57.77:8000/updates/latest.json"
],
"dangerousInsecureTransportProtocol": true
```

La app prueba LAN primero y luego Tailscale. Para cambiar la IP, editá `endpoints` y recompilá el cliente.

## 5. Comportamiento en la PC

Al abrir Irrigación Bot (Tauri):

1. `check()` consulta `/updates/latest.json`
2. Si `version` > versión instalada → modal *"Hay una nueva versión… [Actualizar ahora]"*
3. Al confirmar → descarga silenciosa, verifica firma, instala y reinicia

Si el servidor no responde, la app arranca normalmente.

## 6. Formato de `latest.json`

Ver plantilla: `updates/latest.json.example`

```json
{
  "version": "0.2.0",
  "notes": "Changelog breve",
  "pub_date": "2026-08-12T14:00:00Z",
  "platforms": {
    "linux-x86_64": {
      "signature": "<contenido del .sig>",
      "url": "http://172.30.12.101:8000/updates/Irrigacion Bot_0.2.0_amd64.AppImage.tar.gz"
    }
  }
}
```

## Checklist de release

1. [ ] Bump `version` en `desktop-app/src-tauri/tauri.conf.json` y `desktop-app/package.json`
2. [ ] Compilar con `TAURI_SIGNING_PRIVATE_KEY` exportada
3. [ ] `./scripts/publish_update.sh`
4. [ ] Subir `updates/` al servidor y redeploy
5. [ ] Probar desde una PC con la versión anterior instalada
