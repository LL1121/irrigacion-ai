# Ideas (backlog de producto)

Notas sueltas para no perder el hilo. No es un plan de implementación: cuando toque uno de estos temas, se arma el plan aparte.

Cómo anotar: fecha, el problema de verdad (no el caso puntual), y la dirección que nos gusta.

---

## Sysadmin local vía Tauri

**Anotado:** 13 ago 2026

### Qué se busca

Un asistente que **hace cosas**, no solo charla. En las PCs de la oficina (cliente Tauri) debería poder actuar como un sysadmin chico: buscar un archivo en **esa** máquina, más adelante prender una PC (WOL), etc.

Hoy **no puede**. El cerebro (Groq/Gemini + API) vive en el servidor. Tauri es un cascarón: el chat se va al server y el disco de la PC no se ve. Las skills corren en sandbox/inline **en el server**, sin shell ni `subprocess` sobre el host. A propósito: bot de oficina, no root remoto.

### Cómo lo pensamos

No meter el LLM adentro de Tauri. El server sigue pensando y hablando. **Tauri son las manos en esa PC.**

```
Usuario (Tauri en la PC de la oficina)
        │  "buscame el excel de padrones"
        ▼
Servidor (agente: entiende, decide, habla)
        │  tool: buscar archivos locales
        ▼
Tauri en ESA misma PC  →  disco / share  →  resultado al agente
```

En Rust, comandos chicos y allowlist (no “todo el disco”):

- buscar por nombre en Documentos, Descargas, un share tipo `S:\Irrigacion`
- leer / abrir un archivo
- después: WOL, impresoras, lo que pinte

HITL si va a leer algo sensible o borrar. En la **PWA del celu** esto no existe: no hay disco de oficina.

### Dos lecturas (no mezclar al arrancar)

| Qué | Se puede | Cómo |
|-----|----------|------|
| Estoy en la PC de Juan, con Tauri, busco un archivo **de esa PC** | Sí — **fase 1** | Tools locales en ese Tauri, atadas a esa sesión de chat |
| Estoy en la mía y quiero un archivo **que está en la de Juan** | Más adelante — **fase 2** | Cada PC con Tauri abierto + “presente”; el server le pide a la de Juan. Permisos, que esté prendida, quién puede ver qué |

Fase 2 es una flota de agentes. No empezarla hasta que fase 1 ande y sea segura.

### Qué no es

- Un agente que recorre `/home` o `/etc` del **servidor**
- Skills remotas con `os.system` / `subprocess` (el centinela las bloquea)
- Un modelo local en cada escritorio (innecesario y pesado)

### Cuando se implemente (fase 1, a groso modo)

1. Comandos Tauri: `search_files` / `read_file` (raíces permitidas).
2. El API, si el chat viene de desktop, puede pedir esas tools al cliente (no a la PWA).
3. El agente trata “buscame el archivo X” como tool local, no como skill de marketplace ni Drive, salvo que el usuario hable de Drive.

---

## Otras ideas

_(ir agregando abajo)_
