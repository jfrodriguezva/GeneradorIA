using System.Collections.ObjectModel;
using System.IO;
using System.Windows;

namespace Generativa.Host;

public partial class MainWindow : Window
{
    private const string FrontendUrl = "http://127.0.0.1:20000";

    private readonly ObservableCollection<string> _statusLines = [];
    private ServiceOrchestrator? _orchestrator;

    public MainWindow()
    {
        InitializeComponent();
        StatusList.ItemsSource = _statusLines;
        Loaded += MainWindow_Loaded;
        Closing += MainWindow_Closing;
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        var root = ServiceOrchestrator.FindRepoRoot(AppContext.BaseDirectory);
        if (root is null)
        {
            _statusLines.Add("No se encontró la carpeta raíz del proyecto (worker-python / api-csharp).");
            _statusLines.Add("Verifica la instalación.");
            return;
        }

        _orchestrator = new ServiceOrchestrator(root);
        var progress = new Progress<string>(line =>
        {
            if (_statusLines.Count > 0 && _statusLines[^1].StartsWith(line.Split(':')[0]))
            {
                _statusLines[^1] = line;
            }
            else
            {
                _statusLines.Add(line);
            }
        });

        try
        {
            await _orchestrator.StartAllAsync(progress, CancellationToken.None);
        }
        catch (Exception ex)
        {
            _statusLines.Add($"Error iniciando servicios: {ex.Message}");
            return;
        }

        await Browser.EnsureCoreWebView2Async();
        Browser.CoreWebView2.Navigate(FrontendUrl);
        StartupPanel.Visibility = Visibility.Collapsed;
        Browser.Visibility = Visibility.Visible;
    }

    private void MainWindow_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        _orchestrator?.StopAll();
    }
}
