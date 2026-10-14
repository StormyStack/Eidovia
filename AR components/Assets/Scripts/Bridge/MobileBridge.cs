using System;
using UnityEngine;

/// <summary>
/// Link between the game and the Eidovia React Native app (Unity as a Library).
/// Only passes game messages; the app decides what to do with them.
///
/// App -> Unity:  UnitySendMessage("XR Origin", "OnHostMessage", json)
///   {"type":"init", "moduleId":"...", "sceneName":"..."}
///   {"type":"restart"}                 start the DNA journey again
///   {"type":"wallet","total":n,"added":k}  wildcards from the server (k new cards to announce)
///
/// Unity -> App:  expo.modules.eidoviaunity.UnityBridge.onUnityMessage(json)  (arrives as UnityView onUnityMessage)
///   {"type":"ready"} · {"type":"progress",...} · {"type":"part_discovered",...}
///   {"type":"stage_completed",...} · {"type":"journey_completed"}
///   {"type":"mode","ar":true|false}   AR on this phone, or 3D mode (no ARCore)
///   {"type":"wildcard_used","mode":"skip|jump","from","to","cost","left"}
///   {"type":"previous_used","from","to"} · {"type":"wildcard_earned","stage"}
///
/// LevelManager adds this to XR Origin automatically. In the Editor messages are only logged.
/// </summary>
public class MobileBridge : MonoBehaviour
{
    public static MobileBridge Instance { get; private set; }
    public bool debugLog = true;

    [Serializable] class HostMessage { public string type; public string moduleId; public string sceneName; public int total = -1; public int added; }
    [Serializable] class Progress { public string type = "progress"; public int stage; public int stageCount; public int found; public int required; public int wildcards; }
    [Serializable] class StageDone { public string type = "stage_completed"; public int stage; public bool skipped; }
    [Serializable] class Discovered { public string type = "part_discovered"; public string part; public int stage; }
    [Serializable] class Mode { public string type = "mode"; public bool ar; }
    [Serializable] class WildUsed { public string type = "wildcard_used"; public string mode; public int from; public int to; public int cost; public int left; }
    [Serializable] class PrevUsed { public string type = "previous_used"; public int from; public int to; }
    [Serializable] class Earned { public string type = "wildcard_earned"; public int stage; }

    public string ModuleId { get; private set; }

    LevelManager level;
#if UNITY_ANDROID && !UNITY_EDITOR
    AndroidJavaClass bridge;
#endif

    void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(this); return; }
        Instance = this;
#if UNITY_ANDROID && !UNITY_EDITOR
        try { bridge = new AndroidJavaClass("expo.modules.eidoviaunity.UnityBridge"); }
        catch (Exception) { bridge = null; }    // running as a normal app, not inside the mobile app
#endif
    }

    void Start()
    {
        level = FindFirstObjectByType<LevelManager>();
        if (level != null)
        {
            level.LevelChanged += _ => SendProgress();
            level.PartDiscovered += part => { Send(JsonUtility.ToJson(new Discovered { part = part, stage = level.Index })); SendProgress(); };
            level.StageCompleted += (stage, skipped) => Send(JsonUtility.ToJson(new StageDone { stage = stage, skipped = skipped }));
            level.JourneyCompleted += () => Send("{\"type\":\"journey_completed\"}");
            level.WildcardUsed += (mode, from, to, cost, left) => Send(JsonUtility.ToJson(new WildUsed { mode = mode, from = from, to = to, cost = cost, left = left }));
            level.PreviousUsed += (from, to) => Send(JsonUtility.ToJson(new PrevUsed { from = from, to = to }));
            level.WildcardEarned += stage => Send(JsonUtility.ToJson(new Earned { stage = stage }));
        }
        ARSupportFallback.ModeDecided += SendMode;
        Send("{\"type\":\"ready\"}");
        if (ARSupportFallback.Decided) SendMode();
    }

    void OnDestroy() { ARSupportFallback.ModeDecided -= SendMode; }

    void SendMode() { Send(JsonUtility.ToJson(new Mode { ar = !ARSupportFallback.NoAR })); }

    /// <summary>True when the game runs inside the Eidovia mobile app.</summary>
    public bool IsEmbedded
    {
        get
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            return bridge != null;
#else
            return false;
#endif
        }
    }

    // ------------------------------------------------------------ App -> Unity

    public void OnHostMessage(string json)
    {
        HostMessage m = null;
        try { m = JsonUtility.FromJson<HostMessage>(json); } catch (Exception e) { Debug.LogWarning("[Bridge] bad message: " + e.Message); }
        if (m == null || string.IsNullOrEmpty(m.type)) return;
        if (debugLog) Debug.Log("[Bridge] <- " + m.type);

        switch (m.type)
        {
            case "init":
                ModuleId = m.moduleId;
                SendProgress();
                if (ARSupportFallback.Decided) SendMode();
                break;
            case "restart":
                if (level != null) level.Restart();
                break;
            case "wallet":
                if (level != null && m.total >= 0) { level.SetWallet(m.total, m.added); SendProgress(); }
                break;
        }
    }

    // ------------------------------------------------------------ Unity -> App

    void SendProgress()
    {
        if (level == null) return;
        Send(JsonUtility.ToJson(new Progress
        {
            stage = level.Index, stageCount = level.StageCount, found = level.FoundCount, required = level.RequiredCount, wildcards = level.Wildcards,
        }));
    }

    public void Send(string json)
    {
        if (debugLog) Debug.Log("[Bridge] -> " + json);
#if UNITY_ANDROID && !UNITY_EDITOR
        if (bridge == null) return;
        try { bridge.CallStatic("onUnityMessage", json); }
        catch (Exception e) { Debug.LogWarning("[Bridge] send failed: " + e.Message); }
#endif
    }
}
