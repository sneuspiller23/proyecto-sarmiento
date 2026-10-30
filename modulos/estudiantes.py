"""Estudiantes: lista, alta, edición, desactivación y trayectoria."""
import re
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

import db
from comun import (ANIO_ACTUAL, NOTA_APROBACION, auditar, cursos_propios, destino_seguro, dni_valido,
                   etiquetas_alerta, marcas, normalizar_dni, porcentaje, puede_ver_estudiante, requiere_rol)

bp = Blueprint('estudiantes', __name__, url_prefix='/estudiantes')

CAMPOS_ESTUDIANTE = {
    'dni': 'DNI',
    'apellido': 'Apellido',
    'nombre': 'Nombre',
    'fecha_nac': 'Fecha de nacimiento',
    'responsable_nombre': 'Responsable',
    'responsable_telefono': 'Teléfono del responsable',
}


def validar_estudiante(form, estudiante_id=None):
    datos = {campo: (form.get(campo) or '').strip() for campo in CAMPOS_ESTUDIANTE}
    datos['dni'] = normalizar_dni(datos['dni'])
    errores = {}
    for campo, etiqueta in CAMPOS_ESTUDIANTE.items():
        if not datos[campo]:
            errores[campo] = f'Complete el dato «{etiqueta}».'
        elif len(datos[campo]) > 80:
            errores[campo] = 'El texto es demasiado largo (máximo 80 caracteres).'
    if 'dni' not in errores:
        if not dni_valido(datos['dni']):
            errores['dni'] = 'El DNI debe tener 7 u 8 números. Puede escribirlo con puntos: 45.123.456.'
        else:
            otro = db.get_db().execute('SELECT id FROM estudiantes WHERE dni = ? AND id IS NOT ?',
                                       (datos['dni'], estudiante_id)).fetchone()
            if otro:
                errores['dni'] = 'Ya hay un estudiante registrado con ese DNI.'
    if 'fecha_nac' not in errores:
        try:
            nacimiento = date.fromisoformat(datos['fecha_nac'])
            if nacimiento >= date.today():
                errores['fecha_nac'] = 'La fecha de nacimiento tiene que ser anterior a hoy.'
            elif nacimiento.year < 1950:
                errores['fecha_nac'] = 'Revise el año de nacimiento.'
        except ValueError:
            errores['fecha_nac'] = 'Ingrese una fecha válida.'
    if 'responsable_telefono' not in errores and not re.fullmatch(r'[\d\s()+\-]{6,25}', datos['responsable_telefono']):
        errores['responsable_telefono'] = 'Use solo números, espacios y guiones. Ejemplo: 11 4567-8901.'
    return datos, errores


def insertar_estudiante(con, datos):
    """Da de alta al estudiante y deja la fila de auditoría. No hace commit."""
    cur = con.execute(
        '''INSERT INTO estudiantes (dni, nombre, apellido, fecha_nac, responsable_nombre, responsable_telefono)
           VALUES (:dni, :nombre, :apellido, :fecha_nac, :responsable_nombre, :responsable_telefono)''', datos)
    auditar(con, 'Alta de estudiante', f'{datos["apellido"]}, {datos["nombre"]} (DNI {datos["dni"]})')
    return cur.lastrowid


def buscar_estudiante(con, estudiante_id):
    estudiante = con.execute('SELECT * FROM estudiantes WHERE id = ?', (estudiante_id,)).fetchone()
    if estudiante is None:
        abort(404)
    return estudiante


@bp.route('')
@requiere_rol('admin', 'directivo', 'preceptor', 'docente')
def lista():
    busqueda = request.args.get('q', '').strip()
    ver_inactivos = request.args.get('inactivos') == '1' and g.usuario['rol'] == 'admin'
    sql = '''SELECT e.*, c.nombre AS curso FROM estudiantes e
             LEFT JOIN inscripciones i ON i.estudiante_id = e.id AND i.anio_lectivo = ?
             LEFT JOIN cursos c ON c.id = i.curso_id
             WHERE 1 = 1'''
    parametros = [ANIO_ACTUAL]
    if not ver_inactivos:
        sql += ' AND e.activo = 1'
    if busqueda:
        dni = normalizar_dni(busqueda)
        if dni.isdigit():
            sql += ' AND e.dni LIKE ?'
            parametros.append(dni + '%')
        else:
            sql += ' AND (e.apellido LIKE ? OR e.nombre LIKE ?)'
            parametros += [f'%{busqueda}%', f'%{busqueda}%']
    cursos = cursos_propios()
    if cursos is not None:
        sql += f' AND i.curso_id IN ({marcas(cursos)})'
        parametros += cursos
    sql += ' ORDER BY e.apellido, e.nombre'
    estudiantes = db.get_db().execute(sql, parametros).fetchall()
    return render_template('estudiantes/lista.html', estudiantes=estudiantes,
                           busqueda=busqueda, ver_inactivos=ver_inactivos)


@bp.route('/nuevo', methods=['GET', 'POST'])
@requiere_rol('admin')
def nuevo():
    datos, errores = {'dni': normalizar_dni(request.args.get('dni', ''))}, {}
    if request.method == 'POST':
        datos, errores = validar_estudiante(request.form)
        if not errores:
            con = db.get_db()
            estudiante_id = insertar_estudiante(con, datos)
            con.commit()
            flash(f'Se registró a {datos["apellido"]}, {datos["nombre"]}.', 'success')
            return redirect(url_for('estudiantes.trayectoria', id=estudiante_id))
    return render_template('estudiantes/form.html', datos=datos, errores=errores, estudiante=None)


@bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@requiere_rol('admin')
def editar(id):
    con = db.get_db()
    estudiante = buscar_estudiante(con, id)
    volver = destino_seguro(request.args.get('volver'))
    datos, errores = dict(estudiante), {}
    if request.method == 'POST':
        datos, errores = validar_estudiante(request.form, id)
        if not errores:
            cambios = [etiqueta for campo, etiqueta in CAMPOS_ESTUDIANTE.items()
                       if str(estudiante[campo]) != datos[campo]]
            if cambios:
                con.execute(
                    '''UPDATE estudiantes SET dni = :dni, nombre = :nombre, apellido = :apellido,
                              fecha_nac = :fecha_nac, responsable_nombre = :responsable_nombre,
                              responsable_telefono = :responsable_telefono
                       WHERE id = :id''', {**datos, 'id': id})
                auditar(con, 'Modificación de estudiante',
                        f'{datos["apellido"]}, {datos["nombre"]} (DNI {datos["dni"]}): {", ".join(cambios)}')
                con.commit()
                flash('Datos del estudiante actualizados.', 'success')
            else:
                flash('No había cambios para guardar.', 'info')
            return redirect(volver or url_for('estudiantes.trayectoria', id=id))
    return render_template('estudiantes/form.html', datos=datos, errores=errores,
                           estudiante=estudiante, volver=volver)


@bp.route('/<int:id>/estado', methods=['POST'])
@requiere_rol('admin')
def estado(id):
    con = db.get_db()
    estudiante = buscar_estudiante(con, id)
    nuevo_estado = 0 if estudiante['activo'] else 1
    con.execute('UPDATE estudiantes SET activo = ? WHERE id = ?', (nuevo_estado, id))
    accion = 'Reactivación de estudiante' if nuevo_estado else 'Desactivación de estudiante'
    auditar(con, accion, f'{estudiante["apellido"]}, {estudiante["nombre"]} (DNI {estudiante["dni"]})')
    con.commit()
    flash(f'{estudiante["apellido"]}, {estudiante["nombre"]} quedó {"activo" if nuevo_estado else "desactivado"}.',
          'success')
    return redirect(url_for('estudiantes.lista', inactivos='1'))


@bp.route('/<int:id>')
@requiere_rol('admin', 'directivo', 'preceptor', 'docente')
def trayectoria(id):
    con = db.get_db()
    estudiante = buscar_estudiante(con, id)
    if not puede_ver_estudiante(id):
        abort(403)
    inscripciones = con.execute(
        '''SELECT i.*, c.nombre AS curso, u.nombre AS registrada_por
           FROM inscripciones i JOIN cursos c ON c.id = i.curso_id
           LEFT JOIN usuarios u ON u.id = i.usuario_id
           WHERE i.estudiante_id = ? ORDER BY i.anio_lectivo DESC''', (id,)).fetchall()
    anio = request.args.get('anio', type=int) or ANIO_ACTUAL
    inscripcion = next((i for i in inscripciones if i['anio_lectivo'] == anio), None)

    asistencia, faltas_recientes, materias, notas_bajas = None, [], [], 0
    if inscripcion:
        conteo = {'P': 0, 'A': 0, 'T': 0}
        for fila in con.execute('''SELECT estado, COUNT(*) AS cantidad FROM asistencias
                                   WHERE estudiante_id = ? AND curso_id = ? GROUP BY estado''',
                                (id, inscripcion['curso_id'])):
            conteo[fila['estado']] = fila['cantidad']
        total = sum(conteo.values())
        asistencia = {'total': total, 'presentes': conteo['P'], 'ausentes': conteo['A'],
                      'tardes': conteo['T'], 'porcentaje': porcentaje(conteo['P'] + conteo['T'], total)}
        faltas_recientes = con.execute(
            '''SELECT fecha FROM asistencias WHERE estudiante_id = ? AND curso_id = ? AND estado = 'A'
               ORDER BY fecha DESC LIMIT 12''', (id, inscripcion['curso_id'])).fetchall()

        por_materia = {}
        for fila in con.execute(
                '''SELECT m.id, m.nombre, u.nombre AS docente, n.trimestre, n.nota, n.observacion
                   FROM materias m
                   LEFT JOIN usuarios u ON u.id = m.docente_id
                   LEFT JOIN notas n ON n.materia_id = m.id AND n.estudiante_id = ?
                   WHERE m.curso_id = ? ORDER BY m.nombre, n.trimestre''', (id, inscripcion['curso_id'])):
            materia = por_materia.setdefault(fila['id'], {'nombre': fila['nombre'], 'docente': fila['docente'],
                                                          'notas': {}, 'observaciones': []})
            if fila['nota'] is not None:
                materia['notas'][fila['trimestre']] = fila['nota']
                if fila['nota'] < NOTA_APROBACION:
                    notas_bajas += 1
                if fila['observacion']:
                    materia['observaciones'].append(f'{fila["trimestre"]}.º: {fila["observacion"]}')
        materias = list(por_materia.values())

    alertas = etiquetas_alerta(asistencia['ausentes'] if asistencia else 0, notas_bajas)
    return render_template('estudiantes/trayectoria.html', estudiante=estudiante, inscripciones=inscripciones,
                           anio=anio, inscripcion=inscripcion, asistencia=asistencia,
                           faltas_recientes=faltas_recientes, materias=materias, alertas=alertas)
