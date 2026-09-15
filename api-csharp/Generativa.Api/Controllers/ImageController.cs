using System.Net.Http.Json;
using Generativa.Api.Models;
using Microsoft.AspNetCore.Mvc;

namespace Generativa.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class ImageController : ControllerBase
{
    private readonly IHttpClientFactory _httpClientFactory;

    public ImageController(IHttpClientFactory httpClientFactory)
    {
        _httpClientFactory = httpClientFactory;
    }

    [HttpGet("health")]
    public async Task<IActionResult> Health(CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ImageWorker");
        try
        {
            var response = await client.GetAsync("/health", cancellationToken);
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            return StatusCode((int)response.StatusCode, body);
        }
        catch (HttpRequestException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new { status = "worker_unreachable" });
        }
    }

    [HttpPost("generate")]
    public async Task<IActionResult> Generate([FromBody] GenerateImageRequest request, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ImageWorker");

        var payload = new
        {
            prompt = request.Prompt,
            negative_prompt = request.NegativePrompt,
            steps = request.Steps,
            guidance_scale = request.GuidanceScale,
            width = request.Width,
            height = request.Height,
            seed = request.Seed,
            upscale = request.Upscale
        };

        HttpResponseMessage upstreamResponse;
        try
        {
            upstreamResponse = await client.PostAsJsonAsync("/generate", payload, cancellationToken);
        }
        catch (HttpRequestException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new { error = "No se pudo contactar al worker de imágenes." });
        }

        var body = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
        return StatusCode((int)upstreamResponse.StatusCode, System.Text.Json.JsonSerializer.Deserialize<object>(body));
    }

    [HttpPost("edit")]
    public async Task<IActionResult> Edit([FromBody] EditImageRequest request, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ImageWorker");

        var payload = new
        {
            image_base64 = request.ImageBase64,
            prompt = request.Prompt,
            negative_prompt = request.NegativePrompt,
            strength = request.Strength,
            steps = request.Steps,
            guidance_scale = request.GuidanceScale,
            seed = request.Seed,
            upscale = request.Upscale
        };

        HttpResponseMessage upstreamResponse;
        try
        {
            upstreamResponse = await client.PostAsJsonAsync("/edit", payload, cancellationToken);
        }
        catch (HttpRequestException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new { error = "No se pudo contactar al worker de imágenes." });
        }

        var body = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
        return StatusCode((int)upstreamResponse.StatusCode, System.Text.Json.JsonSerializer.Deserialize<object>(body));
    }

    [HttpPost("inpaint")]
    public async Task<IActionResult> Inpaint([FromBody] InpaintRequest request, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ImageWorker");

        var payload = new
        {
            image_base64 = request.ImageBase64,
            prompt = request.Prompt,
            negative_prompt = request.NegativePrompt,
            mask_base64 = request.MaskBase64,
            mask_target = request.MaskTarget,
            strength = request.Strength,
            steps = request.Steps,
            guidance_scale = request.GuidanceScale,
            seed = request.Seed,
            upscale = request.Upscale
        };

        HttpResponseMessage upstreamResponse;
        try
        {
            upstreamResponse = await client.PostAsJsonAsync("/inpaint", payload, cancellationToken);
        }
        catch (HttpRequestException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new { error = "No se pudo contactar al worker de imágenes." });
        }

        var body = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
        return StatusCode((int)upstreamResponse.StatusCode, System.Text.Json.JsonSerializer.Deserialize<object>(body));
    }

    [HttpPost("generate-controlled")]
    public async Task<IActionResult> GenerateControlled([FromBody] ControlledGenerateRequest request, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ImageWorker");

        var payload = new
        {
            reference_image_base64 = request.ReferenceImageBase64,
            control_type = request.ControlType,
            prompt = request.Prompt,
            negative_prompt = request.NegativePrompt,
            controlnet_conditioning_scale = request.ControlnetConditioningScale,
            steps = request.Steps,
            guidance_scale = request.GuidanceScale,
            seed = request.Seed,
            upscale = request.Upscale
        };

        HttpResponseMessage upstreamResponse;
        try
        {
            upstreamResponse = await client.PostAsJsonAsync("/generate-controlled", payload, cancellationToken);
        }
        catch (HttpRequestException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new { error = "No se pudo contactar al worker de imágenes." });
        }

        var body = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
        return StatusCode((int)upstreamResponse.StatusCode, System.Text.Json.JsonSerializer.Deserialize<object>(body));
    }

    [HttpPost("generate-with-reference")]
    public async Task<IActionResult> GenerateWithReference([FromBody] ReferenceGenerateRequest request, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ImageWorker");

        var payload = new
        {
            reference_image_base64 = request.ReferenceImageBase64,
            prompt = request.Prompt,
            negative_prompt = request.NegativePrompt,
            ip_adapter_scale = request.IpAdapterScale,
            steps = request.Steps,
            guidance_scale = request.GuidanceScale,
            width = request.Width,
            height = request.Height,
            seed = request.Seed,
            upscale = request.Upscale
        };

        HttpResponseMessage upstreamResponse;
        try
        {
            upstreamResponse = await client.PostAsJsonAsync("/generate-with-reference", payload, cancellationToken);
        }
        catch (HttpRequestException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new { error = "No se pudo contactar al worker de imágenes." });
        }

        var body = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
        return StatusCode((int)upstreamResponse.StatusCode, System.Text.Json.JsonSerializer.Deserialize<object>(body));
    }

    [HttpPost("faceswap")]
    public async Task<IActionResult> FaceSwap([FromBody] FaceSwapRequest request, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ImageWorker");

        var payload = new
        {
            source_image_base64 = request.SourceImageBase64,
            target_image_base64 = request.TargetImageBase64,
            restore_face = request.RestoreFace
        };

        HttpResponseMessage upstreamResponse;
        try
        {
            upstreamResponse = await client.PostAsJsonAsync("/faceswap", payload, cancellationToken);
        }
        catch (HttpRequestException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new { error = "No se pudo contactar al worker de imágenes." });
        }

        var body = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
        return StatusCode((int)upstreamResponse.StatusCode, System.Text.Json.JsonSerializer.Deserialize<object>(body));
    }

    [HttpPost("upscale")]
    public async Task<IActionResult> Upscale([FromBody] UpscaleRequest request, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ImageWorker");

        var payload = new { image_base64 = request.ImageBase64 };

        HttpResponseMessage upstreamResponse;
        try
        {
            upstreamResponse = await client.PostAsJsonAsync("/upscale", payload, cancellationToken);
        }
        catch (HttpRequestException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new { error = "No se pudo contactar al worker de imágenes." });
        }

        var body = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
        return StatusCode((int)upstreamResponse.StatusCode, System.Text.Json.JsonSerializer.Deserialize<object>(body));
    }
}
