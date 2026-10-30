"""Administración: cursos, materias y usuarios (admin) y auditoría (directivo)."""
import re
import sqlite3
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

import db
from comun import (ANIO_ACTUAL, ROLES, anios_con_cursos, auditar, curso_con_inscriptos, cursos_con_inscriptos,
                   requiere_rol, usuarios_con_rol)

bp = Blueprint('administracion', __name__)


# ---------------------------------------------------------------------------
# Cursos
# ---------------------------------------------------------------------------

@bp.route('/cursos')
@requiere_rol('admin')
def cursos_lista():
    anio = request.args.get('anio', type=int) or ANIO_ACTUAL
    cursos = db.get_db().execute(
        '''SELECT c.*, u.nombre AS preceptor,
                  (SELECT COUNT(*) FROM inscripciones i WHERE i.curso_id = c.id) AS inscriptos,
                  (SELECT COUNT(*) FROM materias m WHERE m.curso_id = c.id) AS materias
           FROM cursos c LEFT JOIN usuarios u ON u.id = c.preceptor_id
           WHERE c.anio_lectivo = ? ORDER BY c.nombre''', (anio,)).fetchall()
    return render_template('cursos/lista.html', cursos=cursos, anio=anio, anios=anios_con_cursos())


@bp.route('/cursos/nuevo', methods=['GET', 'POST'], endpoint='cursos_nuevo')
@bp.route('/cursos/<int:id>/editar', methods=['GET', 'POST'], endpoint='cursos_editar')
@requiere_rol('admin')
def curso_form(id=None):
    con = db.get_db()
    curso = None
    if id is not None:
        curso = curso_con_inscriptos(id)
        if curso is None:
            abort(404)
    datos = dict(curso) if curso else {'anio_lectivo': ANIO_ACTUAL, 'cupo': 30}
    errores = {}
    if request.method == 'POST':
        datos = {campo: request.form.get(campo, '').strip()
                 for campo in ('nombre', 'anio_lectivo', 'preceptor_id', 'cupo')}
        anio = cupo = None
        if not datos['nombre']:
            errores['nombre'] = 'Escriba el nombre del curso, por ejemplo «1° A».'
        elif len(datos['nombre']) > 20:
            errores['nombre'] = 'Use un nombre corto (máximo 20 caracteres).'
        try:
            anio = int(datos['anio_lectivo'])
            if not 2000 <= anio <= 2100:
                raise ValueError
        except ValueError:
            errores['anio_lectivo'] = 'Ingrese un año válido, por ejemplo 2026.'
        try:
            cupo = int(datos['cupo'])
            if not 1 <= cupo <= 60:
                raise ValueError
        except ValueError:
            errores['cupo'] = 'El cupo tiene que ser un número entre 1 y 60.'
        preceptor_id = int(datos['preceptor_id']) if datos['preceptor_id'].isdigit() else None
        if preceptor_id and preceptor_id not in [u['id'] for u in usuarios_con_rol('preceptor')]:
            errores['preceptor_id'] = 'Elija un preceptor de la lista.'
        if curso and curso['inscriptos']:
            if cupo is not None and cupo < curso['inscriptos']:
                errores['cupo'] = f'El curso ya tiene {curso["inscriptos"]} inscriptos: el cupo no puede ser menor.'
            if anio is not None and anio != curso['anio_lectivo']:
                errores['anio_lectivo'] = 'No se puede cambiar el año de un curso que ya tiene inscriptos.'
        if 'nombre' not in errores and anio:
            otro = con.execute('SELECT id FROM cursos WHERE nombre = ? AND anio_lectivo = ? AND id IS NOT ?',
                               (datos['nombre'], anio, id)).fetchone()
            if otro:
                errores['nombre'] = f'Ya existe el curso {datos["nombre"]} en {anio}.'
        if not errores:
            if curso:
                con.execute('UPDATE cursos SET nombre = ?, anio_lectivo = ?, preceptor_id = ?, cupo = ? WHERE id = ?',
                            (datos['nombre'], anio, preceptor_id, cupo, id))
                auditar(con, 'Modificación de curso', f'{datos["nombre"]} {anio}')
            else:
                con.execute('INSERT INTO cursos (nombre, anio_lectivo, preceptor_id, cupo) VALUES (?, ?, ?, ?)',
                            (datos['nombre'], anio, preceptor_id, cupo))
                auditar(con, 'Alta de curso', f'{datos["nombre"]} {anio}')
            con.commit()
            flash(f'Curso {datos["nombre"]} {anio} guardado.', 'success')
            return redirect(url_for('administracion.cursos_lista', anio=anio))
    return render_template('cursos/form.html', curso=curso, datos=datos, errores=errores,
                           preceptores=usuarios_con_rol('preceptor'))


