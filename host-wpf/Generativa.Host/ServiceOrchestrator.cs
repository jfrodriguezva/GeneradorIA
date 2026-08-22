using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;

namespace Generativa.Host;

public record ManagedService(
    string Name,
    string HealthUrl,
    Func<string, ProcessStartInfo> BuildStartInfo);

public class ServiceOrchestrator
{
    private readonly string _root;
    private readonly string _logDir;
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(3) };
    private readonly List<Process> _spawned = [];

    public ServiceOrchestrator(string root)
    {
        _root = root;
        _logDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Generativa", "logs");
        Directory.CreateDirectory(_logDir);
    }

    public static string? FindRepoRoot(string startDir)
    {
        var dir = new DirectoryInfo(startDir);
        for (var i = 0; i < 8 && dir is not null; i++, dir = dir.Parent)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, "worker-python")) &&
                Directory.Exists(Path.Combine(dir.FullName, "api-csharp")))
            {
                return dir.FullName;
            }
        }
        return null;
    }

    private IEnumerable<ManagedService> Services()
    {
        var modelPath = Path.Combine(_root, "worker-python", "models", "qwen2.5-3b-instruct-q4_k_m.gguf");
        var workerPythonDir = Path.Combine(_root, "worker-python");

        yield return new ManagedService(
            "Worker de chat",
            "http://127.0.0.1:8011/health",
            _ => new ProcessStartInfo
            {
                FileName = Path.Combine(workerPythonDir, ".venv", "Scripts", "python.exe"),
                Arguments = "chat/main.py",
                WorkingDirectory = workerPythonDir,
                Environment = { ["GENERATIVA_MODEL_PATH"] = modelPath },
            });

        yield return new ManagedService(
            "Worker de imágenes",
            "http://127.0.0.1:8002/health",
            _ => new ProcessStartInfo
            {
                FileName = Path.Combine(workerPythonDir, ".venv-image", "Scripts", "python.exe"),
                Arguments = "image/main.py",
                WorkingDirectory = workerPythonDir,
            });

        yield return new ManagedService(
            "API",
            "http://127.0.0.1:20001/health",
            _ => BuildApiStartInfo());

        yield return new ManagedService(
            "Frontend",
            "http://127.0.0.1:20000/",
            _ => BuildFrontendStartInfo());
    }

    private ProcessStartInfo BuildApiStartInfo()
    {
        var apiProjectDir = Path.Combine(_root, "api-csharp", "Generativa.Api");

        // Layout instalado: exe self-contained publicado como hermano del host.
        var installedExe = Path.Combine(_root, "api-csharp", "Generativa.Api.exe");
        if (File.Exists(installedExe))
        {
            return new ProcessStartInfo
            {
                FileName = installedExe,
                WorkingDirectory = Path.GetDirectoryName(installedExe)!,
                Environment = { ["ASPNETCORE_URLS"] = "http://127.0.0.1:20001" },
            };
        }

        // Layout de desarrollo: `dotnet publish` local en api-csharp/Generativa.Api/publish.
        var publishedExe = Path.Combine(apiProjectDir, "publish", "Generativa.Api.exe");
        if (File.Exists(publishedExe))
        {
            return new ProcessStartInfo
            {
                FileName = publishedExe,
                WorkingDirectory = Path.GetDirectoryName(publishedExe)!,
                Environment = { ["ASPNETCORE_URLS"] = "http://127.0.0.1:20001" },
            };
        }

        var debugDll = Path.Combine(apiProjectDir, "bin", "Debug", "net10.0", "Generativa.Api.dll");
        if (File.Exists(debugDll))
        {
            return new ProcessStartInfo
            {
                FileName = "dotnet",
                Arguments = $"\"{debugDll}\"",
                WorkingDirectory = apiProjectDir,
                Environment = { ["ASPNETCORE_URLS"] = "http://127.0.0.1:20001" },
            };
        }

        return new ProcessStartInfo
        {
            FileName = "dotnet",
            Arguments = "run --launch-profile http",
            WorkingDirectory = apiProjectDir,
        };
    }

    private static readonly string[] KnownNodeInstallDirs =
    [
        @"C:\Program Files\nodejs",
        @"C:\Program Files (x86)\nodejs",
    ];

    private ProcessStartInfo BuildFrontendStartInfo()
    {
        var frontendDir = Path.Combine(_root, "frontend-nextjs");
        // BUILD_ID solo existe tras `next build`: la carpeta .next tambien la crea `next dev`,
        // asi que mirar solo la carpeta hacia lanzar `next start` sin build de produccion.
        var hasProdBuild = File.Exists(Path.Combine(frontendDir, ".next", "BUILD_ID"));

        // npm.cmd es un batch: si se lanza como proceso directo resuelve sus rutas internas
        // contra el directorio de trabajo y busca npm-prefix.js dentro del proyecto (falla con
        // MODULE_NOT_FOUND). Va por cmd /c call y con la ruta completa, nunca por nombre suelto.
        var npmCmd = ResolveNpmCmd();

        return new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = $"/c call \"{npmCmd}\" run {(hasProdBuild ? "start" : "dev")}",
            WorkingDirectory = frontendDir,
        };
    }

    /// <summary>
    /// Ruta completa de npm.cmd. Si Node.js se acaba de instalar (ej. durante el setup del
    /// instalador) puede no estar todavía en el PATH de este proceso, así que se cae a las
    /// rutas de instalación por defecto.
    /// </summary>
    private static string ResolveNpmCmd()
    {
        var pathVar = Environment.GetEnvironmentVariable("PATH") ?? "";
        var fromPath = pathVar.Split(Path.PathSeparator)
            .Where(dir => dir.Length > 0)
            .Select(dir => Path.Combine(dir, "npm.cmd"))
            .FirstOrDefault(File.Exists);

        return fromPath
            ?? KnownNodeInstallDirs.Select(dir => Path.Combine(dir, "npm.cmd")).FirstOrDefault(File.Exists)
            ?? "npm.cmd";
    }

    public async Task StartAllAsync(IProgress<string> progress, CancellationToken cancellationToken)
    {
        foreach (var service in Services())
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (await IsHealthyAsync(service.HealthUrl, cancellationToken))
            {
                progress.Report($"{service.Name}: ya estaba corriendo");
                continue;
            }

            progress.Report($"{service.Name}: iniciando...");
            var startInfo = service.BuildStartInfo(_root);
            startInfo.UseShellExecute = false;
            startInfo.RedirectStandardOutput = true;
            startInfo.RedirectStandardError = true;
            startInfo.CreateNoWindow = true;

            var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
            var logPath = Path.Combine(_logDir, $"{SanitizeFileName(service.Name)}.log");
            var logWriter = new StreamWriter(logPath, append: false) { AutoFlush = true };
            process.OutputDataReceived += (_, e) => { if (e.Data is not null) logWriter.WriteLine(e.Data); };
            process.ErrorDataReceived += (_, e) => { if (e.Data is not null) logWriter.WriteLine(e.Data); };

            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            _spawned.Add(process);

            progress.Report($"{service.Name}: esperando a que responda...");
            var ready = await WaitForHealthyAsync(service.HealthUrl, TimeSpan.FromMinutes(5), cancellationToken);
            progress.Report(ready ? $"{service.Name}: listo" : $"{service.Name}: no respondió a tiempo (revisa {logPath})");
        }
    }

    private async Task<bool> IsHealthyAsync(string url, CancellationToken cancellationToken)
    {
        try
        {
            using var response = await _http.GetAsync(url, cancellationToken);
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    private async Task<bool> WaitForHealthyAsync(string url, TimeSpan timeout, CancellationToken cancellationToken)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (await IsHealthyAsync(url, cancellationToken))
            {
                return true;
            }
            await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);
        }
        return false;
    }

    private static string SanitizeFileName(string name) =>
        string.Join("_", name.Split(Path.GetInvalidFileNameChars()));

    public void StopAll()
    {
        foreach (var process in _spawned)
        {
            try
            {
                if (!process.HasExited)
                {
                    process.Kill(entireProcessTree: true);
                }
            }
            catch
            {
                // el proceso ya pudo haber salido por su cuenta
            }
        }
    }
}
