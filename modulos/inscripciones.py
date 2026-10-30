"""Inscripción (lo más importante de la demo), constancia y lista de inscripciones."""
import sqlite3
from datetime import date

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

import db
from comun import (ANIO_ACTUAL, ahora, anios_con_cursos, auditar, curso_con_inscriptos, cursos_con_inscriptos,
                   dni_valido, estudiantes_sin_inscripcion, normalizar_dni, numero_inscripcion, requiere_rol)
from modulos.estudiantes import insertar_estudiante, validar_estudiante

bp = Blueprint('inscripciones', __name__, url_prefix='/inscripciones')

ERROR_AL_GUARDAR = 'La inscripción no se guardó y no se emitió constancia. Intente nuevamente o avise a soporte.'


def inscripcion_del_anio(con, dni):
    return con.execute(
        '''SELECT i.*, c.nombre AS curso FROM inscripciones i
           JOIN estudiantes e ON e.id = i.estudiante_id
           JOIN cursos c ON c.id = i.curso_id
           WHERE e.dni = ? AND i.anio_lectivo = ?''', (dni, ANIO_ACTUAL)).fetchone()


def avisar_duplicado(estudiante, inscripcion):
    flash(f'{estudiante["apellido"]}, {estudiante["nombre"]} ya está inscripto/a en {inscripcion["curso"]} '
          f'para {ANIO_ACTUAL}. No se creó otra inscripción: esta es la que ya existe.', 'warning')
    return redirect(url_for('inscripciones.ver', id=inscripcion['id']))


def formulario(estudiante, datos, errores):
    return render_template('inscripciones/form.html', estudiante=estudiante, datos=datos,
                           errores=errores, cursos=cursos_con_inscriptos())


@bp.route('/nueva')
@requiere_rol('admin')
def nueva():
    """Paso 1: buscar por DNI. Paso 2: revisar al estudiante o darlo de alta."""
    texto = request.args.get('dni', '').strip()
    sin_inscripcion = estudiantes_sin_inscripcion()
    if not texto:
        return render_template('inscripciones/buscar.html', sin_inscripcion=sin_inscripcion)
    dni = normalizar_dni(texto)
    if not dni_valido(dni):
        return render_template('inscripciones/buscar.html', sin_inscripcion=sin_inscripcion, dni=texto,
                               error='El DNI debe tener 7 u 8 números. Ejemplo: 45.123.456 o 45123456.')
    con = db.get_db()
    estudiante = con.execute('SELECT * FROM estudiantes WHERE dni = ?', (dni,)).fetchone()
    if estudiante is None:
        flash(f'No hay ningún estudiante con DNI {dni}. Complete el alta para inscribirlo.', 'info')
        return formulario(None, {'dni': dni}, {})
    if not estudiante['activo']:
        return render_template('inscripciones/buscar.html', sin_inscripcion=sin_inscripcion, dni=texto,
                               error=f'{estudiante["apellido"]}, {estudiante["nombre"]} está desactivado/a. '
                                     'Reactívelo desde Estudiantes para poder inscribirlo.')
    existente = inscripcion_del_anio(con, dni)
    if existente:
        return avisar_duplicado(estudiante, existente)
    return formulario(estudiante, dict(estudiante), {})


