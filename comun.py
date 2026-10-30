"""Constantes y utilidades que comparten todos los módulos del SIGE."""
import re
from datetime import date, datetime
from functools import wraps

from flask import abort, g, redirect, request, url_for

import db

NOTA_MIN = 1
NOTA_MAX = 10
NOTA_APROBACION = 6
LIMITE_FALTAS = 10
ANIO_ACTUAL = 2026

ROLES = {
    'admin': 'Administración',
    'directivo': 'Directivo',
    'preceptor': 'Preceptor',
    'docente': 'Docente',
}
ESTADOS_ASISTENCIA = {'P': 'Presente', 'A': 'Ausente', 'T': 'Tarde'}


# ---------------------------------------------------------------------------
# Utilidades generales
# ---------------------------------------------------------------------------

def ahora():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def normalizar_dni(texto):
    """'40.123.456', '40 123 456' y '40-123-456' quedan como '40123456'."""
    return re.sub(r'[\s.\-]', '', texto or '')


def dni_valido(dni):
    return re.fullmatch(r'\d{7,8}', dni) is not None


def marcas(lista):
    """Signos de pregunta para un IN (...) de SQL; con lista vacía no coincide nada."""
    return ', '.join('?' * len(lista)) or 'NULL'


def porcentaje(parte, total):
    return round(parte * 100 / total, 1) if total else None


def destino_seguro(url):
    """Solo se permite volver a rutas internas del sistema."""
    if url and url.startswith('/') and not url.startswith('//'):
        return url
    return None


def auditar(con, accion, detalle, usuario_id=None):
    """Agrega una fila de auditoría. No hace commit: va en la misma transacción que el cambio."""
    if usuario_id is None and g.get('usuario'):
        usuario_id = g.usuario['id']
    con.execute('INSERT INTO auditoria (fecha_hora, usuario_id, accion, detalle) VALUES (?, ?, ?, ?)',
                (ahora(), usuario_id, accion, detalle))


def numero_inscripcion(inscripcion_id, anio):
    return f'INS-{anio}-{inscripcion_id:06d}'


def formatear_fecha(valor):
    """'2026-03-09' → '09/03/2026'; con hora: '09/03/2026 14:05'."""
    if not valor:
        return ''
    if isinstance(valor, datetime):
        valor = valor.isoformat(sep=' ')
    elif isinstance(valor, date):
        valor = valor.isoformat()
    texto = f'{valor[8:10]}/{valor[5:7]}/{valor[:4]}'
    if len(valor) > 10:
        texto += ' ' + valor[11:16]
    return texto


def formatear_nota(valor):
    if valor is None or valor == '':
        return ''
    return f'{valor:g}'.replace('.', ',')


# ---------------------------------------------------------------------------
# Roles y alcance de cada usuario
# ---------------------------------------------------------------------------

