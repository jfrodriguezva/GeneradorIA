"""Estudio de Producción de Cortometrajes y Keyframes IA para las 10 series de PrayVis.

Genera:
1. Keyframes 16:9 (1280×720) con IA en la GPU de Google Colab (`/generate`) a partir de los prompts
   oficiales de `docs/prompts/serie_visual/` de PrayVis, guardándolos tanto en `videos_prayvis/keyframes_ia/`
   como en `PrayVis/imagenes_entrada/` (con validación 16:9 ≥ 1280 px lista para `imagenes.mjs`).
2. 10 Cortometrajes Piloto en MP4 (1280×720, 24 fps, H.264 + audio estéreo AAC 192 kbps), uno por cada
   una de las 10 series de PrayVis (5 del Universo Uapeani + 5 de Historia de México), combinando:
   - Keyframes generados por IA en Google Colab GPU + arte oficial de capítulos y galerías de `PrayVis`.
   - Voces neuronales dramatizadas en español de México (`es-MX-JorgeNeural` y `es-MX-DaliaNeural`)
     diferenciando narrador y personajes masculinos/femeninos.
   - Partitura musical generativa y paisaje sonoro propio de cada serie (`musica.js` + `atmosfera.js`)
     con atenuación automática (ducking) durante los diálogos.
   - Movimiento de cámara cinematográfico (Ken Burns sub-píxel), partículas atmosféricas por serie y
     subtítulos sincronizados.
3. 1 Cortometraje Antología / Tráiler Maestro (`00_prayvis_antologia_10_series.mp4`) que presenta las
   10 series del catálogo de PrayVis.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from typing import Dict, List, Optional

import requests
from PIL import Image

import video as video_mod


# ==============================================================================
# GUIONES CURADOS FIELES A LOS TEXTOS Y ESCENAS ORIGINALES DE PRAYVIS
# ==============================================================================

CORTOMETRAJES_PRAYVIS: List[dict] = [
    {
        "orden": 1,
        "slug": "caricateri",
        "archivo_mp4": "01_caricateri_ep00_el_fuego_que_se_apaga.mp4",
        "episodio_titulo": "Episodio 0 · Prólogo: El fuego que se apaga",
        "escenas": [
            {
                "heading": "EXT. TZINTZUNTZAN — SUEÑO — AMANECER BLANCO",
                "keyframe_name": "CAR_E00_S01_v1.png",
                "fallback_art": "/series/caricateri/cap-000.jpg",
                "prompt": (
                    "Caricateri, episode 0, scene 1. Setting: EXT. TZINTZUNTZAN — SUEÑO — AMANECER BLANCO. "
                    "Tzintzuntzan and lake Patzcuaro, Purepecha state, stone terraces covered in white morning mist, "
                    "indigenous Purepecha man looking toward the ceremonial center, cinematic realist keyframe, "
                    "16:9, painterly photorealism, motivated natural light, no text, no watermark"
                ),
                "lines": [
                    {
                        "speaker": None,
                        "text": "La primera vez que soñó con la ciudad vacía, el padre de Caricateri pensó que era una advertencia sobre una guerra. Una neblina blanquecina cubría el lago de Pátzcuaro. Nada estaba destruido, pero nadie trabajaba.",
                        "pause_after_ms": 380,
                    },
                    {
                        "speaker": "PADRE",
                        "text": "¿Qué esperan?",
                        "pause_after_ms": 300,
                    },
                    {
                        "speaker": "CARGADOR",
                        "text": "Que alguien nos diga qué hacer.",
                        "pause_after_ms": 420,
                    },
                ],
            },
            {
                "heading": "EXT. TERRAZAS DE TZINTZUNTZAN — SUEÑO — CONTINUO",
                "keyframe_name": "CAR_E00_S02_v1.png",
                "fallback_art": "/series/caricateri/galeria-28.jpg",
                "prompt": (
                    "Caricateri, episode 0, scene 2. Ancient Purepecha stone ceremonial platform in Tzintzuntzan "
                    "under pale mist, cold stone brazier with extinguished fire, no embers, solemn atmosphere, "
                    "cinematic realist keyframe, 16:9, painterly photorealism, no text"
                ),
                "lines": [
                    {
                        "speaker": None,
                        "text": "A su alrededor cruzaban desconocidos con bultos y niños, como quien ya no puede volver a casa. En la plataforma ceremonial, donde debía arder la llama, no quedaba ni rescoldo.",
                        "pause_after_ms": 420,
                    },
                ],
            },
            {
                "heading": "EXT. PATIO DE LA CASA — MADRUGADA",
                "keyframe_name": "CAR_E00_S04_v1.png",
                "fallback_art": "/series/caricateri/galeria-16.jpg",
                "prompt": (
                    "Caricateri, episode 0, scene 4. Courtyard of a Purepecha house at dawn, two indigenous men "
                    "kneeling by a clay brazier, blowing on glowing orange embers under grey ash, warm firelight "
                    "illuminating their hands and faces, cinematic realist keyframe, 16:9, photorealistic"
                ),
                "lines": [
                    {
                        "speaker": None,
                        "text": "El padre despertó y se arrodilló junto al recipiente donde la familia guardaba la brasa bajo la ceniza. Sopló hasta que la luz naranja le subió a las manos.",
                        "pause_after_ms": 350,
                    },
                    {
                        "speaker": "PADRE",
                        "text": "Soñé que la ciudad no tenía a quién escuchar. En mi sueño no faltaban hombres capaces: nadie les había enseñado a decidir.",
                        "pause_after_ms": 350,
                    },
                    {
                        "speaker": "SICUIRANCHA",
                        "text": "Hay decisiones que no pueden esperar a que cada hombre esté de acuerdo. Si llega ese día, necesitaremos hombres que obedezcan sin dividirse.",
                        "pause_after_ms": 420,
                    },
                ],
            },
            {
                "heading": "INT. HABITACIÓN DE CARICATERI / EXT. LAGO — AMANECER",
                "keyframe_name": "CAR_E00_S06_v1.png",
                "fallback_art": "/series/caricateri/galeria-29.jpg",
                "prompt": (
                    "Caricateri, episode 0, scene 6. Sunrise over Lake Patzcuaro and Tzintzuntzan terraces, "
                    "wooden canoes gliding on golden water, smoke rising from hearths, ceremonial fire burning "
                    "on the high temple, cinematic realist keyframe, 16:9, painterly photorealism"
                ),
                "lines": [
                    {
                        "speaker": None,
                        "text": "Junto a la estera donde dormía el niño Caricateri, su padre comprendió el verdadero peligro. Afuera, las canoas salían al lago de Pátzcuaro y, en lo alto del recinto, el fuego seguía ardiendo.",
                        "pause_after_ms": 500,
                    },
                ],
            },
        ],
    },
    {
        "orden": 2,
        "slug": "antes-de-la-tormenta",
        "archivo_mp4": "02_antes_de_la_tormenta_ep01_intriga.mp4",
        "episodio_titulo": "Episodio 1 · Intriga en Tenochtitlan",
        "escenas": [
            {
                "heading": "EXT. CANALES DE TENOCHTITLAN — AMANECER ENTRE BRUMA",
                "keyframe_name": "PV00_E01_S01_v1.png",
                "fallback_art": "/series/antes-de-la-tormenta/cap-001.jpg",
                "prompt": (
                    "Uapeani Antes de la tormenta, episode 1, scene 1. Tenochtitlan canals and chinampas at dawn "
                    "before the storm, canoes carrying tribute, monumental Mexica architecture in the mist, "
                    "cinematic historical concept art, 16:9, photorealistic, 35mm film still"
                ),
                "lines": [
                    {
                        "speaker": None,
                        "text": "En los canales de Tenochtitlan, el agua devolvía el reflejo de los templos antes de que el viento agitara la laguna. Uapeani observaba las canoas de tributo mientras las noticias del oriente viajaban en voz baja.",
                        "pause_after_ms": 400,
                    },
                ],
            },
            {
                "heading": "INT. SALA DE CONSEJO — TARDE DE TORMENTA",
                "keyframe_name": None,
                "fallback_art": "/series/antes-de-la-tormenta/cap-002.jpg",
                "lines": [
                    {
                        "speaker": "UAPEANI",
                        "text": "Ningún imperio cae en una sola mañana. Primero se acostumbra a no escuchar a quienes guardan los caminos.",
                        "pause_after_ms": 380,
                    },
                    {
                        "speaker": "QUIYAUHTZIN",
                        "text": "Los mensajeros de la costa no hablan de dioses. Hablan de madera, de metal y de alianzas que nuestra soberbia dejó abiertas.",
                        "pause_after_ms": 420,
                    },
                ],
            },
            {
                "heading": "EXT. TERRAZA SOBRE EL LAGO — NOCHE DE RELÁMPAGOS",
                "keyframe_name": None,
                "fallback_art": "/series/antes-de-la-tormenta/cap-005.jpg",
                "lines": [
                    {
                        "speaker": None,
                        "text": "Sobre el valle cayó la primera lluvia de la estación. Entre Tzintzuntzan y México, dos pueblos que habían sido rivales tendrían que aprender a mirarse de frente antes de la tormenta.",
                        "pause_after_ms": 480,
                    },
                ],
            },
        ],
    },
    {
        "orden": 3,
        "slug": "la-unificacion",
        "archivo_mp4": "03_la_unificacion_ep01_el_peso_del_sueno.mp4",
        "episodio_titulo": "Capítulo I · El peso del sueño",
        "escenas": [
            {
                "heading": "EXT. PUERTO DEL PACÍFICO — LAS NAOS DE LA UNIÓN",
                "keyframe_name": None,
                "fallback_art": "/series/la-unificacion/cap-001.jpg",
                "lines": [
                    {
                        "speaker": None,
                        "text": "Cuando los reinos del Anáhuac y de Michoacán sellaron la paz, comprendieron que defender la orilla no bastaba. Había que cruzar el mar con velas propias y conocer el mundo sin esperar a ser descubiertos.",
                        "pause_after_ms": 400,
                    },
                    {
                        "speaker": "OCELOTL",
                        "text": "Llevamos maíz, obsidiana y cuerdas de cuenta. Si el mar tiene otra orilla, alguien allá también está contando las estrellas.",
                        "pause_after_ms": 380,
                    },
                ],
            },
            {
                "heading": "EXT. CUBIERTA EN MAR ABIERTO — RUTA DE LOS SOÑADORES",
                "keyframe_name": None,
                "fallback_art": "/series/la-unificacion/cap-012.jpg",
                "lines": [
                    {
                        "speaker": "XOCHITZIN",
                        "text": "Los capitanes cuentan lanzas; nosotras contamos el agua, las semillas y los puertos donde dos lenguas pueden entenderse sin sangre.",
                        "pause_after_ms": 400,
                    },
                    {
                        "speaker": None,
                        "text": "Desde los Andes de Killa hasta los fiordos nevados de Sigrid, el viaje de la Unificación trazó el mapa de un siglo dieciséis donde los pueblos dialogaron como iguales.",
                        "pause_after_ms": 480,
                    },
                ],
            },
        ],
    },
    {
        "orden": 4,
        "slug": "mictlania",
        "archivo_mp4": "04_mictlania_ep01_lo_que_mas_amas.mp4",
        "episodio_titulo": "Capítulo 1 · Lo que más amas",
        "escenas": [
            {
                "heading": "EXT. ORILLA DEL RÍO APANOHUACALHUIA — PRIMER NIVEL DEL MICTLÁN",
                "keyframe_name": None,
                "fallback_art": "/series/mictlania/cap-001.jpg",
                "lines": [
                    {
                        "speaker": None,
                        "text": "Nadie desciende al Mictlán con las manos llenas de oro. A la orilla del río profundo, entre pétalos de cempasúchil y niebla morada, solo espera la mirada leal de Xólotl.",
                        "pause_after_ms": 400,
                    },
                    {
                        "speaker": "XÓLOTL",
                        "text": "Para cruzar las nueve regiones no necesitas recordar cómo moriste, sino aquello que amaste lo suficiente para no olvidarlo en el viento de obsidiana.",
                        "pause_after_ms": 420,
                    },
                ],
            },
            {
                "heading": "INT. CASA DE MICTLANTECUHTLI — NOVENO LUGAR",
                "keyframe_name": None,
                "fallback_art": "/series/mictlania/cap-015.jpg",
                "lines": [
                    {
                        "speaker": "MICTECACÍHUATL",
                        "text": "Los vivos creen que el inframundo es castigo. Aquí solo pesa la verdad que cada alma calló en la tierra.",
                        "pause_after_ms": 420,
                    },
                    {
                        "speaker": None,
                        "text": "El tambor del huéhuetl marcó el pulso en la oscuridad mientras comenzaba la travesía por los nueve lugares del descanso.",
                        "pause_after_ms": 480,
                    },
                ],
            },
        ],
    },
    {
        "orden": 5,
        "slug": "uapeanibot",
        "archivo_mp4": "05_uapeanibot_ep01_el_sol_en_el_pecho.mp4",
        "episodio_titulo": "Capítulo 1 · El sol en el pecho",
        "escenas": [
            {
                "heading": "INT. CÁMARA DE JADE Y LUZ — TENOCHTITLAN DEL FUTURO",
                "keyframe_name": None,
                "fallback_art": "/series/uapeanibot/cap-001.jpg",
                "lines": [
                    {
                        "speaker": None,
                        "text": "Siglos después de la Unificación, cuando las ciudades crecieron como jardines de piedra solar y circuitos de luz, despertó una memoria grabada en jade.",
                        "pause_after_ms": 400,
                    },
                    {
                        "speaker": "UAPEANIBOT",
                        "text": "Mis sensores registran la frecuencia del lago y las voces antiguas. No fui construido para reemplazar a los vivos, sino para recordar por qué encendieron el primer fuego.",
                        "pause_after_ms": 420,
                    },
                ],
            },
            {
                "heading": "EXT. PUERTA DEL MICTLÁN CUÁNTICO — AMANECER LUMINOSO",
                "keyframe_name": None,
                "fallback_art": "/series/uapeanibot/cap-008.jpg",
                "lines": [
                    {
                        "speaker": None,
                        "text": "Bajo un cielo recorrido por campanas y pulsos de luz, el pasado mesoamericano y el mañana se encontraron en un mismo latido.",
                        "pause_after_ms": 480,
                    },
                ],
            },
        ],
    },
    {
        "orden": 6,
        "slug": "inquisidor",
        "archivo_mp4": "06_inquisidor_ep01_la_palabra.mp4",
        "episodio_titulo": "Episodio 1 · La palabra (Nueva España, 1594)",
        "escenas": [
            {
                "heading": "INT. ESTANCIA DE DILIGENCIAS — MÉXICO, 1594 — MAÑANA",
                "keyframe_name": "SO_E01_S01_v1.png",
                "fallback_art": "/series/inquisidor/cap-001.jpg",
                "prompt": (
                    "El Santo Oficio, episode 1, scene 1. Setting: INT. ESTANCIA DE DILIGENCIAS — MAÑANA. "
                    "Mexico City, New Spain, 1594; Inquisition era, austere colonial stone room, a shaft of "
                    "morning light over a wooden table with ink and parchment, a commissioner and notary questioning "
                    "a humble weaver, cinematic realist keyframe, 16:9, painterly photorealism, no text"
                ),
                "lines": [
                    {
                        "speaker": None,
                        "text": "La luz entraba demasiado recta en la estancia de diligencias. El notario colocó un pliego limpio frente a Gregorio Salcedo, tejedor que había acudido sin intención de perjudicar a nadie. Ni espada ni guardias: sobre la mesa sólo había palabras aún no pronunciadas.",
                        "pause_after_ms": 380,
                    },
                    {
                        "speaker": "RODRIGO",
                        "text": "Hablad despacio. Si la memoria os falta, decid que os falta. No estáis aquí para satisfacer una pregunta antes de oírla.",
                        "pause_after_ms": 350,
                    },
                    {
                        "speaker": "GREGORIO",
                        "text": "Pasé por detrás del taller de Olmos; entonces escuché rezos, o eso creí. No vi practicar ceremonia alguna.",
                        "pause_after_ms": 400,
                    },
                ],
            },
            {
                "heading": "INT. CASA DE LOS MENDOZA / TALLER DE OLMOS — ANOCHECER",
                "keyframe_name": "SO_E01_S04_v1.png",
                "fallback_art": "/series/inquisidor/cap-002.jpg",
                "prompt": (
                    "El Santo Oficio, episode 1, scene 4. Colonial bookbinder workshop in 1594 Mexico City illuminated "
                    "by warm candlelight, wooden presses, leather volumes, a family working quietly in the shadows, "
                    "cinematic realist keyframe, 16:9, painterly photorealism, no text"
                ),
                "lines": [
                    {
                        "speaker": "BEATRIZ",
                        "text": "Un nombre escrito con duda en un folio termina pesando igual que una sentencia cuando nadie se atreve a corregirlo.",
                        "pause_after_ms": 380,
                    },
                    {
                        "speaker": None,
                        "text": "En el silencio del archivo virreinal, Gabriel de Mendoza comprendió que una sola palabra mal copiada bastaba para encerrar a una familia entera.",
                        "pause_after_ms": 480,
                    },
                ],
            },
        ],
    },
    {
        "orden": 7,
        "slug": "independencia",
        "archivo_mp4": "07_independencia_ep01_el_hombre_que_murio_dos_veces.mp4",
        "episodio_titulo": "Episodio 1 · El hombre que murió dos veces (1808)",
        "escenas": [
            {
                "heading": "INT. DESPACHO EN QUERÉTARO — MEDIA NOCHE DE 1808",
                "keyframe_name": "IND_E01_S01_v1.png",
                "fallback_art": "/series/independencia/cap-001.jpg",
                "prompt": (
                    "La patria de los traidores, episode 1, scene 1. New Spain 1808, colonial study at midnight "
                    "lit by oil lamp, wax-sealed letters and maps of the Bajio on a wooden desk, two conspirators "
                    "in period dress speaking in whispers, cinematic realist keyframe, 16:9, photorealistic"
                ),
                "lines": [
                    {
                        "speaker": None,
                        "text": "Al ritmo apresurado del clavecín y el reloj, las cartas cruzaban el Bajío con nombres fingidos. En Nueva España, la lealtad y la traición se escribían con la misma tinta.",
                        "pause_after_ms": 380,
                    },
                    {
                        "speaker": "EMISARIO",
                        "text": "Si el virrey cae, todos jurarán haber estado de nuestro lado desde el primer día. Si fracasamos, ni las piedras pronunciarán nuestro nombre.",
                        "pause_after_ms": 420,
                    },
                ],
            },
            {
                "heading": "EXT. CAMINO REAL DEL BAJÍO — AMANECER CON NIEBLA",
                "keyframe_name": None,
                "fallback_art": "/series/independencia/cap-004.jpg",
                "lines": [
                    {
                        "speaker": None,
                        "text": "Entre tertulias literarias y emboscadas en los caminos reales, nacía una patria dividida por sus propios secretos.",
                        "pause_after_ms": 480,
                    },
                ],
            },
        ],
    },
    {
        "orden": 8,
        "slug": "reforma",
        "archivo_mp4": "08_reforma_ep01_el_mundo_que_prometimos.mp4",
        "episodio_titulo": "Episodio 1 · El mundo que prometimos (1857)",
        "escenas": [
            {
                "heading": "INT. SALÓN EN PENUMBRA — CIUDAD DE MÉXICO, 1858",
                "keyframe_name": "REF_E01_S01_v1.png",
                "fallback_art": "/series/reforma/cap-001.jpg",
                "prompt": (
                    "Lo que la guerra nos quito, episode 1, scene 1. Mexico City 1858, Reform War era, melancholic "
                    "nineteenth century parlor in blue-grey and sepia tones, rain on the tall window, a piano and "
                    "oil lamp, cinematic realist keyframe, 16:9, painterly photorealism"
                ),
                "lines": [
                    {
                        "speaker": None,
                        "text": "Un vals lento en tono menor acompañaba la lluvia sobre los balcones. La Guerra de Reforma no sólo partió los caminos de la República: partió las mesas donde cenaban los hermanos.",
                        "pause_after_ms": 400,
                    },
                    {
                        "speaker": "LEONOR",
                        "text": "Prometimos que las leyes nuevas nos darían un país más justo, pero en esta casa sólo contamos las sillas que van quedando vacías.",
                        "pause_after_ms": 420,
                    },
                ],
            },
            {
                "heading": "EXT. CAMPO EN NIEBLA TRAS LA BATALLA — ATARDECER",
                "keyframe_name": None,
                "fallback_art": "/series/reforma/cap-003.jpg",
                "lines": [
                    {
                        "speaker": None,
                        "text": "Cuando los cañones callaron entre la niebla, quedó únicamente la memoria de lo que la guerra nos quitó.",
                        "pause_after_ms": 480,
                    },
                ],
            },
        ],
    },
    {
        "orden": 9,
        "slug": "porfiriato",
        "archivo_mp4": "09_porfiriato_ep01_la_prueba_del_amor.mp4",
        "episodio_titulo": "Episodio 1 · La prueba del amor (1900)",
        "escenas": [
            {
                "heading": "EXT. CALLE EMPEDRADA BAJO FAROLES DE GAS — NOCHE DE LLUVIA",
                "keyframe_name": "POR_E01_S01_v1.png",
                "fallback_art": "/series/porfiriato/cap-001.jpg",
                "prompt": (
                    "Los pecados de la noche, episode 1, scene 1. Mexico City 1900, Porfiriato noir, wet cobblestone "
                    "street at night reflecting golden gas streetlamps, horse carriage in the cigarette smoke and mist, "
                    "black garnet and gold palette, cinematic realist keyframe, 16:9, photorealistic"
                ),
                "lines": [
                    {
                        "speaker": None,
                        "text": "Bajo el resplandor dorado de los faroles de gas y el compás nocturno de una habanera, la Ciudad de México del centenario ocultaba sus crímenes tras cortinas de terciopelo.",
                        "pause_after_ms": 400,
                    },
                    {
                        "speaker": "INSPECTOR",
                        "text": "En el Porfiriato el orden se mide por lo que no sale en los periódicos de la mañana. Los pecados de la noche se pagan antes del alba.",
                        "pause_after_ms": 420,
                    },
                ],
            },
            {
                "heading": "INT. SALÓN PRIVADO — MEDIANOCHE",
                "keyframe_name": None,
                "fallback_art": "/series/porfiriato/cap-005.jpg",
                "lines": [
                    {
                        "speaker": None,
                        "text": "Entre el humo, el piano nocturno y las promesas rotas, cada secreto compraba un día más de silencio.",
                        "pause_after_ms": 480,
                    },
                ],
            },
        ],
    },
    {
        "orden": 10,
        "slug": "baronesa",
        "archivo_mp4": "10_baronesa_ep01_la_mujer_que_no_se_inclina.mp4",
        "episodio_titulo": "Episodio 1 · La mujer que no se inclina (Xalapa, 1758)",
        "escenas": [
            {
                "heading": "INT. CASA COMERCIAL EN XALAPA — FERIA DE LAS FLOTAS, 1758",
                "keyframe_name": "BAR_E01_S01_v1.png",
                "fallback_art": "/series/baronesa/galeria-01.jpg",
                "prompt": (
                    "La Baronesa, episode 1, scene 1. Xalapa, Veracruz, New Spain, 1758, grand colonial merchant house "
                    "with humid green mountain light entering through tall arches, a poised eighteenth-century woman "
                    "inspecting trade ledgers and chests, cinematic realist keyframe, 16:9, photorealistic"
                ),
                "lines": [
                    {
                        "speaker": None,
                        "text": "En la Xalapa húmeda de mil setecientos cincuenta y ocho, donde las flotas de Cádiz y las recuas de Puebla decidían las fortunas del virreinato, una mujer llevaba las cuentas que ningún caballero se atrevía a disputar.",
                        "pause_after_ms": 400,
                    },
                    {
                        "speaker": "BARONESA",
                        "text": "Los títulos se heredan o se compran en la corte; el crédito en este camino se gana cumpliendo cada palabra cuando las mulas cruzan la sierra.",
                        "pause_after_ms": 420,
                    },
                ],
            },
            {
                "heading": "EXT. CAMINO DE LOS ARRIEROS EN LA NIEBLA VERACRUZANA — TARDE",
                "keyframe_name": None,
                "fallback_art": "/series/baronesa/galeria-08.jpg",
                "lines": [
                    {
                        "speaker": None,
                        "text": "Al compás de las cuerdas y el piano de salón, la Baronesa demostró que su casa no se inclinaba ante ningún monopolio.",
                        "pause_after_ms": 480,
                    },
                ],
            },
        ],
    },
]


def _resolve_prayvis_image(prayvis_dir: str, rel_web_path: str) -> Optional[Image.Image]:
    full = os.path.join(prayvis_dir, "web", "public", rel_web_path.lstrip("/").replace("/", os.sep))
    if os.path.exists(full):
        return Image.open(full).convert("RGB")
    # Buscar cualquier imagen en la carpeta de la serie
    parts = rel_web_path.strip("/").split("/")
    if len(parts) >= 2:
        serie_dir = os.path.join(prayvis_dir, "web", "public", parts[0], parts[1])
        if os.path.isdir(serie_dir):
            for f in sorted(os.listdir(serie_dir)):
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    return Image.open(os.path.join(serie_dir, f)).convert("RGB")
    return None


def _generate_keyframe_on_colab_gpu(
    worker_url: str,
    prompt: str,
    seed: int = 101,
    timeout: int = 180,
) -> Optional[Image.Image]:
    """Solicita un keyframe 16:9 al worker GPU de Google Colab (`/generate`) y lo escala a 1280×720."""
    url = f"{worker_url.rstrip('/')}/generate"
    payload = {
        "prompt": prompt,
        "steps": 24,
        "guidance_scale": 7.0,
        "width": 768,
        "height": 432,
        "seed": seed,
        "upscale": False,
        "hires_fix": False,
        "restore_faces": False,
    }
    for attempt in range(1, 3):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code == 524 and attempt < 2:
                time.sleep(4)
                continue
            if resp.status_code == 200:
                data = resp.json()
                raw = base64.b64decode(data["image_base64"])
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                # Escalar a 1280×720 exacto (16:9 válido para `imagenes.mjs` en PrayVis)
                return img.resize((1280, 720), Image.Resampling.LANCZOS)
        except Exception as exc:
            print(f"  [aviso] Intento {attempt} en Colab GPU falló: {exc}")
            time.sleep(2)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generador de Cortometrajes y Keyframes de las 10 series de PrayVis")
    parser.add_argument(
        "--prayvis-dir",
        default=r"C:\Users\jfrodriguezv\.gemini\antigravity\brain\4fc65d27-cb45-43e5-827d-0be3066948ff\scratch\PrayVis",
        help="Ruta local al repositorio PrayVis",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "videos_prayvis")),
        help="Carpeta donde se guardarán los cortometrajes MP4 y keyframes generados",
    )
    parser.add_argument(
        "--worker-url",
        default=os.environ.get("GENERATIVA_IMAGE_WORKER_URL", ""),
        help="URL del túnel de Google Colab GPU para generar nuevos keyframes con IA",
    )
    parser.add_argument(
        "--only-slug",
        default="",
        help="Si se especifica, genera únicamente la serie con ese slug",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    keyframes_out_dir = os.path.join(args.output_dir, "keyframes_ia")
    os.makedirs(keyframes_out_dir, exist_ok=True)
    prayvis_entrada_dir = os.path.join(args.prayvis_dir, "imagenes_entrada")
    if os.path.isdir(args.prayvis_dir):
        os.makedirs(prayvis_entrada_dir, exist_ok=True)

    colab_alive = False
    if args.worker_url:
        try:
            r = requests.get(f"{args.worker_url.rstrip('/')}/health", timeout=10)
            if r.status_code == 200:
                colab_alive = True
                print(f"[PrayVis Studio] Conectado a Google Colab GPU: {args.worker_url} -> {r.json()}")
        except Exception as exc:
            print(f"[PrayVis Studio] Túnel Colab no accesible ({exc}); usando arte local de PrayVis.")

    manifest_videos: List[dict] = []
    manifest_keyframes: List[dict] = []

    for spec in CORTOMETRAJES_PRAYVIS:
        slug = spec["slug"]
        if args.only_slug and slug != args.only_slug:
            continue

        out_mp4 = os.path.join(args.output_dir, spec["archivo_mp4"])
        print(f"\n==================================================================")
        print(f"▶ Produciendo Cortometraje [{spec['orden']:02d}/10]: {spec['slug'].upper()} — {spec['episodio_titulo']}")
        print(f"==================================================================")

        scenes_data: List[dict] = []
        for s_idx, sc in enumerate(spec["escenas"]):
            img: Optional[Image.Image] = None
            kf_name = sc.get("keyframe_name")

            # Si ya generamos este keyframe en disco en esta corrida o antes, reutilizarlo
            if kf_name:
                cached_kf = os.path.join(keyframes_out_dir, kf_name)
                if os.path.exists(cached_kf):
                    img = Image.open(cached_kf).convert("RGB")
                    print(f"  ✔ Keyframe IA en caché: {kf_name}")
                elif colab_alive and sc.get("prompt"):
                    print(f"  ⚡ Generando Keyframe IA 16:9 en Google Colab GPU: {kf_name}...")
                    t_kf = time.time()
                    img = _generate_keyframe_on_colab_gpu(
                        args.worker_url,
                        prompt=sc["prompt"],
                        seed=1000 + spec["orden"] * 100 + s_idx,
                    )
                    if img is not None:
                        img.save(cached_kf, format="PNG")
                        if os.path.isdir(prayvis_entrada_dir):
                            img.save(os.path.join(prayvis_entrada_dir, kf_name), format="PNG")
                        elapsed_kf = round(time.time() - t_kf, 2)
                        print(f"  ✔ Keyframe IA generado en {elapsed_kf}s -> {cached_kf} (1280×720)")
                        manifest_keyframes.append(
                            {
                                "file": kf_name,
                                "series": slug,
                                "heading": sc["heading"],
                                "seconds": elapsed_kf,
                                "width": img.width,
                                "height": img.height,
                            }
                        )

            # Combinar con el arte oficial de capítulos/galería de PrayVis si no era escena de keyframe nuevo
            if img is None:
                img = _resolve_prayvis_image(args.prayvis_dir, sc["fallback_art"])
            if img is None:
                img = Image.new("RGB", (1280, 720), (24, 18, 14))

            scenes_data.append(
                {
                    "heading": sc["heading"],
                    "image": img,
                    "lines": sc["lines"],
                }
            )

        t0 = time.time()
        meta = video_mod.render_cortometraje_mp4(
            series_slug=slug,
            episode_title=spec["episodio_titulo"],
            scenes_data=scenes_data,
            output_mp4_path=out_mp4,
            width=1280,
            height=720,
            fps=24,
            remote_worker_url=args.worker_url if colab_alive else None,
        )
        render_sec = round(time.time() - t0, 2)
        size_mb = round(os.path.getsize(out_mp4) / (1024 * 1024), 2)
        print(
            f"  🎬 Cortometraje listo: {spec['archivo_mp4']} | "
            f"Duración: {meta['duration_seconds']}s ({meta['frames']} cuadros) | "
            f"Peso: {size_mb} MB | Renderizado en {render_sec}s"
        )
        manifest_videos.append(
            {
                "order": spec["orden"],
                "slug": slug,
                "title": video_mod.AMBIENTES[slug]["titulo"],
                "collection": video_mod.AMBIENTES[slug]["coleccion"],
                "episode_title": spec["episodio_titulo"],
                "file": spec["archivo_mp4"],
                "duration_seconds": meta["duration_seconds"],
                "size_mb": size_mb,
                "scenes": meta["scenes"],
            }
        )

    # 3. Generar el Cortometraje Antología / Tráiler General de las 10 Series (`00_prayvis_antologia_10_series.mp4`)
    if not args.only_slug:
        print(f"\n==================================================================")
        print(f"▶ Produciendo Tráiler Antología Maestro: 00_prayvis_antologia_10_series.mp4")
        print(f"==================================================================")
        antologia_scenes: List[dict] = []
        for spec in CORTOMETRAJES_PRAYVIS:
            slug = spec["slug"]
            amb = video_mod.AMBIENTES[slug]
            img = _resolve_prayvis_image(args.prayvis_dir, f"/series/{slug}/portada.jpg")
            if img is None:
                img = _resolve_prayvis_image(args.prayvis_dir, spec["escenas"][0]["fallback_art"])
            if img is None:
                img = Image.new("RGB", (1280, 720), (20, 15, 12))
            antologia_scenes.append(
                {
                    "heading": f"{amb['coleccion'].upper()} · {amb['codigo']} · {amb['titulo'].upper()}",
                    "image": img,
                    "lines": [
                        {
                            "speaker": amb["titulo"].upper(),
                            "text": f"{amb['genero']}. «{amb['lema']}».",
                            "pause_after_ms": 280,
                        }
                    ],
                }
            )

        out_antologia = os.path.join(args.output_dir, "00_prayvis_antologia_10_series.mp4")
        meta_ant = video_mod.render_cortometraje_mp4(
            series_slug="caricateri",
            episode_title="Antología Oficial · Las 10 Series de PrayVis",
            scenes_data=antologia_scenes,
            output_mp4_path=out_antologia,
            width=1280,
            height=720,
            fps=24,
            remote_worker_url=args.worker_url if colab_alive else None,
        )
        size_ant_mb = round(os.path.getsize(out_antologia) / (1024 * 1024), 2)
        print(
            f"  🎬 Antología lista: 00_prayvis_antologia_10_series.mp4 | "
            f"Duración: {meta_ant['duration_seconds']}s | Peso: {size_ant_mb} MB"
        )
        manifest_videos.insert(
            0,
            {
                "order": 0,
                "slug": "antologia-prayvis",
                "title": "Antología PrayVis (10 Series)",
                "collection": "Universo Uapeani + Historia de México",
                "episode_title": "Recorrido por las 10 series",
                "file": "00_prayvis_antologia_10_series.mp4",
                "duration_seconds": meta_ant["duration_seconds"],
                "size_mb": size_ant_mb,
                "scenes": meta_ant["scenes"],
            },
        )

    report_path = os.path.join(args.output_dir, "reporte_videos_prayvis.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "colab_gpu_url": args.worker_url,
                "colab_gpu_active": colab_alive,
                "total_videos": len(manifest_videos),
                "total_ai_keyframes": len(manifest_keyframes),
                "videos": manifest_videos,
                "ai_keyframes": manifest_keyframes,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\n[PrayVis Studio] Reporte guardado en: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
