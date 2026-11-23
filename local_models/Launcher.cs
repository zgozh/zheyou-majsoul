// SPDX-License-Identifier: Apache-2.0
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyProduct("Zheyou Mahjong Soul")]
[assembly: AssemblyTitle("Zheyou")]
[assembly: AssemblyVersion("0.1.0.0")]
[assembly: AssemblyFileVersion("0.1.0.0")]

internal static class Launcher
{
    static readonly string App = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "app");

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern bool SetWindowText(IntPtr window, string title);

    [STAThread]
    static int Main()
    {
        bool acquired;
        using (var mutex = new Mutex(true, "Local\\ZheyouMajsoul", out acquired))
        {
            if (!acquired) return 0;
            Process service = null;
            try
            {
                Directory.CreateDirectory(Path.Combine(App, "logs"));
                service = StartService();
                WaitForListener(service);
                using (var ui = StartUi())
                {
                    bool triedRestart = false;
                    bool branded = false;
                    while (!ui.WaitForExit(750))
                    {
                        if (!branded)
                        {
                            ui.Refresh();
                            if (ui.MainWindowHandle != IntPtr.Zero)
                                branded = SetWindowText(ui.MainWindowHandle, "柘栯");
                        }
                        if (!service.HasExited) continue;
                        if (triedRestart) break;
                        triedRestart = true;
                        service.Dispose();
                        service = StartService();
                    }
                    ui.WaitForExit();
                    if (ui.ExitCode != 0) Log("Client exited with code " + ui.ExitCode);
                    return ui.ExitCode;
                }
            }
            catch (Exception error)
            {
                Log(error.ToString());
                MessageBox.Show("启动失败。请查看 app\\logs\\launcher.log 和 local-models.log。\n" + error.Message,
                    "柘栯", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
            finally
            {
                if (service != null)
                {
                    if (!service.HasExited)
                    {
                        try { service.StandardInput.WriteLine("stop"); service.StandardInput.Close(); }
                        catch (IOException) { }
                        if (!service.WaitForExit(8000)) service.Kill();
                    }
                    service.Dispose();
                }
            }
        }
    }

    static Process StartService()
    {
        var info = new ProcessStartInfo(Path.Combine(App, "runtime", "python", "python.exe"),
            "-B local_models\\server.py --managed") {
            WorkingDirectory = App, UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
        };
        return Process.Start(info);
    }

    static void WaitForListener(Process service)
    {
        var deadline = Stopwatch.StartNew();
        while (deadline.Elapsed < TimeSpan.FromSeconds(12))
        {
            if (service.HasExited) throw new InvalidOperationException("本地推理服务退出。请检查端口 25034 和依赖日志。");
            try
            {
                var request = WebRequest.Create("http://127.0.0.1:25034/healthz");
                request.Proxy = null;
                request.Timeout = 600;
                using (var response = request.GetResponse()) return;
            }
            catch (WebException error)
            {
                if (error.Response != null) error.Response.Dispose();
                Thread.Sleep(250);
            }
        }
        throw new TimeoutException("本地推理服务未能在启动期限内监听。");
    }

    static Process StartUi()
    {
        var info = new ProcessStartInfo(Path.Combine(App, "ZheyouClient.exe")) {
            WorkingDirectory = App, UseShellExecute = false, RedirectStandardError = true,
        };
        info.EnvironmentVariables["RUST_BACKTRACE"] = "1";
        var ui = new Process { StartInfo = info };
        ui.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs line) {
            if (line.Data != null) Log(line.Data);
        };
        ui.Start();
        ui.BeginErrorReadLine();
        return ui;
    }

    static readonly object LogLock = new object();
    static void Log(string text)
    {
        lock (LogLock)
        {
            try { File.AppendAllText(Path.Combine(App, "logs", "launcher.log"), DateTime.Now + " " + text + "\r\n"); }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }
}
