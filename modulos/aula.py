"""Lo que se carga en el aula: asistencia (preceptor) y notas (docente)."""
import sqlite3
from datetime import date

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

import db
from comun import (ANIO_ACTUAL, ESTADOS_ASISTENCIA, NOTA_MAX, NOTA_MIN, auditar, formatear_nota,
                   materias_del_docente, requiere_rol)

bp = Blueprint('aula', __name__)


# ---------------------------------------------------------------------------
# Asistencia (preceptor)
# ---------------------------------------------------------------------------

def curso_del_preceptor(curso_id):
    curso = db.get_db().execute('SELECT * FROM cursos WHERE id = ?', (curso_id,)).fetchone()
    if curso is None:
        abort(404)
    if curso['preceptor_id'] != g.usuario['id']:
        abort(403)
    return curso


@bp.route('/asistencia')
@requiere_rol('preceptor')
def asistencia_seleccion():
    cursos = db.get_db().execute(
        'SELECT * FROM cursos WHERE preceptor_id = ? AND anio_lectivo = ? ORDER BY nombre',
        (g.usuario['id'], ANIO_ACTUAL)).fetchall()
    return render_template('asistencia/seleccion.html', cursos=cursos, hoy=date.today().isoformat())


@bp.route('/asistencia/planilla', methods=['GET', 'POST'])
@requiere_rol('preceptor')
def asistencia_planilla():
    origen = request.form if request.method == 'POST' else request.args
    curso = curso_del_preceptor(origen.get('curso_id', type=int))
    try:
        fecha = date.fromisoformat(origen.get('fecha', ''))
    except ValueError:
        flash('Elija una fecha válida.', 'danger')
        return redirect(url_for('aula.asistencia_seleccion'))
    if fecha > date.today():
        flash('No se puede tomar asistencia de una fecha futura.', 'danger')
        return redirect(url_for('aula.asistencia_seleccion'))
    if fecha.year != curso['anio_lectivo']:
        flash(f'La fecha tiene que ser del año lectivo {curso["anio_lectivo"]}.', 'danger')
        return redirect(url_for('aula.asistencia_seleccion'))

    con = db.get_db()
    estudiantes = con.execute(
        '''SELECT e.id, e.dni, e.apellido, e.nombre, a.estado
           FROM inscripciones i
           JOIN estudiantes e ON e.id = i.estudiante_id
           LEFT JOIN asistencias a ON a.estudiante_id = e.id AND a.fecha = ?
           WHERE i.curso_id = ? AND e.activo = 1
           ORDER BY e.apellido, e.nombre''', (fecha.isoformat(), curso['id'])).fetchall()
    edicion = any(e['estado'] for e in estudiantes)

    if request.method == 'POST':
        conteo = {'P': 0, 'A': 0, 'T': 0}
        try:
            for estudiante in estudiantes:
                estado = request.form.get(f'estado_{estudiante["id"]}', 'P')
                if estado not in ESTADOS_ASISTENCIA:
                    estado = 'P'
                conteo[estado] += 1
                con.execute(
                    '''INSERT INTO asistencias (estudiante_id, curso_id, fecha, estado, usuario_id)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT (estudiante_id, fecha) DO UPDATE SET
                           estado = excluded.estado, curso_id = excluded.curso_id,
                           usuario_id = excluded.usuario_id''',
                    (estudiante['id'], curso['id'], fecha.isoformat(), estado, g.usuario['id']))
            resumen = f'Presentes: {conteo["P"]} · Ausentes: {conteo["A"]} · Tardes: {conteo["T"]}'
            auditar(con, 'Corrección de asistencia' if edicion else 'Carga de asistencia',
                    f'{curso["nombre"]} {fecha:%d/%m/%Y}. {resumen}')
            con.commit()
        except sqlite3.Error:
            con.rollback()
            current_app.logger.exception('Error al guardar la asistencia')
            flash('La asistencia no se guardó. Intente nuevamente.', 'danger')
        else:
            flash(f'Asistencia de {curso["nombre"]} del {fecha:%d/%m/%Y} guardada. {resumen}.', 'success')
        return redirect(url_for('aula.asistencia_planilla', curso_id=curso['id'], fecha=fecha.isoformat()))

    return render_template('asistencia/planilla.html', curso=curso, fecha=fecha,
                           estudiantes=estudiantes, edicion=edicion)


# ---------------------------------------------------------------------------
# Notas (docente)
# ---------------------------------------------------------------------------

