# Sistema Integral de Gestión Escolar (SIGE)

Aplicación web de demostración para un trabajo práctico de Sistemas de Información.
Gestiona estudiantes, inscripciones, asistencia y notas de un colegio secundario,
con acceso según el rol de cada usuario.

Idea central: **registrar una vez, consultar según el rol y conservar el historial.**

Prioridad: **que sea simple, que funcione y que se vea prolijo en la demo.** Nada de
arquitectura de más, ni frameworks extra, ni paso de compilación. Todo en **español**.

---

## 1. Tecnología

- **Python 3.10+** con **Flask** (única dependencia: `pip install flask`).
- **SQLite** con el módulo `sqlite3` de Python. Sin ORM: SQL directo.
- Plantillas **Jinja2** (vienen con Flask).
- Estilos con **Bootstrap 5** (copia local en `static/vendor`, para que la demo funcione sin internet)
  y un `static/style.css` corto. JavaScript mínimo.
- Contraseñas con `werkzeug.security` (viene con Flask).

Para correrlo:

```bash
pip install -r requirements.txt
python app.py
```

Abre en http://localhost:5000. Si no existe `sige.db`, se crea sola con datos de ejemplo.
Para reiniciar la demo alcanza con borrar `sige.db`. Pruebas: `python -m unittest discover tests`.

## 2. Archivos

```
sige/
├── app.py          # arma la app: sesión, seguridad (CSRF), menú y errores
├── comun.py        # constantes, roles, alertas y consultas compartidas
├── db.py           # conexión, creación de tablas y datos de ejemplo
├── schema.sql      # tablas
├── modulos/        # un Blueprint por grupo de pantallas (general, estudiantes,
│                   #   inscripciones, aula, reportes, administracion)
├── templates/      # base.html + una plantilla por pantalla
├── static/         # style.css y Bootstrap en vendor/
├── tests/          # pruebas con unittest; cada una usa una copia de la base
└── README.md       # cómo ejecutarlo; se ve en la app en «Documentación» (solo admin)
```

Las rutas se nombran con el Blueprint: `url_for('inscripciones.nueva')`, `url_for('aula.notas_planilla')`.

## 3. Roles

| Rol | Puede |
|---|---|
| `admin` (Administración) | Estudiantes, inscripciones, cursos, materias y usuarios |
| `directivo` | Ver todo: estudiantes, trayectorias, reportes y auditoría |
| `preceptor` | Tomar asistencia de **sus** cursos y ver sus estudiantes |
| `docente` | Cargar notas de **sus** materias y ver sus estudiantes |

- Login con sesión de Flask. Decorador `@requiere_rol('admin', 'directivo')` en cada ruta.
- El menú de `base.html` muestra solo lo que corresponde al rol.
- Un docente o preceptor que entra a algo que no es suyo recibe 403 con una página amable.

## 4. Base de datos (`schema.sql`)

```sql
usuarios(id, usuario UNIQUE, clave_hash, nombre, rol)
estudiantes(id, dni UNIQUE, nombre, apellido, fecha_nac,
            responsable_nombre, responsable_telefono, activo DEFAULT 1)
cursos(id, nombre, anio_lectivo, preceptor_id, cupo DEFAULT 30)  -- nombre: "1° A"
materias(id, nombre, curso_id, docente_id)
inscripciones(id, estudiante_id, curso_id, anio_lectivo, fecha, usuario_id,
              UNIQUE(estudiante_id, anio_lectivo))
asistencias(id, estudiante_id, curso_id, fecha, estado,  -- P, A o T
            usuario_id, UNIQUE(estudiante_id, fecha))
notas(id, estudiante_id, materia_id, trimestre, nota, observacion, usuario_id,
      UNIQUE(estudiante_id, materia_id, trimestre))
auditoria(id, fecha_hora, usuario_id, accion, detalle)
```

- Activar `PRAGMA foreign_keys = ON`.
- Los estudiantes no se borran: se desactivan (`activo = 0`).
- Constantes al principio de `comun.py`: `NOTA_MIN = 1`, `NOTA_MAX = 10`,
  `NOTA_APROBACION = 6`, `LIMITE_FALTAS = 10`, `ANIO_ACTUAL = 2026`.

## 5. Funciones y pantallas

**Login e inicio.** Al entrar, cada rol ve un tablero con sus accesos rápidos.
Directivo y admin además ven contadores (estudiantes, inscriptos del año, alertas).

**Estudiantes (admin).** Lista con buscador por DNI o apellido, alta, edición y
desactivación. El DNI se guarda sin puntos ni espacios.

