var builder = WebApplication.CreateBuilder(args);

var chatWorkerBaseUrl = builder.Configuration["ChatWorker:BaseUrl"] ?? "http://127.0.0.1:8011";
var imageWorkerBaseUrl = builder.Configuration["ImageWorker:BaseUrl"] ?? "http://127.0.0.1:8002";

builder.Services.AddControllers();
builder.Services.AddOpenApi();

builder.Services.AddHttpClient("ChatWorker", client =>
{
    client.BaseAddress = new Uri(chatWorkerBaseUrl);
    client.Timeout = TimeSpan.FromMinutes(5);
});

builder.Services.AddHttpClient("ImageWorker", client =>
{
    client.BaseAddress = new Uri(imageWorkerBaseUrl);
    client.Timeout = TimeSpan.FromMinutes(20);
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