@bp.route('/cursos/<int:id>/eliminar', methods=['POST'])
@requiere_rol('admin')
def cursos_eliminar(id):
    con = db.get_db()
    curso = con.execute('SELECT * FROM cursos WHERE id = ?', (id,)).fetchone()
    if curso is None:
        abort(404)
    try:
        con.execute('DELETE FROM materias WHERE curso_id = ?', (id,))
        con.execute('DELETE FROM cursos WHERE id = ?', (id,))
        auditar(con, 'Baja de curso', f'{curso["nombre"]} {curso["anio_lectivo"]}')
        con.commit()
        flash(f'Se eliminó el curso {curso["nombre"]} {curso["anio_lectivo"]}.', 'success')
    except sqlite3.IntegrityError:
        con.rollback()
        flash(f'No se puede eliminar {curso["nombre"]}: ya tiene inscripciones, asistencia o notas. '
              'El historial se conserva.', 'danger')
    return redirect(url_for('administracion.cursos_lista', anio=curso['anio_lectivo']))


# ---------------------------------------------------------------------------
# Materias
# ---------------------------------------------------------------------------

@bp.route('/materias')
@requiere_rol('admin')
def materias_lista():
    curso_id = request.args.get('curso_id', type=int)
    sql = '''SELECT m.*, c.nombre AS curso, c.anio_lectivo, u.nombre AS docente,
                    (SELECT COUNT(*) FROM notas n WHERE n.materia_id = m.id) AS notas
             FROM materias m JOIN cursos c ON c.id = m.curso_id
             LEFT JOIN usuarios u ON u.id = m.docente_id
             WHERE c.anio_lectivo = ?'''
    parametros = [ANIO_ACTUAL]
    if curso_id:
        sql += ' AND c.id = ?'
        parametros.append(curso_id)
    sql += ' ORDER BY c.nombre, m.nombre'
    materias = db.get_db().execute(sql, parametros).fetchall()
    return render_template('materias/lista.html', materias=materias, cursos=cursos_con_inscriptos(),
                           curso_id=curso_id)


@bp.route('/materias/nueva', methods=['GET', 'POST'], endpoint='materias_nueva')
@bp.route('/materias/<int:id>/editar', methods=['GET', 'POST'], endpoint='materias_editar')
@requiere_rol('admin')
def materia_form(id=None):
    con = db.get_db()
    materia = None
    if id is not None:
        materia = con.execute(
            '''SELECT m.*, (SELECT COUNT(*) FROM notas n WHERE n.materia_id = m.id) AS notas
               FROM materias m WHERE m.id = ?''', (id,)).fetchone()
        if materia is None:
            abort(404)
    datos = dict(materia) if materia else {'curso_id': request.args.get('curso_id', type=int)}
    errores = {}
    cursos = cursos_con_inscriptos()
    if request.method == 'POST':
        datos = {campo: request.form.get(campo, '').strip() for campo in ('nombre', 'curso_id', 'docente_id')}
        curso_id = int(datos['curso_id']) if datos['curso_id'].isdigit() else None
        docente_id = int(datos['docente_id']) if datos['docente_id'].isdigit() else None
        datos['curso_id'], datos['docente_id'] = curso_id, docente_id
        if not datos['nombre']:
            errores['nombre'] = 'Escriba el nombre de la materia.'
        elif len(datos['nombre']) > 60:
            errores['nombre'] = 'Use un nombre más corto (máximo 60 caracteres).'
        if curso_id not in [c['id'] for c in cursos] and not (materia and curso_id == materia['curso_id']):
            errores['curso_id'] = 'Elija un curso de la lista.'
        elif materia and materia['notas'] and curso_id != materia['curso_id']:
            errores['curso_id'] = 'La materia ya tiene notas cargadas: no se puede pasar a otro curso.'
        if docente_id and docente_id not in [u['id'] for u in usuarios_con_rol('docente')]:
            errores['docente_id'] = 'Elija un docente de la lista.'
        if 'nombre' not in errores and 'curso_id' not in errores:
            otra = con.execute('SELECT id FROM materias WHERE nombre = ? AND curso_id = ? AND id IS NOT ?',
                               (datos['nombre'], curso_id, id)).fetchone()
            if otra:
                errores['nombre'] = 'Ese curso ya tiene una materia con ese nombre.'
        if not errores:
            curso = con.execute('SELECT nombre FROM cursos WHERE id = ?', (curso_id,)).fetchone()
            if materia:
                con.execute('UPDATE materias SET nombre = ?, curso_id = ?, docente_id = ? WHERE id = ?',
                            (datos['nombre'], curso_id, docente_id, id))
                auditar(con, 'Modificación de materia', f'{datos["nombre"]} ({curso["nombre"]})')
            else:
                con.execute('INSERT INTO materias (nombre, curso_id, docente_id) VALUES (?, ?, ?)',
                            (datos['nombre'], curso_id, docente_id))
                auditar(con, 'Alta de materia', f'{datos["nombre"]} ({curso["nombre"]})')
            con.commit()
            flash(f'Materia {datos["nombre"]} de {curso["nombre"]} guardada.', 'success')
            return redirect(url_for('administracion.materias_lista', curso_id=curso_id))
    return render_template('materias/form.html', materia=materia, datos=datos, errores=errores,
                           cursos=cursos, docentes=usuarios_con_rol('docente'))


