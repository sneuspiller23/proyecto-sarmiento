# Proyecto Sarmiento

**Sistema Integral de Gestión Escolar.** El nombre es un homenaje a Domingo Faustino Sarmiento, impulsor de la educación pública argentina.

Aplicación web de demostración para el trabajo práctico de Sistemas de Información.
Gestiona estudiantes, inscripciones, asistencia y notas de un colegio secundario, con
acceso según el rol de cada usuario.

**Registrar una vez, consultar según el rol y conservar el historial.**

## Cómo ejecutarlo

Requisito: Python 3.10 o superior. No hace falta internet: Bootstrap está incluido en
`static/vendor`.

```bash
pip install -r requirements.txt
python app.py
```

Abrir <http://localhost:5000>. La primera vez se crea `sige.db` con datos de ejemplo.
Para reiniciar la demo, cerrar la aplicación, borrar `sige.db` y volver a ejecutarla.

## Usuarios de prueba

Todos con la contraseña `1234`.

| Usuario | Rol | Qué puede hacer |
|---|---|---|
| `admin` | Administración | Estudiantes, inscripciones, cursos, materias, usuarios, reportes y esta documentación |
| `directora` | Directivo | Ver estudiantes, trayectorias, inscripciones, reportes y auditoría |
| `preceptor` | Preceptor | Tomar asistencia de 1° A y 1° B y ver a sus estudiantes |
| `docente` | Docente | Cargar notas de Matemática de 1° A y 1° B y de Lengua de 1° A |

También existen `preceptor2` (2.º año), `preceptor3` (3.er año) y `docente2` a `docente6`,
que tienen el resto de las materias.

## Datos de ejemplo (todos ficticios)

- **Dos años lectivos:** 2025 (1.º y 2.º, A y B) y 2026 (1.º, 2.º y 3.º, A y B), con cupo de 30. Los estudiantes de 2.º y 3.º de 2026 cursaron el año anterior, así que su trayectoria tiene historial.
- **Materias en cada curso:** Matemática, Lengua, Historia, Geografía, Inglés y Biología, todas con docente asignado.
- **144 estudiantes:** 139 inscriptos en 2026 (entre 21 y 25 por curso), 3 registrados **sin inscripción** (Aguirre, Molina y Navarro) para inscribirlos en vivo y 2 desactivados que dejaron la escuela en 2025.
- **Asistencia** de todos los días hábiles de 2025 y de 2026 hasta el día anterior a la creación de la base (sin el receso de invierno). La de hoy queda libre para la demo.
- **Notas** de los tres trimestres de 2025 y del 1.º y 2.º de 2026. El 3.er trimestre de 2026 queda vacío para cargarlo en la demo.
- **Alertas preparadas:** Benítez, Tomás (1° A) y Medina, Santiago (2° A) superan el límite de faltas; Domínguez, Mateo (1° A), Quiroga, Bruno (3° A) y Ortiz, Lautaro (2° A) tienen notas bajas.
- **Auditoría** con las inscripciones, las cargas de notas y las últimas dos semanas de asistencia e ingresos.

## Guion de la demo (5 minutos)

1. Entrar como `admin` → «Nueva inscripción» → elegir a un estudiante sin inscripción (o buscar su DNI con puntos) → elegir curso → «Guardar inscripción» → «Imprimir».
2. Volver a buscar el mismo DNI → aparece el aviso de duplicado y la inscripción existente.
3. Entrar como `preceptor` → «Tomar asistencia de hoy» en 1° A → marcar ausentes → guardar.
4. Entrar como `docente` → «Notas» → Matemática 1° A, 3.er trimestre → escribir un 15 → ver el error.
5. Entrar como `directora` → trayectoria de Benítez o Domínguez (alertas) → en la trayectoria de un alumno de 2.º o 3.º, abrir el año anterior → «Reportes» → «Descargar CSV» → «Auditoría».

## Reglas principales

