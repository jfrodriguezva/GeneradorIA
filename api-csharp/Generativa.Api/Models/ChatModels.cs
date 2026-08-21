using System.Text.Json.Serialization;

namespace Generativa.Api.Models;

public class ChatMessage
{
    [JsonPropertyName("role")]
    public string Role { get; set; } = "user";

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;
}

public class ChatRequest
{
    public List<ChatMessage> Messages { get; set; } = [];
    public bool Stream { get; set; } = true;
    public double Temperature { get; set; } = 0.7;
    public int MaxTokens { get; set; } = 1024;
}
