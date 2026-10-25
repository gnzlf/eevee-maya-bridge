using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

internal static class Program
{
    internal static string[] Arguments;
    internal static string Extract()
    {
        string folder = Path.Combine(Path.GetTempPath(), "EeveeMayaBridge-Setup-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        foreach (string name in new[] { "payload.zip", "InstallBridge.ps1" })
            using (Stream input = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
            using (FileStream output = File.Create(Path.Combine(folder, name))) input.CopyTo(output);
        return folder;
    }
    internal static string Quote(string value)
    {
        StringBuilder result = new StringBuilder("\""); int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { ++slashes; continue; }
            if (c == '"') result.Append('\\', slashes * 2 + 1);
            else result.Append('\\', slashes);
            result.Append(c); slashes = 0;
        }
        return result.Append('\\', slashes * 2).Append('"').ToString();
    }
    internal static int Install(Action<string> output)
    {
        string folder = Extract();
        try
        {
            string arguments = "-NoProfile -ExecutionPolicy Bypass -File " + Quote(Path.Combine(folder, "InstallBridge.ps1")) +
                " -PayloadPath " + Quote(Path.Combine(folder, "payload.zip"));
            for (int i = 0; i < Arguments.Length; ++i)
            {
                string flag = Arguments[i];
                if (flag == "--install-root" || flag == "--blender-path" || flag == "--module-directory")
                {
                    if (i + 1 >= Arguments.Length) throw new ArgumentException("Falta el valor de " + flag);
                    string name = flag == "--install-root" ? "InstallRoot" : flag == "--blender-path" ? "BlenderPath" : "ModuleDirectory";
                    arguments += " -" + name + " " + Quote(Arguments[++i]);
                }
                else if (flag == "--test-no-registration") arguments += " -NoRegistration";
                else if (flag == "--test-skip-maya-check") arguments += " -SkipMayaCheck";
            }
            ProcessStartInfo info = new ProcessStartInfo("powershell.exe", arguments);
            info.UseShellExecute = false; info.CreateNoWindow = true; info.WindowStyle = ProcessWindowStyle.Hidden;
            info.RedirectStandardOutput = true; info.RedirectStandardError = true;
            info.StandardOutputEncoding = Encoding.UTF8; info.StandardErrorEncoding = Encoding.UTF8;
            using (Process process = new Process())
            {
                process.StartInfo = info;
                process.OutputDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) output(e.Data); };
                process.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) output(e.Data); };
                process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine(); process.WaitForExit();
                return process.ExitCode;
            }
        }
        finally { try { Directory.Delete(folder, true); } catch (IOException) { } }
    }
    [STAThread]
    private static int Main(string[] args)
    {
        bool owns;
        using (System.Threading.Mutex gate = new System.Threading.Mutex(true, "Local\\EeveeMayaBridgeInstaller-" + Environment.UserName, out owns))
        {
            if (!owns) { if (Array.IndexOf(args,"--headless") < 0) MessageBox.Show("Ya hay otra instalación de Eevee en curso."); return 1; }
            return Execute(args);
        }
    }
    private static int Execute(string[] args)
    {
        Arguments = args;
        if (Array.IndexOf(args, "--headless") >= 0)
        {
            string log = Path.Combine(Path.GetTempPath(), "EeveeMayaBridge-install.log");
            using (StreamWriter writer = new StreamWriter(log, false, Encoding.UTF8))
            {
                object gate = new object();
                try { return Install(delegate(string line) { lock (gate) { writer.WriteLine(line); writer.Flush(); } }); }
                catch (Exception error) { writer.WriteLine(error.ToString()); return 1; }
            }
        }
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        using (SetupWindow window = new SetupWindow()) { Application.Run(window); return window.Result; }
    }
}

internal sealed class SetupWindow : Form
{
    private readonly Label status;
    private readonly ProgressBar progress;
    private readonly TextBox log;
    private readonly Button action;
    private bool installing;
    internal int Result = 2;
    internal SetupWindow()
    {
        Text = "Instalar Eevee Maya Bridge"; ClientSize = new Size(610, 420);
        StartPosition = FormStartPosition.CenterScreen; FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
        Font = new Font("Segoe UI", 10);
        Label heading = new Label { Text = "Eevee Maya Bridge", Font = new Font("Segoe UI", 19, FontStyle.Bold), Location = new Point(24, 20), Size = new Size(560, 40) };
        Label description = new Label { Text = "Viewport Eevee para Maya 2024 · Windows de 64 bits\nIncluye el puente y prepara Blender portátil si hace falta.\nLas actualizaciones se activan al reiniciar Maya.", Location = new Point(26, 75), Size = new Size(550, 80) };
        status = new Label { Text = "Listo para instalar en tu cuenta de Windows.", Location = new Point(26, 162), Size = new Size(550, 40) };
        progress = new ProgressBar { Location = new Point(26, 205), Size = new Size(550, 18) };
        log = new TextBox { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Location = new Point(26, 239), Size = new Size(550, 107), Font = new Font("Segoe UI", 9) };
        action = new Button { Text = "Instalar / actualizar", Location = new Point(365, 367), Size = new Size(210, 33) };
        Controls.AddRange(new Control[] { heading, description, status, progress, log, action });
        action.Click += StartInstall;
        FormClosing += delegate(object sender, FormClosingEventArgs e) { if (installing) e.Cancel = true; };
    }
    private void WriteLine(string line)
    {
        if (InvokeRequired) { BeginInvoke(new Action<string>(WriteLine), line); return; }
        log.AppendText(line + Environment.NewLine);
        if (line.StartsWith("PROGRESS|"))
        {
            string[] parts = line.Split(new[] { '|' }, 3); int value;
            if (parts.Length == 3 && Int32.TryParse(parts[1], out value)) { progress.Value = Math.Max(0, Math.Min(100, value)); status.Text = parts[2]; }
        }
    }
    private void StartInstall(object sender, EventArgs args)
    {
        if (Result != 2) { Close(); return; }
        installing = true; action.Enabled = false; status.Text = "Preparando instalación…";
        BackgroundWorker worker = new BackgroundWorker();
        worker.DoWork += delegate(object s, DoWorkEventArgs e) { e.Result = Program.Install(WriteLine); };
        worker.RunWorkerCompleted += delegate(object s, RunWorkerCompletedEventArgs e)
        {
            installing = false; action.Enabled = true; action.Text = "Cerrar";
            Result = e.Error == null ? (int)e.Result : 1;
            if (Result == 0) status.Text = "Instalado. Reinicia Maya y carga eeveeBridge.py en Plug-in Manager.";
            else { status.Text = "No se completó la instalación. Revisa el mensaje de abajo."; if (e.Error != null) WriteLine(e.Error.Message); }
        };
        worker.RunWorkerAsync();
    }
}
