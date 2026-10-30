-- Tablas del Proyecto Sarmiento (Sistema Integral de Gestión Escolar)

CREATE TABLE usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario     TEXT    NOT NULL UNIQUE,
    clave_hash  TEXT    NOT NULL,
    nombre      TEXT    NOT NULL,
    rol         TEXT    NOT NULL CHECK (rol IN ('admin', 'directivo', 'preceptor', 'docente'))
);

CREATE TABLE estudiantes (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    dni                   TEXT    NOT NULL UNIQUE,
    nombre                TEXT    NOT NULL,
    apellido              TEXT    NOT NULL,
    fecha_nac             TEXT    NOT NULL,
    responsable_nombre    TEXT    NOT NULL,
    responsable_telefono  TEXT    NOT NULL,
    activo                INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_estudiantes_apellido ON estudiantes (apellido);

CREATE TABLE cursos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre        TEXT    NOT NULL,
    anio_lectivo  INTEGER NOT NULL,
    preceptor_id  INTEGER REFERENCES usuarios (id),
    cupo          INTEGER NOT NULL DEFAULT 30 CHECK (cupo > 0),
    UNIQUE (nombre, anio_lectivo)
);

CREATE TABLE materias (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT    NOT NULL,
    curso_id    INTEGER NOT NULL REFERENCES cursos (id),
    docente_id  INTEGER REFERENCES usuarios (id),
    UNIQUE (nombre, curso_id)
);

CREATE TABLE inscripciones (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    estudiante_id  INTEGER NOT NULL REFERENCES estudiantes (id),
    curso_id       INTEGER NOT NULL REFERENCES cursos (id),
    anio_lectivo   INTEGER NOT NULL,
    fecha          TEXT    NOT NULL,
    usuario_id     INTEGER REFERENCES usuarios (id),
    UNIQUE (estudiante_id, anio_lectivo)
);

CREATE TABLE asistencias (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    estudiante_id  INTEGER NOT NULL REFERENCES estudiantes (id),
    curso_id       INTEGER NOT NULL REFERENCES cursos (id),
    fecha          TEXT    NOT NULL,
    estado         TEXT    NOT NULL CHECK (estado IN ('P', 'A', 'T')),
    usuario_id     INTEGER REFERENCES usuarios (id),
    UNIQUE (estudiante_id, fecha)
);
CREATE INDEX idx_asistencias_curso_fecha ON asistencias (curso_id, fecha);

CREATE TABLE notas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    estudiante_id  INTEGER NOT NULL REFERENCES estudiantes (id),
    materia_id     INTEGER NOT NULL REFERENCES materias (id),
    trimestre      INTEGER NOT NULL CHECK (trimestre BETWEEN 1 AND 3),
    nota           REAL    NOT NULL,
    observacion    TEXT,
    usuario_id     INTEGER REFERENCES usuarios (id),
    UNIQUE (estudiante_id, materia_id, trimestre)
);

CREATE TABLE auditoria (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora  TEXT    NOT NULL,
    usuario_id  INTEGER REFERENCES usuarios (id),
    accion      TEXT    NOT NULL,
    detalle     TEXT
);
