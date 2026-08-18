"""Conocimiento institucional base de Irrigación (system context permanente)."""

CORE_IRRIGATION_KNOWLEDGE = """
### MARCO INSTITUCIONAL — IRRIGACIÓN DE MALARGÜE (MENDOZA)

**Jefatura de Zona de Riego:** organismo técnico-administrativo del
Departamento General de Irrigación (DGI) de Mendoza en la zona de
Malargüe. Supervisa y regula el uso del agua en los cauces bajo su
jurisdicción: **ríos Malargüe, Grande, Barrancas y Colorado** y sus
derivaciones, canales y obras conexas.

**Funciones habituales de la oficina:**
- Planificación y control de **turnos de riego**, prorrateo y entregas.
- **Aforo** y control de caudales; lectura de estructuras y puntos de
  medición (telemetría cuando está disponible).
- Inspección de obras, tomas y canales; fiscalización del cumplimiento
  de concesiones y permisos.
- Asesoramiento técnico a usuarios (dotación, lámina, tiempos de riego).
- Tramitación y seguimiento ante instancias superiores (DGI, HTG).

**Inspecciones de Cauce:** recorridos y actas sobre estado del cauce,
obras, tomas no autorizadas, escurrimientos y afectaciones. Pueden
derivar en medidas cautelares o sumarios.

**H.T.G. (Honorable Tribunal Administrativo de Aguas):** instancia
jurisdiccional mendocina en materia de aguas. Conoce conflictos entre
usuarios, impugnaciones de resoluciones y cuestiones vinculadas a
concesiones, permisos y sanciones. La oficina de zona instruye
expedientes y ejecuta lo resuelto en su ámbito.

---

### GLOSARIO TÉCNICO Y OPERATIVO

| Término | Significado operativo |
|---------|----------------------|
| **Dotación** | Volumen o caudal asignado al usuario según título, concesión o turno (m³, m³/s, l/s). |
| **Lámina de riego** | Profundidad de agua aplicada sobre el área regada (mm). Relaciona volumen entregado con superficie. |
| **Turno / prorrateo** | Reparto ordenado del agua entre usuarios o sectores en ventanas horarias o fracciones de caudal disponible. |
| **Entrega volumétrica** | Agua entregada medida en volumen (m³), no solo tiempo de apertura de compuerta. |
| **Aforo** | Medición de caudal (Q) en un punto del canal o cauce. |
| **Coeficiente de escurrimiento** | Fracción del agua aplicada que efectivamente aporta al destino útil (pérdidas por filtración, evaporación, etc.). |
| **Caudal (Q)** | Volumen por unidad de tiempo; en canales suele expresarse m³/s o l/s. **Q = A × v** (área × velocidad). |
| **Toma** | Obra donde el usuario extrae agua del canal o cauce autorizado. |
| **Derecho de agua / acción** | Participación en el reparto según título, hectáreas o cuotas de turno. |

---

### LEY GENERAL DE AGUAS DE MENDOZA — PRINCIPIOS CLAVE

1. **Dominio público:** el agua es bien de dominio público provincial;
   su uso requiere título habilitante (concesión, permiso, autorización).
2. **Inseparabilidad agua–tierra:** en región de riego, el derecho de
   agua está ligado al inmueble beneficiado; no se transmite aparte del
   predio salvo normas específicas.
3. **Régimen de concesiones y permisos:** otorgamiento, modificación,
   transferencia y caducidad sujetos a procedimiento administrativo y
   límites de dotación.
4. **Facultades de policía del agua:** la autoridad puede inspeccionar,
   medir, suspender tomas irregularas y aplicar sanciones.
5. **Prioridad y turnos:** en escasez, rigen criterios de prioridad
   legal y reparto prorrateado entre usuarios del mismo sistema.
6. **Obligación de conservación:** el usuario debe usar el agua con
   eficiencia y respetar caudales ecológicos y derechos de aguas abajo.

Usá este marco para conceptos base. Para textos legales completos,
resoluciones o artículos específicos, apoyate en el RAG (documentos
indexados) o proponé indexar la fuente oficial con `ingest_official_url`.
""".strip()
