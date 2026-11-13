var builder = WebApplication.CreateBuilder(args);

var chatWorkerBaseUrl = Environment.GetEnvironmentVariable("GENERATIVA_CHAT_WORKER_URL")
    ?? builder.Configuration["ChatWorker:BaseUrl"]
    ?? "http://127.0.0.1:8011";
var imageWorkerBaseUrl = Environment.GetEnvironmentVariable("GENERATIVA_IMAGE_WORKER_URL")
    ?? builder.Configuration["ImageWorker:BaseUrl"]
    ?? "http://127.0.0.1:8002";

Console.WriteLine($"[Generativa.Api] ChatWorker  -> {chatWorkerBaseUrl}");
Console.WriteLine($"[Generativa.Api] ImageWorker -> {imageWorkerBaseUrl}");

builder.Services.AddControllers();
builder.Services.AddOpenApi();

builder.Services.AddHttpClient("ChatWorker", client =>
{
    client.BaseAddress = new Uri(chatWorkerBaseUrl);
    client.DefaultRequestHeaders.Add("ngrok-skip-browser-warning", "true");
    client.Timeout = TimeSpan.FromMinutes(5);
});

builder.Services.AddHttpClient("ImageWorker", client =>
{
    client.BaseAddress = new Uri(imageWorkerBaseUrl);
    client.DefaultRequestHeaders.Add("ngrok-skip-browser-warning", "true");
    // Subido de 20 a 45 min: combinar hires_fix + restore_faces + strength alto en
    // /inpaint puede pasar los 20 min en CPU (visto en uso real, no solo en teoría) y
    // el timeout anterior lo cortaba a medias -- ver ImageController.ForwardToWorkerAsync
    // para el manejo de error cuando de todos modos se agota.
    client.Timeout = TimeSpan.FromMinutes(45);
});

builder.Services.AddCors(options =>
{
    options.AddPolicy("LocalFrontend", policy =>
    {
        policy.WithOrigins("http://localhost:20001", "http://127.0.0.1:20001")
              .AllowAnyHeader()
              .AllowAnyMethod();
    });
});

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.UseCors("LocalFrontend");
app.UseAuthorization();
app.MapControllers();
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.Run();
