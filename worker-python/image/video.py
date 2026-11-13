"""Motor de generación de video y cortometrajes cinematográficos para Generativa / PrayVis.

Integra:
1. Partitura musical generativa y paisaje sonoro por serie (port directo de
   `PrayVis/contenido/produccion_series/comun/musica.js` y `atmosfera.js` a NumPy estéreo 44.1 kHz):
   - Instrumentos sintetizados: flauta de barro, ocarina, campana, piano, arpa, clavecín,
     cuerdas, coro, órgano, pad, pulso, bajo, teponaztli, huéhuetl, latido, sonaja y escobilla.
   - Reverberación estéreo de sala (2.8 s) y atenuación automática (ducking) durante los diálogos.
2. Narración neuronal dramatizada en español de México (`edge-tts`: `es-MX-JorgeNeural` y
   `es-MX-DaliaNeural`), diferenciando narrador y personajes masculinos/femeninos con timbre y
   cadencia propios por personaje (igual que `narrar.mjs` y `unidades.js`).
3. Cámara cinematográfica (Ken Burns sub-píxel: zoom in/out, paneos laterales y diagonales),
   partículas atmosféricas por serie (`brasas`, `lluvia` con relámpago, `viento`, `almas` y pétalos
   de cempasúchil, red de `datos`, `velas`, `tinta`, `niebla`, `humo` con farol de gas, `polvo`),
   cartelas de lugar/tiempo, indicador de personaje hablante y subtítulos sincronizados en MP4 H.264/AAC.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import math
import os
import shutil
import subprocess
import tempfile
import wave
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field


# ==============================================================================
# 1. CATÁLOGO DE AMBIENTES Y PARTITURAS DE LAS 10 SERIES DE PRAYVIS
# ==============================================================================

AMBIENTES: Dict[str, dict] = {
    "caricateri": {
        "coleccion": "Universo Uapeani",
        "codigo": "PV-000C",
        "titulo": "Caricateri",
        "genero": "Aventura · origen",
        "lema": "El fuego que se apaga",
        "particulas": "brasas",
        "sonido": "fuego",
        "fondo": "#170d08",
        "papel": "#f1e2c8",
        "acento": "#e0743f",
        "luz": "#ffb35c",
    },
    "antes-de-la-tormenta": {
        "coleccion": "Universo Uapeani",
        "codigo": "PV-000",
        "titulo": "Uapeani · Antes de la tormenta",
        "genero": "Aventura · épica",
        "lema": "Antes de la tormenta",
        "particulas": "lluvia",
        "sonido": "tormenta",
        "fondo": "#0b131b",
        "papel": "#e9e3d4",
        "acento": "#7fb0d6",
        "luz": "#cfe6ff",
    },
    "la-unificacion": {
        "coleccion": "Universo Uapeani",
        "codigo": "PV-001–005",
        "titulo": "La Unificación",
        "genero": "Aventura · viaje",
        "lema": "Un mundo sin mapa",
        "particulas": "viento",
        "sonido": "viento",
        "fondo": "#081615",
        "papel": "#efe6cf",
        "acento": "#4fb8a2",
        "luz": "#f4d58d",
    },
    "mictlania": {
        "coleccion": "Universo Uapeani",
        "codigo": "PV-006",
        "titulo": "Mictlania",
        "genero": "Aventura · inframundo",
        "lema": "Los nueve lugares",
        "particulas": "almas",
        "sonido": "inframundo",
        "fondo": "#0d0814",
        "papel": "#e6dcd6",
        "acento": "#b48ae0",
        "luz": "#ff9f2e",
    },
    "uapeanibot": {
        "coleccion": "Universo Uapeani",
        "codigo": "PV-007",
        "titulo": "UapeaniBot",
        "genero": "Aventura · futuro",
        "lema": "Un inicio en el futuro",
        "particulas": "datos",
        "sonido": "futuro",
        "fondo": "#0c1116",
        "papel": "#f3eee2",
        "acento": "#f0b43c",
        "luz": "#9ff0ff",
    },
    "inquisidor": {
        "coleccion": "Historia de México",
        "codigo": "PV-010",
        "titulo": "El Santo Oficio",
        "genero": "Terror · suspenso (1594)",
        "lema": "Lo que se confiesa en la oscuridad",
        "particulas": "velas",
        "sonido": "terror",
        "fondo": "#070505",
        "papel": "#d9cfbf",
        "acento": "#a8322a",
        "luz": "#ffb04a",
    },
    "independencia": {
        "coleccion": "Historia de México",
        "codigo": "PV-020",
        "titulo": "La patria de los traidores",
        "genero": "Espionaje · intriga (1808–1829)",
        "lema": "La patria de los traidores",
        "particulas": "tinta",
        "sonido": "reloj",
        "fondo": "#100d09",
        "papel": "#efe3c6",
        "acento": "#c49a4a",
        "luz": "#ffe2a0",
    },
    "reforma": {
        "coleccion": "Historia de México",
        "codigo": "PV-030",
        "titulo": "Lo que la guerra nos quitó",
        "genero": "Drama · duelo (1855–1867)",
        "lema": "Lo que deja el duelo",
        "particulas": "niebla",
        "sonido": "lluvia-suave",
        "fondo": "#0e1114",
        "papel": "#e8e4dc",
        "acento": "#8fa3b5",
        "luz": "#dfe8f0",
    },
    "porfiriato": {
        "coleccion": "Historia de México",
        "codigo": "PV-040",
        "titulo": "Los pecados de la noche",
        "genero": "Thriller · noir (1887–1920)",
        "lema": "Los pecados de la noche",
        "particulas": "humo",
        "sonido": "noche",
        "fondo": "#0a0a0c",
        "papel": "#ece6da",
        "acento": "#d4a64a",
        "luz": "#ffd27a",
    },
    "baronesa": {
        "coleccion": "Historia de México",
        "codigo": "PV-050",
        "titulo": "La Baronesa",
        "genero": "Drama de época (1758)",
        "lema": "La mujer que no se inclina",
        "particulas": "polvo",
        "sonido": "salon",
        "fondo": "#120b10",
        "papel": "#f2e8e2",
        "acento": "#c77d98",
        "luz": "#ffd9c2",
    },
}

PARTITURAS: Dict[str, dict] = {
    "caricateri": {
        "bpm": 58, "compas": 4, "raiz": 62, "escala": [0, 3, 5, 7, 10], "progresion": [0, 3, 2, 0],
        "melodia": "flauta", "densidad": 0.6, "nivel": 1.0, "pasos": 2,
        "acomp": [("dron", "pad")],
        "perc": [("teponaztli", "x.....x...x....."), ("sonaja", "........o.......")],
    },
    "antes-de-la-tormenta": {
        "bpm": 70, "compas": 4, "raiz": 57, "escala": [0, 2, 3, 5, 7, 8, 10], "progresion": [0, 5, 3, 4],
        "melodia": "flauta", "densidad": 0.7, "nivel": 1.0, "pasos": 2,
        "acomp": [("ostinato", "bajo"), ("acorde", "cuerdas")],
        "perc": [("huehuetl", "x.......x.x.....")],
    },
    "la-unificacion": {
        "bpm": 84, "compas": 4, "raiz": 62, "escala": [0, 2, 3, 5, 7, 9, 10], "progresion": [0, 3, 6, 0],
        "melodia": "flauta", "densidad": 0.7, "nivel": 1.0, "pasos": 2,
        "acomp": [("arpegio", "arpa")],
        "perc": [("sonaja", "o.o.o.o.o.o.o.o."), ("teponaztli", "x.......x.....x.")],
    },
    "mictlania": {
        "bpm": 50, "compas": 4, "raiz": 52, "escala": [0, 1, 3, 5, 7, 8, 10], "progresion": [0, 1, 0, 6],
        "melodia": "ocarina", "densidad": 0.5, "nivel": 1.0, "pasos": 2,
        "acomp": [("dron", "coro")],
        "perc": [("huehuetl", "x..............."), ("latido", "........x.x.....")],
    },
    "uapeanibot": {
        "bpm": 96, "compas": 4, "raiz": 69, "escala": [0, 2, 4, 7, 9], "progresion": [0, 3, 4, 2],
        "melodia": "campana", "densidad": 0.6, "nivel": 1.4, "pasos": 2,
        "acomp": [("arpegio", "pulso"), ("acorde", "pad")],
        "perc": [("sonaja", "..o...o...o...o.")],
    },
    "inquisidor": {
        "bpm": 44, "compas": 4, "raiz": 50, "escala": [0, 1, 3, 5, 7, 8, 10], "progresion": [0, 0, 1, 0],
        "melodia": "coro", "densidad": 0.45, "nivel": 1.4, "pasos": 1,
        "acomp": [("dron", "organo")],
        "perc": [("latido", "x.x.............")],
    },
    "independencia": {
        "bpm": 96, "compas": 4, "raiz": 55, "escala": [0, 2, 3, 5, 7, 8, 11], "progresion": [0, 3, 4, 0],
        "melodia": "clave", "densidad": 0.65, "nivel": 1.8, "pasos": 2,
        "acomp": [("alberti", "clave")],
        "perc": [],
    },
    "reforma": {
        "bpm": 72, "compas": 3, "raiz": 62, "escala": [0, 2, 3, 5, 7, 8, 10], "progresion": [0, 5, 3, 4],
        "melodia": "piano", "densidad": 0.55, "nivel": 1.1, "pasos": 2,
        "acomp": [("vals", "piano")],
        "perc": [],
    },
    "porfiriato": {
        "bpm": 76, "compas": 4, "raiz": 60, "escala": [0, 2, 3, 5, 7, 8, 10], "progresion": [0, 3, 5, 4],
        "melodia": "piano", "densidad": 0.5, "nivel": 1.1, "pasos": 2,
        "acomp": [("habanera", "bajo"), ("acorde", "cuerdas")],
        "perc": [("escobilla", "..o...o...o...o.")],
    },
    "baronesa": {
        "bpm": 84, "compas": 3, "raiz": 65, "escala": [0, 2, 4, 5, 7, 9, 11], "progresion": [0, 5, 3, 4],
        "melodia": "cuerdas", "densidad": 0.6, "nivel": 1.1, "pasos": 2,
        "acomp": [("vals", "piano")],
        "perc": [],
    },
}


# ==============================================================================
# 2. MOTOR DE SÍNTESIS MUSICAL Y PAISAJE SONORO (PORT FIEL DE MUSICA.JS)
# ==============================================================================

def _semilla_prng(texto: str) -> Callable[[], float]:
    """PRNG determinista idéntico a `semilla(texto)` en `musica.js`."""
    h = 2166136261
    for c in texto:
        h = ((h ^ ord(c)) * 16777619) & 0xFFFFFFFF

    def _next() -> float:
        nonlocal h
        h = (h + 0x6D2B79F5) & 0xFFFFFFFF
        t = h
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return _next


def _midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def _adsr_envelope(
    n_samples: int,
    sr: int,
    attack: float,
    sustain_dur: float,
    release: float,
    peak: float,
) -> np.ndarray:
    """Envolvente ataque lineal + sostén + caída exponencial igual que `env()` en `musica.js`."""
    env = np.zeros(n_samples, dtype=np.float32)
    n_att = max(1, int(attack * sr))
    n_sus = max(0, int(sustain_dur * sr))
    n_rel = max(1, int(release * sr))

    idx1 = min(n_samples, n_att)
    env[:idx1] = np.linspace(0.0, peak, idx1, dtype=np.float32)

    idx2 = min(n_samples, n_att + n_sus)
    if idx2 > idx1:
        env[idx1:idx2] = peak

    idx3 = min(n_samples, idx2 + n_rel)
    if idx3 > idx2:
        t_rel = np.linspace(0.0, 1.0, idx3 - idx2, dtype=np.float32)
        env[idx2:idx3] = peak * ((0.0001 / max(peak, 1e-5)) ** t_rel)
    return env


def _synth_note(
    inst: str,
    freq: float,
    dur: float,
    vol: float,
    sr: int = 44100,
) -> np.ndarray:
    """Sintetiza una nota del instrumento indicado según `INSTRUMENTOS` de `musica.js`."""
    if inst in ("flauta", "ocarina"):
        tail = 0.35
        total_dur = max(0.08, dur + tail)
        n = int(total_dur * sr)
        t = np.arange(n, dtype=np.float32) / sr
        vib_depth = 0.006 if inst == "flauta" else 0.004
        vib_env = np.clip((t - 0.2) / 0.25, 0.0, 1.0)
        phase = 2.0 * np.pi * freq * t + (vib_depth * freq / 5.2) * vib_env * np.sin(2.0 * np.pi * 5.2 * t)
        env = _adsr_envelope(n, sr, 0.08 if inst == "flauta" else 0.12, max(0.0, dur - 0.1), tail, 0.21 * vol)
        sig = np.sin(phase) * env
        if inst == "flauta":
            # Segundo armónico suave + soplo inicial
            sig += 0.12 * np.sin(2.0 * phase) * env
            n_breath = min(n, int(0.09 * sr))
            noise = np.random.uniform(-1.0, 1.0, n_breath).astype(np.float32)
            sig[:n_breath] += noise * _adsr_envelope(n_breath, sr, 0.01, 0.02, 0.06, 0.035 * vol)
        return sig

    if inst == "campana":
        total_dur = 2.5
        n = int(total_dur * sr)
        t = np.arange(n, dtype=np.float32) / sr
        sig = np.zeros(n, dtype=np.float32)
        for mult, amp in ((1.0, 0.22), (2.76, 0.07), (5.4, 0.035)):
            env = _adsr_envelope(n, sr, 0.004, 0.0, 2.3 / (mult ** 0.3), amp * vol)
            sig += np.sin(2.0 * np.pi * (freq * mult) * t) * env
        return sig

    if inst in ("piano", "arpa", "clave"):
        caida = min(2.6, 0.6 + 220.0 / max(freq, 40.0)) if inst == "piano" else (1.2 if inst == "arpa" else 0.85)
        total_dur = max(0.15, dur + caida)
        n = int(total_dur * sr)
        t = np.arange(n, dtype=np.float32) / sr
        sig = np.zeros(n, dtype=np.float32)
        partials = (
            ((1.0, 0.24), (2.0, 0.08), (3.0, 0.03), (4.0, 0.014))
            if inst == "piano"
            else (((1.0, 0.16), (2.0, 0.05), (3.0, 0.02)) if inst == "arpa" else ((1.0, 0.18), (2.0, 0.09), (3.0, 0.05), (4.0, 0.025)))
        )
        for mult, amp in partials:
            env = _adsr_envelope(n, sr, 0.003, min(dur, 0.08) if inst == "piano" else 0.0, caida / (mult ** 0.4), amp * vol)
            sig += np.sin(2.0 * np.pi * (freq * mult) * t) * env
        return sig

    if inst in ("cuerdas", "coro", "organo", "pad"):
        tail = 0.8 if inst != "pad" else 1.6
        total_dur = max(0.25, dur + tail)
        n = int(total_dur * sr)
        t = np.arange(n, dtype=np.float32) / sr
        att = 0.35 if inst == "cuerdas" else (0.45 if inst == "coro" else (0.25 if inst == "organo" else 0.8))
        peak = (0.11 if inst == "cuerdas" else (0.12 if inst == "coro" else (0.10 if inst == "organo" else 0.08))) * vol
        env = _adsr_envelope(n, sr, att, max(0.0, dur - att * 0.8), tail, peak)
        sig = np.zeros(n, dtype=np.float32)
        for det_cents in (-7.0, 0.0, 7.0):
            f_det = freq * (2.0 ** (det_cents / 1200.0))
            vib = 1.0 + 0.003 * np.sin(2.0 * np.pi * 5.0 * t)
            sig += (
                0.65 * np.sin(2.0 * np.pi * f_det * vib * t)
                + 0.25 * np.sin(2.0 * np.pi * (2.0 * f_det) * t)
                + 0.10 * np.sin(2.0 * np.pi * (3.0 * f_det) * t)
            ) / 3.0
        return sig * env

    if inst in ("bajo", "pulso"):
        total_dur = max(0.15, dur + 0.35)
        n = int(total_dur * sr)
        t = np.arange(n, dtype=np.float32) / sr
        env = _adsr_envelope(n, sr, 0.008, dur * 0.5, 0.35, 0.22 * vol)
        return (np.sin(2.0 * np.pi * freq * t) + 0.22 * np.sin(2.0 * np.pi * 2.0 * freq * t)) * env

    if inst == "teponaztli":
        n = int(0.45 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        f_glide = freq * (1.0 + 0.03 * np.exp(-t / 0.03))
        env = _adsr_envelope(n, sr, 0.002, 0.0, 0.35, 0.22 * vol)
        return np.sin(2.0 * np.pi * f_glide * t) * env

    if inst in ("huehuetl", "latido"):
        n = int((0.65 if inst == "huehuetl" else 0.32) * sr)
        t = np.arange(n, dtype=np.float32) / sr
        f0, f1 = (95.0, 48.0) if inst == "huehuetl" else (70.0, 40.0)
        f_inst = f1 + (f0 - f1) * np.exp(-t / 0.09)
        phase = 2.0 * np.pi * np.cumsum(f_inst) / sr
        env = _adsr_envelope(n, sr, 0.003, 0.0, 0.55 if inst == "huehuetl" else 0.22, 0.42 * vol)
        return np.sin(phase).astype(np.float32) * env

    if inst in ("sonaja", "escobilla"):
        dur_p = 0.09 if inst == "sonaja" else 0.18
        n = int(dur_p * sr)
        noise = np.diff(np.random.uniform(-1.0, 1.0, n + 1).astype(np.float32))
        env = _adsr_envelope(n, sr, 0.01, 0.0, dur_p - 0.01, (0.045 if inst == "sonaja" else 0.035) * vol)
        return noise * env

    # Fallback piano suave
    n = int(max(0.2, dur + 0.4) * sr)
    t = np.arange(n, dtype=np.float32) / sr
    return np.sin(2.0 * np.pi * freq * t) * _adsr_envelope(n, sr, 0.01, dur * 0.5, 0.4, 0.18 * vol)


def _generar_tema(rnd: Callable[[], float], corcheas: int, largo: int, pasos: int = 2) -> List[dict]:
    ritmos = (
        [[2, 2, 2, 2], [3, 1, 2, 2], [2, 1, 1, 4], [4, 2, 2], [1, 1, 2, 4], [2, 2, 4], [6, 2], [3, 3, 2]]
        if corcheas == 8
        else [[2, 2, 2], [3, 1, 2], [4, 2], [2, 4], [1, 1, 2, 2], [6]]
    )
    notas: List[dict] = []
    grado = [0, 2, 4][int(rnd() * 3) % 3]
    paso = 0
    for _ in range(2):
        patron = ritmos[int(rnd() * len(ritmos)) % len(ritmos)]
        for dur in patron:
            notas.append({"paso": paso, "dur": dur, "grado": grado})
            paso += dur
            salto = (-1 if rnd() < 0.5 else 1) if rnd() < 0.75 else round((rnd() - 0.5) * 2 * (pasos + 1))
            grado = max(-2, min(largo + 3, grado + salto))
    notas[-1]["grado"] = 0 if rnd() < 0.5 else largo
    return notas


def _variacion_tema(rnd: Callable[[], float], notas: List[dict]) -> List[dict]:
    out = []
    for i, x in enumerate(notas):
        if i < len(notas) - 2:
            out.append(dict(x))
        else:
            out.append({**x, "grado": x["grado"] + (-1 if rnd() < 0.5 else 2)})
    return out


def synthesize_series_music_and_ambience(
    slug: str,
    duration_sec: float,
    speech_intervals: Optional[List[Tuple[float, float]]] = None,
    sr: int = 44100,
) -> np.ndarray:
    """Genera el buffer estéreo (N, 2) en float32 de la partitura + atmósfera sonora de la serie."""
    p = PARTITURAS.get(slug, PARTITURAS["caricateri"])
    amb = AMBIENTES.get(slug, AMBIENTES["caricateri"])
    rnd = _semilla_prng(slug)

    n_total = int(math.ceil((duration_sec + 3.0) * sr))
    mix_l = np.zeros(n_total, dtype=np.float32)
    mix_r = np.zeros(n_total, dtype=np.float32)

    corchea = 30.0 / p["bpm"]
    corcheas_compas = p["compas"] * 2
    dur_compas = corchea * corcheas_compas
    escala = p["escala"]
    L = len(escala)

    def nota_midi(grado: int, octava: int = 0) -> float:
        return p["raiz"] + 12 * ((grado // L) + octava) + escala[grado % L]

    tema_a = _generar_tema(rnd, corcheas_compas, L, p.get("pasos", 2))
    tema_b = _generar_tema(rnd, corcheas_compas, L, p.get("pasos", 2))
    tema_a2 = _variacion_tema(rnd, tema_a)
    tema_b2 = _variacion_tema(rnd, tema_b)

    def mezclar(inst: str, t_start: float, midi: float, dur: float, vol: float = 1.0, pan: float = 0.0):
        if t_start < 0 or t_start >= duration_sec + 1.0:
            return
        sig = _synth_note(inst, _midi_to_hz(midi), dur, vol * p.get("nivel", 1.0), sr=sr)
        i0 = int(t_start * sr)
        i1 = min(n_total, i0 + len(sig))
        if i1 <= i0:
            return
        seg = sig[: i1 - i0]
        gain_l = math.cos((pan + 1.0) * math.pi / 4.0)
        gain_r = math.sin((pan + 1.0) * math.pi / 4.0)
        mix_l[i0:i1] += seg * gain_l
        mix_r[i0:i1] += seg * gain_r

    # Programar compases igual que `motor(ctx, slug)` en `musica.js`
    frase_actual: Optional[List[dict]] = None
    i_compas = 0
    t_cursor = 0.1
    progresion = p["progresion"]

    while t_cursor < duration_sec + 0.5:
        g = progresion[i_compas % len(progresion)]
        previo = progresion[(i_compas - 1) % len(progresion)]
        tonos = [g, g + 2, g + 4]

        for tipo, inst in p["acomp"]:
            if tipo == "dron":
                if g != previo or i_compas == 0:
                    mezclar(inst, t_cursor, nota_midi(g, -1), dur_compas * 1.05, 0.85, pan=-0.15)
                    mezclar(inst, t_cursor, nota_midi(g + (3 if L == 5 else 4), -1), dur_compas * 1.05, 0.55, pan=0.15)
                else:
                    mezclar(inst, t_cursor, nota_midi(g, -1), dur_compas * 1.05, 0.6, pan=0.0)
            elif tipo == "acorde":
                for idx_t, x in enumerate(tonos):
                    mezclar(inst, t_cursor, nota_midi(x, -1), dur_compas * 0.98, 0.52, pan=(idx_t - 1) * 0.25)
            elif tipo == "ostinato":
                for k in range(corcheas_compas):
                    mezclar(inst, t_cursor + k * corchea, nota_midi(g, -2), corchea * 0.8, 0.95 if k % 4 == 0 else 0.52)
            elif tipo == "arpegio":
                for k in range(corcheas_compas):
                    salto_oct = L if (3 <= k < 6) else 0
                    midi_arp = nota_midi(tonos[k % 3] + salto_oct, -1)
                    mezclar(inst, t_cursor + k * corchea, midi_arp, corchea, 0.58, pan=math.sin(k) * 0.3)
                    if inst == "pulso":
                        # Eco característico de UapeaniBot
                        mezclar(inst, t_cursor + (k + 1.5) * corchea, midi_arp, corchea * 0.8, 0.22, pan=-math.sin(k) * 0.4)
            elif tipo == "alberti":
                for k, x in enumerate([0, 2, 1, 2]):
                    mezclar(inst, t_cursor + k * corchea, nota_midi(tonos[x], -1), corchea, 0.48, pan=-0.2)
                    mezclar(inst, t_cursor + (k + 4) * corchea, nota_midi(tonos[x], -1), corchea, 0.44, pan=0.2)
            elif tipo == "vals":
                mezclar(inst, t_cursor, nota_midi(g, -2), corchea * 2.0, 0.78, pan=-0.15)
                for k in (2, 4):
                    for x in tonos:
                        mezclar(inst, t_cursor + k * corchea, nota_midi(x, -1), corchea * 1.6, 0.34, pan=0.15)
            elif tipo == "habanera":
                for k, d_grado, v_hab in ((0, 0, 1.0), (3, 4, 0.6), (4, 0, 0.8), (6, 4, 0.7)):
                    mezclar(inst, t_cursor + k * corchea / 2.0, nota_midi(g + d_grado, -2), corchea * 1.4, v_hab)

        for inst, patron in p["perc"]:
            for k, c in enumerate(patron):
                if c != "." and k < corcheas_compas * 2:
                    midi_p = (p["raiz"] - 5) if (k % 2 == 1) else p["raiz"]
                    mezclar(inst, t_cursor + k * corchea / 2.0, midi_p, 0.1, 0.95 if c == "x" else 0.48, pan=0.1 if k % 2 else -0.1)

        ciclo = i_compas % 16
        par = ciclo - (ciclo % 2)
        if ciclo % 2 == 0:
            mapa_frases = {0: tema_a, 2: tema_b, 4: tema_a2, 6: tema_b2, 12: tema_a2 if p["densidad"] >= 0.6 else None}
            frase_actual = mapa_frases.get(par)
            if frase_actual in (tema_b, tema_b2) and rnd() > p["densidad"] + 0.3:
                frase_actual = None

        if frase_actual:
            desde = (ciclo % 2) * corcheas_compas
            for x in frase_actual:
                if desde <= x["paso"] < desde + corcheas_compas:
                    t_nota = t_cursor + (x["paso"] - desde) * corchea + (rnd() - 0.5) * 0.015
                    mezclar(
                        p["melodia"],
                        t_nota,
                        nota_midi(x["grado"], 0),
                        x["dur"] * corchea * 0.95,
                        0.85 + rnd() * 0.15,
                        pan=0.08 * math.sin(x["paso"]),
                    )

        i_compas += 1
        t_cursor += dur_compas

    # Reverberación estéreo suave (aproximación por retardos múltiples exponenciales de sala 2.8 s)
    for delay_sec, gain in ((0.07, 0.22), (0.16, 0.15), (0.31, 0.10), (0.58, 0.06), (1.05, 0.03)):
        d = int(delay_sec * sr)
        if d < n_total:
            mix_l[d:] += mix_r[:-d] * gain
            mix_r[d:] += mix_l[:-d] * gain

    # Paisaje sonoro sutil según `atmosfera.js` (fuego, lluvia/tormenta, viento, inframundo, reloj, etc.)
    rng = np.random.default_rng(abs(hash(slug)) % (2**32))
    sonido = amb.get("sonido", "fuego")
    white = rng.uniform(-1.0, 1.0, n_total).astype(np.float32)
    brown = np.cumsum(white * 0.015).astype(np.float32)
    # Eliminar deriva DC con media móvil
    brown -= np.convolve(brown, np.ones(2048, dtype=np.float32) / 2048.0, mode="same")
    max_b = float(np.max(np.abs(brown)) or 1.0)
    brown /= max_b

    amb_l = brown * 0.035
    amb_r = np.roll(brown, 800) * 0.035
    if sonido == "fuego":
        # Chisporroteo cálido de brasas
        for _ in range(int(duration_sec * 3.5)):
            idx = int(rng.integers(0, max(1, n_total - 1200)))
            crackle = rng.uniform(-1.0, 1.0, 600).astype(np.float32) * np.exp(-np.linspace(0, 5, 600, dtype=np.float32))
            amb_l[idx : idx + 600] += crackle * 0.04
            amb_r[idx : idx + 600] += crackle * 0.035
    elif sonido in ("tormenta", "lluvia-suave"):
        rain = (white[1:] - 0.7 * white[:-1]) * (0.025 if sonido == "tormenta" else 0.015)
        amb_l[: len(rain)] += rain
        amb_r[: len(rain)] += np.roll(rain, 300)

    n_exact = int(duration_sec * sr)
    stereo = np.stack([mix_l[:n_exact] + amb_l[:n_exact], mix_r[:n_exact] + amb_r[:n_exact]], axis=1)

    # Atenuación suave (ducking: `atenuar(true)` en `musica.js` baja la música cuando hay voz hablada)
    duck_curve = np.ones(n_exact, dtype=np.float32) * 0.75
    if speech_intervals:
        for t0, t1 in speech_intervals:
            i0 = max(0, int(t0 * sr))
            i1 = min(n_exact, int(t1 * sr))
            if i1 > i0:
                duck_curve[i0:i1] = 0.24
        # Suavizar transiciones de ducking (ventana de 0.35 s)
        win_len = max(1, int(0.35 * sr))
        kernel = np.ones(win_len, dtype=np.float32) / win_len
        duck_curve = np.convolve(duck_curve, kernel, mode="same")

    # Fade in (1.2 s) y fade out (1.8 s)
    fade_in = min(n_exact, int(1.2 * sr))
    fade_out = min(n_exact, int(1.8 * sr))
    if fade_in > 0:
        duck_curve[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
    if fade_out > 0:
        duck_curve[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)

    stereo *= duck_curve[:, None]
    peak_val = float(np.max(np.abs(stereo)) or 1.0)
    if peak_val > 0.92:
        stereo *= 0.92 / peak_val
    return stereo


# ==============================================================================
# 3. NARRACIÓN NEURONAL EN ESPAÑOL DE MÉXICO (EDGE-TTS + REPARTO DRAMATIZADO)
# ==============================================================================

PERS_FEMENINOS = {
    "INÉS", "BEATRIZ", "ISABEL", "LEONOR", "LUZ", "CARMEN", "RAQUEL", "ESTHER",
    "MERCEDES", "DOLORES", "SOLEDAD", "MADRE", "MUJER", "NIÑA", "ABUELA", "SEÑORA",
    "VIUDA", "MONJA", "PRIORA", "HERMANA", "CONSTANZA", "ROSARIO", "PILAR",
    "CONSUELO", "AMPARO", "ASUNCIÓN", "PAZAPEME", "XOCHITZIN", "QUIYAUHTZIN",
    "TEYOLIA", "TONALLI", "KILLA", "CITLALI", "SIGRID", "UACÚXANE", "CATALINA",
    "ELVIRA", "JACINTA", "MAGDALENA", "ANA", "BARONESA", "MICTECACÍHUATL",
}


def detectar_genero_personaje(speaker: Optional[str]) -> str:
    if not speaker:
        return "narrador"
    primera = speaker.strip().upper().split()[0].rstrip(":,.")
    if primera in PERS_FEMENINOS:
        return "f"
    if primera.endswith(("ISTA", "GUARDIA", "CENTINELA", "POETA", "PADRE", "HOMBRE")):
        return "m"
    return "f" if primera.endswith("A") else "m"


def parametros_voz_personaje(speaker: Optional[str]) -> Tuple[str, str, str]:
    """Devuelve `(voice, rate, pitch)` en `edge-tts` según si es narrador o personaje."""
    rol = detectar_genero_personaje(speaker)
    if rol == "narrador":
        return ("es-MX-JorgeNeural", "-4%", "-2Hz")
    h = sum(ord(c) * 31 for c in (speaker or "")) % 5
    if rol == "f":
        rate_offset = -2 + h * 2
        pitch_offset = -2 + h * 2
        return ("es-MX-DaliaNeural", f"{rate_offset:+d}%", f"{pitch_offset:+d}Hz")
    else:
        rate_offset = -3 + h * 2
        pitch_offset = -6 + h * 2
        return ("es-MX-JorgeNeural", f"{rate_offset:+d}%", f"{pitch_offset:+d}Hz")


async def _edge_tts_to_file(text: str, out_mp3: str, voice: str, rate: str, pitch: str) -> None:
    import edge_tts

    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await comm.save(out_mp3)


def synthesize_speech_to_pcm(
    text: str,
    speaker: Optional[str] = None,
    sr: int = 44100,
    remote_worker_url: Optional[str] = None,
) -> np.ndarray:
    """Sintetiza un parlamento en español de México y devuelve muestras mono float32 a `sr` Hz."""
    clean_text = " ".join(text.replace("—", " ").split()).strip()
    if not clean_text:
        return np.zeros(int(0.2 * sr), dtype=np.float32)

    voice, rate, pitch = parametros_voz_personaje(speaker)

    with tempfile.TemporaryDirectory() as tmpdir:
        mp3_path = os.path.join(tmpdir, "tts.mp3")
        wav_path = os.path.join(tmpdir, "tts.wav")
        ok = False

        # 1. Intentar con `edge-tts` local
        try:
            asyncio.run(_edge_tts_to_file(clean_text, mp3_path, voice, rate, pitch))
            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 256:
                ok = True
        except Exception:
            ok = False

        # 2. Si estamos en un entorno sin salida directa a Edge pero con `remote_worker_url` (Colab), pedir `/tts`
        if not ok and remote_worker_url:
            try:
                import requests

                resp = requests.post(
                    f"{remote_worker_url.rstrip('/')}/tts",
                    json={"text": clean_text, "speaker": speaker},
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw = base64.b64decode(data["audio_base64"])
                    with open(mp3_path, "wb") as f:
                        f.write(raw)
                    ok = os.path.getsize(mp3_path) > 256
            except Exception:
                ok = False

        if ok:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", mp3_path,
                    "-ac", "1", "-ar", str(sr), "-f", "s16le", wav_path,
                ],
                check=True,
            )
            pcm_i16 = np.fromfile(wav_path, dtype=np.int16)
            pcm = pcm_i16.astype(np.float32) / 32768.0
            # Normalizar nivel de voz a pico 0.88
            peak = float(np.max(np.abs(pcm)) or 1.0)
            return (pcm * (0.88 / peak)).astype(np.float32)

        # 3. Fallback offline determinista (cadencia silábica suave si no hubiera red)
        words = clean_text.split()
        dur = max(1.8, min(9.0, len(words) * 0.36))
        n = int(dur * sr)
        t = np.arange(n, dtype=np.float32) / sr
        f0 = 195.0 if detectar_genero_personaje(speaker) == "f" else 118.0
        syl_env = 0.5 + 0.5 * np.sin(2.0 * np.pi * 4.2 * t)
        carrier = (
            0.55 * np.sin(2.0 * np.pi * f0 * t)
            + 0.30 * np.sin(2.0 * np.pi * (2.0 * f0) * t)
            + 0.15 * np.sin(2.0 * np.pi * (3.0 * f0) * t)
        )
        return (carrier * syl_env * _adsr_envelope(n, sr, 0.08, dur - 0.25, 0.17, 0.35)).astype(np.float32)


# ==============================================================================
# 4. MOTOR VISUAL: CÁMARA KEN BURNS + PARTÍCULAS DE ATMÓSFERA + SUBTÍTULOS CINE
# ==============================================================================

def _hex_to_bgr(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (200, 200, 200)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (200, 200, 200)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [
            "C:/Windows/Fonts/georgiab.ttf",
            "C:/Windows/Fonts/timesbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            "C:/Windows/Fonts/georgia.ttf",
            "C:/Windows/Fonts/times.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _prepare_16_9_canvas(img: Image.Image, width: int = 1280, height: int = 720) -> np.ndarray:
    """Convierte cualquier imagen (retrato vertical, cuadrada o panorámica) en un lienzo 16:9
    cinematográfico sin deformarla: si es vertical/cuadrada, crea un fondo desenfocado atmosférico
    con iluminación lateral y encuadra la obra con nitidez; si ya es panorámica, hace cover 16:9."""
    img = img.convert("RGB")
    src_w, src_h = img.size
    target_ratio = width / height
    src_ratio = src_w / max(1, src_h)

    if abs(src_ratio - target_ratio) <= 0.22:
        # Recorte centrado 16:9 (cover)
        scale = max(width / src_w, height / src_h)
        nw, nh = int(round(src_w * scale)), int(round(src_h * scale))
        resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
        x0 = max(0, (nw - width) // 2)
        y0 = max(0, (nh - height) // 2)
        cropped = resized.crop((x0, y0, x0 + width, y0 + height))
        return cv2.cvtColor(np.array(cropped), cv2.COLOR_RGB2BGR)

    # Lienzo compuesto: fondo expandido con desenfoque gaussiano profundo + imagen principal
    bg_scale = max(width / src_w, height / src_h)
    bg_w, bg_h = int(round(src_w * bg_scale)), int(round(src_h * bg_scale))
    bg = img.resize((bg_w, bg_h), Image.Resampling.BICUBIC)
    bx0, by0 = (bg_w - width) // 2, (bg_h - height) // 2
    bg_crop = np.array(bg.crop((bx0, by0, bx0 + width, by0 + height)))
    bg_bgr = cv2.cvtColor(bg_crop, cv2.COLOR_RGB2BGR)
    bg_bgr = cv2.GaussianBlur(bg_bgr, (65, 65), 24)
    bg_bgr = (bg_bgr.astype(np.float32) * 0.42).astype(np.uint8)

    fg_scale = min((width * 0.86) / src_w, (height * 0.94) / src_h)
    fg_w, fg_h = int(round(src_w * fg_scale)), int(round(src_h * fg_scale))
    fg = cv2.cvtColor(np.array(img.resize((fg_w, fg_h), Image.Resampling.LANCZOS)), cv2.COLOR_RGB2BGR)

    x_off = (width - fg_w) // 2
    y_off = (height - fg_h) // 2

    # Borde suave (feathering de 14 px) para fundir con el fondo atmosférico
    mask = np.ones((fg_h, fg_w), dtype=np.float32)
    border = min(16, fg_w // 12, fg_h // 12)
    if border > 1:
        ramp = np.linspace(0.0, 1.0, border, dtype=np.float32)
        mask[:border, :] *= ramp[:, None]
        mask[-border:, :] *= ramp[::-1, None]
        mask[:, :border] *= ramp[None, :]
        mask[:, -border:] *= ramp[None, ::-1]

    roi = bg_bgr[y_off : y_off + fg_h, x_off : x_off + fg_w].astype(np.float32)
    blended = roi * (1.0 - mask[:, :, None]) + fg.astype(np.float32) * mask[:, :, None]
    bg_bgr[y_off : y_off + fg_h, x_off : x_off + fg_w] = np.clip(blended, 0, 255).astype(np.uint8)
    return bg_bgr


def _apply_ken_burns(
    base_bgr: np.ndarray,
    progress: float,
    motion_mode: int,
) -> np.ndarray:
    """Aplica movimiento de cámara cinematográfico sub-píxel (`cv2.warpAffine`) sin saltos."""
    h, w = base_bgr.shape[:2]
    # Suavizado cosenoidal (ease-in-out)
    p = 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, progress)))

    mode = motion_mode % 5
    if mode == 0:  # Zoom in lento hacia el centro-superior
        zoom = 1.02 + 0.11 * p
        tx, ty = 0.0, -0.02 * h * p
    elif mode == 1:  # Zoom out revelando la escena
        zoom = 1.13 - 0.11 * p
        tx, ty = 0.0, 0.015 * h * (1.0 - p)
    elif mode == 2:  # Paneo cinematográfico izquierda -> derecha
        zoom = 1.10
        tx, ty = (-0.04 + 0.08 * p) * w, 0.0
    elif mode == 3:  # Paneo derecha -> izquierda con ligero ascenso
        zoom = 1.10
        tx, ty = (0.04 - 0.08 * p) * w, -0.015 * h * p
    else:  # Dolly diagonal dramático
        zoom = 1.04 + 0.09 * p
        tx, ty = (-0.025 + 0.05 * p) * w, (-0.02 + 0.04 * p) * h

    cx, cy = w * 0.5 + tx, h * 0.5 + ty
    crop_w, crop_h = w / zoom, h / zoom
    x0 = cx - crop_w * 0.5
    y0 = cy - crop_h * 0.5

    # Matriz afín de destino (w, h) -> origen (x0..x0+crop_w, y0..y0+crop_h)
    sx = zoom
    sy = zoom
    m = np.array(
        [
            [sx, 0.0, -x0 * sx],
            [0.0, sy, -y0 * sy],
        ],
        dtype=np.float32,
    )
    return cv2.warpAffine(base_bgr, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)


class AtmosphereParticles:
    """Motor de partículas por serie (port directo de `TIPOS` en `atmosfera.js`)."""

    def __init__(self, slug: str, width: int = 1280, height: int = 720):
        self.slug = slug
        self.amb = AMBIENTES.get(slug, AMBIENTES["caricateri"])
        self.kind = self.amb.get("particulas", "brasas")
        self.w = width
        self.h = height
        self.color_luz = _hex_to_bgr(self.amb["luz"])
        self.color_acento = _hex_to_bgr(self.amb["acento"])
        self.rng = np.random.default_rng(abs(hash(slug)) % (2**32))
        self.items: List[dict] = []
        self._init_particles()

    def _init_particles(self):
        counts = {
            "brasas": 42, "lluvia": 95, "viento": 28, "almas": 32,
            "datos": 40, "velas": 26, "tinta": 24, "niebla": 10,
            "humo": 14, "polvo": 30,
        }
        n = counts.get(self.kind, 30)
        for _ in range(n):
            self.items.append(
                {
                    "x": float(self.rng.uniform(0, self.w)),
                    "y": float(self.rng.uniform(0, self.h)),
                    "r": float(self.rng.uniform(1.5, 4.2)),
                    "vx": float(self.rng.uniform(-0.8, 0.8)),
                    "vy": float(self.rng.uniform(-1.8, -0.5)),
                    "phase": float(self.rng.uniform(0, 6.28)),
                    "sub": "alma" if self.rng.random() < 0.55 else "petalo",
                }
            )

    def render_overlay(self, frame_bgr: np.ndarray, t_sec: float) -> np.ndarray:
        out = frame_bgr.copy()
        overlay = out.copy()

        if self.kind == "lluvia":
            for p in self.items:
                x = int((p["x"] + t_sec * 110.0) % (self.w + 60)) - 30
                y = int((p["y"] + t_sec * 520.0 * (0.8 + 0.4 * (p["r"] / 4.2))) % (self.h + 40)) - 20
                length = int(12 + p["r"] * 3.5)
                cv2.line(overlay, (x, y), (x + length // 4, y + length), self.color_luz, 1, cv2.LINE_AA)
            cv2.addWeighted(overlay, 0.22, out, 0.78, 0, out)
            # Relámpago ocasional
            if math.sin(t_sec * 1.7) > 0.985:
                out = cv2.addWeighted(out, 0.82, np.full_like(out, self.color_luz), 0.18, 0)
            return out

        if self.kind == "viento":
            for p in self.items:
                x = int((p["x"] + t_sec * (55.0 + p["r"] * 18.0)) % (self.w + 180)) - 90
                y = int((p["y"] + math.sin(t_sec * 1.2 + p["phase"]) * 18.0) % self.h)
                length = int(45 + p["r"] * 22)
                cv2.line(overlay, (x, y), (x + length, y), self.color_luz, 1, cv2.LINE_AA)
            cv2.addWeighted(overlay, 0.16, out, 0.84, 0, out)
            return out

        if self.kind == "datos":
            pts = []
            for p in self.items:
                x = int((p["x"] + p["vx"] * t_sec * 18.0) % self.w)
                y = int((p["y"] - abs(p["vy"]) * t_sec * 16.0) % self.h)
                pts.append((x, y))
                col = self.color_luz if math.sin(p["phase"] * 3.0) > 0 else self.color_acento
                cv2.rectangle(overlay, (x - 2, y - 2), (x + 2, y + 2), col, -1)
            for i in range(len(pts)):
                for j in range(i + 1, min(len(pts), i + 6)):
                    dist = math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
                    if dist < 115:
                        cv2.line(overlay, pts[i], pts[j], self.color_luz, 1, cv2.LINE_AA)
            cv2.addWeighted(overlay, 0.24, out, 0.76, 0, out)
            return out

        # Brasas, almas, velas, tinta, polvo, niebla, humo
        for p in self.items:
            vy = -28.0 if self.kind in ("brasas", "almas", "velas", "humo") else 14.0
            if self.kind == "almas" and p["sub"] == "petalo":
                vy = 24.0
            x = int((p["x"] + math.sin(t_sec * 1.4 + p["phase"]) * 22.0) % self.w)
            y = int((p["y"] + vy * t_sec) % self.h)
            r = max(2, int(p["r"]))
            col = self.color_acento if (self.kind == "almas" and p["sub"] == "alma") else self.color_luz
            cv2.circle(overlay, (x, y), r + 2, self.color_acento, -1, cv2.LINE_AA)
            cv2.circle(overlay, (x, y), r, col, -1, cv2.LINE_AA)

        alpha = 0.34 if self.kind in ("brasas", "almas") else 0.20
        cv2.addWeighted(overlay, alpha, out, 1.0 - alpha, 0, out)
        return out


def _wrap_text(text: str, max_chars: int = 68) -> List[str]:
    words = text.split()
    lines: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for w in words:
        if cur and cur_len + 1 + len(w) > max_chars:
            lines.append(" ".join(cur))
            cur = [w]
            cur_len = len(w)
        else:
            cur.append(w)
            cur_len += len(w) + (1 if cur_len > 0 else 0)
    if cur:
        lines.append(" ".join(cur))
    return lines[:3]


def _draw_hud_and_subtitles(
    frame_bgr: np.ndarray,
    slug: str,
    scene_heading: Optional[str],
    speaker: Optional[str],
    subtitle_text: Optional[str],
    scene_elapsed: float,
) -> np.ndarray:
    """Dibuja cintillo de escena, insignia de hablante y subtítulo cinematográfico en alta definición."""
    amb = AMBIENTES.get(slug, AMBIENTES["caricateri"])
    h, w = frame_bgr.shape[:2]

    # Viñeta oscura suave en la parte inferior para lectura impecable
    gradient = np.linspace(1.0, 0.38, int(h * 0.32), dtype=np.float32)[:, None, None]
    y_grad = h - int(h * 0.32)
    frame_bgr[y_grad:, :, :] = (frame_bgr[y_grad:, :, :].astype(np.float32) * gradient).astype(np.uint8)

    pil_img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    acento_rgb = _hex_to_rgb(amb["acento"])
    luz_rgb = _hex_to_rgb(amb["luz"])
    papel_rgb = _hex_to_rgb(amb["papel"])

    # 1. Cintillo superior izquierdo: Serie y encabezado de escena (primeros 4.5 s de cada escena)
    font_small = _load_font(17, bold=True)
    font_heading = _load_font(19, bold=False)

    badge_text = f"{amb['codigo']} · {amb['titulo'].upper()}"
    draw.rounded_rectangle((36, 28, 36 + len(badge_text) * 10 + 28, 62), radius=6, fill=(12, 10, 10, 175), outline=(*acento_rgb, 190), width=1)
    draw.text((50, 35), badge_text, font=font_small, fill=(*luz_rgb, 245))

    if scene_heading and scene_elapsed < 5.5:
        alpha_h = int(235 * min(1.0, (5.5 - scene_elapsed) / 1.0))
        heading_clean = scene_heading.strip().upper()
        box_w = min(w - 80, len(heading_clean) * 10 + 36)
        draw.rounded_rectangle((36, 70, 36 + box_w, 106), radius=6, fill=(15, 12, 10, int(alpha_h * 0.72)))
        draw.rectangle((36, 70, 41, 106), fill=(*acento_rgb, alpha_h))
        draw.text((52, 77), heading_clean[:78], font=font_heading, fill=(*papel_rgb, alpha_h))

    # 2. Subtítulo e indicador de personaje hablante en la parte inferior
    if subtitle_text:
        font_sub = _load_font(26, bold=False)
        font_spk = _load_font(20, bold=True)
        lines = _wrap_text(subtitle_text, max_chars=64)
        line_h = 34
        total_h = len(lines) * line_h + (34 if speaker else 0) + 24
        box_y0 = h - total_h - 34
        box_y1 = h - 28
        draw.rounded_rectangle(
            (110, box_y0, w - 110, box_y1),
            radius=12,
            fill=(10, 8, 8, 188),
            outline=(*acento_rgb, 140),
            width=1,
        )

        y_text = box_y0 + 12
        if speaker:
            spk_label = f"◆ {speaker.upper()}"
            bbox_s = draw.textbbox((0, 0), spk_label, font=font_spk)
            sw = bbox_s[2] - bbox_s[0]
            draw.text(((w - sw) // 2, y_text), spk_label, font=font_spk, fill=(*luz_rgb, 255))
            y_text += 32

        for line in lines:
            bbox_l = draw.textbbox((0, 0), line, font=font_sub)
            lw = bbox_l[2] - bbox_l[0]
            lx = (w - lw) // 2
            # Sombra negra nítida
            draw.text((lx + 2, y_text + 2), line, font=font_sub, fill=(0, 0, 0, 240))
            draw.text((lx, y_text), line, font=font_sub, fill=(248, 244, 236, 255))
            y_text += line_h

    combined = Image.alpha_composite(pil_img, overlay).convert("RGB")
    return cv2.cvtColor(np.array(combined), cv2.COLOR_RGB2BGR)


def _render_title_card_frame(
    backdrop_bgr: np.ndarray,
    slug: str,
    episode_title: str,
    progress: float,
    particles: AtmosphereParticles,
    t_sec: float,
    is_outro: bool = False,
) -> np.ndarray:
    """Renderiza un cuadro de la cartela de apertura o cierre de la serie."""
    amb = AMBIENTES.get(slug, AMBIENTES["caricateri"])
    h, w = backdrop_bgr.shape[:2]

    frame = _apply_ken_burns(backdrop_bgr, progress, motion_mode=0)
    frame = cv2.GaussianBlur(frame, (21, 21), 8)
    fondo_bgr = np.full_like(frame, _hex_to_bgr(amb["fondo"]))
    frame = cv2.addWeighted(frame, 0.42, fondo_bgr, 0.58, 0)
    frame = particles.render_overlay(frame, t_sec)

    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    acento_rgb = _hex_to_rgb(amb["acento"])
    luz_rgb = _hex_to_rgb(amb["luz"])
    papel_rgb = _hex_to_rgb(amb["papel"])

    alpha = int(255 * math.sin(math.pi * max(0.05, min(0.95, progress))))
    font_col = _load_font(20, bold=True)
    font_title = _load_font(58, bold=True)
    font_ep = _load_font(30, bold=False)
    font_lema = _load_font(23, bold=False)

    top_tag = f"PRAYVIS · {amb['coleccion'].upper()} · {amb['codigo']}"
    b0 = draw.textbbox((0, 0), top_tag, font=font_col)
    draw.text(((w - (b0[2] - b0[0])) // 2, h // 2 - 135), top_tag, font=font_col, fill=(*acento_rgb, alpha))

    main_title = amb["titulo"]
    b1 = draw.textbbox((0, 0), main_title, font=font_title)
    draw.text(((w - (b1[2] - b1[0])) // 2, h // 2 - 82), main_title, font=font_title, fill=(*papel_rgb, alpha))

    # Línea ornamental central
    draw.line((w // 2 - 180, h // 2 + 2, w // 2 + 180, h // 2 + 2), fill=(*acento_rgb, alpha), width=2)

    sub_line = f"«{amb['lema']}»" if is_outro else episode_title
    b2 = draw.textbbox((0, 0), sub_line, font=font_ep)
    draw.text(((w - (b2[2] - b2[0])) // 2, h // 2 + 24), sub_line, font=font_ep, fill=(*luz_rgb, alpha))

    footer = "Serie Visual · Generativa IA + Google Colab GPU" if is_outro else f"{amb['genero']} · «{amb['lema']}»"
    b3 = draw.textbbox((0, 0), footer, font=font_lema)
    draw.text(((w - (b3[2] - b3[0])) // 2, h // 2 + 80), footer, font=font_lema, fill=(*papel_rgb, int(alpha * 0.85)))

    combined = Image.alpha_composite(pil_img, overlay).convert("RGB")
    return cv2.cvtColor(np.array(combined), cv2.COLOR_RGB2BGR)


# ==============================================================================
# 5. ENSAMBLADOR COMPLETO DE CORTOMETRAJE MP4 (VIDEO H.264 + AUDIO ESTÉREO AAC)
# ==============================================================================

class DialogueLineSpec(BaseModel):
    speaker: Optional[str] = Field(default=None, description="Nombre del personaje en mayúsculas, o None para el narrador")
    text: str = Field(..., description="Texto hablado y subtitulado de la línea")
    pause_after_ms: int = Field(default=320, description="Pausa dramática tras la línea en milisegundos")


class VideoSceneSpec(BaseModel):
    heading: str = Field(..., description="Encabezado de lugar y momento (ej. EXT. TZINTZUNTZAN — AMANECER)")
    image_base64: Optional[str] = Field(default=None, description="Imagen keyframe en base64 (si ya existe)")
    prompt: Optional[str] = Field(default=None, description="Prompt para generar el keyframe en GPU si no se pasa image_base64")
    lines: List[DialogueLineSpec] = Field(default_factory=list, description="Parlamentos de narrador y personajes en esta escena")


class VideoGenerateRequest(BaseModel):
    series_slug: str = Field(default="caricateri", description="Slug de la serie de PrayVis (ej. caricateri, inquisidor, mictlania)")
    episode_title: str = Field(default="Episodio Piloto", description="Título del episodio o cortometraje")
    scenes: List[VideoSceneSpec] = Field(..., description="Lista de escenas del cortometraje")
    width: int = Field(default=1280, description="Ancho del video MP4 (16:9)")
    height: int = Field(default=720, description="Alto del video MP4 (16:9)")
    fps: int = Field(default=24, description="Cuadros por segundo")
    seed: Optional[int] = Field(default=42, description="Semilla para generación de keyframes")


class TTSRequest(BaseModel):
    text: str
    speaker: Optional[str] = None


def render_cortometraje_mp4(
    series_slug: str,
    episode_title: str,
    scenes_data: List[dict],
    output_mp4_path: str,
    width: int = 1280,
    height: int = 720,
    fps: int = 24,
    sr: int = 44100,
    remote_worker_url: Optional[str] = None,
) -> dict:
    """Renderiza un cortometraje completo en `.mp4` (H.264 + AAC) a partir de escenas con imágenes y líneas de guion.

    Cada elemento de `scenes_data` tiene:
      - `heading`: str
      - `image`: PIL.Image.Image
      - `lines`: List[{"speaker": Optional[str], "text": str, "pause_after_ms": int}]
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_mp4_path)), exist_ok=True)

    intro_sec = 3.2
    outro_sec = 2.8
    crossfade_sec = 0.45

    # 1. Sintetizar todas las voces de todas las escenas y calcular tiempos exactos
    audio_segments: List[Tuple[int, np.ndarray]] = []
    speech_intervals: List[Tuple[float, float]] = []
    scene_timings: List[dict] = []

    t_cursor = intro_sec

    for s_idx, sc in enumerate(scenes_data):
        sc_start = t_cursor
        t_cursor += 0.45  # Respiro visual al abrir la escena
        sub_events: List[dict] = []

        for line in sc.get("lines", []):
            spk = line.get("speaker")
            txt = line.get("text", "").strip()
            if not txt:
                continue
            pcm = synthesize_speech_to_pcm(txt, speaker=spk, sr=sr, remote_worker_url=remote_worker_url)
            dur_line = len(pcm) / sr
            t0 = t_cursor
            t1 = t0 + dur_line
            audio_segments.append((int(t0 * sr), pcm))
            speech_intervals.append((t0, t1))
            sub_events.append({"t0": t0, "t1": t1 + 0.18, "speaker": spk, "text": txt})
            pause_s = max(0.2, line.get("pause_after_ms", 320) / 1000.0)
            t_cursor = t1 + pause_s

        t_cursor += 0.45  # Respiro al cerrar la escena
        sc_end = max(sc_start + 3.5, t_cursor)
        t_cursor = sc_end
        scene_timings.append(
            {
                "index": s_idx,
                "heading": sc.get("heading", ""),
                "canvas_bgr": _prepare_16_9_canvas(sc["image"], width=width, height=height),
                "t0": sc_start,
                "t1": sc_end,
                "subtitles": sub_events,
            }
        )

    total_duration = t_cursor + outro_sec
    n_total_samples = int(math.ceil(total_duration * sr))

    # 2. Sintetizar partitura generativa + paisaje sonoro de la serie con ducking automático
    music_stereo = synthesize_series_music_and_ambience(
        series_slug,
        duration_sec=total_duration,
        speech_intervals=speech_intervals,
        sr=sr,
    )
    if len(music_stereo) < n_total_samples:
        pad = np.zeros((n_total_samples - len(music_stereo), 2), dtype=np.float32)
        music_stereo = np.vstack([music_stereo, pad])
    else:
        music_stereo = music_stereo[:n_total_samples]

    # Mezclar las voces centradas en estéreo sobre la partitura atenuada
    for start_sample, pcm in audio_segments:
        end_sample = min(n_total_samples, start_sample + len(pcm))
        if end_sample > start_sample:
            seg = pcm[: end_sample - start_sample]
            music_stereo[start_sample:end_sample, 0] += seg * 0.92
            music_stereo[start_sample:end_sample, 1] += seg * 0.92

    peak_master = float(np.max(np.abs(music_stereo)) or 1.0)
    if peak_master > 0.98:
        music_stereo *= 0.98 / peak_master

    # 3. Guardar WAV maestro temporal y codificar video + audio en un solo paso con FFmpeg
    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "master_audio.wav")
        pcm_int16 = np.clip(music_stereo * 32767.0, -32768, 32767).astype(np.int16)
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm_int16.tobytes())

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{width}x{height}", "-pix_fmt", "bgr24", "-r", str(fps),
            "-i", "-",
            "-i", wav_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            output_mp4_path,
        ]

        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
        particles = AtmosphereParticles(series_slug, width=width, height=height)
        total_frames = int(round(total_duration * fps))
        first_backdrop = scene_timings[0]["canvas_bgr"] if scene_timings else np.zeros((height, width, 3), dtype=np.uint8)
        last_backdrop = scene_timings[-1]["canvas_bgr"] if scene_timings else first_backdrop

        try:
            for f_idx in range(total_frames):
                t_sec = f_idx / fps

                if t_sec < intro_sec:
                    prog = t_sec / max(0.01, intro_sec)
                    frame = _render_title_card_frame(
                        first_backdrop, series_slug, episode_title, prog, particles, t_sec, is_outro=False
                    )
                elif t_sec >= total_duration - outro_sec:
                    prog = (t_sec - (total_duration - outro_sec)) / max(0.01, outro_sec)
                    frame = _render_title_card_frame(
                        last_backdrop, series_slug, episode_title, prog, particles, t_sec, is_outro=True
                    )
                else:
                    # Encontrar escena activa
                    active_sc = scene_timings[-1]
                    for sc in scene_timings:
                        if sc["t0"] <= t_sec < sc["t1"]:
                            active_sc = sc
                            break

                    sc_dur = max(0.1, active_sc["t1"] - active_sc["t0"])
                    sc_prog = (t_sec - active_sc["t0"]) / sc_dur
                    frame = _apply_ken_burns(active_sc["canvas_bgr"], sc_prog, motion_mode=active_sc["index"])

                    # Transición suave (dissolve) con la escena previa durante los primeros `crossfade_sec`
                    if (t_sec - active_sc["t0"]) < crossfade_sec and active_sc["index"] > 0:
                        prev_sc = scene_timings[active_sc["index"] - 1]
                        prev_frame = _apply_ken_burns(prev_sc["canvas_bgr"], 1.0, motion_mode=prev_sc["index"])
                        alpha_cf = (t_sec - active_sc["t0"]) / crossfade_sec
                        frame = cv2.addWeighted(frame, alpha_cf, prev_frame, 1.0 - alpha_cf, 0)

                    frame = particles.render_overlay(frame, t_sec)

                    # Buscar subtítulo activo
                    cur_spk = None
                    cur_txt = None
                    for sub in active_sc["subtitles"]:
                        if sub["t0"] <= t_sec <= sub["t1"]:
                            cur_spk = sub["speaker"]
                            cur_txt = sub["text"]
                            break

                    frame = _draw_hud_and_subtitles(
                        frame,
                        slug=series_slug,
                        scene_heading=active_sc["heading"],
                        speaker=cur_spk,
                        subtitle_text=cur_txt,
                        scene_elapsed=t_sec - active_sc["t0"],
                    )

                proc.stdin.write(frame.tobytes())
        finally:
            if proc.stdin:
                proc.stdin.close()
            proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg falló al codificar {output_mp4_path} (código {proc.returncode})")

    return {
        "output_path": output_mp4_path,
        "duration_seconds": round(total_duration, 2),
        "frames": total_frames,
        "scenes": len(scene_timings),
        "width": width,
        "height": height,
        "fps": fps,
    }