def requiere_rol(*roles):
    """Exige sesión iniciada y, si se indican roles, que el usuario tenga uno de ellos."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if g.usuario is None:
                return redirect(url_for('general.login', next=request.full_path))
            if roles and g.usuario['rol'] not in roles:
                abort(403)
            return vista(*args, **kwargs)
        return envoltura
    return decorador


def cursos_propios():
    """Ids de los cursos del año que le tocan al usuario. None significa «todos»."""
    usuario = g.usuario
    if usuario['rol'] in ('admin', 'directivo'):
        return None
    con = db.get_db()
    if usuario['rol'] == 'preceptor':
        filas = con.execute('SELECT id FROM cursos WHERE preceptor_id = ? AND anio_lectivo = ?',
                            (usuario['id'], ANIO_ACTUAL))
    else:
        filas = con.execute('''SELECT DISTINCT c.id FROM materias m JOIN cursos c ON c.id = m.curso_id
                               WHERE m.docente_id = ? AND c.anio_lectivo = ?''',
                            (usuario['id'], ANIO_ACTUAL))
    return [fila['id'] for fila in filas]


def puede_ver_estudiante(estudiante_id):
    cursos = cursos_propios()
    if cursos is None:
        return True
    fila = db.get_db().execute(
        f'SELECT 1 FROM inscripciones WHERE estudiante_id = ? AND curso_id IN ({marcas(cursos)})',
        [estudiante_id, *cursos]).fetchone()
    return fila is not None


# ---------------------------------------------------------------------------
# Consultas que usan varias pantallas
# ---------------------------------------------------------------------------

def cursos_con_inscriptos(anio=ANIO_ACTUAL):
    return db.get_db().execute(
        '''SELECT c.*, (SELECT COUNT(*) FROM inscripciones i WHERE i.curso_id = c.id) AS inscriptos
           FROM cursos c WHERE c.anio_lectivo = ? ORDER BY c.nombre''', (anio,)).fetchall()


def curso_con_inscriptos(curso_id):
    return db.get_db().execute(
        '''SELECT c.*, (SELECT COUNT(*) FROM inscripciones i WHERE i.curso_id = c.id) AS inscriptos
           FROM cursos c WHERE c.id = ?''', (curso_id,)).fetchone()


def anios_con_cursos():
    anios = {fila[0] for fila in db.get_db().execute('SELECT DISTINCT anio_lectivo FROM cursos')}
    return sorted(anios | {ANIO_ACTUAL}, reverse=True)


def usuarios_con_rol(rol):
    return db.get_db().execute('SELECT * FROM usuarios WHERE rol = ? ORDER BY nombre', (rol,)).fetchall()


def estudiantes_sin_inscripcion():
    return db.get_db().execute(
        '''SELECT * FROM estudiantes e
           WHERE e.activo = 1 AND NOT EXISTS (
               SELECT 1 FROM inscripciones i WHERE i.estudiante_id = e.id AND i.anio_lectivo = ?)
           ORDER BY e.apellido, e.nombre''', (ANIO_ACTUAL,)).fetchall()


def materias_del_docente():
    return db.get_db().execute(
        '''SELECT m.*, c.nombre AS curso FROM materias m JOIN cursos c ON c.id = m.curso_id
           WHERE m.docente_id = ? AND c.anio_lectivo = ? ORDER BY c.nombre, m.nombre''',
        (g.usuario['id'], ANIO_ACTUAL)).fetchall()


# ---------------------------------------------------------------------------
# Alertas (el sistema solo señala; las decisiones son de las personas)
# ---------------------------------------------------------------------------

def etiquetas_alerta(faltas, notas_bajas):
    etiquetas = []
    if faltas > LIMITE_FALTAS:
        etiquetas.append('Revisar asistencia')
    if notas_bajas:
        etiquetas.append('Revisar rendimiento')
    return etiquetas


def estudiantes_con_alerta(cursos=None, curso_id=None):
    filas = db.get_db().execute(
        '''SELECT e.id, e.dni, e.apellido, e.nombre, c.id AS curso_id, c.nombre AS curso,
                  (SELECT COUNT(*) FROM asistencias a
                    WHERE a.estudiante_id = e.id AND a.curso_id = c.id AND a.estado = 'A') AS faltas,
                  (SELECT COUNT(*) FROM notas n JOIN materias m ON m.id = n.materia_id
                    WHERE n.estudiante_id = e.id AND m.curso_id = c.id AND n.nota < ?) AS notas_bajas
           FROM inscripciones i
           JOIN estudiantes e ON e.id = i.estudiante_id
           JOIN cursos c ON c.id = i.curso_id
           WHERE i.anio_lectivo = ? AND e.activo = 1
           ORDER BY c.nombre, e.apellido, e.nombre''',
        (NOTA_APROBACION, ANIO_ACTUAL)).fetchall()
    resultado = []
    for fila in filas:
        if cursos is not None and fila['curso_id'] not in cursos:
            continue
        if curso_id and fila['curso_id'] != curso_id:
            continue
        etiquetas = etiquetas_alerta(fila['faltas'], fila['notas_bajas'])
        if etiquetas:
            resultado.append({**dict(fila), 'alertas': etiquetas})
    return resultado
