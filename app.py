"""Sistema Integral de Gestión Escolar (SIGE).

Registrar una vez, consultar según el rol y conservar el historial.
Para ejecutar:  pip install -r requirements.txt  y luego  python app.py

Este archivo arma la aplicación: sesión, seguridad, menú y páginas de error.
Las pantallas están en la carpeta «modulos», un Blueprint por grupo.
"""
import os
import secrets

from flask import Flask, abort, g, render_template, request, session, url_for

import db
from comun import (ANIO_ACTUAL, ESTADOS_ASISTENCIA, LIMITE_FALTAS, NOTA_APROBACION, NOTA_MAX, NOTA_MIN, ROLES,
                   formatear_fecha, formatear_nota, numero_inscripcion)
from modulos import administracion, aula, estudiantes, general, inscripciones, reportes

# Menú lateral: (texto, endpoint, roles que lo ven, otras pantallas que lo marcan como activo)
MENU = [
    ('Inicio', 'general.inicio', None, ()),
    ('Nueva inscripción', 'inscripciones.nueva', ('admin',), ('inscripciones.guardar',)),
    ('Inscripciones', 'inscripciones.lista', ('admin', 'directivo'), ('inscripciones.ver',)),
    ('Estudiantes', 'estudiantes.lista', ('admin', 'directivo'),
     ('estudiantes.nuevo', 'estudiantes.editar', 'estudiantes.trayectoria')),
    ('Asistencia', 'aula.asistencia_seleccion', ('preceptor',), ('aula.asistencia_planilla',)),
    ('Notas', 'aula.notas_seleccion', ('docente',), ('aula.notas_planilla',)),
    ('Mis estudiantes', 'estudiantes.lista', ('preceptor', 'docente'), ('estudiantes.trayectoria',)),
    ('Reportes', 'reportes.index', ('admin', 'directivo'),
     ('reportes.nomina', 'reportes.asistencia', 'reportes.alertas')),
    ('Cursos', 'administracion.cursos_lista', ('admin',),
     ('administracion.cursos_nuevo', 'administracion.cursos_editar')),
    ('Materias', 'administracion.materias_lista', ('admin',),
     ('administracion.materias_nueva', 'administracion.materias_editar')),
    ('Usuarios', 'administracion.usuarios_lista', ('admin',),
     ('administracion.usuarios_nuevo', 'administracion.usuarios_editar')),
    ('Auditoría', 'administracion.auditoria', ('directivo',), ()),
    ('Documentación', 'general.documentacion', ('admin',), ()),
]

MENSAJES_ERROR = {
    400: ('Solicitud no válida',
          'El formulario venció o llegó incompleto. Vuelva atrás, recargue la página e intente de nuevo.'),
    403: ('Acceso no permitido',
          'Esta sección no corresponde a su rol o a sus cursos. Si cree que debería verla, consulte con Administración.'),
    404: ('No encontrado', 'La página o el registro que busca no existe.'),
    405: ('Acción no permitida', 'Esa acción no se puede hacer desde esta dirección.'),
    500: ('Ocurrió un error',
          'Algo falló en el sistema y la operación no se completó. Intente nuevamente o avise a soporte.'),
}

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SIGE_CLAVE_SECRETA', 'sige-demo-solo-para-uso-local')
app.teardown_appcontext(db.cerrar_db)
app.add_template_filter(formatear_fecha, 'fecha')
app.add_template_filter(formatear_nota, 'nota')
app.add_template_global(numero_inscripcion)
for modulo in (general, estudiantes, inscripciones, aula, reportes, administracion):
    app.register_blueprint(modulo.bp)
db.inicializar(ANIO_ACTUAL)


def token_csrf():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(16)
    return session['csrf']


@app.before_request
def cargar_usuario():
    g.usuario = None
    usuario_id = session.get('usuario_id')
    if usuario_id is not None:
        g.usuario = db.get_db().execute('SELECT * FROM usuarios WHERE id = ?', (usuario_id,)).fetchone()
    if request.method == 'POST':
        token = session.get('csrf')
        if not token or request.form.get('csrf') != token:
            abort(400)


@app.context_processor
def datos_para_plantillas():
    usuario = g.get('usuario')
    menu = []
    if usuario:
        for texto, endpoint, roles, relacionados in MENU:
            if roles is None or usuario['rol'] in roles:
                activo = request.endpoint == endpoint or request.endpoint in relacionados
                menu.append({'texto': texto, 'url': url_for(endpoint), 'activo': activo})
    return {
        'usuario': usuario, 'menu': menu, 'csrf_token': token_csrf, 'ROLES': ROLES,
        'ANIO_ACTUAL': ANIO_ACTUAL, 'NOTA_MIN': NOTA_MIN, 'NOTA_MAX': NOTA_MAX,
        'NOTA_APROBACION': NOTA_APROBACION, 'LIMITE_FALTAS': LIMITE_FALTAS,
        'ESTADOS_ASISTENCIA': ESTADOS_ASISTENCIA,
    }


def mostrar_error(error):
    codigo = getattr(error, 'code', 500) or 500
    titulo, mensaje = MENSAJES_ERROR.get(codigo, MENSAJES_ERROR[500])
    return render_template('error.html', codigo=codigo, titulo=titulo, mensaje=mensaje), codigo


for codigo in MENSAJES_ERROR:
    app.register_error_handler(codigo, mostrar_error)


if __name__ == '__main__':
    app.run(debug=os.environ.get('SIGE_DEBUG') == '1')
