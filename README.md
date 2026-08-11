# irrigacion-bot

Sistema de IA institucional para la oficina de Irrigación de Malargüe.

Arquitectura híbrida: backend local en Python (FastAPI) + PostgreSQL con `pgvector` + **Groq** (chat) + **Gemini** (OCR/embeddings/centinela) + desktop Tauri.

## Deploy de producción (on-prem / LAN)

Pensado para un **servidor de la oficina** (sin exposición a Internet).

### 1. Preparar secretos

```bash
cp .env.production.example .env.production
# Editar: POSTGRES_PASSWORD, GROQ_API_KEY, GEMINI_API_KEY, CORS_ORIGINS
```

Generar password fuerte:

```bash
openssl rand -base64 32
```

`DOCKER_GID` se detecta solo en el script de deploy (`getent group docker`).

### 2. Desplegar

```bash
chmod +x scripts/*.sh
./scripts/deploy.sh
```

Construye `skill-sandbox-image`, levanta `db` + `api` (`docker-compose.prod.yml`) y deja el API en `http://<IP-SERVIDOR>:8000`.

### 3. Firewall (imprescindible)

Permitir **solo la red LAN** hacia el puerto API. **No** publicar Postgres (queda en red Docker interna).

### 4. Clientes de escritorio

```bash
./scripts/build_desktop.sh
# instalar el paquete en desktop-app/src-tauri/target/release/bundle/
```

En la app: **Configuración** (engranaje) → URL del servidor:

```text
http://<IP-O-HOSTNAME-DEL-SERVIDOR>:8000
```

### 5. Backups

```bash
./scripts/backup_db.sh
# dumps en ./backups/*.sql.gz
```

### Checklist de salida

- [ ] `.env.production` con secretos reales (no placeholders)
- [ ] `curl http://127.0.0.1:8000/health` → ok
- [ ] Firewall LAN-only en `:8000`
- [ ] App Tauri apunta a la IP del servidor
- [ ] Backup programado (cron diario de `backup_db.sh`)
- [ ] Probar upload + chat + skill maliciosa (rejected)

### Proveedores de IA

| Uso | Proveedor | Modelo default |
|-----|-----------|----------------|
| Chat / agente RAG | Groq | `llama-3.3-70b-versatile` |
| OCR (PDF escaneado / imágenes) | Gemini | `gemini-2.5-flash` |
| Embeddings RAG + caché | Gemini | `text-embedding-004` (768 dims) |
| Centinela de skills | Gemini | `gemini-2.5-flash` |

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