def materia_del_docente(materia_id):
    materia = db.get_db().execute(
        '''SELECT m.*, c.nombre AS curso, c.anio_lectivo FROM materias m
           JOIN cursos c ON c.id = m.curso_id WHERE m.id = ?''', (materia_id,)).fetchone()
    if materia is None:
        abort(404)
    if materia['docente_id'] != g.usuario['id']:
        abort(403)
    return materia


@bp.route('/notas')
@requiere_rol('docente')
def notas_seleccion():
    return render_template('notas/seleccion.html', materias=materias_del_docente(),
                           elegida=request.args.get('materia_id', type=int))


@bp.route('/notas/planilla', methods=['GET', 'POST'])
@requiere_rol('docente')
def notas_planilla():
    origen = request.form if request.method == 'POST' else request.args
    materia = materia_del_docente(origen.get('materia_id', type=int))
    trimestre = origen.get('trimestre', type=int)
    if trimestre not in (1, 2, 3):
        flash('Elija un trimestre (1, 2 o 3).', 'danger')
        return redirect(url_for('aula.notas_seleccion'))

    con = db.get_db()
    estudiantes = con.execute(
        '''SELECT e.id, e.dni, e.apellido, e.nombre, n.nota, n.observacion
           FROM inscripciones i
           JOIN estudiantes e ON e.id = i.estudiante_id
           LEFT JOIN notas n ON n.estudiante_id = e.id AND n.materia_id = ? AND n.trimestre = ?
           WHERE i.curso_id = ? AND e.activo = 1
           ORDER BY e.apellido, e.nombre''', (materia['id'], trimestre, materia['curso_id'])).fetchall()
    valores = {e['id']: {'nota': formatear_nota(e['nota']), 'observacion': e['observacion'] or ''}
               for e in estudiantes}
    errores = {}

    if request.method == 'POST':
        cargas = []
        for estudiante in estudiantes:
            texto = request.form.get(f'nota_{estudiante["id"]}', '').strip()
            observacion = request.form.get(f'obs_{estudiante["id"]}', '').strip()[:200]
            valores[estudiante['id']] = {'nota': texto, 'observacion': observacion}
            if not texto:
                cargas.append((estudiante['id'], None, observacion))
                continue
            try:
                nota = float(texto.replace(',', '.'))
            except ValueError:
                errores[estudiante['id']] = 'Escriba un número, por ejemplo 7 o 7,5.'
                continue
            if not NOTA_MIN <= nota <= NOTA_MAX:
                errores[estudiante['id']] = f'La nota tiene que estar entre {NOTA_MIN} y {NOTA_MAX}.'
                continue
            cargas.append((estudiante['id'], nota, observacion))

        if not errores:  # con algún error no se guarda ninguna (la planilla lo explica arriba)
            try:
                for estudiante_id, nota, observacion in cargas:
                    if nota is None:
                        con.execute('DELETE FROM notas WHERE estudiante_id = ? AND materia_id = ? AND trimestre = ?',
                                    (estudiante_id, materia['id'], trimestre))
                    else:
                        con.execute(
                            '''INSERT INTO notas (estudiante_id, materia_id, trimestre, nota, observacion, usuario_id)
                               VALUES (?, ?, ?, ?, ?, ?)
                               ON CONFLICT (estudiante_id, materia_id, trimestre) DO UPDATE SET
                                   nota = excluded.nota, observacion = excluded.observacion,
                                   usuario_id = excluded.usuario_id''',
                            (estudiante_id, materia['id'], trimestre, nota, observacion or None, g.usuario['id']))
                cargadas = sum(1 for carga in cargas if carga[1] is not None)
                auditar(con, 'Carga de notas',
                        f'{materia["nombre"]} {materia["curso"]}, {trimestre}.º trimestre: {cargadas} notas')
                con.commit()
            except sqlite3.Error:
                con.rollback()
                current_app.logger.exception('Error al guardar las notas')
                flash('Las notas no se guardaron. Intente nuevamente.', 'danger')
            else:
                flash(f'Notas de {materia["nombre"]} ({materia["curso"]}, {trimestre}.º trimestre) guardadas.',
                      'success')
                return redirect(url_for('aula.notas_planilla', materia_id=materia['id'], trimestre=trimestre))

    return render_template('notas/planilla.html', materia=materia, trimestre=trimestre,
                           estudiantes=estudiantes, valores=valores, errores=errores)
