using System.Net.Http.Json;
using Generativa.Api.Models;
using Microsoft.AspNetCore.Mvc;

namespace Generativa.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class ChatController : ControllerBase
{
    private readonly IHttpClientFactory _httpClientFactory;

    public ChatController(IHttpClientFactory httpClientFactory)
    {
        _httpClientFactory = httpClientFactory;
    }

    [HttpGet("health")]
    public async Task<IActionResult> Health(CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ChatWorker");
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

    [HttpPost]
    public async Task Post([FromBody] ChatRequest request, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("ChatWorker");

        var payload = new
        {
            messages = request.Messages.Select(m => new { role = m.Role, content = m.Content }),
            stream = request.Stream,
            temperature = request.Temperature,
            max_tokens = request.MaxTokens
        };

        using var upstreamRequest = new HttpRequestMessage(HttpMethod.Post, "/chat")
        {
            Content = JsonContent.Create(payload)
        };

        HttpResponseMessage upstreamResponse;
        try
        {
            upstreamResponse = await client.SendAsync(
                upstreamRequest, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        }
        catch (HttpRequestException)
        {
            Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
            await Response.WriteAsJsonAsync(new { error = "No se pudo contactar al worker de chat." }, cancellationToken);
            return;
        }

        using (upstreamResponse)
        {
            if (!upstreamResponse.IsSuccessStatusCode)
            {
                Response.StatusCode = (int)upstreamResponse.StatusCode;
                var errorBody = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
                await Response.WriteAsync(errorBody, cancellationToken);
                return;
            }

            if (!request.Stream)
            {
                Response.ContentType = "application/json";
                var body = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
                await Response.WriteAsync(body, cancellationToken);
                return;
            }

            Response.ContentType = "text/event-stream";
            Response.Headers.CacheControl = "no-cache";
            await using var upstreamStream = await upstreamResponse.Content.ReadAsStreamAsync(cancellationToken);
            await upstreamStream.CopyToAsync(Response.Body, cancellationToken);
        }
    }
}