@bp.route('/nueva', methods=['POST'])
@requiere_rol('admin')
def guardar():
    """Pasos 3 a 7: validar, evitar duplicados, guardar en una transacción y emitir la constancia."""
    con = db.get_db()
    estudiante = None
    estudiante_id = request.form.get('estudiante_id', type=int)
    if estudiante_id:
        estudiante = con.execute('SELECT * FROM estudiantes WHERE id = ? AND activo = 1',
                                 (estudiante_id,)).fetchone()
        if estudiante is None:
            abort(404)
        datos, errores = dict(estudiante), {}
    else:
        datos, errores = validar_estudiante(request.form)
        if dni_valido(datos['dni']):
            registrado = con.execute('SELECT * FROM estudiantes WHERE dni = ?', (datos['dni'],)).fetchone()
            if registrado:
                existente = inscripcion_del_anio(con, datos['dni'])
                if existente:  # p. ej., un segundo envío del mismo formulario
                    return avisar_duplicado(registrado, existente)
                errores['dni'] = 'Ya hay un estudiante con ese DNI: vuelva a buscarlo para inscribirlo.'

    curso_id = request.form.get('curso_id', type=int)
    datos['curso_id'] = curso_id
    curso = curso_con_inscriptos(curso_id) if curso_id else None
    if curso is None:
        errores['curso_id'] = 'Elija el curso en el que se inscribe.'
    elif curso['anio_lectivo'] != ANIO_ACTUAL:
        errores['curso_id'] = (f'El curso {curso["nombre"]} es del año lectivo {curso["anio_lectivo"]}. '
                               f'Elija un curso de {ANIO_ACTUAL}.')
    elif curso['inscriptos'] >= curso['cupo']:
        errores['curso_id'] = (f'El curso {curso["nombre"]} no tiene cupo ({curso["cupo"]} lugares ocupados). '
                               'Elija otra división.')

    if errores:
        return formulario(estudiante, datos, errores)

    if estudiante:
        existente = inscripcion_del_anio(con, estudiante['dni'])
        if existente:
            return avisar_duplicado(estudiante, existente)

    try:
        if estudiante is None:
            estudiante_id = insertar_estudiante(con, datos)
        cur = con.execute(
            '''INSERT INTO inscripciones (estudiante_id, curso_id, anio_lectivo, fecha, usuario_id)
               VALUES (?, ?, ?, ?, ?)''',
            (estudiante_id, curso['id'], ANIO_ACTUAL, date.today().isoformat(), g.usuario['id']))
        inscripcion_id = cur.lastrowid
        auditar(con, 'Inscripción',
                f'{numero_inscripcion(inscripcion_id, ANIO_ACTUAL)}: {datos["apellido"]}, {datos["nombre"]} '
                f'(DNI {datos["dni"]}) en {curso["nombre"]} {ANIO_ACTUAL}')
        con.commit()
    except sqlite3.IntegrityError:
        # La restricción UNIQUE es la segunda barrera contra duplicados (doble clic, dos pestañas).
        con.rollback()
        registrado = con.execute('SELECT * FROM estudiantes WHERE dni = ?', (datos['dni'],)).fetchone()
        existente = inscripcion_del_anio(con, datos['dni'])
        if registrado and existente:
            return avisar_duplicado(registrado, existente)
        current_app.logger.exception('Inscripción rechazada por la base de datos')
        flash(ERROR_AL_GUARDAR, 'danger')
        return formulario(estudiante, datos, {})
    except sqlite3.Error:
        con.rollback()
        current_app.logger.exception('Error al guardar la inscripción')
        flash(ERROR_AL_GUARDAR, 'danger')
        return formulario(estudiante, datos, {})

    flash('Inscripción guardada. Ya puede imprimir la constancia.', 'success')
    return redirect(url_for('inscripciones.ver', id=inscripcion_id))


@bp.route('/<int:id>')
@requiere_rol('admin', 'directivo')
def ver(id):
    """Constancia de inscripción, armada siempre con los datos guardados."""
    inscripcion = db.get_db().execute(
        '''SELECT i.*, e.dni, e.apellido, e.nombre, e.fecha_nac, e.responsable_nombre,
                  e.responsable_telefono, c.nombre AS curso, u.nombre AS registrada_por
           FROM inscripciones i
           JOIN estudiantes e ON e.id = i.estudiante_id
           JOIN cursos c ON c.id = i.curso_id
           LEFT JOIN usuarios u ON u.id = i.usuario_id
           WHERE i.id = ?''', (id,)).fetchone()
    if inscripcion is None:
        abort(404)
    return render_template('inscripciones/constancia.html', i=inscripcion, emitida=ahora())


@bp.route('')
@requiere_rol('admin', 'directivo')
def lista():
    anio = request.args.get('anio', type=int) or ANIO_ACTUAL
    curso_id = request.args.get('curso_id', type=int)
    sql = '''SELECT i.*, e.dni, e.apellido, e.nombre, c.nombre AS curso, u.nombre AS registrada_por
             FROM inscripciones i
             JOIN estudiantes e ON e.id = i.estudiante_id
             JOIN cursos c ON c.id = i.curso_id
             LEFT JOIN usuarios u ON u.id = i.usuario_id
             WHERE i.anio_lectivo = ?'''
    parametros = [anio]
    if curso_id:
        sql += ' AND i.curso_id = ?'
        parametros.append(curso_id)
    sql += ' ORDER BY i.id DESC'
    inscripciones = db.get_db().execute(sql, parametros).fetchall()
    return render_template('inscripciones/lista.html', inscripciones=inscripciones,
                           cursos=cursos_con_inscriptos(anio), curso_id=curso_id, anio=anio,
                           anios=anios_con_cursos())
