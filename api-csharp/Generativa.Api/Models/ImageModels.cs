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
}

public class FaceSwapRequest
{
    public string SourceImageBase64 { get; set; } = string.Empty;
    public string TargetImageBase64 { get; set; } = string.Empty;
}

public class UpscaleRequest
{
    public string ImageBase64 { get; set; } = string.Empty;
}
