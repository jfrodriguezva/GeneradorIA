"use client";

import { useState } from "react";
import styles from "./page.module.css";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:20000";

type Mode = "generate" | "edit" | "inpaint" | "controlled" | "reference" | "faceswap";

const MASK_TARGETS = {
  ropa: "Ropa",
  fondo: "Fondo / escenario",
  persona: "Persona completa",
  rostro: "Rostro y cabello",
} as const;

type MaskTargetKey = keyof typeof MASK_TARGETS;

const CONTROL_TYPES = {
  pose: "Pose (conserva la postura exacta)",
  edges: "Bordes (conserva contornos/objetos)",
} as const;

type ControlTypeKey = keyof typeof CONTROL_TYPES;

const FRAMING_PRESETS = {
  retrato: { label: "Retrato", width: 512, height: 768 },
  cuerpoCompleto: { label: "Cuerpo completo", width: 512, height: 896 },
  cuadrado: { label: "Cuadrado", width: 768, height: 768 },
  horizontal: { label: "Horizontal / paisaje", width: 896, height: 512 },
} as const;

type FramingKey = keyof typeof FRAMING_PRESETS;

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // quita el prefijo "data:image/png;base64,"
      resolve(result.split(",", 2)[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function ImagenesPage() {
  const [mode, setMode] = useState<Mode>("generate");

  // Generar desde texto
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [framing, setFraming] = useState<FramingKey>("retrato");

  // Editar foto existente
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourcePreviewUrl, setSourcePreviewUrl] = useState<string | null>(null);
  const [editPrompt, setEditPrompt] = useState("");
  const [strength, setStrength] = useState(0.6);

  // Inpainting dirigido (cambiar solo ropa / fondo / persona / rostro)
  const [inpaintFile, setInpaintFile] = useState<File | null>(null);
  const [inpaintPreviewUrl, setInpaintPreviewUrl] = useState<string | null>(null);
  const [inpaintPrompt, setInpaintPrompt] = useState("");
  const [maskTarget, setMaskTarget] = useState<MaskTargetKey>("ropa");
  const [inpaintStrength, setInpaintStrength] = useState(0.97);

  // Cambiar escenario/ropa conservando pose exacta (ControlNet)
  const [controlFile, setControlFile] = useState<File | null>(null);
  const [controlPreviewUrl, setControlPreviewUrl] = useState<string | null>(null);
  const [controlPrompt, setControlPrompt] = useState("");
  const [controlType, setControlType] = useState<ControlTypeKey>("pose");

  // Misma persona en una escena nueva (IP-Adapter)
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [referencePreviewUrl, setReferencePreviewUrl] = useState<string | null>(null);
  const [referencePrompt, setReferencePrompt] = useState("");
  const [ipAdapterScale, setIpAdapterScale] = useState(0.6);

  // Face-swap
  const [faceSourceFile, setFaceSourceFile] = useState<File | null>(null);
  const [faceSourcePreviewUrl, setFaceSourcePreviewUrl] = useState<string | null>(null);
  const [faceTargetFile, setFaceTargetFile] = useState<File | null>(null);
  const [faceTargetPreviewUrl, setFaceTargetPreviewUrl] = useState<string | null>(null);
  const [restoreFace, setRestoreFace] = useState(true);

  const [upscale, setUpscale] = useState(true);
  // Disponibles en "generar" y "editar": segunda pasada de refinamiento (más nítido,
  // ~30-40% más lento) y GFPGAN sobre el resultado (requiere GFPGANv1.4.pth, si falta
  // se ignora sin error).
  const [hiresFix, setHiresFix] = useState(false);
  const [restoreFacesInResult, setRestoreFacesInResult] = useState(false);

  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isUpscaling, setIsUpscaling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [resultDimensions, setResultDimensions] = useState<{ width: number; height: number } | null>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setSourceFile(file);
    setSourcePreviewUrl(file ? URL.createObjectURL(file) : null);
  }

  function handleInpaintFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setInpaintFile(file);
    setInpaintPreviewUrl(file ? URL.createObjectURL(file) : null);
  }

  function handleControlFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setControlFile(file);
    setControlPreviewUrl(file ? URL.createObjectURL(file) : null);
  }

  function handleReferenceFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setReferenceFile(file);
    setReferencePreviewUrl(file ? URL.createObjectURL(file) : null);
  }

  function handleFaceSourceChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setFaceSourceFile(file);
    setFaceSourcePreviewUrl(file ? URL.createObjectURL(file) : null);
  }

  function handleFaceTargetChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setFaceTargetFile(file);
    setFaceTargetPreviewUrl(file ? URL.createObjectURL(file) : null);
  }

  async function generate() {
    const trimmed = prompt.trim();
    if (!trimmed || isGenerating) return;

    setError(null);
    setIsGenerating(true);
    const start = performance.now();

    try {
      const response = await fetch(`${API_BASE_URL}/api/image/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: trimmed,
          negativePrompt: negativePrompt.trim() || null,
          steps: 50,
          guidanceScale: 7.5,
          width: FRAMING_PRESETS[framing].width,
          height: FRAMING_PRESETS[framing].height,
          upscale,
          hiresFix,
          restoreFaces: restoreFacesInResult,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.error ?? `El servidor respondió con estado ${response.status}`);
      }

      setImageUrl(`data:image/png;base64,${data.image_base64}`);
      setResultDimensions(data.width && data.height ? { width: data.width, height: data.height } : null);
      setElapsedMs(performance.now() - start);
    } catch (err) {
      setError((err as Error).message || "Ocurrió un error al generar la imagen.");
    } finally {
      setIsGenerating(false);
    }
  }

  async function editPhoto() {
    const trimmed = editPrompt.trim();
    if (!trimmed || !sourceFile || isGenerating) return;

    setError(null);
    setIsGenerating(true);
    const start = performance.now();

    try {
      const imageBase64 = await fileToBase64(sourceFile);

      const response = await fetch(`${API_BASE_URL}/api/image/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          imageBase64,
          prompt: trimmed,
          strength,
          steps: 50,
          guidanceScale: 7.5,
          upscale,
          hiresFix,
          restoreFaces: restoreFacesInResult,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.error ?? `El servidor respondió con estado ${response.status}`);
      }

      setImageUrl(`data:image/png;base64,${data.image_base64}`);
      setResultDimensions(data.width && data.height ? { width: data.width, height: data.height } : null);
      setElapsedMs(performance.now() - start);
    } catch (err) {
      setError((err as Error).message || "Ocurrió un error al editar la imagen.");
    } finally {
      setIsGenerating(false);
    }
  }

  async function inpaint() {
    const trimmed = inpaintPrompt.trim();
    if (!trimmed || !inpaintFile || isGenerating) return;

    setError(null);
    setIsGenerating(true);
    const start = performance.now();

    try {
      const imageBase64 = await fileToBase64(inpaintFile);

      const response = await fetch(`${API_BASE_URL}/api/image/inpaint`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          imageBase64,
          prompt: trimmed,
          maskTarget,
          strength: inpaintStrength,
          steps: 50,
          guidanceScale: 7.5,
          upscale,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail ?? data?.error ?? `El servidor respondió con estado ${response.status}`);
      }

      setImageUrl(`data:image/png;base64,${data.image_base64}`);
      setResultDimensions(data.width && data.height ? { width: data.width, height: data.height } : null);
      setElapsedMs(performance.now() - start);
    } catch (err) {
      setError((err as Error).message || "Ocurrió un error al editar la imagen.");
    } finally {
      setIsGenerating(false);
    }
  }

  async function generateControlled() {
    const trimmed = controlPrompt.trim();
    if (!trimmed || !controlFile || isGenerating) return;

    setError(null);
    setIsGenerating(true);
    const start = performance.now();

    try {
      const referenceImageBase64 = await fileToBase64(controlFile);

      const response = await fetch(`${API_BASE_URL}/api/image/generate-controlled`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          referenceImageBase64,
          controlType,
          prompt: trimmed,
          steps: 50,
          guidanceScale: 7.5,
          upscale,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail ?? data?.error ?? `El servidor respondió con estado ${response.status}`);
      }

      setImageUrl(`data:image/png;base64,${data.image_base64}`);
      setResultDimensions(data.width && data.height ? { width: data.width, height: data.height } : null);
      setElapsedMs(performance.now() - start);
    } catch (err) {
      setError((err as Error).message || "Ocurrió un error al generar la imagen.");
    } finally {
      setIsGenerating(false);
    }
  }

  async function generateWithReference() {
    const trimmed = referencePrompt.trim();
    if (!trimmed || !referenceFile || isGenerating) return;

    setError(null);
    setIsGenerating(true);
    const start = performance.now();

    try {
      const referenceImageBase64 = await fileToBase64(referenceFile);

      const response = await fetch(`${API_BASE_URL}/api/image/generate-with-reference`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          referenceImageBase64,
          prompt: trimmed,
          ipAdapterScale,
          steps: 30,
          guidanceScale: 7.5,
          width: FRAMING_PRESETS[framing].width,
          height: FRAMING_PRESETS[framing].height,
          upscale,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail ?? data?.error ?? `El servidor respondió con estado ${response.status}`);
      }

      setImageUrl(`data:image/png;base64,${data.image_base64}`);
      setResultDimensions(data.width && data.height ? { width: data.width, height: data.height } : null);
      setElapsedMs(performance.now() - start);
    } catch (err) {
      setError((err as Error).message || "Ocurrió un error al generar la imagen.");
    } finally {
      setIsGenerating(false);
    }
  }

  async function faceSwap() {
    if (!faceSourceFile || !faceTargetFile || isGenerating) return;

    setError(null);
    setIsGenerating(true);
    const start = performance.now();

    try {
      const [sourceImageBase64, targetImageBase64] = await Promise.all([
        fileToBase64(faceSourceFile),
        fileToBase64(faceTargetFile),
      ]);

      const response = await fetch(`${API_BASE_URL}/api/image/faceswap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourceImageBase64, targetImageBase64, restoreFace }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail ?? data?.error ?? `El servidor respondió con estado ${response.status}`);
      }

      setImageUrl(`data:image/png;base64,${data.image_base64}`);
      setElapsedMs(performance.now() - start);
    } catch (err) {
      setError((err as Error).message || "Ocurrió un error al intercambiar el rostro.");
    } finally {
      setIsGenerating(false);
    }
  }

  async function upscaleResult() {
    if (!imageUrl || isUpscaling) return;
    setError(null);
    setIsUpscaling(true);

    try {
      const imageBase64 = imageUrl.split(",", 2)[1];
      const response = await fetch(`${API_BASE_URL}/api/image/upscale`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageBase64 }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail ?? data?.error ?? `El servidor respondió con estado ${response.status}`);
      }

      setImageUrl(`data:image/png;base64,${data.image_base64}`);
      setResultDimensions(data.width && data.height ? { width: data.width, height: data.height } : null);
    } catch (err) {
      setError((err as Error).message || "Ocurrió un error al escalar la imagen.");
    } finally {
      setIsUpscaling(false);
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1 className={styles.title}>Generativa — Imágenes</h1>

        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${mode === "generate" ? styles.tabActive : ""}`}
            onClick={() => setMode("generate")}
          >
            Generar desde texto
          </button>
          <button
            className={`${styles.tab} ${mode === "edit" ? styles.tabActive : ""}`}
            onClick={() => setMode("edit")}
          >
            Editar una foto
          </button>
          <button
            className={`${styles.tab} ${mode === "inpaint" ? styles.tabActive : ""}`}
            onClick={() => setMode("inpaint")}
          >
            Cambiar ropa / fondo
          </button>
          <button
            className={`${styles.tab} ${mode === "controlled" ? styles.tabActive : ""}`}
            onClick={() => setMode("controlled")}
          >
            Nueva escena (misma pose)
          </button>
          <button
            className={`${styles.tab} ${mode === "reference" ? styles.tabActive : ""}`}
            onClick={() => setMode("reference")}
          >
            Misma persona, otra escena
          </button>
          <button
            className={`${styles.tab} ${mode === "faceswap" ? styles.tabActive : ""}`}
            onClick={() => setMode("faceswap")}
          >
            Face-swap
          </button>
        </div>

        {mode === "generate" && (
          <div className={styles.form}>
            <label className={styles.label}>
              Prompt
              <textarea
                className={styles.textarea}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Un zorro rojo en un bosque nevado, estilo pintura digital"
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

            <label className={styles.label}>
              Encuadre
              <select
                className={styles.input}
                value={framing}
                onChange={(e) => setFraming(e.target.value as FramingKey)}
              >
                {Object.entries(FRAMING_PRESETS).map(([key, preset]) => (
                  <option key={key} value={key}>
                    {preset.label} ({preset.width}×{preset.height})
                  </option>
                ))}
              </select>
              <span className={styles.hint}>
                Para cuerpo completo, describe en el prompt que quieres ver a la persona de pies a cabeza.
              </span>
            </label>

            <label className={styles.checkboxLabel}>
              <input type="checkbox" checked={upscale} onChange={(e) => setUpscale(e.target.checked)} />
              Escalar a Full HD
            </label>

            <label className={styles.checkboxLabel}>
              <input type="checkbox" checked={hiresFix} onChange={(e) => setHiresFix(e.target.checked)} />
              Refinamiento extra (más nítido, ~30-40% más lento)
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={restoreFacesInResult}
                onChange={(e) => setRestoreFacesInResult(e.target.checked)}
              />
              Pulir rostro (GFPGAN, requiere GFPGANv1.4.pth)
            </label>

            <button
              className={styles.button}
              onClick={generate}
              disabled={isGenerating || !prompt.trim()}
            >
              {isGenerating ? "Generando a máxima calidad… (~15-20 min en CPU)" : "Generar imagen (máxima calidad)"}
            </button>
          </div>
        )}

        {mode === "edit" && (
          <div className={styles.form}>
            <label className={styles.label}>
              Foto a editar
              <input type="file" accept="image/*" onChange={handleFileChange} />
            </label>

            {sourcePreviewUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={sourcePreviewUrl} alt="Foto original" className={styles.sourcePreview} />
            )}

            <label className={styles.label}>
              Describe el cambio
              <textarea
                className={styles.textarea}
                value={editPrompt}
                onChange={(e) => setEditPrompt(e.target.value)}
                placeholder="la misma persona vestida de charro mexicano, sombrero, traje tradicional"
                rows={3}
              />
            </label>

            <label className={styles.label}>
              Intensidad del cambio: {strength.toFixed(2)}
              <input
                type="range"
                min={0.2}
                max={0.9}
                step={0.05}
                value={strength}
                onChange={(e) => setStrength(Number(e.target.value))}
              />
              <span className={styles.hint}>
                Bajo = se parece más a la foto original. Alto = cambia más, pero puede perder el parecido.
              </span>
            </label>

            <label className={styles.checkboxLabel}>
              <input type="checkbox" checked={upscale} onChange={(e) => setUpscale(e.target.checked)} />
              Escalar a Full HD
            </label>

            <label className={styles.checkboxLabel}>
              <input type="checkbox" checked={hiresFix} onChange={(e) => setHiresFix(e.target.checked)} />
              Refinamiento extra (más nítido, ~30-40% más lento)
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={restoreFacesInResult}
                onChange={(e) => setRestoreFacesInResult(e.target.checked)}
              />
              Pulir rostro (GFPGAN, requiere GFPGANv1.4.pth)
            </label>

            <button
              className={styles.button}
              onClick={editPhoto}
              disabled={isGenerating || !editPrompt.trim() || !sourceFile}
            >
              {isGenerating ? "Editando a máxima calidad… (~15-20 min en CPU)" : "Editar imagen (máxima calidad)"}
            </button>
          </div>
        )}

        {mode === "inpaint" && (
          <div className={styles.form}>
            <label className={styles.label}>
              Foto a editar
              <input type="file" accept="image/*" onChange={handleInpaintFileChange} />
            </label>

            {inpaintPreviewUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={inpaintPreviewUrl} alt="Foto original" className={styles.sourcePreview} />
            )}

            <label className={styles.label}>
              Qué zona cambiar
              <select
                className={styles.input}
                value={maskTarget}
                onChange={(e) => setMaskTarget(e.target.value as MaskTargetKey)}
              >
                {Object.entries(MASK_TARGETS).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
              <span className={styles.hint}>
                La zona se detecta sola (segmentación); el resto de la imagen queda intacto.
              </span>
            </label>

            <label className={styles.label}>
              Describe el resultado que quieres en esa zona
              <textarea
                className={styles.textarea}
                value={inpaintPrompt}
                onChange={(e) => setInpaintPrompt(e.target.value)}
                placeholder="vestido rojo de gala, tela satinada"
                rows={3}
              />
            </label>

            <label className={styles.label}>
              Intensidad del cambio: {inpaintStrength.toFixed(2)}
              <input
                type="range"
                min={0.6}
                max={1.0}
                step={0.05}
                value={inpaintStrength}
                onChange={(e) => setInpaintStrength(Number(e.target.value))}
              />
            </label>

            <label className={styles.checkboxLabel}>
              <input type="checkbox" checked={upscale} onChange={(e) => setUpscale(e.target.checked)} />
              Escalar a Full HD
            </label>

            <button
              className={styles.button}
              onClick={inpaint}
              disabled={isGenerating || !inpaintPrompt.trim() || !inpaintFile}
            >
              {isGenerating ? "Editando a máxima calidad… (~10-15 min en CPU)" : "Aplicar cambio dirigido"}
            </button>
          </div>
        )}

        {mode === "controlled" && (
          <div className={styles.form}>
            <label className={styles.label}>
              Foto de referencia (se conserva la pose/contornos, no el contenido)
              <input type="file" accept="image/*" onChange={handleControlFileChange} />
            </label>

            {controlPreviewUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={controlPreviewUrl} alt="Foto de referencia" className={styles.sourcePreview} />
            )}

            <label className={styles.label}>
              Qué conservar de la referencia
              <select
                className={styles.input}
                value={controlType}
                onChange={(e) => setControlType(e.target.value as ControlTypeKey)}
              >
                {Object.entries(CONTROL_TYPES).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.label}>
              Describe la escena/ropa nueva
              <textarea
                className={styles.textarea}
                value={controlPrompt}
                onChange={(e) => setControlPrompt(e.target.value)}
                placeholder="la misma persona en una playa al atardecer, vestido blanco de lino"
                rows={3}
              />
              <span className={styles.hint}>
                Conserva la pose exacta de la referencia; no conserva el rostro — combina con
                face-swap después si necesitas que sea la misma cara.
              </span>
            </label>

            <label className={styles.checkboxLabel}>
              <input type="checkbox" checked={upscale} onChange={(e) => setUpscale(e.target.checked)} />
              Escalar a Full HD
            </label>

            <button
              className={styles.button}
              onClick={generateControlled}
              disabled={isGenerating || !controlPrompt.trim() || !controlFile}
            >
              {isGenerating ? "Generando a máxima calidad… (~15-20 min en CPU)" : "Generar escena nueva"}
            </button>
          </div>
        )}

        {mode === "reference" && (
          <div className={styles.form}>
            <label className={styles.label}>
              Foto de referencia de la persona (rostro visible)
              <input type="file" accept="image/*" onChange={handleReferenceFileChange} />
            </label>

            {referencePreviewUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={referencePreviewUrl} alt="Foto de referencia" className={styles.sourcePreview} />
            )}

            <label className={styles.label}>
              Describe la escena nueva
              <textarea
                className={styles.textarea}
                value={referencePrompt}
                onChange={(e) => setReferencePrompt(e.target.value)}
                placeholder="la misma persona caminando por una calle de París, otoño"
                rows={3}
              />
            </label>

            <label className={styles.label}>
              Encuadre
              <select
                className={styles.input}
                value={framing}
                onChange={(e) => setFraming(e.target.value as FramingKey)}
              >
                {Object.entries(FRAMING_PRESETS).map(([key, preset]) => (
                  <option key={key} value={key}>
                    {preset.label} ({preset.width}×{preset.height})
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.label}>
              Parecido a la referencia: {ipAdapterScale.toFixed(2)}
              <input
                type="range"
                min={0.2}
                max={1.0}
                step={0.05}
                value={ipAdapterScale}
                onChange={(e) => setIpAdapterScale(Number(e.target.value))}
              />
              <span className={styles.hint}>
                Alto = se parece más a la referencia. Bajo = más libertad en la escena, menos parecido.
              </span>
            </label>

            <label className={styles.checkboxLabel}>
              <input type="checkbox" checked={upscale} onChange={(e) => setUpscale(e.target.checked)} />
              Escalar a Full HD
            </label>

            <button
              className={styles.button}
              onClick={generateWithReference}
              disabled={isGenerating || !referencePrompt.trim() || !referenceFile}
            >
              {isGenerating ? "Generando… (más lento, no usa aceleración OpenVINO)" : "Generar con esa identidad"}
            </button>
          </div>
        )}

        {mode === "faceswap" && (
          <div className={styles.form}>
            <label className={styles.label}>
              Foto con el rostro que quieres usar
              <input type="file" accept="image/*" onChange={handleFaceSourceChange} />
            </label>
            {faceSourcePreviewUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={faceSourcePreviewUrl} alt="Rostro origen" className={styles.sourcePreview} />
            )}

            <label className={styles.label}>
              Foto donde quieres colocar ese rostro
              <input type="file" accept="image/*" onChange={handleFaceTargetChange} />
            </label>
            {faceTargetPreviewUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={faceTargetPreviewUrl} alt="Foto destino" className={styles.sourcePreview} />
            )}

            <label className={styles.checkboxLabel}>
              <input type="checkbox" checked={restoreFace} onChange={(e) => setRestoreFace(e.target.checked)} />
              Restaurar iluminación/textura del rostro (GFPGAN)
            </label>

            <button
              className={styles.button}
              onClick={faceSwap}
              disabled={isGenerating || !faceSourceFile || !faceTargetFile}
            >
              {isGenerating ? "Intercambiando rostro… (unos segundos)" : "Intercambiar rostro"}
            </button>
          </div>
        )}

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.resultBox}>
          {imageUrl ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageUrl} alt="Resultado" className={styles.image} />
              <div className={styles.resultMetaRow}>
                {elapsedMs !== null && (
                  <span className={styles.meta}>Generada en {(elapsedMs / 1000).toFixed(1)}s</span>
                )}
                {resultDimensions && (
                  <span className={styles.meta}>
                    {resultDimensions.width}×{resultDimensions.height}px
                  </span>
                )}
                <button className={styles.smallButton} onClick={upscaleResult} disabled={isUpscaling}>
                  {isUpscaling ? "Escalando…" : "Escalar a Full HD"}
                </button>
              </div>
            </>
          ) : (
            <p className={styles.placeholder}>El resultado aparecerá aquí.</p>
          )}
        </div>
      </main>
    </div>
  );
}