- El DNI se guarda solo con números: `45.123.456`, `45 123 456` y `45123456` son el mismo.
- Un estudiante tiene una sola inscripción por año lectivo (control en el formulario y restricción `UNIQUE` en la base). El botón «Guardar» se desactiva después del primer clic.
- La inscripción, el alta del estudiante nuevo y la fila de auditoría se guardan en una sola transacción. Si algo falla, no se guarda nada y no se muestra constancia.
- La asistencia de un día se carga una vez; si se vuelve a abrir, se corrige (no se duplica).
- Las notas van de `NOTA_MIN` a `NOTA_MAX`; si una está fuera de rango no se guarda ninguna.
- Alertas: «Revisar asistencia» con más de `LIMITE_FALTAS` faltas y «Revisar rendimiento» con alguna nota menor a `NOTA_APROBACION`. El sistema solo señala; decide el equipo escolar.
- Los estudiantes no se borran: se desactivan. La auditoría registra ingresos, inscripciones, cambios de estudiantes, asistencia, notas y exportaciones.
- Un docente o preceptor que intenta entrar a algo que no es suyo recibe una página 403.

Las constantes (`NOTA_MIN`, `NOTA_MAX`, `NOTA_APROBACION`, `LIMITE_FALTAS`, `ANIO_ACTUAL`) están al principio de `comun.py`.

## Dónde está cada requisito

| Requisito | Dónde está |
|---|---|
| Buscar por DNI y normalizarlo | `normalizar_dni` en `comun.py`; búsqueda en `nueva` de `modulos/inscripciones.py` |
| Alta con el DNI ya cargado | `nueva` y `guardar` en `modulos/inscripciones.py`; validación en `validar_estudiante` de `modulos/estudiantes.py` |
| Errores junto a cada campo, sin perder lo cargado | Macros `campo` y `resumen_errores` en `templates/_macros.html` |
| Curso del año correcto y con cupo | `guardar` en `modulos/inscripciones.py` |
| No duplicar inscripciones | `inscripcion_del_anio` y `avisar_duplicado` en `modulos/inscripciones.py`; `UNIQUE (estudiante_id, anio_lectivo)` en `schema.sql` |
| Guardar en una transacción con auditoría | `guardar` en `modulos/inscripciones.py` (`commit` y `rollback`) y `auditar` en `comun.py` |
| Constancia lista para imprimir | `ver` en `modulos/inscripciones.py` y `templates/inscripciones/constancia.html` |
| Evitar el doble clic | Script `data-un-envio` en `templates/base.html` |
| Control por rol y por curso | `requiere_rol`, `cursos_propios` y `puede_ver_estudiante` en `comun.py` |
| Menú según el rol | `MENU` en `app.py` |
| Asistencia sin duplicar el día | `asistencia_planilla` en `modulos/aula.py`; `UNIQUE (estudiante_id, fecha)` en `schema.sql` |
| Notas dentro del rango | `notas_planilla` en `modulos/aula.py` |
| Trayectoria y alertas | `trayectoria` en `modulos/estudiantes.py`; `estudiantes_con_alerta` en `comun.py` |
| Reportes y CSV | `modulos/reportes.py` |
| Cursos, materias, usuarios y auditoría | `modulos/administracion.py` |
| Protección de formularios (CSRF) | `cargar_usuario` y `token_csrf` en `app.py` |
| Datos de ejemplo | `cargar_datos_ejemplo` en `db.py` |

## Archivos

```
app.py               arma la aplicación: sesión, seguridad, menú y páginas de error
comun.py             constantes, roles, alertas y consultas compartidas
db.py                conexión, creación de tablas y datos de ejemplo
schema.sql           tablas
modulos/             un Blueprint por grupo de pantallas
  general.py         ingreso, inicio y documentación
  estudiantes.py     lista, alta, edición y trayectoria
  inscripciones.py   inscripción, constancia y lista
  aula.py            asistencia y notas
  reportes.py        reportes y CSV
  administracion.py  cursos, materias, usuarios y auditoría
templates/           base.html y una plantilla por pantalla
static/              style.css y Bootstrap (vendor/)
tests/               pruebas automáticas
```

## Pruebas

```bash
python -m unittest discover tests
```

Recorren las pantallas de cada rol, los accesos no permitidos, todos los pasos de la
inscripción (incluida una falla simulada al guardar), la asistencia, las notas, la
trayectoria, los reportes y la administración. Cada prueba usa una copia nueva de la base
de ejemplo, así que no modifican el `sige.db` de la demo.

## Configuración opcional

- `SIGE_CLAVE_SECRETA`: clave de sesión propia (por defecto se usa una fija, solo para la demo).
- `SIGE_DEBUG=1`: modo de desarrollo de Flask (recarga automática).
- `SIGE_DB`: ruta de otra base de datos (la usan las pruebas).
