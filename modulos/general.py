"""Ingreso, salida, tablero de inicio y documentación."""
import html
import os
import re
from datetime import date

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import db
from comun import (ANIO_ACTUAL, ROLES, auditar, cursos_propios, destino_seguro, estudiantes_con_alerta,
                   estudiantes_sin_inscripcion, materias_del_docente, requiere_rol)

bp = Blueprint('general', __name__)

RUTA_README = os.path.join(db.CARPETA, 'README.md')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if g.usuario:
        return redirect(url_for('general.inicio'))
    if request.method == 'POST':
        nombre_usuario = request.form.get('usuario', '').strip().lower()
        clave = request.form.get('clave', '')
        con = db.get_db()
        usuario = con.execute('SELECT * FROM usuarios WHERE usuario = ?', (nombre_usuario,)).fetchone()
        if usuario and check_password_hash(usuario['clave_hash'], clave):
            session.clear()
            session['usuario_id'] = usuario['id']
            auditar(con, 'Inicio de sesión', f'{usuario["usuario"]} ({ROLES[usuario["rol"]]})', usuario['id'])
            con.commit()
            return redirect(destino_seguro(request.args.get('next')) or url_for('general.inicio'))
        auditar(con, 'Inicio de sesión fallido', f'Usuario ingresado: {nombre_usuario[:40]}')
        con.commit()
        flash('Usuario o contraseña incorrectos.', 'danger')
    return render_template('login.html')


@bp.route('/logout', methods=['POST'])
def logout():
    if g.usuario:
        con = db.get_db()
        auditar(con, 'Cierre de sesión', g.usuario['usuario'])
        con.commit()
    session.clear()
    flash('Sesión cerrada. ¡Hasta pronto!', 'success')
    return redirect(url_for('general.login'))


@bp.route('/')
@requiere_rol()
def inicio():
    con = db.get_db()
    usuario = g.usuario
    hoy = date.today().isoformat()
    datos = {'hoy': hoy}
    if usuario['rol'] in ('admin', 'directivo'):
        datos['total_estudiantes'] = con.execute(
            'SELECT COUNT(*) FROM estudiantes WHERE activo = 1').fetchone()[0]
        datos['inscriptos'] = con.execute(
            'SELECT COUNT(*) FROM inscripciones WHERE anio_lectivo = ?', (ANIO_ACTUAL,)).fetchone()[0]
        datos['sin_inscripcion'] = estudiantes_sin_inscripcion()
        datos['alertas'] = estudiantes_con_alerta()
    elif usuario['rol'] == 'preceptor':
        datos['cursos'] = con.execute(
            '''SELECT c.*, (SELECT COUNT(*) FROM inscripciones i WHERE i.curso_id = c.id) AS inscriptos,
                      EXISTS (SELECT 1 FROM asistencias a WHERE a.curso_id = c.id AND a.fecha = ?) AS tomada_hoy
               FROM cursos c WHERE c.preceptor_id = ? AND c.anio_lectivo = ? ORDER BY c.nombre''',
            (hoy, usuario['id'], ANIO_ACTUAL)).fetchall()
        datos['alertas'] = estudiantes_con_alerta(cursos_propios())
    else:
        datos['materias'] = materias_del_docente()
        datos['alertas'] = estudiantes_con_alerta(cursos_propios())
    return render_template('inicio.html', **datos)


@bp.route('/documentacion')
@requiere_rol('admin')
def documentacion():
    """El README del proyecto, visible solo para Administración."""
    with open(RUTA_README, encoding='utf-8') as archivo:
        contenido = markdown_a_html(archivo.read())
    return render_template('documentacion.html', contenido=contenido)


# ---------------------------------------------------------------------------
# Conversor de Markdown mínimo: alcanza para el README (títulos, párrafos, listas,
# tablas, bloques de código, negritas, código y enlaces) sin agregar dependencias.
# ---------------------------------------------------------------------------

def _en_linea(texto):
    texto = html.escape(texto, quote=False)
    texto = re.sub(r'`([^`]+)`', r'<code>\1</code>', texto)
    texto = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', texto)
    texto = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'<a href="\2">\1</a>', texto)
    texto = re.sub(r'&lt;(https?://[^&\s]+)&gt;', r'<a href="\1">\1</a>', texto)
    return texto


def _es_inicio_de_bloque(linea):
    return (linea.startswith(('#', '|', '```')) or re.match(r'[-*] ', linea) is not None
            or re.match(r'\d+\. ', linea) is not None)


def markdown_a_html(texto):
    lineas = texto.splitlines()
    partes, i = [], 0
    while i < len(lineas):
        linea = lineas[i]
        if not linea.strip():
            i += 1
        elif linea.startswith('```'):
            bloque, i = [], i + 1
            while i < len(lineas) and not lineas[i].startswith('```'):
                bloque.append(lineas[i])
                i += 1
            partes.append(f'<pre><code>{html.escape(chr(10).join(bloque))}</code></pre>')
            i += 1
        elif re.match(r'#{1,4} ', linea):
            nivel = len(linea.split(' ')[0])
            partes.append(f'<h{nivel}>{_en_linea(linea[nivel + 1:])}</h{nivel}>')
            i += 1
        elif linea.startswith('|'):
            filas = []
            while i < len(lineas) and lineas[i].startswith('|'):
                filas.append([celda.strip() for celda in lineas[i].strip().strip('|').split('|')])
                i += 1
            cabecera = ''.join(f'<th>{_en_linea(c)}</th>' for c in filas[0])
            cuerpo = ''.join('<tr>' + ''.join(f'<td>{_en_linea(c)}</td>' for c in fila) + '</tr>'
                             for fila in filas[2:])
            partes.append(f'<div class="table-responsive"><table class="table table-sm">'
                          f'<thead><tr>{cabecera}</tr></thead><tbody>{cuerpo}</tbody></table></div>')
        elif re.match(r'([-*]|\d+\.) ', linea):
            etiqueta = 'ol' if linea[0].isdigit() else 'ul'
            items = []
            while i < len(lineas) and lineas[i].strip():
                actual = lineas[i]
                marca = re.match(r'([-*]|\d+\.) ', actual)
                if marca:
                    items.append(actual[marca.end():])
                elif actual.startswith(' ') and items:
                    items[-1] += ' ' + actual.strip()
                else:
                    break
                i += 1
            partes.append(f'<{etiqueta}>' + ''.join(f'<li>{_en_linea(item)}</li>' for item in items)
                          + f'</{etiqueta}>')
        else:
            parrafo, i = [linea.strip()], i + 1
            while i < len(lineas) and lineas[i].strip() and not _es_inicio_de_bloque(lineas[i]):
                parrafo.append(lineas[i].strip())
                i += 1
            partes.append(f'<p>{_en_linea(" ".join(parrafo))}</p>')
    return '\n'.join(partes)