@bp.route('/materias/<int:id>/eliminar', methods=['POST'])
@requiere_rol('admin')
def materias_eliminar(id):
    con = db.get_db()
    materia = con.execute('SELECT m.*, c.nombre AS curso FROM materias m JOIN cursos c ON c.id = m.curso_id '
                          'WHERE m.id = ?', (id,)).fetchone()
    if materia is None:
        abort(404)
    try:
        con.execute('DELETE FROM materias WHERE id = ?', (id,))
        auditar(con, 'Baja de materia', f'{materia["nombre"]} ({materia["curso"]})')
        con.commit()
        flash(f'Se eliminó {materia["nombre"]} de {materia["curso"]}.', 'success')
    except sqlite3.IntegrityError:
        con.rollback()
        flash(f'No se puede eliminar {materia["nombre"]}: ya tiene notas cargadas. El historial se conserva.',
              'danger')
    return redirect(url_for('administracion.materias_lista', curso_id=materia['curso_id']))


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

@bp.route('/usuarios')
@requiere_rol('admin')
def usuarios_lista():
    usuarios = db.get_db().execute('SELECT * FROM usuarios ORDER BY rol, nombre').fetchall()
    return render_template('usuarios/lista.html', usuarios=usuarios)


@bp.route('/usuarios/<int:id>/rol', methods=['POST'])
@requiere_rol('admin')
def usuarios_rol(id):
    con = db.get_db()
    usuario = con.execute('SELECT * FROM usuarios WHERE id = ?', (id,)).fetchone()
    if usuario is None:
        abort(404)
    rol = request.form.get('rol')
    if rol not in ROLES:
        flash('Elija un rol de la lista.', 'danger')
    elif id == g.usuario['id'] and rol != 'admin':
        flash('No puede quitarse a sí mismo el rol de Administración.', 'danger')
    elif rol != usuario['rol']:
        con.execute('UPDATE usuarios SET rol = ? WHERE id = ?', (rol, id))
        auditar(con, 'Cambio de rol', f'{usuario["usuario"]}: {ROLES[usuario["rol"]]} → {ROLES[rol]}')
        con.commit()
        flash(f'{usuario["nombre"]} ahora tiene el rol {ROLES[rol]}.', 'success')
    return redirect(url_for('administracion.usuarios_lista'))


