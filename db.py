"""Conexión a SQLite, creación de tablas y datos de ejemplo del SIGE."""
import os
import random
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta

from flask import g
from werkzeug.security import generate_password_hash

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_DB = os.environ.get('SIGE_DB') or os.path.join(CARPETA, 'sige.db')  # las pruebas usan otra base
RUTA_ESQUEMA = os.path.join(CARPETA, 'schema.sql')


def conectar():
    conexion = sqlite3.connect(RUTA_DB)
    conexion.row_factory = sqlite3.Row
    conexion.execute('PRAGMA foreign_keys = ON')
    return conexion


def get_db():
    """Una conexión por solicitud; se cierra sola al terminar (ver cerrar_db)."""
    if 'db' not in g:
        g.db = conectar()
    return g.db


def cerrar_db(error=None):
    conexion = g.pop('db', None)
    if conexion is not None:
        conexion.close()


def inicializar(anio):
    """Si no existe sige.db, la crea con las tablas y los datos de ejemplo."""
    if os.path.exists(RUTA_DB):
        return False
    conexion = conectar()
    try:
        with open(RUTA_ESQUEMA, encoding='utf-8') as archivo:
            conexion.executescript(archivo.read())
        cargar_datos_ejemplo(conexion, anio)
        conexion.commit()
    except Exception:
        conexion.close()
        os.remove(RUTA_DB)
        raise
    conexion.close()
    return True


# ---------------------------------------------------------------------------
# Datos de ejemplo (todos ficticios)
#
# Un colegio con 1.º, 2.º y 3.er año (divisiones A y B), el año lectivo actual
# y el anterior: así la trayectoria muestra historial. Siempre se generan los
# mismos datos porque el azar usa una semilla fija.
# ---------------------------------------------------------------------------

USUARIOS_EJEMPLO = [
    # (usuario, nombre, rol) — contraseña de todos: 1234
    ('admin', 'Laura Gómez', 'admin'),
    ('directora', 'Marta Ríos', 'directivo'),
    ('preceptor', 'Diego Sosa', 'preceptor'),
    ('preceptor2', 'Lucía Paredes', 'preceptor'),
    ('preceptor3', 'Hugo Iturbe', 'preceptor'),
    ('docente', 'Carla Méndez', 'docente'),
    ('docente2', 'Jorge Villalba', 'docente'),
    ('docente3', 'Analía Correa', 'docente'),
    ('docente4', 'Pablo Rinaldi', 'docente'),
    ('docente5', 'Silvina Ferraro', 'docente'),
    ('docente6', 'Ramiro Benavídez', 'docente'),
]

DIVISIONES = ('A', 'B')
PRECEPTOR_POR_ANIO = {1: 'preceptor', 2: 'preceptor2', 3: 'preceptor3'}
MATERIAS_EJEMPLO = ['Matemática', 'Lengua', 'Historia', 'Geografía', 'Inglés', 'Biología']


def docente_de(anio_curso, division, materia):
    """Quién da cada materia. «docente» tiene Matemática de 1.º y Lengua de 1.º A."""
    if materia == 'Matemática':
        return 'docente' if anio_curso == 1 else 'docente2'
    if materia == 'Lengua':
        return 'docente' if (anio_curso, division) == (1, 'A') else 'docente3'
    if materia in ('Historia', 'Geografía'):
        return 'docente4'
    if materia == 'Inglés':
        return 'docente5'
    return 'docente6'


# Cantidad de estudiantes por curso del año actual (cupo 30)
TAMANIO_CURSOS = {'1° A': 24, '1° B': 23, '2° A': 25, '2° B': 22, '3° A': 24, '3° B': 21}

