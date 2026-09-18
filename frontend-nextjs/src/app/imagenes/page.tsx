"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./page.module.css";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:20000";

const FRAMING_PRESETS = {
  retrato: { label: "Retrato", width: 512, height: 768 },
  cuerpoCompleto: { label: "Cuerpo completo", width: 512, height: 896 },
  cuadrado: { label: "Cuadrado", width: 768, height: 768 },
  horizontal: { label: "Horizontal / paisaje", width: 896, height: 512 },
} as const;
type FramingKey = keyof typeof FRAMING_PRESETS;

const MASK_TARGETS = {
  ropa: "Ropa",
  fondo: "Fondo / escenario",
  rostro: "Rostro y cabello",
} as const;
type MaskTargetKey = keyof typeof MASK_TARGETS;

const CONTROL_TYPES = {
  pose: "Pose (conserva la postura exacta)",
  edges: "Bordes (conserva contornos/objetos)",
} as const;
type ControlTypeKey = keyof typeof CONTROL_TYPES;

// Cada modo mapea 1:1 a un endpoint del backend ya construido. needsImage=false
// significa que genera desde cero (ignora la imagen activa como input directo).
const MODES = {
  generate: {
    label: "Generar desde texto",
    hint: "Crea una imagen nueva desde cero, sin partir de ninguna foto.",
    needsImage: false,
    needsSecondImage: false,
  },
  edit: {
    label: "Editar libre",
    hint: "Cambia el estilo o detalles de toda la foto activa a la vez.",
    needsImage: true,
    needsSecondImage: false,
  },
  inpaint: {
    label: "Cambiar ropa / fondo / rostro",
    hint: "Edita solo una zona (se detecta sola); el resto queda intacto.",
    needsImage: true,
    needsSecondImage: false,
  },
  controlled: {
    label: "Nueva escena, misma pose",
    hint: "Cambia el escenario/ropa conservando la postura exacta. No conserva la cara.",
    needsImage: true,
    needsSecondImage: false,
  },
  reference: {
    label: "Misma persona, otra escena",
    hint: "Genera una escena nueva pareciéndose a la persona de la foto activa.",
    needsImage: true,
    needsSecondImage: false,
  },
  faceswap: {
    label: "Face-swap",
    hint: "Coloca el rostro de otra foto sobre la persona de la foto activa.",
    needsImage: true,
    needsSecondImage: true,
  },
} as const;
type Mode = keyof typeof MODES;

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

