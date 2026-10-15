using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

/// <summary>
/// Menu: Eidovia > Export for Mobile App
/// Exports this game as an Android library ("Unity as a Library") into the Eidovia React Native app:
///   Thesis/apps/mobile/unity/builds/android   (unityLibrary + gradle files)
/// The mobile app's config plugin (modules/eidovia-unity) links it into the Android build.
///
/// Menu: Eidovia > Build Mobile App (APK)
/// Runs Thesis/apps/mobile/scripts/build-android.ps1 in a PowerShell window: expo prebuild + Gradle,
/// producing ONE app (Eidovia) with this game inside, at Thesis/apps/mobile/dist/Eidovia-release.apk.
/// </summary>
public static class EidoviaMobileExport
{
    const string PathKey = "Eidovia.MobileExportPath";

    /// <summary>
    /// Thesis/apps/mobile/unity/builds/android. Works for the project inside the repo (Thesis/AR components)
    /// and for a copy next to the repo (…/AR Game beside …/Thesis).
    /// </summary>
    static string DefaultPath
    {
        get
        {
            string inRepo = Path.GetFullPath(Path.Combine(Application.dataPath, "../../apps/mobile"));
            string mobile = Directory.Exists(inRepo) ? inRepo
                : Path.GetFullPath(Path.Combine(Application.dataPath, "../../Thesis/apps/mobile"));
            return Path.Combine(mobile, "unity", "builds", "android");
        }
    }

    [MenuItem("Eidovia/Export for Mobile App", priority = 1)]
    public static void Export()
    {
        string path = EditorPrefs.GetString(PathKey, DefaultPath);
        if (!Directory.Exists(Path.GetDirectoryName(path)))
        {
            string picked = EditorUtility.SaveFolderPanel("Folder for the Unity export (apps/mobile/unity/builds/android)", "", "android");
            if (string.IsNullOrEmpty(picked)) return;
            path = picked;
        }
        EditorPrefs.SetString(PathKey, path);
        Export(path);
    }

    [MenuItem("Eidovia/Build Mobile App (APK)", priority = 2)]
    public static void BuildApp()
    {
        string export = EditorPrefs.GetString(PathKey, DefaultPath);
        string app = Path.GetFullPath(Path.Combine(export, "../../.."));          // .../apps/mobile
        string script = Path.Combine(app, "scripts", "build-android.ps1");
        if (!File.Exists(Path.Combine(export, "unityLibrary", "build.gradle")))
        {
            EditorUtility.DisplayDialog("Eidovia build", "Run Eidovia > Export for Mobile App first.", "OK");
            return;
        }
        if (!File.Exists(script))
        {
            EditorUtility.DisplayDialog("Eidovia build", "Build script not found:\n" + script, "OK");
            return;
        }
        var start = new System.Diagnostics.ProcessStartInfo("powershell.exe",
            "-NoProfile -NoExit -ExecutionPolicy Bypass -File \"" + script + "\"")
        {
            UseShellExecute = true,
            WorkingDirectory = app,
        };
        System.Diagnostics.Process.Start(start);
        Debug.Log("[Eidovia] Building the mobile app (log: " + Path.Combine(app, "dist", "build-android.log") + ")");
    }

    [MenuItem("Eidovia/Change Export Folder...", priority = 20)]
    public static void ChangeFolder()
    {
        string picked = EditorUtility.SaveFolderPanel("Folder for the Unity export", EditorPrefs.GetString(PathKey, DefaultPath), "android");
        if (!string.IsNullOrEmpty(picked)) EditorPrefs.SetString(PathKey, picked);
    }

    /// <param name="interactive">false: no dialogs and no Explorer window (scripted export)</param>
    public static void Export(string path, bool interactive = true)
    {
        if (EditorUserBuildSettings.activeBuildTarget != BuildTarget.Android)
        {
            if (interactive) EditorUtility.DisplayDialog("Eidovia export", "Switch the build target to Android first (File > Build Profiles > Android > Switch Platform).", "OK");
            else throw new System.InvalidOperationException("Build target is not Android");
            return;
        }

        // Settings that "Unity as a Library" needs
        PlayerSettings.Android.applicationEntry = AndroidApplicationEntry.Activity;     // GameActivity cannot be embedded
        PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
        // every Android 10+ phone: 64-bit (ARM64) and older 32-bit (ARMv7) ones
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARMv7 | AndroidArchitecture.ARM64;
        bool previousExport = EditorUserBuildSettings.exportAsGoogleAndroidProject;
        EditorUserBuildSettings.exportAsGoogleAndroidProject = true;

        string[] scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
        if (scenes.Length == 0) scenes = new[] { "Assets/Scenes/Root_ARPersistent.unity" };

        Directory.CreateDirectory(path);
        var options = new BuildPlayerOptions
        {
            scenes = scenes,
            locationPathName = path,
            target = BuildTarget.Android,
            options = BuildOptions.None,
        };

        BuildReport report;
        try { report = BuildPipeline.BuildPlayer(options); }
        finally { EditorUserBuildSettings.exportAsGoogleAndroidProject = previousExport; }

        if (report.summary.result != BuildResult.Succeeded)
        {
            if (interactive) EditorUtility.DisplayDialog("Eidovia export", "Export failed: " + report.summary.result + ". See the Console.", "OK");
            else throw new System.Exception("Export failed: " + report.summary.result);
            return;
        }

        PatchLibraryManifest(Path.Combine(path, "unityLibrary", "src", "main", "AndroidManifest.xml"));
        File.WriteAllText(Path.Combine(path, "EIDOVIA_EXPORT.txt"),
            "Exported from Unity " + Application.unityVersion + " on " + System.DateTime.Now + "\n" +
            "Next: in Thesis/apps/mobile run  npx expo prebuild --platform android --clean  then  npx expo run:android --device\n");
        Debug.Log("[Eidovia] Unity library exported to " + path);
        if (!interactive) return;
        EditorUtility.RevealInFinder(path);
        EditorUtility.DisplayDialog("Eidovia export", "Done!\n\n" + path +
            "\n\nNow, in Thesis/apps/mobile:\n  npx expo prebuild --platform android --clean\n  npx expo run:android --device", "OK");
    }

    /// <summary>
    /// The library must not declare its own launcher or app-level attributes (the React Native app owns those),
    /// so the build has ONE app icon. Unity's activity stays in the library but is not exported.
    /// </summary>
    static void PatchLibraryManifest(string file)
    {
        if (!File.Exists(file)) { Debug.LogWarning("[Eidovia] manifest not found: " + file); return; }
        string xml = File.ReadAllText(file);
        xml = Regex.Replace(xml, @"<intent-filter>(?:(?!</intent-filter>).)*android\.intent\.category\.LAUNCHER(?:(?!</intent-filter>).)*</intent-filter>", "", RegexOptions.Singleline);
        var attr = new Regex(@"(<application\b[^>]*?)\s+android:(icon|roundIcon|label|theme|extractNativeLibs|allowBackup|enableOnBackInvokedCallback|appCategory)=""[^""]*""");
        for (string before = null; before != xml;) { before = xml; xml = attr.Replace(xml, "$1", 1); }
        xml = Regex.Replace(xml, @"(<activity\b[^>]*?android:exported="")true("")", "$1false$2");
        // AR is optional (3D mode on phones without ARCore), so these features must not exclude any phone
        xml = Regex.Replace(xml, @"(<uses-feature\s+android:name=""(?:android\.hardware\.camera\.ar|com\.google\.ar\.core\.depth)""\s+android:required="")true("")", "$1false$2");
        File.WriteAllText(file, xml);
    }
}