# Estudiantes con nombre fijo: los usa el guion de la demo.
ESTUDIANTES_FIJOS = [
    # (curso del año actual o None si no está inscripto, apellido, nombre, nombre del responsable)
    ('1° A', 'Acosta', 'Valentina', 'Mariana'),
    ('1° A', 'Benítez', 'Tomás', 'Jorge'),
    ('1° A', 'Castro', 'Lucía', 'Silvia'),
    ('1° A', 'Domínguez', 'Mateo', 'Raúl'),
    ('1° A', 'Escobar', 'Martina', 'Andrea'),
    ('1° B', 'Fernández', 'Joaquín', 'Claudia'),
    ('1° B', 'Giménez', 'Sofía', 'Pablo'),
    ('1° B', 'Herrera', 'Benjamín', 'Verónica'),
    ('1° B', 'Ibarra', 'Camila', 'Sergio'),
    ('1° B', 'Juárez', 'Thiago', 'Natalia'),
    ('2° A', 'Ledesma', 'Emma', 'Gustavo'),
    ('2° A', 'Medina', 'Santiago', 'Lorena'),
    ('2° A', 'Núñez', 'Mía', 'Fernando'),
    ('2° A', 'Ortiz', 'Lautaro', 'Patricia'),
    ('2° A', 'Paz', 'Isabella', 'Ricardo'),
    ('3° A', 'Quiroga', 'Bruno', 'Gabriela'),
    ('3° A', 'Romero', 'Catalina', 'Hernán'),
    ('3° A', 'Suárez', 'Felipe', 'Carolina'),
    ('3° A', 'Torres', 'Abril', 'Daniel'),
    ('3° A', 'Vera', 'Nicolás', 'Paula'),
    (None, 'Aguirre', 'Julieta', 'Mónica'),
    (None, 'Molina', 'Facundo', 'Alejandro'),
    (None, 'Navarro', 'Renata', 'Cecilia'),
]

# Casos preparados para que se vean las alertas del año actual.
FALTAS_PREPARADAS = {('Benítez', 'Tomás'): 0.13, ('Medina', 'Santiago'): 0.11}
RENDIMIENTO_BAJO = {('Domínguez', 'Mateo'): 4.8, ('Quiroga', 'Bruno'): 5.3}
NOTAS_FIJAS = {
    # (apellido, materia): nota del 1.er trimestre del año actual
    ('Domínguez', 'Matemática'): 4,
    ('Domínguez', 'Lengua'): 5,
    ('Domínguez', 'Inglés'): 5,
    ('Ortiz', 'Historia'): 5,
}

NOMBRES = [
    'Agustín', 'Alma', 'Ámbar', 'Bautista', 'Bianca', 'Candela', 'Ciro', 'Clara', 'Delfina', 'Dylan',
    'Elena', 'Emilia', 'Facundo', 'Felicitas', 'Francisco', 'Gael', 'Guadalupe', 'Ignacio', 'Isabel',
    'Joaquina', 'Juan Cruz', 'Julián', 'Justina', 'Lara', 'Lautaro', 'León', 'Lola', 'Lorenzo', 'Luana',
    'Luca', 'Malena', 'Manuel', 'Martín', 'Máximo', 'Mía', 'Milagros', 'Morena', 'Nahuel', 'Olivia',
    'Pilar', 'Ramiro', 'Rocío', 'Santino', 'Sol', 'Tiziano', 'Uma', 'Valentín', 'Victoria', 'Zoe',
    'Agustina', 'Benicio', 'Camilo', 'Josefina', 'Lisandro', 'Paloma', 'Renzo', 'Sara', 'Simón',
]
APELLIDOS = [
    'Álvarez', 'Arias', 'Barrios', 'Blanco', 'Bustos', 'Cabrera', 'Cáceres', 'Campos', 'Cardozo',
    'Carrizo', 'Cejas', 'Coronel', 'Díaz', 'Farías', 'Figueroa', 'Flores', 'Franco', 'Funes', 'Gallardo',
    'Gil', 'Godoy', 'González', 'Gutiérrez', 'Ibáñez', 'Lagos', 'Lucero', 'Luna', 'Maldonado', 'Mansilla',
    'Martínez', 'Miranda', 'Morales', 'Moreno', 'Muñoz', 'Ojeda', 'Olivera', 'Pacheco', 'Peralta',
    'Pereyra', 'Ponce', 'Quinteros', 'Ramírez', 'Reyes', 'Rivero', 'Rojas', 'Ruiz', 'Sánchez', 'Silva',
    'Sotelo', 'Toledo', 'Varela', 'Vázquez', 'Vega', 'Zalazar',
]
NOMBRES_ADULTOS = [
    'Adriana', 'Alberto', 'Analía', 'Andrés', 'Beatriz', 'Carlos', 'Cristina', 'Daniela', 'Eduardo',
    'Elena', 'Fabián', 'Florencia', 'Gabriel', 'Graciela', 'Guillermo', 'Inés', 'Javier', 'Julia',
    'Leandro', 'Liliana', 'Marcelo', 'María', 'Mariano', 'Miriam', 'Norma', 'Oscar', 'Romina', 'Rubén',
    'Sandra', 'Sebastián', 'Valeria', 'Walter',
]