type ImageEntry = { url: string; base64: string; label: string };

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",", 2)[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function ImagenesPage() {
  // La imagen "activa": lo que subiste o lo último que generaste. Cada operación
  // exitosa la reemplaza y la empuja al historial, así se puede seguir editando la
  // misma foto sin volver a subirla cada vez.
  const [current, setCurrent] = useState<ImageEntry | null>(null);
  const [history, setHistory] = useState<ImageEntry[]>([]);

  const [mode, setMode] = useState<Mode>("generate");

  // Campos compartidos entre modos
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [framing, setFraming] = useState<FramingKey>("retrato");
  const [strength, setStrength] = useState(0.6);
  const [maskTarget, setMaskTarget] = useState<MaskTargetKey>("ropa");
  const [controlType, setControlType] = useState<ControlTypeKey>("pose");
  const [ipAdapterScale, setIpAdapterScale] = useState(0.6);
  const [upscale, setUpscale] = useState(true);
  const [hiresFix, setHiresFix] = useState(false);
  const [restoreFaces, setRestoreFaces] = useState(false);

  // Face-swap necesita una segunda imagen (el rostro de origen) además de la activa
  const [secondImage, setSecondImage] = useState<ImageEntry | null>(null);

  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [resultDimensions, setResultDimensions] = useState<{ width: number; height: number } | null>(null);

  // Cronómetro en vivo mientras corre una operación: no hay progreso real que reportar
  // (el worker no manda avance parcial), pero saber cuánto tiempo lleva corriendo es
  // mejor que un texto estático fijo mientras se espera varios minutos en CPU.
  const [runningMs, setRunningMs] = useState(0);
  const runStartRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(() => {
      if (runStartRef.current !== null) {
        setRunningMs(performance.now() - runStartRef.current);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [isRunning]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>, target: "current" | "second") {
    const file = e.target.files?.[0];
    if (!file) return;
    const base64 = await fileToBase64(file);
    const entry: ImageEntry = { url: URL.createObjectURL(file), base64, label: "Subida" };
    if (target === "current") {
      setCurrent(entry);
      setHistory((h) => [...h, entry]);
    } else {
      setSecondImage(entry);
    }
  }

  function pushResult(imageBase64: string, label: string, width?: number, height?: number) {
    const entry: ImageEntry = {
      url: `data:image/png;base64,${imageBase64}`,
      base64: imageBase64,
      label,
    };
    setCurrent(entry);
    setHistory((h) => [...h, entry]);
    setResultDimensions(width && height ? { width, height } : null);
  }

  async function run() {
    if (isRunning) return;
    const cfg = MODES[mode];
    if (cfg.needsImage && !current) {
      setError("Sube o genera una imagen primero.");
      return;
    }
    if (cfg.needsSecondImage && !secondImage) {
      setError("Face-swap necesita una segunda foto (el rostro a usar).");
      return;
    }

    setError(null);
    setIsRunning(true);
    const start = performance.now();
    runStartRef.current = start;
    setRunningMs(0);

    try {
      let endpoint = "";
      let body: Record<string, unknown> = {};

      if (mode === "generate") {
        endpoint = "/api/image/generate";
        body = {
          prompt,
          negativePrompt: negativePrompt.trim() || null,
          steps: 50,
          guidanceScale: 7.5,
          width: FRAMING_PRESETS[framing].width,
          height: FRAMING_PRESETS[framing].height,
          upscale,
          hiresFix,
          restoreFaces,
        };
      } else if (mode === "edit") {
        endpoint = "/api/image/edit";
        body = {
          imageBase64: current!.base64,
          prompt,
          negativePrompt: negativePrompt.trim() || null,
          strength,
          steps: 50,
          guidanceScale: 7.5,
          upscale,
          hiresFix,
          restoreFaces,
        };
      } else if (mode === "inpaint") {
        endpoint = "/api/image/inpaint";
        body = {
          imageBase64: current!.base64,
          prompt,
          negativePrompt: negativePrompt.trim() || null,
          maskTarget,
          strength: 0.9,
          steps: 50,
          guidanceScale: 7.5,
          upscale,
          hiresFix,
          restoreFaces,
        };
      } else if (mode === "controlled") {
        endpoint = "/api/image/generate-controlled";
        body = {
          referenceImageBase64: current!.base64,
          controlType,
          prompt,
          negativePrompt: negativePrompt.trim() || null,
          controlnetConditioningScale: 1.0,
          steps: 50,
          guidanceScale: 7.5,
          upscale,
        };
      } else if (mode === "reference") {
        endpoint = "/api/image/generate-with-reference";
        body = {
          referenceImageBase64: current!.base64,
          prompt,
          negativePrompt: negativePrompt.trim() || null,
          ipAdapterScale,
          steps: 30,
          guidanceScale: 7.5,
          width: FRAMING_PRESETS[framing].width,
          height: FRAMING_PRESETS[framing].height,
          upscale,
        };
      } else if (mode === "faceswap") {
        endpoint = "/api/image/faceswap";
        body = {
          sourceImageBase64: secondImage!.base64,
          targetImageBase64: current!.base64,
          restoreFace: restoreFaces,
        };
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.error ?? data?.detail ?? `El servidor respondió con estado ${response.status}`);
      }

      pushResult(data.image_base64, MODES[mode].label, data.width, data.height);
      setElapsedMs(performance.now() - start);
    } catch (err) {
      setError((err as Error).message || "Ocurrió un error.");
    } finally {
      setIsRunning(false);
    }
  }

  async function upscaleCurrent() {
    if (!current || isRunning) return;
    setError(null);
    setIsRunning(true);
    runStartRef.current = performance.now();
    setRunningMs(0);
    try {
      const response = await fetch(`${API_BASE_URL}/api/image/upscale`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageBase64: current.base64 }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error ?? data?.detail ?? "Error al escalar.");
      pushResult(data.image_base64, "Escalado a Full HD", data.width, data.height);
    } catch (err) {
      setError((err as Error).message || "Ocurrió un error al escalar.");
    } finally {
      setIsRunning(false);
    }
  }

  const cfg = MODES[mode];
  const canRun =
    prompt.trim().length > 0 || mode === "faceswap"
      ? (!cfg.needsImage || !!current) && (!cfg.needsSecondImage || !!secondImage)
      : false;

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1 className={styles.title}>Generativa — Imágenes</h1>
        <p className={styles.hint}>
          Sube o genera una imagen una sola vez; cada resultado se convierte en la base del
          siguiente paso, sin volver a subir nada. Usa el historial de abajo para regresar a
          cualquier versión anterior.
        </p>

        <div className={styles.workspace}>
          {/* Lienzo: imagen activa + subir + historial */}
          <p className={styles.sectionTitle}>1. Tu imagen</p>
          <div className={styles.canvas}>
            <div className={styles.canvasImageWrap}>
              {current ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={current.url} alt="Imagen activa" />
              ) : (
                <span className={styles.canvasEmpty}>
                  Sube una imagen o genera una desde texto para empezar.
                </span>
              )}
              {isRunning && (
                <div className={styles.processingOverlay}>
                  <span className={styles.processingSpinner} />
                  <span>Generando… {formatDuration(runningMs)}</span>
                </div>
              )}
            </div>

            <div className={styles.canvasActions}>
              <label className={styles.uploadButton}>
                Subir imagen
                <input type="file" accept="image/*" onChange={(e) => handleUpload(e, "current")} />
              </label>
              {current && (
                <button className={styles.smallButton} onClick={upscaleCurrent} disabled={isRunning}>
                  Escalar a Full HD
                </button>
              )}
              {resultDimensions && (
                <span className={styles.meta}>
                  {resultDimensions.width}×{resultDimensions.height}px
                </span>
              )}
              {elapsedMs !== null && (
                <span className={styles.meta}>
                  Tiempo de generación: {formatDuration(elapsedMs)} ({(elapsedMs / 1000).toFixed(1)}s)
                </span>
              )}
            </div>

            {history.length > 1 && (
              <div className={styles.historyStrip}>
                {history.map((h, i) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={i}
                    src={h.url}
                    alt={h.label}
                    title={h.label}
                    className={`${styles.historyThumb} ${h.url === current?.url ? styles.historyThumbActive : ""}`}
                    onClick={() => setCurrent(h)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Selector de qué hacer */}
          <p className={styles.sectionTitle}>2. Qué quieres hacer</p>
          <div className={styles.modeGrid}>
            {Object.entries(MODES).map(([key, m]) => (
              <button
                key={key}
                className={`${styles.modeCard} ${mode === key ? styles.modeCardActive : ""}`}
                onClick={() => setMode(key as Mode)}
                disabled={m.needsImage && !current && key !== mode}
                title={m.hint}
              >
                {m.label}
              </button>
            ))}
          </div>
          <p className={styles.hint}>{MODES[mode].hint}</p>

          {/* Formulario dinámico según el modo */}
          <p className={styles.sectionTitle}>3. Detalles</p>
          <div className={styles.form}>
            {mode === "faceswap" ? (
              <label className={styles.label}>
                Foto con el rostro que quieres usar
                <input type="file" accept="image/*" onChange={(e) => handleUpload(e, "second")} />
                {secondImage && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={secondImage.url} alt="Rostro origen" className={styles.sourcePreview} />
                )}
              </label>
            ) : (
              <>
                <label className={styles.label}>
                  Describe lo que quieres
                  <textarea
                    className={styles.textarea}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder={
                      mode === "generate"
                        ? "Un zorro rojo en un bosque nevado, estilo pintura digital"
                        : mode === "inpaint"
                          ? "vestido rojo, tela satinada"
                          : "la misma persona en una playa al atardecer"
                    }
                    rows={3}
                  />
                </label>
                <label className={styles.label}>
                  Prompt negativo (opcional)
                  <input
                    className={styles.input}
                    value={negativePrompt}
                    onChange={(e) => setNegativePrompt(e.target.value)}
                    placeholder="borroso, baja calidad, deformado"
                  />
                </label>
              </>
            )}

            {(mode === "generate" || mode === "reference") && (
              <label className={styles.label}>
                Encuadre
                <select className={styles.input} value={framing} onChange={(e) => setFraming(e.target.value as FramingKey)}>
                  {Object.entries(FRAMING_PRESETS).map(([key, p]) => (
                    <option key={key} value={key}>
                      {p.label} ({p.width}×{p.height})
                    </option>
                  ))}
                </select>
              </label>
            )}

            {mode === "edit" && (
              <label className={styles.label}>
                Intensidad del cambio: {strength.toFixed(2)}
                <input type="range" min={0.2} max={0.9} step={0.05} value={strength} onChange={(e) => setStrength(Number(e.target.value))} />
                <span className={styles.hint}>Bajo = se parece más a la foto original. Alto = cambia más.</span>
              </label>
            )}

            {mode === "inpaint" && (
              <label className={styles.label}>
                Qué zona cambiar
                <select className={styles.input} value={maskTarget} onChange={(e) => setMaskTarget(e.target.value as MaskTargetKey)}>
                  {Object.entries(MASK_TARGETS).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
                <span className={styles.hint}>La zona se detecta sola; el resto de la imagen queda intacto.</span>
              </label>
            )}

            {mode === "controlled" && (
              <label className={styles.label}>
                Qué conservar de la imagen activa
                <select className={styles.input} value={controlType} onChange={(e) => setControlType(e.target.value as ControlTypeKey)}>
                  {Object.entries(CONTROL_TYPES).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
                <span className={styles.hint}>No conserva el rostro — combina después con face-swap si lo necesitas.</span>
              </label>
            )}

            {mode === "reference" && (
              <label className={styles.label}>
                Parecido a la imagen activa: {ipAdapterScale.toFixed(2)}
                <input type="range" min={0.2} max={1.0} step={0.05} value={ipAdapterScale} onChange={(e) => setIpAdapterScale(Number(e.target.value))} />
              </label>
            )}

            <div className={styles.fieldsRow}>
              {mode !== "faceswap" && mode !== "controlled" && mode !== "reference" && (
                <label className={styles.checkboxLabel}>
                  <input type="checkbox" checked={hiresFix} onChange={(e) => setHiresFix(e.target.checked)} />
                  Refinamiento extra
                </label>
              )}
              <label className={styles.checkboxLabel}>
                <input type="checkbox" checked={restoreFaces} onChange={(e) => setRestoreFaces(e.target.checked)} />
                Pulir rostro (GFPGAN)
              </label>
              {mode !== "faceswap" && (
                <label className={styles.checkboxLabel}>
                  <input type="checkbox" checked={upscale} onChange={(e) => setUpscale(e.target.checked)} />
                  Escalar a Full HD
                </label>
              )}
            </div>

            <button className={styles.button} onClick={run} disabled={isRunning || !canRun}>
              {isRunning ? `Procesando… ${formatDuration(runningMs)} (puede tardar varios minutos en CPU)` : MODES[mode].label}
            </button>
          </div>
        </div>

        {error && <p className={styles.error}>{error}</p>}
      </main>
    </div>
  );
}
