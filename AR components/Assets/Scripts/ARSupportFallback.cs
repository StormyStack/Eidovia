using System;
using System.Collections;
using UnityEngine;
using UnityEngine.XR.ARFoundation;

/// <summary>
/// Makes the game run on every phone.
///   ARCore works          -> normal AR (camera view, place the DNA on a surface)
///   no ARCore on the phone -> 3D mode: AR is switched off, the DNA appears in front of the camera on a plain
///                            background; tap, drag, pinch and twist work as in AR, levels are the same
/// ARCore is set to "Optional" (Project Settings > XR Plug-in Management > ARCore) so the app installs everywhere.
/// LevelManager adds this to XR Origin automatically.
/// </summary>
public class ARSupportFallback : MonoBehaviour
{
    /// <summary>True when the game runs without AR (3D mode).</summary>
    public static bool NoAR { get; private set; }
    /// <summary>True once AR support has been checked.</summary>
    public static bool Decided { get; private set; }
    /// <summary>Raised once the mode is known (read NoAR).</summary>
    public static event Action ModeDecided;

    [SerializeField] float needsInstallGrace = 15f;   // ARCore install prompt declined / ignored -> 3D mode
    [SerializeField] float installTimeout = 120f;     // downloading Google Play Services for AR
    [SerializeField] Color background = new Color(0.07f, 0.10f, 0.18f);

    ARModelSpawner spawner;

    IEnumerator Start()
    {
        NoAR = false;
        Decided = false;
        spawner = FindFirstObjectByType<ARModelSpawner>();
#if UNITY_EDITOR
        Decide(false);   // the Editor keeps its mouse-on-a-virtual-floor testing
        yield break;
#else
        if (ARSession.state == ARSessionState.None || ARSession.state == ARSessionState.CheckingAvailability)
            yield return ARSession.CheckAvailability();

        float start = Time.realtimeSinceStartup;
        float needsInstallSince = -1f;
        while (Time.realtimeSinceStartup - start < installTimeout)
        {
            ARSessionState s = ARSession.state;
            if (s == ARSessionState.Unsupported) break;
            if (s == ARSessionState.Ready || s == ARSessionState.SessionInitializing || s == ARSessionState.SessionTracking) break;
            if (s == ARSessionState.NeedsInstall)
            {
                if (needsInstallSince < 0f) needsInstallSince = Time.realtimeSinceStartup;
                if (Time.realtimeSinceStartup - needsInstallSince > needsInstallGrace) break;
            }
            else needsInstallSince = -1f;
            yield return null;
        }
        ARSessionState final = ARSession.state;
        Decide(!(final == ARSessionState.Ready || final == ARSessionState.SessionInitializing || final == ARSessionState.SessionTracking));
#endif
    }

    void Decide(bool noAR)
    {
        NoAR = noAR;
        Decided = true;
        if (noAR) EnterNoArMode();
        Debug.Log("[ARSupport] " + (noAR ? "3D mode (no ARCore on this phone)" : "AR mode") + ", session state " + ARSession.state);
        if (ModeDecided != null) ModeDecided();
    }

    void EnterNoArMode()
    {
        foreach (ARSession s in FindObjectsByType<ARSession>(FindObjectsSortMode.None)) s.enabled = false;
        foreach (ARPlaneManager p in FindObjectsByType<ARPlaneManager>(FindObjectsSortMode.None)) p.enabled = false;
        Camera cam = Camera.main;
        if (cam == null) return;
        ARCameraBackground bg = cam.GetComponent<ARCameraBackground>();
        if (bg != null) bg.enabled = false;
        ARCameraManager camManager = cam.GetComponent<ARCameraManager>();
        if (camManager != null) camManager.enabled = false;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = background;
    }

    void Update()
    {
        // 3D mode: nothing to scan, so the DNA appears right away (also after a level change removed it)
        if (!NoAR || spawner == null || spawner.HasModel || !spawner.HasPrefab) return;
        spawner.PlaceOrMove(new Vector2(Screen.width * 0.5f, Screen.height * 0.45f));
    }
}