def dias_de_clase(desde, hasta, anio):
    """Días hábiles desde «desde» hasta el día anterior a «hasta», sin el receso de invierno."""
    receso = (date(anio, 7, 20), date(anio, 7, 31))
    dias, dia = [], desde
    while dia < hasta:
        if dia.weekday() < 5 and not receso[0] <= dia <= receso[1]:
            dias.append(dia)
        dia += timedelta(days=1)
    return dias


def momento(dia, rnd, desde_hora, hasta_hora):
    return f'{dia.isoformat()} {rnd.randint(desde_hora, hasta_hora):02d}:{rnd.randint(0, 59):02d}:{rnd.randint(0, 59):02d}'


def nota_al_azar(rnd, nivel, minimo):
    valor = round((nivel + rnd.gauss(0, 0.7)) * 2) / 2
    return min(10, max(minimo, valor))


def cargar_datos_ejemplo(con, anio):
    rnd = random.Random(anio)  # misma semilla: siempre los mismos datos
    anterior = anio - 1
    auditoria = []  # (fecha_hora, usuario_id, accion, detalle); se inserta ordenada al final

    clave = generate_password_hash('1234')
    usuarios = {}
    for usuario, nombre, rol in USUARIOS_EJEMPLO:
        cur = con.execute('INSERT INTO usuarios (usuario, clave_hash, nombre, rol) VALUES (?, ?, ?, ?)',
                          (usuario, clave, nombre, rol))
        usuarios[usuario] = cur.lastrowid
    admin = usuarios['admin']

    # Cursos y materias: el año anterior tenía 1.º y 2.º; el actual tiene 1.º, 2.º y 3.º.
    cursos = {}
    for anio_lectivo, niveles in ((anterior, (1, 2)), (anio, (1, 2, 3))):
        for nivel in niveles:
            for division in DIVISIONES:
                nombre = f'{nivel}° {division}'
                preceptor = usuarios[PRECEPTOR_POR_ANIO[nivel]]
                cur = con.execute('INSERT INTO cursos (nombre, anio_lectivo, preceptor_id, cupo) VALUES (?, ?, ?, 30)',
                                  (nombre, anio_lectivo, preceptor))
                curso = {'id': cur.lastrowid, 'nombre': nombre, 'anio': anio_lectivo,
                         'preceptor_id': preceptor, 'materias': []}
                for materia in MATERIAS_EJEMPLO:
                    docente = usuarios[docente_de(nivel, division, materia)]
                    cur = con.execute('INSERT INTO materias (nombre, curso_id, docente_id) VALUES (?, ?, ?)',
                                      (materia, curso['id'], docente))
                    curso['materias'].append((cur.lastrowid, materia, docente))
                cursos[(anio_lectivo, nombre)] = curso

    # Estudiantes: los fijos, más los necesarios para completar cada curso, más dos que
    # dejaron la escuela el año anterior (quedan desactivados, con su historial).
    estudiantes = [{'curso': curso, 'apellido': apellido, 'nombre': nombre, 'responsable': responsable}
                   for curso, apellido, nombre, responsable in ESTUDIANTES_FIJOS]
    usados = {(e['apellido'], e['nombre']) for e in estudiantes}

    def nuevo_estudiante(**extra):
        while True:
            apellido, nombre = rnd.choice(APELLIDOS), rnd.choice(NOMBRES)
            if (apellido, nombre) not in usados:
                usados.add((apellido, nombre))
                return {'apellido': apellido, 'nombre': nombre, 'responsable': rnd.choice(NOMBRES_ADULTOS), **extra}

    cantidad = Counter(e['curso'] for e in estudiantes)
    for curso, total in TAMANIO_CURSOS.items():
        for _ in range(total - cantidad[curso]):
            estudiantes.append(nuevo_estudiante(curso=curso))
    for curso_anterior in ('1° B', '2° A'):
        estudiantes.append(nuevo_estudiante(curso=None, curso_anterior=curso_anterior, activo=0))

    inscriptos = {anterior: [], anio: []}  # año -> [(estudiante, curso)]
    dnis_usados = set()
    for e in estudiantes:
        if e['curso']:
            nivel = int(e['curso'][0])
            if nivel > 1:
                e['curso_anterior'] = f'{nivel - 1}° {e["curso"][-1]}'
        elif e.get('curso_anterior'):
            nivel = int(e['curso_anterior'][0]) + 1
        else:
            nivel = 1
        dni = None
        while dni is None or dni in dnis_usados:
            dni = f'{54 - nivel}{rnd.randint(100000, 999999)}'
        dnis_usados.add(dni)
        e['dni'] = dni
        nacimiento = date(anio - 12 - nivel, 1, 1) + timedelta(days=rnd.randint(0, 364))
        telefono = f'11 {rnd.randint(4000, 6999)}-{rnd.randint(1000, 9999)}'
        cur = con.execute(
            '''INSERT INTO estudiantes (dni, nombre, apellido, fecha_nac, responsable_nombre,
                                        responsable_telefono, activo)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (dni, e['nombre'], e['apellido'], nacimiento.isoformat(), f'{e["responsable"]} {e["apellido"]}',
             telefono, e.get('activo', 1)))
        e['id'] = cur.lastrowid
        clave_alumno = (e['apellido'], e['nombre'])
        e['nivel_notas'] = RENDIMIENTO_BAJO.get(clave_alumno, rnd.uniform(6.8, 9.2))
        e['minimo_nota'] = 1 if clave_alumno in RENDIMIENTO_BAJO else 6
        e['tardes'] = rnd.uniform(0.005, 0.035)
        e['faltas'] = {anterior: rnd.uniform(0.002, 0.02),
                       anio: FALTAS_PREPARADAS.get(clave_alumno, rnd.uniform(0.002, 0.02))}
        if e.get('curso_anterior'):
            inscriptos[anterior].append((e, cursos[(anterior, e['curso_anterior'])]))
        if e['curso']:
            inscriptos[anio].append((e, cursos[(anio, e['curso'])]))

    # Inscripciones (entre diciembre y febrero, cargadas por Administración)
    for anio_lectivo, lista in inscriptos.items():
        for e, curso in sorted(lista, key=lambda par: (par[1]['nombre'], par[0]['apellido'], par[0]['nombre'])):
            dia = date(anio_lectivo - 1, 12, 1) + timedelta(days=rnd.randint(0, 85))
            while dia.weekday() > 4:
                dia += timedelta(days=1)
            cur = con.execute(
                'INSERT INTO inscripciones (estudiante_id, curso_id, anio_lectivo, fecha, usuario_id) VALUES (?, ?, ?, ?, ?)',
                (e['id'], curso['id'], anio_lectivo, dia.isoformat(), admin))
            auditoria.append((momento(dia, rnd, 8, 12), admin, 'Inscripción',
                              f'INS-{anio_lectivo}-{cur.lastrowid:06d}: {e["apellido"]}, {e["nombre"]} '
                              f'(DNI {e["dni"]}) en {curso["nombre"]} {anio_lectivo}'))

    # Asistencia: todo el año anterior y el actual hasta ayer
    hoy = date.today()
    hasta = hoy if date(anio, 3, 25) <= hoy <= date(anio, 12, 15) else date(anio, 11, 30)
    dias = {anterior: dias_de_clase(date(anterior, 3, 3), date(anterior, 12, 6), anterior),
            anio: dias_de_clase(date(anio, 3, 2), hasta, anio)}
    filas, resumen = [], Counter()
    for anio_lectivo, lista in inscriptos.items():
        for e, curso in lista:
            for dia in dias[anio_lectivo]:
                azar = rnd.random()
                faltas = e['faltas'][anio_lectivo]
                estado = 'A' if azar < faltas else 'T' if azar < faltas + e['tardes'] else 'P'
                filas.append((e['id'], curso['id'], dia.isoformat(), estado, curso['preceptor_id']))
                if anio_lectivo == anio:
                    resumen[(curso['nombre'], dia, estado)] += 1
    con.executemany(
        'INSERT INTO asistencias (estudiante_id, curso_id, fecha, estado, usuario_id) VALUES (?, ?, ?, ?, ?)', filas)
    for dia in dias[anio][-10:]:  # la auditoría muestra las cargas de las últimas dos semanas
        for (anio_lectivo, nombre), curso in cursos.items():
            if anio_lectivo != anio:
                continue
            detalle = (f'{nombre} {dia:%d/%m/%Y}. Presentes: {resumen[(nombre, dia, "P")]} · '
                       f'Ausentes: {resumen[(nombre, dia, "A")]} · Tardes: {resumen[(nombre, dia, "T")]}')
            auditoria.append((momento(dia, rnd, 7, 8), curso['preceptor_id'], 'Carga de asistencia', detalle))

    # Notas: tres trimestres del año anterior; 1.º y 2.º del actual (el 3.º queda para cargar en la demo)
    cierre_trimestre = {1: (5, 29), 2: (8, 28), 3: (11, 27)}
    filas = []
    for anio_lectivo, trimestres in ((anterior, (1, 2, 3)), (anio, (1, 2))):
        cargadas = Counter()
        for e, curso in inscriptos[anio_lectivo]:
            for materia_id, materia, docente in curso['materias']:
                for trimestre in trimestres:
                    nota = None
                    if anio_lectivo == anio and trimestre == 1:
                        nota = NOTAS_FIJAS.get((e['apellido'], materia))
                    if nota is None:
                        nota = nota_al_azar(rnd, e['nivel_notas'], e['minimo_nota'])
                    if nota < 6:
                        observacion = 'Necesita reforzar contenidos.'
                    elif nota >= 9.5 and rnd.random() < 0.3:
                        observacion = 'Excelente desempeño.'
                    else:
                        observacion = None
                    filas.append((e['id'], materia_id, trimestre, nota, observacion, docente))
                    cargadas[(materia_id, trimestre)] += 1
        if anio_lectivo == anio:
            for (anio_c, nombre), curso in cursos.items():
                if anio_c != anio:
                    continue
                for materia_id, materia, docente in curso['materias']:
                    for trimestre in trimestres:
                        mes, dia = cierre_trimestre[trimestre]
                        auditoria.append((momento(date(anio, mes, dia), rnd, 14, 20), docente, 'Carga de notas',
                                          f'{materia} {nombre}, {trimestre}.º trimestre: '
                                          f'{cargadas[(materia_id, trimestre)]} notas'))
    con.executemany(
        '''INSERT INTO notas (estudiante_id, materia_id, trimestre, nota, observacion, usuario_id)
           VALUES (?, ?, ?, ?, ?, ?)''', filas)

    # Algunos ingresos al sistema y las bajas de los que dejaron la escuela
    for dia in dias[anio][-10:]:
        for usuario in ('preceptor', 'preceptor2', 'preceptor3'):
            auditoria.append((f'{dia.isoformat()} 07:0{rnd.randint(0, 9)}:00', usuarios[usuario],
                              'Inicio de sesión', f'{usuario} (Preceptor)'))
        auditoria.append((momento(dia, rnd, 9, 11), usuarios['directora'], 'Inicio de sesión', 'directora (Directivo)'))
    for e in estudiantes:
        if not e.get('activo', 1):
            auditoria.append((momento(date(anterior, 12, 15), rnd, 9, 12), admin, 'Desactivación de estudiante',
                              f'{e["apellido"]}, {e["nombre"]} (DNI {e["dni"]})'))

    auditoria.sort()
    auditoria.append((datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None, 'Datos de ejemplo',
                      'Se creó la base con datos de ejemplo ficticios.'))
    con.executemany('INSERT INTO auditoria (fecha_hora, usuario_id, accion, detalle) VALUES (?, ?, ?, ?)', auditoria)