@bp.route('/usuarios/nuevo', methods=['GET', 'POST'], endpoint='usuarios_nuevo')
@bp.route('/usuarios/<int:id>/editar', methods=['GET', 'POST'], endpoint='usuarios_editar')
@requiere_rol('admin')
def usuario_form(id=None):
    con = db.get_db()
    usuario = None
    if id is not None:
        usuario = con.execute('SELECT * FROM usuarios WHERE id = ?', (id,)).fetchone()
        if usuario is None:
            abort(404)
    datos = dict(usuario) if usuario else {'rol': 'docente'}
    errores = {}
    if request.method == 'POST':
        datos = {campo: request.form.get(campo, '').strip() for campo in ('usuario', 'nombre', 'rol')}
        clave = request.form.get('clave', '')
        if usuario:
            datos['usuario'] = usuario['usuario']
        else:
            datos['usuario'] = datos['usuario'].lower()
            if not re.fullmatch(r'[a-z0-9._-]{3,30}', datos['usuario']):
                errores['usuario'] = 'Use de 3 a 30 letras minúsculas, números, punto o guion, sin espacios.'
            elif con.execute('SELECT 1 FROM usuarios WHERE usuario = ?', (datos['usuario'],)).fetchone():
                errores['usuario'] = 'Ese nombre de usuario ya existe.'
        if not datos['nombre']:
            errores['nombre'] = 'Escriba el nombre y apellido.'
        if datos['rol'] not in ROLES:
            errores['rol'] = 'Elija un rol.'
        elif usuario and id == g.usuario['id'] and datos['rol'] != 'admin':
            errores['rol'] = 'No puede quitarse a sí mismo el rol de Administración.'
        if (clave or not usuario) and len(clave) < 4:
            errores['clave'] = 'La contraseña tiene que tener al menos 4 caracteres.'
        if not errores:
            if usuario:
                con.execute('UPDATE usuarios SET nombre = ?, rol = ? WHERE id = ?',
                            (datos['nombre'], datos['rol'], id))
                detalle = f'{usuario["usuario"]}: {datos["nombre"]}, {ROLES[datos["rol"]]}'
                if clave:
                    con.execute('UPDATE usuarios SET clave_hash = ? WHERE id = ?', (generate_password_hash(clave), id))
                    detalle += ', contraseña nueva'
                auditar(con, 'Modificación de usuario', detalle)
            else:
                con.execute('INSERT INTO usuarios (usuario, clave_hash, nombre, rol) VALUES (?, ?, ?, ?)',
                            (datos['usuario'], generate_password_hash(clave), datos['nombre'], datos['rol']))
                auditar(con, 'Alta de usuario', f'{datos["usuario"]} ({ROLES[datos["rol"]]})')
            con.commit()
            flash(f'Usuario {datos["usuario"]} guardado.', 'success')
            return redirect(url_for('administracion.usuarios_lista'))
    # «usuario» ya es quien inició sesión (lo usa base.html); el editado va con otro nombre.
    return render_template('usuarios/form.html', usuario_editado=usuario, datos=datos, errores=errores)


# ---------------------------------------------------------------------------
# Auditoría (directivo)
# ---------------------------------------------------------------------------

@bp.route('/auditoria')
@requiere_rol('directivo')
def auditoria():
    con = db.get_db()
    filtros = {campo: request.args.get(campo, '').strip() for campo in ('usuario_id', 'accion', 'desde', 'hasta')}
    sql = '''SELECT a.*, u.usuario, u.nombre FROM auditoria a
             LEFT JOIN usuarios u ON u.id = a.usuario_id WHERE 1 = 1'''
    parametros = []
    if filtros['usuario_id'].isdigit():
        sql += ' AND a.usuario_id = ?'
        parametros.append(int(filtros['usuario_id']))
    if filtros['accion']:
        sql += ' AND a.accion = ?'
        parametros.append(filtros['accion'])
    for campo, condicion in (('desde', '>='), ('hasta', '<=')):
        try:
            parametros.append(date.fromisoformat(filtros[campo]).isoformat())
            sql += f' AND substr(a.fecha_hora, 1, 10) {condicion} ?'
        except ValueError:
            filtros[campo] = ''
    sql += ' ORDER BY a.id DESC LIMIT 300'
    registros = con.execute(sql, parametros).fetchall()
    usuarios = con.execute('SELECT id, usuario, nombre FROM usuarios ORDER BY nombre').fetchall()
    acciones = [fila[0] for fila in con.execute('SELECT DISTINCT accion FROM auditoria ORDER BY accion')]
    return render_template('auditoria.html', registros=registros, filtros=filtros,
                           usuarios=usuarios, acciones=acciones)