**Inscripción (admin). Es lo más importante de la demo:**
1. Buscar por DNI.
2. Si existe, mostrar sus datos para revisar. Si no, ofrecer el formulario de alta con el DNI ya cargado.
3. Elegir curso del año lectivo.
4. Validar: campos completos y curso del año correcto. Si hay un error, volver al formulario con el mensaje y sin perder lo cargado.
5. Si ya está inscripto ese año, avisar y mostrar la inscripción existente. No crear otra.
6. Guardar en una transacción junto con la fila de auditoría. Si falla, avisar «La inscripción no se guardó» y **no** mostrar constancia.
7. Si salió bien, mostrar la **constancia** en una página lista para imprimir (botón «Imprimir» con `window.print()`).

**Asistencia (preceptor).** Elegir curso y fecha. Aparece la lista de inscriptos con
«Presente» marcado por defecto. Se cambia a Ausente o Tarde y se guarda. Si ese día ya
tenía carga, se edita en lugar de duplicarse.

**Notas (docente).** Elegir materia y trimestre. Planilla con todos los estudiantes del
curso. Solo acepta notas entre `NOTA_MIN` y `NOTA_MAX`.

**Trayectoria (directivo, admin y, de sus cursos, docente y preceptor).** Ficha del
estudiante con su inscripción, faltas, porcentaje de asistencia y notas por materia.
Etiquetas de alerta: «Revisar asistencia» si supera `LIMITE_FALTAS` y «Revisar
rendimiento» si tiene alguna nota por debajo de `NOTA_APROBACION`. El sistema solo
señala; la decisión es de las personas.

**Reportes (directivo y admin).** Nómina por curso, resumen de asistencia por curso y
estudiantes con alerta. Cada uno con botón «Descargar CSV».

**Cursos y materias (admin).** ABM simple, con asignación de preceptor y docente.

**Usuarios (admin).** Alta de usuarios y cambio de rol.

**Documentación (solo admin).** Muestra el `README.md` dentro de la app; el resto de los
roles no la ve ni puede entrar (403).

**Auditoría (directivo).** Tabla con fecha, usuario, acción y detalle. Registrar logins,
inscripciones, cambios de estudiantes, cargas de asistencia y de notas.

## 6. Datos de ejemplo (`db.py`, primera ejecución)

Datos abundantes, porque la app es para mostrar el funcionamiento:

- Usuarios, todos con contraseña `1234`: `admin`, `directora`, `preceptor` (y `preceptor2`,
  `preceptor3`), `docente` (y `docente2` a `docente6`).
- Cursos 2025 (1° y 2°, A y B) y 2026 (1°, 2° y 3°, A y B). `preceptor` tiene 1° A y 1° B.
- Materias por curso: Matemática, Lengua, Historia, Geografía, Inglés y Biología.
  `docente` tiene Matemática de 1° A y 1° B y Lengua de 1° A.
- Unos 140 estudiantes **ficticios** con responsable, inscriptos en 2026; los de 2° y 3° también en 2025.
- Asistencia de todo 2025 y de 2026 hasta ayer; notas de 2025 y del 1.º y 2.º trimestre de 2026.
- Algunos estudiantes con muchas faltas y otros con notas bajas, para que se vean las alertas.
- 3 estudiantes cargados pero **sin inscribir**, para inscribirlos en vivo.

## 7. Estilo

Sobrio y prolijo: barra superior con «Sistema Integral de Gestión Escolar», usuario y
botón Salir; menú lateral; tablas de Bootstrap; mensajes con `flash()` (verde si salió
bien, rojo si hubo error). Tiene que verse bien en una notebook y en una tableta.

## 8. Orden de trabajo

1. `schema.sql`, `db.py` con datos de ejemplo, login, roles y `base.html`.
2. Estudiantes.
3. **Inscripción completa con constancia.**
4. Asistencia.
5. Notas.
6. Trayectoria y alertas.
7. Reportes y CSV.
8. Cursos, materias, usuarios y auditoría.
9. README.

Después de cada paso la app tiene que arrancar y funcionar.

## 9. Guion de la demo (5 minutos)

1. Entrar como `admin` e inscribir a un estudiante sin inscripción → imprimir la constancia.
2. Intentar inscribirlo de nuevo → aviso de duplicado.
3. Entrar como `preceptor` → tomar asistencia de hoy en 1° A.
4. Entrar como `docente` → cargar notas; probar un 15 y ver el error.
5. Entrar como `directora` → trayectoria de un alumno con alerta, reporte en CSV y auditoría.

## 10. Fuera de alcance

Portal de familias, integraciones externas, sueldos, contabilidad, horarios y
decisiones automáticas de promoción.
