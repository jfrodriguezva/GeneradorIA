"use client";

import { useState } from "react";
import styles from "./page.module.css";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:20000";

type Mode = "generate" | "edit" | "faceswap";

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

  // Editar foto existente
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourcePreviewUrl, setSourcePreviewUrl] = useState<string | null>(null);
  const [editPrompt, setEditPrompt] = useState("");
  const [strength, setStrength] = useState(0.6);

  // Face-swap
  const [faceSourceFile, setFaceSourceFile] = useState<File | null>(null);
  const [faceSourcePreviewUrl, setFaceSourcePreviewUrl] = useState<string | null>(null);
  const [faceTargetFile, setFaceTargetFile] = useState<File | null>(null);
  const [faceTargetPreviewUrl, setFaceTargetPreviewUrl] = useState<string | null>(null);

  const [upscale, setUpscale] = useState(false);

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
          steps: 30,
          guidanceScale: 7.0,
          width: 512,
          height: 768,
          upscale,
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
          steps: 30,
          guidanceScale: 7.0,
          upscale,
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
        body: JSON.stringify({ sourceImageBase64, targetImageBase64 }),
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

            <label className={styles.checkboxLabel}>
              <input type="checkbox" checked={upscale} onChange={(e) => setUpscale(e.target.checked)} />
              Escalar a Full HD (más lento)
            </label>

            <button
              className={styles.button}
              onClick={generate}
              disabled={isGenerating || !prompt.trim()}
            >
              {isGenerating ? "Generando… (alta calidad, puede tardar varios minutos en CPU)" : "Generar imagen"}
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
              Escalar a Full HD (más lento)
            </label>

            <button
              className={styles.button}
              onClick={editPhoto}
              disabled={isGenerating || !editPrompt.trim() || !sourceFile}
            >
              {isGenerating ? "Editando… (puede tardar varios minutos en CPU)" : "Editar imagen"}
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
