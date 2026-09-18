namespace Generativa.Api.Models;

public class GenerateImageRequest
{
    public string Prompt { get; set; } = string.Empty;
    public string? NegativePrompt { get; set; }
    public int Steps { get; set; } = 50;
    public double GuidanceScale { get; set; } = 7.5;
    public int Width { get; set; } = 512;
    public int Height { get; set; } = 768;
    public int? Seed { get; set; }
    public bool Upscale { get; set; } = true;
    public bool HiresFix { get; set; } = false;
    public bool RestoreFaces { get; set; } = false;
}

public class EditImageRequest
{
    public string ImageBase64 { get; set; } = string.Empty;
    public string Prompt { get; set; } = string.Empty;
    public string? NegativePrompt { get; set; }
    public double Strength { get; set; } = 0.6;
    public int Steps { get; set; } = 50;
    public double GuidanceScale { get; set; } = 7.5;
    public int? Seed { get; set; }
    public bool Upscale { get; set; } = true;
    public bool HiresFix { get; set; } = false;
    public bool RestoreFaces { get; set; } = false;
}

public class FaceSwapRequest
{
    public string SourceImageBase64 { get; set; } = string.Empty;
    public string TargetImageBase64 { get; set; } = string.Empty;
    public bool RestoreFace { get; set; } = true;
}

public class UpscaleRequest
{
    public string ImageBase64 { get; set; } = string.Empty;
}

public class InpaintRequest
{
    public string ImageBase64 { get; set; } = string.Empty;
    public string Prompt { get; set; } = string.Empty;
    public string? NegativePrompt { get; set; }
    // Una de las dos: MaskBase64 (máscara ya dibujada, blanco = editar) o MaskTarget
    // ("ropa" | "fondo" | "persona" | "rostro") para que se genere sola.
    public string? MaskBase64 { get; set; }
    public string? MaskTarget { get; set; }
    public double Strength { get; set; } = 0.97;
    public int Steps { get; set; } = 50;
    public double GuidanceScale { get; set; } = 7.5;
    public int? Seed { get; set; }
    public bool Upscale { get; set; } = true;
    public bool HiresFix { get; set; } = false;
    public bool RestoreFaces { get; set; } = false;
}

public class ControlledGenerateRequest
{
    public string ReferenceImageBase64 { get; set; } = string.Empty;
    public string ControlType { get; set; } = "pose"; // "pose" | "edges"
    public string Prompt { get; set; } = string.Empty;
    public string? NegativePrompt { get; set; }
    public double ControlnetConditioningScale { get; set; } = 1.0;
    public int Steps { get; set; } = 50;
    public double GuidanceScale { get; set; } = 7.5;
    public int? Seed { get; set; }
    public bool Upscale { get; set; } = true;
    public bool RestoreFaces { get; set; } = false;
}

public class ReferenceGenerateRequest
{
    public string ReferenceImageBase64 { get; set; } = string.Empty;
    public string Prompt { get; set; } = string.Empty;
    public string? NegativePrompt { get; set; }
    public double IpAdapterScale { get; set; } = 0.6;
    public int Steps { get; set; } = 30;
    public double GuidanceScale { get; set; } = 7.5;
    public int Width { get; set; } = 512;
    public int Height { get; set; } = 768;
    public int? Seed { get; set; }
    public bool Upscale { get; set; } = true;
    public bool RestoreFaces { get; set; } = false;
}
