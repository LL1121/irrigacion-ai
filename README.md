# irrigacion-bot

Sistema de IA institucional para la oficina de Irrigación de Malargüe.

Arquitectura híbrida: **un servidor** (FastAPI + PostgreSQL + PWA) y **clientes Tauri** en las PCs de la oficina. Los celulares usan la PWA instalada; las computadoras usan el binario nativo. Todo el cómputo de IA (Groq/Gemini) y la base vectorial viven en el servidor.

```
┌─────────────────────────────────────────────────────────────┐
│  SERVIDOR (on-prem / LAN + Tailscale)                       │
│  docker compose -f docker-compose.prod.yml                  │
│  ┌──────────────┐  ┌─────────────────────────────────────┐  │
│  │ PostgreSQL   │  │ FastAPI :8000                        │  │
│  │ + pgvector   │◄─┤  /api/*  → chat, upload, skills     │  │
│  │ (interno)    │  │  /       → PWA (desktop-app/dist)   │  │
│  └──────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         ▲                              ▲
         │ HTTP                         │ HTTP (misma URL)
         │                              │
   ┌─────┴─────┐                  ┌─────┴─────┐
   │ Tauri     │                  │ Celulares │
   │ (PCs)     │                  │ PWA       │
   │ binario   │                  │ Chrome/   │
   │ liviano   │                  │ Safari    │
   └───────────┘                  └───────────┘
```

| Cliente | Qué instala | URL del servidor |
|---------|-------------|------------------|
| **Celular** | PWA (“Agregar a pantalla de inicio”) | `http://<IP>:8000/` — misma URL para UI y API |
| **PC oficina** | `.deb` / `.AppImage` Tauri | `http://100.68.57.77:8000` (Tailscale) o LAN |

## Deploy de producción (on-prem / LAN)

Pensado para un **servidor de la oficina** (sin exposición a Internet).

### 1. Preparar secretos

```bash
cp .env.example .env
# Editar: POSTGRES_PASSWORD, GROQ_API_KEY, GEMINI_API_KEY, CORS_ORIGINS
# Opcional: API_PUBLIC_URL, LAN_API_URL (IPs reales del servidor)
```

Generar password fuerte:

```bash
openssl rand -base64 32
```

`DOCKER_GID` se detecta solo en el script de deploy (`getent group docker`).

### 2. Desplegar (servidor: DB + API + PWA)

En el **servidor** (con Docker instalado):

```bash
chmod +x scripts/*.sh
./scripts/deploy.sh
```

El script:
1. Compila la PWA (`npm run build` → `desktop-app/dist`)
2. Construye la imagen sandbox de skills
3. Levanta PostgreSQL + FastAPI con la PWA montada en `/`

Queda todo en `http://<IP-SERVIDOR>:8000` (API **y** interfaz móvil).

### 3. Celulares (PWA)

1. Conectarse a la LAN de oficina o Tailscale.
2. Abrir en Chrome/Safari: `http://172.30.12.101:8000/` (LAN) o `http://100.68.57.77:8000/` (Tailscale).
3. **Agregar a la pantalla de inicio** / **Instalar aplicación**.
4. Listo — la app detecta la API automáticamente (mismo origen, sin configurar URL).

### 4. PCs de escritorio (Tauri)

En una máquina de build (puede ser el mismo servidor o tu notebook):

```bash
./scripts/build_desktop.sh
# instalar el paquete en desktop-app/src-tauri/target/release/bundle/
```

El build embebe `API_PUBLIC_URL` del `.env` como URL default del cliente.

En la app: **Configuración** → URL del servidor si hace falta cambiarla.

Default:

```text
http://100.68.57.77:8000
```

LAN oficina (opcional): `http://172.30.12.101:8000`

### 5. Firewall + Tailscale

El API escucha en `0.0.0.0:8000` (LAN **y** Tailscale).

- **LAN oficina:** `http://172.30.12.101:8000`
- **Remoto (Tailscale):** `http://100.68.57.77:8000`

Asegurate de que:
1. Tailscale esté activo en el servidor y en los clientes que lo necesiten.
2. El firewall del host permita TCP `8000` al menos desde la interfaz Tailscale (`tailscale0`) / ACL del tailnet.
3. **No** publiques Postgres (sigue interno a Docker).

### 6. Backups

```bash
./scripts/backup_db.sh
# dumps en ./backups/*.sql.gz
```

### Checklist de salida

- [ ] `.env` con secretos reales (no placeholders)
- [ ] `curl http://127.0.0.1:8000/health` → ok
- [ ] `curl -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/` → 200 (PWA)
- [ ] PWA instalable desde celular en la LAN
- [ ] App Tauri instalada en al menos una PC de prueba
- [ ] Firewall LAN-only en `:8000`
- [ ] Backup programado (cron diario de `backup_db.sh`)
- [ ] Probar upload + chat + skill maliciosa (rejected)

### Actualizar frontend en producción

Si cambiás solo la UI (sin tocar backend):

```bash
cd desktop-app && npm run build && cd ..
docker compose --env-file .env -f docker-compose.prod.yml restart api
```

O volvé a correr `./scripts/deploy.sh` (rebuild completo).

### Proveedores de IA

| Uso | Proveedor | Modelo default |
|-----|-----------|----------------|
| Chat / agente RAG | Groq | `llama-3.3-70b-versatile` |
| OCR (PDF escaneado / imágenes) | Gemini | `gemini-flash-latest` |
| Embeddings RAG + caché | Gemini | `gemini-embedding-001` (768 dims) |
| Centinela de skills | Gemini | `gemini-flash-latest` |

> **Migración:** el schema usa `VECTOR(768)`. Si tenías una DB vieja con `VECTOR(1536)`, recreá el volumen (`docker compose down -v` / prod equivalente) antes de reindexar documentos.

---

## Desarrollo local (lab)

### Base de datos

```bash
docker compose up -d
```

Credenciales locales: `localhost:5434` / `irrigacion_db` / `postgres` / `postgres_local_pass`.

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

### Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Healthcheck |
| POST | `/api/upload` | Indexar documentos |
| POST | `/api/chat` | Chat (caché → LangGraph RAG) |
| GET | `/api/sessions` | Conversaciones |
| GET | `/api/sessions/{id}/messages` | Historial |
| POST | `/api/skills/execute` | Audita + sandbox Docker |

### Skills (Zero Trust)

```bash
cd backend && source .venv/bin/activate
python sandbox_env/build_image.py
```

Contenedor: `network_mode=none`, 256 MB RAM, 0.5 CPU, read-only + tmpfs `/tmp`, `remove=True`.

### Desktop (dev)

```bash
cd desktop-app
npm install
npm run tauri dev
```
