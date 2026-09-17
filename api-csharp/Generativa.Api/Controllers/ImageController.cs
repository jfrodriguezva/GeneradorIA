using System.Net.Http.Json;
using System.Text.Json;
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

    /// <summary>
    /// Reenvía un POST al worker de imágenes y devuelve su respuesta tal cual.
    ///
    /// Bug real encontrado en uso normal (no en pruebas): con hires_fix + restore_faces +
    /// strength alto en /inpaint, la corrida se pasó del timeout de 20 min del HttpClient
    /// ("ImageWorker" en Program.cs). Un timeout de HttpClient lanza TaskCanceledException,
    /// no HttpRequestException — el catch que ya existía en cada endpoint NO lo cubría, así
    /// que la excepción se propagaba sin manejar. Peor: aunque la respuesta SÍ llegara pero
    /// con un cuerpo que no fuera JSON válido, `JsonSerializer.Deserialize&lt;object&gt;(body)`
    /// tronaba sin protección. El resultado visible para el usuario: el frontend recibía el
    /// texto crudo de la excepción de .NET ("System.Text.Json.JsonException: ...") en vez de
    /// JSON, y `response.json()` fallaba con "Unexpected token 'S'... is not valid JSON" —
    /// un error críptico que no decía nada sobre la causa real (timeout).
    ///
    /// Este helper centraliza el manejo correcto para los 8 endpoints que repetían el mismo
    /// patrón roto, en vez de parchear uno solo.
    /// </summary>
    private static async Task<IActionResult> ForwardToWorkerAsync(
        HttpClient client, string path, object payload, CancellationToken cancellationToken)
    {
        HttpResponseMessage upstreamResponse;
        try
        {
            upstreamResponse = await client.PostAsJsonAsync(path, payload, cancellationToken);
        }
        catch (HttpRequestException)
        {
            return new ObjectResult(new { error = "No se pudo contactar al worker de imágenes." })
            {
                StatusCode = StatusCodes.Status503ServiceUnavailable
            };
        }
        catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            // El cliente cancela por su propio timeout (no el del usuario) -> esto es un
            // timeout real del HttpClient hacia el worker, no una cancelación del request
            // original. Con generaciones de varios minutos (hires_fix + restore_faces +
            // strength alto pueden sumar mucho tiempo en CPU), esto puede pasar en uso
            // normal, no solo si el worker está roto -- ver el timeout en Program.cs.
            return new ObjectResult(new
            {
                error = "El worker de imágenes tardó más de lo esperado y se agotó el tiempo de espera (45 min). " +
                         "Con hires_fix/restore_faces activados junto con strength alto, la generación puede tardar " +
                         "mucho en CPU. Prueba con menos opciones activadas a la vez, o vuelve a intentarlo."
            })
            {
                StatusCode = StatusCodes.Status504GatewayTimeout
            };
        }

        var body = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
        try
        {
            return new ObjectResult(JsonSerializer.Deserialize<object>(body))
            {
                StatusCode = (int)upstreamResponse.StatusCode
            };
        }
        catch (JsonException)
        {
            // El worker respondió pero no con JSON válido (crash a medias, proxy intermedio,
            // conexión cortada, etc.) -- se devuelve el texto crudo en un campo, nunca se deja
            // que la excepción se propague sin manejar hacia el frontend.
            return new ObjectResult(new { error = "Respuesta inválida del worker de imágenes.", raw = body })
            {
                StatusCode = StatusCodes.Status502BadGateway
            };
        }
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
            upscale = request.Upscale,
            hires_fix = request.HiresFix,
            restore_faces = request.RestoreFaces
        };

        return await ForwardToWorkerAsync(client, "/generate", payload, cancellationToken);
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
            upscale = request.Upscale,
            hires_fix = request.HiresFix,
            restore_faces = request.RestoreFaces
        };

        return await ForwardToWorkerAsync(client, "/edit", payload, cancellationToken);
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
            upscale = request.Upscale,
            hires_fix = request.HiresFix,
            restore_faces = request.RestoreFaces
        };

        return await ForwardToWorkerAsync(client, "/inpaint", payload, cancellationToken);
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

        return await ForwardToWorkerAsync(client, "/generate-controlled", payload, cancellationToken);
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

        return await ForwardToWorkerAsync(client, "/generate-with-reference", payload, cancellationToken);
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

        return await ForwardToWorkerAsync(client, "/faceswap", payload, cancellationToken);
    }

    [HttpPost("upscale")]
    public async Task<IActionResult> Upscale([FromBody] UpscaleRequest request, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ImageWorker");

        var payload = new { image_base64 = request.ImageBase64 };

        return await ForwardToWorkerAsync(client, "/upscale", payload, cancellationToken);
    }
}
