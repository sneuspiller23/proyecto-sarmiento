"""Reportes con filtro por curso y descarga en CSV (directivo y admin)."""
import csv
import io
import re

from flask import Blueprint, Response, abort, render_template, request

import db
from comun import (ANIO_ACTUAL, LIMITE_FALTAS, NOTA_APROBACION, auditar, cursos_con_inscriptos,
                   estudiantes_con_alerta, formatear_fecha, porcentaje, requiere_rol)

bp = Blueprint('reportes', __name__, url_prefix='/reportes')


def respuesta_csv(nombre_archivo, encabezados, filas):
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=';')  # punto y coma: Excel en español lo abre directo
    escritor.writerow(encabezados)
    escritor.writerows(filas)
    con = db.get_db()
    auditar(con, 'Exportación CSV', nombre_archivo)
    con.commit()
    return Response('﻿' + salida.getvalue(), content_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{nombre_archivo}"'})


def nombre_para_archivo(texto):
    return re.sub(r'[^A-Za-z0-9]+', '_', texto).strip('_')


def texto_porcentaje(valor):
    return '' if valor is None else f'{valor:g} %'.replace('.', ',')


def mostrar_reporte(titulo, descripcion, archivo, encabezados, filas, endpoint, ids=None, curso_id=None,
                    permite_todos=False):
    if request.args.get('formato') == 'csv':
        return respuesta_csv(archivo, encabezados, filas)
    return render_template('reportes/tabla.html', titulo=titulo, descripcion=descripcion,
                           encabezados=encabezados, filas=filas, ids=ids, cursos=cursos_con_inscriptos(),
                           curso_id=curso_id, permite_todos=permite_todos, endpoint=endpoint)


@bp.route('')
@requiere_rol('admin', 'directivo')
def index():
    return render_template('reportes/index.html')


@bp.route('/nomina')
@requiere_rol('admin', 'directivo')
def nomina():
    cursos = cursos_con_inscriptos()
    curso_id = request.args.get('curso_id', type=int) or (cursos[0]['id'] if cursos else None)
    curso = next((c for c in cursos if c['id'] == curso_id), None)
    if curso is None:
        abort(404)
    estudiantes = db.get_db().execute(
        '''SELECT e.* FROM inscripciones i JOIN estudiantes e ON e.id = i.estudiante_id
           WHERE i.curso_id = ? AND e.activo = 1 ORDER BY e.apellido, e.nombre''', (curso_id,)).fetchall()
    filas = [[n, e['apellido'], e['nombre'], e['dni'], formatear_fecha(e['fecha_nac']),
              e['responsable_nombre'], e['responsable_telefono']] for n, e in enumerate(estudiantes, 1)]
    return mostrar_reporte(
        f'Nómina de {curso["nombre"]} — {ANIO_ACTUAL}', f'{len(filas)} estudiantes inscriptos.',
        f'nomina_{nombre_para_archivo(curso["nombre"])}_{ANIO_ACTUAL}.csv',
        ['N.º', 'Apellido', 'Nombre', 'DNI', 'Fecha de nacimiento', 'Responsable', 'Teléfono'],
        filas, 'reportes.nomina', ids=[e['id'] for e in estudiantes], curso_id=curso_id)


@bp.route('/asistencia')
@requiere_rol('admin', 'directivo')
def asistencia():
    con = db.get_db()
    curso_id = request.args.get('curso_id', type=int)
    if not curso_id:
        resumen = con.execute(
            '''SELECT c.nombre,
                      (SELECT COUNT(*) FROM inscripciones i WHERE i.curso_id = c.id) AS inscriptos,
                      COUNT(DISTINCT a.fecha) AS dias, COUNT(a.id) AS registros,
                      COALESCE(SUM(a.estado = 'P'), 0) AS presentes,
                      COALESCE(SUM(a.estado = 'A'), 0) AS ausentes,
                      COALESCE(SUM(a.estado = 'T'), 0) AS tardes
               FROM cursos c LEFT JOIN asistencias a ON a.curso_id = c.id
               WHERE c.anio_lectivo = ? GROUP BY c.id ORDER BY c.nombre''', (ANIO_ACTUAL,)).fetchall()
        filas = [[r['nombre'], r['inscriptos'], r['dias'], r['presentes'], r['ausentes'], r['tardes'],
                  texto_porcentaje(porcentaje(r['presentes'] + r['tardes'], r['registros']))] for r in resumen]
        return mostrar_reporte(
            f'Resumen de asistencia por curso — {ANIO_ACTUAL}',
            'El porcentaje cuenta las llegadas tarde como asistencia. Elija un curso para ver el detalle.',
            f'asistencia_por_curso_{ANIO_ACTUAL}.csv',
            ['Curso', 'Inscriptos', 'Días con registro', 'Presentes', 'Ausentes', 'Tardes', '% asistencia'],
            filas, 'reportes.asistencia', permite_todos=True)

    curso = con.execute('SELECT * FROM cursos WHERE id = ?', (curso_id,)).fetchone()
    if curso is None:
        abort(404)
    detalle = con.execute(
        '''SELECT e.id, e.apellido, e.nombre, e.dni, COUNT(a.id) AS registros,
                  COALESCE(SUM(a.estado = 'P'), 0) AS presentes,
                  COALESCE(SUM(a.estado = 'A'), 0) AS ausentes,
                  COALESCE(SUM(a.estado = 'T'), 0) AS tardes
           FROM inscripciones i
           JOIN estudiantes e ON e.id = i.estudiante_id
           LEFT JOIN asistencias a ON a.estudiante_id = e.id AND a.curso_id = i.curso_id
           WHERE i.curso_id = ? AND e.activo = 1
           GROUP BY e.id ORDER BY e.apellido, e.nombre''', (curso_id,)).fetchall()
    filas = [[d['apellido'], d['nombre'], d['dni'], d['registros'], d['presentes'], d['ausentes'], d['tardes'],
              texto_porcentaje(porcentaje(d['presentes'] + d['tardes'], d['registros'])),
              'Revisar asistencia' if d['ausentes'] > LIMITE_FALTAS else ''] for d in detalle]
    return mostrar_reporte(
        f'Asistencia de {curso["nombre"]} — {ANIO_ACTUAL}',
        f'Se marca «Revisar asistencia» cuando las faltas superan {LIMITE_FALTAS}.',
        f'asistencia_{nombre_para_archivo(curso["nombre"])}_{ANIO_ACTUAL}.csv',
        ['Apellido', 'Nombre', 'DNI', 'Días registrados', 'Presentes', 'Ausentes', 'Tardes', '% asistencia',
         'Alerta'],
        filas, 'reportes.asistencia', ids=[d['id'] for d in detalle], curso_id=curso_id, permite_todos=True)


@bp.route('/alertas')
@requiere_rol('admin', 'directivo')
def alertas():
    curso_id = request.args.get('curso_id', type=int)
    con_alerta = estudiantes_con_alerta(curso_id=curso_id)
    filas = [[a['curso'], a['apellido'], a['nombre'], a['dni'], a['faltas'], a['notas_bajas'],
              ' · '.join(a['alertas'])] for a in con_alerta]
    return mostrar_reporte(
        f'Estudiantes con alerta — {ANIO_ACTUAL}',
        f'Faltas por encima de {LIMITE_FALTAS} o notas por debajo de {NOTA_APROBACION}. '
        'El sistema solo señala: las decisiones las toma el equipo escolar.',
        f'estudiantes_con_alerta_{ANIO_ACTUAL}.csv',
        ['Curso', 'Apellido', 'Nombre', 'DNI', 'Faltas', 'Notas bajas', 'Alertas'],
        filas, 'reportes.alertas', ids=[a['id'] for a in con_alerta], curso_id=curso_id, permite_todos=True)
