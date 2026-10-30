"""Pruebas del Proyecto Sarmiento.

Ejecutar desde la carpeta del proyecto:  python -m unittest discover tests

Cada prueba trabaja sobre una copia nueva de la base con los datos de ejemplo,
así que no toca el sige.db de la demo ni depende del orden en que se ejecuten.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, timedelta

CARPETA_PRUEBAS = tempfile.mkdtemp(prefix='sige_pruebas_')
BASE_MODELO = os.path.join(CARPETA_PRUEBAS, 'modelo.db')
os.environ['SIGE_DB'] = BASE_MODELO  # antes de importar la app, para que no use sige.db
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as sige  # noqa: E402  (al importarse crea la base modelo con los datos de ejemplo)
import comun  # noqa: E402
import db  # noqa: E402
from modulos.general import markdown_a_html  # noqa: E402


def tearDownModule():
    shutil.rmtree(CARPETA_PRUEBAS, ignore_errors=True)


class PruebaSIGE(unittest.TestCase):

    def setUp(self):
        self.ruta = os.path.join(CARPETA_PRUEBAS, self.id().split('.')[-1] + '.db')
        shutil.copyfile(BASE_MODELO, self.ruta)
        db.RUTA_DB = self.ruta
        self.con = sqlite3.connect(self.ruta)
        self.con.row_factory = sqlite3.Row

    def tearDown(self):
        self.con.close()

    # --- ayudas ---

    def consultar(self, sql, *parametros):
        return self.con.execute(sql, parametros).fetchall()

    def valor(self, sql, *parametros):
        return self.consultar(sql, *parametros)[0][0]

    def curso(self, nombre, anio=2026):
        return self.valor('SELECT id FROM cursos WHERE nombre = ? AND anio_lectivo = ?', nombre, anio)

    def estudiante(self, apellido):
        return self.consultar('SELECT * FROM estudiantes WHERE apellido = ?', apellido)[0]

    @staticmethod
    def token(cliente):
        with cliente.session_transaction() as sesion:
            return sesion['csrf']

    def entrar(self, usuario):
        cliente = sige.app.test_client()
        cliente.get('/login')
        respuesta = cliente.post('/login', data={'usuario': usuario, 'clave': '1234', 'csrf': self.token(cliente)})
        self.assertEqual(respuesta.status_code, 302, f'no pudo entrar {usuario}')
        cliente.get('/')  # como en el navegador: abrir una página genera el token CSRF de la sesión nueva
        return cliente

    def enviar(self, cliente, url, datos, **opciones):
        return cliente.post(url, data={'csrf': self.token(cliente), **datos}, **opciones)

    # --- datos de ejemplo ---

    def test_datos_de_ejemplo(self):
        self.assertEqual(self.valor('SELECT COUNT(*) FROM estudiantes'), 144)
        self.assertEqual(self.valor('SELECT COUNT(*) FROM inscripciones WHERE anio_lectivo = 2026'), 139)
        self.assertEqual(self.valor('SELECT COUNT(*) FROM inscripciones WHERE anio_lectivo = 2025'), 94)
        self.assertEqual(self.valor('SELECT COUNT(*) FROM estudiantes WHERE activo = 0'), 2)
        with sige.app.test_request_context():
            alertas = comun.estudiantes_con_alerta()
        faltas = {a['apellido'] for a in alertas if a['faltas'] > comun.LIMITE_FALTAS}
        rendimiento = {a['apellido'] for a in alertas if a['notas_bajas']}
        self.assertEqual(faltas, {'Benítez', 'Medina'})
        self.assertEqual(rendimiento, {'Domínguez', 'Ortiz', 'Quiroga'})

    # --- sesión y permisos ---

    def test_login_y_csrf(self):
        anonimo = sige.app.test_client()
        self.assertEqual(anonimo.get('/').status_code, 302)
        anonimo.get('/login')
        respuesta = self.enviar(anonimo, '/login', {'usuario': 'admin', 'clave': 'mal'})
        self.assertIn('incorrectos', respuesta.get_data(as_text=True))
        self.assertEqual(anonimo.post('/login', data={'usuario': 'admin', 'clave': '1234'}).status_code, 400)

    def test_pantallas_por_rol(self):
        benitez, dominguez = self.estudiante('Benítez')['id'], self.estudiante('Domínguez')['id']
        pantallas = {
            'admin': ['/', '/estudiantes', '/estudiantes?q=53', '/estudiantes?q=Acosta&inactivos=1',
                      '/estudiantes/nuevo', f'/estudiantes/{benitez}', f'/estudiantes/{benitez}/editar',
                      '/inscripciones/nueva', '/inscripciones', '/inscripciones?anio=2025', '/inscripciones/1',
                      '/reportes', '/reportes/nomina', '/reportes/asistencia', '/reportes/asistencia?curso_id=1',
                      '/reportes/alertas', '/cursos', '/cursos?anio=2025', '/cursos/nuevo', '/cursos/1/editar',
                      '/materias', '/materias/nueva', '/materias/1/editar', '/usuarios', '/usuarios/nuevo',
                      '/usuarios/1/editar', '/documentacion'],
            'directora': ['/', '/estudiantes', f'/estudiantes/{dominguez}', '/inscripciones', '/inscripciones/1',
                          '/reportes', '/reportes/alertas', '/auditoria',
                          '/auditoria?usuario_id=1&accion=Inscripci%C3%B3n&desde=2020-01-01&hasta=2099-01-01'],
            'preceptor': ['/', '/estudiantes', f'/estudiantes/{benitez}', '/asistencia'],
            'docente': ['/', '/estudiantes', f'/estudiantes/{dominguez}', '/notas', '/notas?materia_id=1'],
        }
        for usuario, rutas in pantallas.items():
            cliente = self.entrar(usuario)
            for ruta in rutas:
                with self.subTest(usuario=usuario, ruta=ruta):
                    self.assertEqual(cliente.get(ruta).status_code, 200)

    def test_accesos_no_permitidos(self):
        alumno_3a = self.valor('SELECT estudiante_id FROM inscripciones WHERE curso_id = ?', self.curso('3° A'))
        historia_1a = self.valor("SELECT id FROM materias WHERE curso_id = ? AND nombre = 'Historia'",
                                 self.curso('1° A'))
        prohibidas = {
            'preceptor': ['/inscripciones/nueva', '/notas', '/auditoria', '/usuarios', '/reportes',
                          '/documentacion', f'/estudiantes/{alumno_3a}'],
            'docente': ['/asistencia', '/inscripciones', '/cursos', f'/notas/planilla?materia_id={historia_1a}&trimestre=1'],
            'directora': ['/usuarios', '/inscripciones/nueva', '/asistencia', '/documentacion'],
            'admin': ['/auditoria'],
        }
        for usuario, rutas in prohibidas.items():
            cliente = self.entrar(usuario)
            for ruta in rutas:
                with self.subTest(usuario=usuario, ruta=ruta):
                    respuesta = cliente.get(ruta)
                    self.assertEqual(respuesta.status_code, 403)
                    self.assertIn('Acceso no permitido', respuesta.get_data(as_text=True))
        self.assertEqual(self.entrar('admin').get('/no-existe').status_code, 404)

    def test_documentacion_solo_para_admin(self):
        texto = self.entrar('admin').get('/documentacion').get_data(as_text=True)
        self.assertIn('<h2>Guion de la demo', texto)
        self.assertIn('<table', texto)
        self.assertIn('Documentación', self.entrar('admin').get('/').get_data(as_text=True))
        self.assertNotIn('Documentación', self.entrar('directora').get('/').get_data(as_text=True))

    def test_markdown_del_readme(self):
        html = markdown_a_html('# Título\n\nTexto con **negrita** y `código`.\n\n- uno\n  sigue\n- dos\n\n'
                               '| A | B |\n|---|---|\n| 1 | 2 |\n\n```bash\npython app.py\n```\n<script>')
        self.assertIn('<h1>Título</h1>', html)
        self.assertIn('<strong>negrita</strong>', html)
        self.assertIn('<li>uno sigue</li>', html)
        self.assertIn('<td>1</td>', html)
        self.assertIn('<pre><code>python app.py</code></pre>', html)
        self.assertIn('&lt;script&gt;', html)

    # --- inscripción (pasos del documento) ---

    def test_buscar_dni(self):
        admin = self.entrar('admin')
        dni = self.estudiante('Aguirre')['dni']
        con_puntos = f'{dni[:2]}.{dni[2:5]}.{dni[5:]}'
        self.assertIn('Estudiante encontrado', admin.get(f'/inscripciones/nueva?dni={con_puntos}').get_data(as_text=True))
        texto = admin.get('/inscripciones/nueva?dni=49 876 543').get_data(as_text=True)
        self.assertIn('Estudiante nuevo', texto)
        self.assertIn('value="49876543"', texto)
        self.assertIn('7 u 8 números', admin.get('/inscripciones/nueva?dni=12').get_data(as_text=True))

    def test_inscripcion_valida_con_constancia_y_auditoria(self):
        admin = self.entrar('admin')
        aguirre = self.estudiante('Aguirre')
        respuesta = self.enviar(admin, '/inscripciones/nueva',
                                {'estudiante_id': aguirre['id'], 'curso_id': self.curso('1° A')})
        self.assertEqual(respuesta.status_code, 302)
        constancia = admin.get(respuesta.location).get_data(as_text=True)
        self.assertIn('Constancia de inscripción', constancia)
        self.assertIn('INS-2026-', constancia)
        ultima = self.valor("SELECT detalle FROM auditoria WHERE accion = 'Inscripción' ORDER BY id DESC LIMIT 1")
        self.assertIn('Aguirre', ultima)

    def test_inscripcion_duplicada_no_crea_otra(self):
        admin = self.entrar('admin')
        aguirre = self.estudiante('Aguirre')
        datos = {'estudiante_id': aguirre['id'], 'curso_id': self.curso('1° A')}
        self.enviar(admin, '/inscripciones/nueva', datos)
        texto = admin.get(f'/inscripciones/nueva?dni={aguirre["dni"]}', follow_redirects=True).get_data(as_text=True)
        self.assertIn('ya está inscripto', texto)
        texto = self.enviar(admin, '/inscripciones/nueva', datos, follow_redirects=True).get_data(as_text=True)
        self.assertIn('ya está inscripto', texto)
        self.assertEqual(self.valor('SELECT COUNT(*) FROM inscripciones WHERE estudiante_id = ?', aguirre['id']), 1)

    def test_curso_de_otro_anio_muestra_error(self):
        admin = self.entrar('admin')
        texto = self.enviar(admin, '/inscripciones/nueva', {'estudiante_id': self.estudiante('Aguirre')['id'],
                                                             'curso_id': self.curso('1° A', 2025)}).get_data(as_text=True)
        self.assertIn('es del año lectivo 2025', texto)
        self.assertIn('La inscripción todavía no se guardó', texto)
        self.assertEqual(self.valor('SELECT COUNT(*) FROM inscripciones WHERE anio_lectivo = 2026'), 139)

    def test_alta_con_errores_conserva_lo_cargado(self):
        admin = self.entrar('admin')
        texto = self.enviar(admin, '/inscripciones/nueva', {
            'dni': '49.876.543', 'apellido': '', 'nombre': 'Ana', 'fecha_nac': '2099-01-01',
            'responsable_nombre': 'Rosa Prueba', 'responsable_telefono': '11 4444-5555',
            'curso_id': self.curso('1° A')}).get_data(as_text=True)
        self.assertIn('Complete el dato', texto)
        self.assertIn('anterior a hoy', texto)
        self.assertIn('value="Ana"', texto)
        self.assertEqual(texto.count('alert-danger'), 1)  # un solo aviso arriba, no dos

    def test_doble_envio_del_alta_queda_una_sola(self):
        admin = self.entrar('admin')
        datos = {'dni': '49.876.543', 'apellido': 'Prueba', 'nombre': 'Ana', 'fecha_nac': '2013-05-04',
                 'responsable_nombre': 'Rosa Prueba', 'responsable_telefono': '11 4444-5555',
                 'curso_id': self.curso('1° A')}
        self.assertEqual(self.enviar(admin, '/inscripciones/nueva', datos).status_code, 302)
        texto = self.enviar(admin, '/inscripciones/nueva', datos, follow_redirects=True).get_data(as_text=True)
        self.assertIn('ya está inscripto', texto)
        self.assertEqual(self.valor("SELECT COUNT(*) FROM estudiantes WHERE dni = '49876543'"), 1)

    def test_falla_al_guardar_no_emite_constancia(self):
        self.con.execute("CREATE TRIGGER falla BEFORE INSERT ON inscripciones "
                         "BEGIN SELECT RAISE(ABORT, 'falla simulada'); END")
        self.con.commit()
        admin = self.entrar('admin')
        antes = self.valor('SELECT COUNT(*) FROM auditoria')
        sige.app.logger.disabled = True  # la falla es a propósito: no ensuciar la salida
        try:
            respuesta = self.enviar(admin, '/inscripciones/nueva', {'estudiante_id': self.estudiante('Molina')['id'],
                                                                    'curso_id': self.curso('1° A')})
        finally:
            sige.app.logger.disabled = False
        texto = respuesta.get_data(as_text=True)
        self.assertIn('no se guardó', texto)
        self.assertNotIn('Constancia de inscripción', texto)
        self.assertEqual(self.valor('SELECT COUNT(*) FROM auditoria'), antes)

    # --- estudiantes ---

    def test_editar_y_desactivar_estudiante(self):
        admin = self.entrar('admin')
        molina = self.estudiante('Molina')
        datos = {campo: molina[campo] for campo in ('dni', 'apellido', 'nombre', 'fecha_nac', 'responsable_nombre')}
        respuesta = self.enviar(admin, f'/estudiantes/{molina["id"]}/editar',
                                {**datos, 'responsable_telefono': '11 5555-0000'})
        self.assertEqual(respuesta.status_code, 302)
        detalle = self.valor("SELECT detalle FROM auditoria WHERE accion = 'Modificación de estudiante'")
        self.assertIn('Teléfono del responsable', detalle)
        self.enviar(admin, f'/estudiantes/{molina["id"]}/estado', {})
        self.assertEqual(self.valor('SELECT activo FROM estudiantes WHERE id = ?', molina['id']), 0)
        self.assertIn('desactivado', admin.get(f'/inscripciones/nueva?dni={molina["dni"]}').get_data(as_text=True))

    # --- asistencia ---

    def test_asistencia(self):
        preceptor = self.entrar('preceptor')
        curso_1a, hoy = self.curso('1° A'), date.today().isoformat()
        alumnos = [f[0] for f in self.consultar('SELECT estudiante_id FROM inscripciones WHERE curso_id = ?', curso_1a)]
        datos = {'curso_id': curso_1a, 'fecha': hoy, f'estado_{alumnos[0]}': 'A', f'estado_{alumnos[1]}': 'T'}
        texto = self.enviar(preceptor, '/asistencia/planilla', datos, follow_redirects=True).get_data(as_text=True)
        self.assertIn('guardada', texto)
        self.assertIn('corrigiendo', texto)
        self.enviar(preceptor, '/asistencia/planilla', {**datos, f'estado_{alumnos[0]}': 'P'})
        self.assertEqual(self.valor('SELECT COUNT(*) FROM asistencias WHERE fecha = ? AND curso_id = ?', hoy, curso_1a),
                         len(alumnos))
        self.assertEqual(self.valor('SELECT estado FROM asistencias WHERE fecha = ? AND estudiante_id = ?',
                                    hoy, alumnos[0]), 'P')
        manana = (date.today() + timedelta(days=1)).isoformat()
        texto = preceptor.get(f'/asistencia/planilla?curso_id={curso_1a}&fecha={manana}',
                              follow_redirects=True).get_data(as_text=True)
        self.assertIn('fecha futura', texto)
        self.assertEqual(preceptor.get(f'/asistencia/planilla?curso_id={self.curso("3° A")}&fecha={hoy}').status_code,
                         403)

    # --- notas ---

    def test_notas(self):
        docente = self.entrar('docente')
        curso_1a = self.curso('1° A')
        mate = self.valor("SELECT id FROM materias WHERE curso_id = ? AND nombre = 'Matemática'", curso_1a)
        alumnos = [f[0] for f in self.consultar('SELECT estudiante_id FROM inscripciones WHERE curso_id = ?', curso_1a)]
        datos = {'materia_id': mate, 'trimestre': 3, f'nota_{alumnos[0]}': '15', f'nota_{alumnos[1]}': '7,5'}
        texto = self.enviar(docente, '/notas/planilla', datos).get_data(as_text=True)
        self.assertIn('entre 1 y 10', texto)
        self.assertIn('value="15"', texto)
        self.assertIn('value="7,5"', texto)
        self.assertEqual(self.valor('SELECT COUNT(*) FROM notas WHERE materia_id = ? AND trimestre = 3', mate), 0)
        texto = self.enviar(docente, '/notas/planilla', {**datos, f'nota_{alumnos[0]}': '9'},
                            follow_redirects=True).get_data(as_text=True)
        self.assertIn('guardadas', texto)
        self.assertEqual(self.valor('SELECT nota FROM notas WHERE materia_id = ? AND trimestre = 3 AND estudiante_id = ?',
                                    mate, alumnos[1]), 7.5)

    # --- trayectoria, reportes, administración y auditoría ---

    def test_trayectoria_y_alertas(self):
        directora = self.entrar('directora')
        texto = directora.get(f'/estudiantes/{self.estudiante("Benítez")["id"]}').get_data(as_text=True)
        self.assertIn('Revisar asistencia', texto)
        texto = directora.get(f'/estudiantes/{self.estudiante("Domínguez")["id"]}').get_data(as_text=True)
        self.assertIn('Revisar rendimiento', texto)
        self.assertIn('Promedio', texto)
        texto = directora.get(f'/estudiantes/{self.estudiante("Ortiz")["id"]}?anio=2025').get_data(as_text=True)
        self.assertIn('Notas 2025', texto)
        self.assertIn('2025 · 1° A', texto)

    def test_reporte_csv(self):
        respuesta = self.entrar('directora').get(f'/reportes/nomina?curso_id={self.curso("1° A")}&formato=csv')
        self.assertEqual(respuesta.mimetype, 'text/csv')
        self.assertIn('attachment', respuesta.headers['Content-Disposition'])
        self.assertIn('Benítez', respuesta.get_data(as_text=True))
        self.assertEqual(self.valor("SELECT COUNT(*) FROM auditoria WHERE accion = 'Exportación CSV'"), 1)

    def test_administracion(self):
        admin = self.entrar('admin')
        texto = self.enviar(admin, f'/cursos/{self.curso("1° A")}/eliminar', {}, follow_redirects=True).get_data(as_text=True)
        self.assertIn('No se puede eliminar', texto)
        self.enviar(admin, '/cursos/nuevo', {'nombre': '9° Z', 'anio_lectivo': '2025', 'preceptor_id': '', 'cupo': '30'})
        texto = self.enviar(admin, f'/cursos/{self.curso("9° Z", 2025)}/eliminar', {},
                            follow_redirects=True).get_data(as_text=True)
        self.assertIn('Se eliminó', texto)
        respuesta = self.enviar(admin, '/materias/nueva', {'nombre': 'Educación Física', 'curso_id': self.curso('1° A'),
                                                           'docente_id': ''})
        self.assertEqual(respuesta.status_code, 302)
        respuesta = self.enviar(admin, '/usuarios/nuevo', {'usuario': 'Docente9', 'nombre': 'Juan Paz',
                                                           'rol': 'docente', 'clave': '1234'})
        self.assertEqual(respuesta.status_code, 302)
        nuevo = self.valor("SELECT id FROM usuarios WHERE usuario = 'docente9'")
        self.enviar(admin, f'/usuarios/{nuevo}/rol', {'rol': 'preceptor'})
        self.assertEqual(self.valor('SELECT rol FROM usuarios WHERE id = ?', nuevo), 'preceptor')
        texto = self.enviar(admin, '/usuarios/1/rol', {'rol': 'docente'}, follow_redirects=True).get_data(as_text=True)
        self.assertIn('No puede quitarse', texto)

    def test_auditoria(self):
        texto = self.entrar('directora').get('/auditoria').get_data(as_text=True)
        for accion in ('Inicio de sesión', 'Inscripción', 'Carga de asistencia', 'Carga de notas'):
            with self.subTest(accion=accion):
                self.assertIn(accion, texto)
        directora = self.entrar('directora')
        texto = self.enviar(directora, '/logout', {}, follow_redirects=True).get_data(as_text=True)
        self.assertIn('Sesión cerrada', texto)


if __name__ == '__main__':
    unittest.main()
