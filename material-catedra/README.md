# Material de cátedra

Programas, planificaciones, casos, prácticos, apuntes y datos que aportan las cátedras para diseñar
y calibrar los juegos.

> **Este material no se sube a GitHub.** El repositorio es público y los apuntes, casos y prácticos
> son de sus docentes. Todo lo que está en esta carpeta, salvo este README, está excluido de git
> (`.gitignore`) y de la imagen Docker (`.dockerignore`): queda solo en esta computadora. Para
> respaldarlo o compartirlo, usar un repositorio privado aparte o una carpeta compartida de la
> Facultad.

## Organización

Una carpeta por carrera y otra por materia, con el código del plan 2020 y un nombre corto:

```
material-catedra/
├── README.md                    este archivo (el único que va a git)
├── INDICE.md                    qué hay, de dónde salió y si se puede publicar
├── carreras/                    planes, correlatividades, acreditaciones
│   ├── contador-publico/
│   └── lic-administracion/
└── materias/
    ├── 3.3-costos-para-la-gestion/      (CP 3.3 / LA 3.2)
    ├── 4.1-estados-contables-y-su-analisis/
    ├── 4.6-impuestos-i/                 (CP)
    ├── 4.7-administracion-de-operaciones/  (LA)
    ├── 5.2-control-interno-y-auditoria/ (CP)
    └── 5.7-taller-de-emprendedurismo/   (LA)
```

Dentro de cada materia, por tipo de material:

| Carpeta | Qué va |
|---|---|
| `oficial/` | Programa aprobado, planificación (documentos públicos del sitio de la Facultad) |
| `casos/` | Casos y trabajos prácticos de la cátedra |
| `datos/` | Datos técnicos o económicos para calibrar (planillas, costos reales, etc.) |
| `notas/` | Apuntes, conversaciones con la cátedra, decisiones de diseño |

## Cómo sumar material

1. Copiar los archivos en la carpeta de la materia (o crearla con el mismo formato de nombre).
2. Anotarlo en `INDICE.md`: qué es, quién lo aportó, fecha y si se puede publicar.
3. Avisar en la conversación para que se lea y se use en el diseño del juego.

## Si algún material se puede publicar

Los documentos oficiales (programas aprobados por resolución) ya son públicos. Si una cátedra
autoriza a publicar un caso o datos, lo que use el juego va al código del juego (por ejemplo, sus
parámetros en `settings.py`), no a esta carpeta.
