using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

/// <summary>
/// The DNA exploration journey: one continuous game.
/// Each stage shows one model from the Levels list. The player discovers every kind of part in it by tapping;
/// when everything is found the model morphs into the next stage
/// (building blocks -> nucleotide -> single strand -> two strands -> double helix).
/// Progress is saved on the device. Put it on XR Origin next to ARModelSpawner.
/// Wildcard power-ups and the Previous button are in LevelManager.Power.cs.
/// </summary>
public partial class LevelManager : MonoBehaviour
{
    [Serializable]
    public class Level
    {
        public string title;
        public GameObject prefab;
        [Tooltip("Story text when the stage starts (leave empty for the built-in text)")]
        [TextArea] public string intro;
        [Tooltip("Text when every part of the stage was discovered (leave empty for the built-in text)")]
        [TextArea] public string complete;
    }

    [SerializeField] ARModelSpawner spawner;
    [SerializeField] ComponentPicker picker;
    [SerializeField] Level[] levels =
    {
        new Level { title = "Level 1: DNA components" },
        new Level { title = "Level 2: Nucleotide" },
        new Level { title = "Level 3: Single strand" },
        new Level { title = "Level 4: Double strand + hydrogen bonds" },
        new Level { title = "Level 5: Double helix" },
    };
    [SerializeField] int startLevel = 0;               // used when there is no saved progress
    [SerializeField] bool buildDefaultUI = true;

    [Header("Game")]
    [SerializeField] bool rememberProgress = true;
    [Tooltip("Seconds without a new discovery before an undiscovered part glows as a hint (0 = never)")]
    [SerializeField] float hintDelay = 25f;
    [SerializeField] float morphOutTime = 0.55f;
    [SerializeField] float morphInTime = 0.8f;

    [Header("Wildcard (skip a stage)")]
    [SerializeField] bool showWildcard = true;
    [SerializeField] int startWildcards = 3;
    [SerializeField] int maxWildcards = 5;
    [Tooltip("Finishing a stage without skipping gives +1 wildcard")]
    [SerializeField] bool earnWildcards = true;

    public int Index { get; private set; }
    public int Wildcards { get; private set; }
    public event Action<int> StageSkipped;
    public bool JourneyComplete { get; private set; }
    public event Action<int> LevelChanged;
    public event Action<string> PartDiscovered;
    public event Action JourneyCompleted;
    /// <summary>Stage index and whether it was skipped with a wildcard.</summary>
    public event Action<int, bool> StageCompleted;

    // progress numbers for the mobile app bridge
    public int FoundCount { get { return found.Count; } }
    public int RequiredCount { get { return required.Count; } }
    public int StageCount { get { return levels.Length; } }

    const string SaveKey = "DNAJourney.Stage";
    const string DoneKey = "DNAJourney.Done";
    const string WildKey = "DNAJourney.Wildcards";

    static readonly string[] StageNames = { "The building blocks", "A nucleotide", "A single strand", "Two strands", "The double helix" };
    static readonly string[] Intros =
    {
        "DNA is built from a few simple parts. Tap each one to discover it.",
        "One sugar, one phosphate and one base join into a nucleotide. Find all of its parts.",
        "Nucleotides link into a long chain. Explore the strand: its parts, its bonds and both ends.",
        "A second strand pairs up with the first, base to base. Discover what holds them together.",
        "The ladder twists into the famous double helix. Explore its backbones and base pairs.",
    };
    static readonly string[] Completes =
    {
        "All building blocks found! Watch them join together...",
        "Nucleotide complete! Many of them link into a chain...",
        "Strand explored! A partner strand is coming...",
        "Both strands explored! Now the ladder twists...",
        "You explored the whole DNA molecule!",
    };

    // stage state
    readonly List<string> required = new List<string>();
    readonly List<string> found = new List<string>();
    MoleculeLife life;
    Dictionary<string, Transform> examples = new Dictionary<string, Transform>();
    bool transitioning, stageDone;
    float lastProgressTime;
    int hintCursor;

    // UI
    Font font;
    RectTransform hud, chipGrid, progressFill, finishCard;
    Text stageText, countText, bannerText;
    CanvasGroup bannerGroup;
    Coroutine bannerRoutine;
    readonly List<Text> chips = new List<Text>();
    RectTransform wildButton, wildStar, wildTip;
    Image wildDisc;
    Text wildCount;
    bool wildArmed;
    float wildArmedUntil, wildShakeUntil, wildPopUntil;

    void Awake()
    {
        if (spawner == null) spawner = FindFirstObjectByType<ARModelSpawner>();
        if (FindFirstObjectByType<MobileBridge>() == null) gameObject.AddComponent<MobileBridge>();   // React Native link
        if (FindFirstObjectByType<ARSupportFallback>() == null) gameObject.AddComponent<ARSupportFallback>();   // 3D mode on phones without AR
    }

    void Start()
    {
        if (picker == null) picker = FindFirstObjectByType<ComponentPicker>();
        if (picker == null && spawner != null) picker = spawner.gameObject.AddComponent<ComponentPicker>();
        if (buildDefaultUI) BuildUI();

        if (spawner != null) spawner.ModelChanged += OnModelChanged;
        if (picker != null) picker.PartSelected += OnPartSelected;

        Index = Mathf.Clamp(rememberProgress ? PlayerPrefs.GetInt(SaveKey, startLevel) : startLevel, 0, Mathf.Max(0, levels.Length - 1));
        JourneyComplete = rememberProgress && PlayerPrefs.GetInt(DoneKey, 0) == 1;
        Wildcards = rememberProgress ? PlayerPrefs.GetInt(WildKey, startWildcards) : startWildcards;
        if (spawner != null && levels.Length > 0) spawner.SetPrefab(levels[Index].prefab);
        RefreshHud();
        ShowWaitingHint();
    }

    void OnDestroy()
    {
        if (spawner != null) spawner.ModelChanged -= OnModelChanged;
        if (picker != null) picker.PartSelected -= OnPartSelected;
    }

    /// <summary>Jump straight to a stage (for testing or a menu).</summary>
    public void Show(int i)
    {
        if (levels == null || levels.Length == 0 || transitioning) return;
        StartCoroutine(MorphTo(Mathf.Clamp(i, 0, levels.Length - 1), false));
    }

    /// <summary>Start the journey again from stage 1.</summary>
    public void Restart()
    {
        JourneyComplete = false;
        if (!HostWallet) Wildcards = startWildcards;     // in the mobile app the server keeps the wildcards
        Save();
        if (finishCard != null) finishCard.gameObject.SetActive(false);
        if (spawner != null && spawner.HasModel) Show(0);
        else { Index = 0; Save(); if (spawner != null) spawner.SetPrefab(levels[0].prefab); RefreshHud(); }
    }

    // ------------------------------------------------------------ stage flow

    void OnModelChanged(GameObject model)
    {
        if (model == null) { RefreshHud(); ShowWaitingHint(); return; }
        SetupStage(model);
        if (!transitioning) Banner(StageTitle(Index), IntroText(Index), 5f);   // first placement
    }

    void SetupStage(GameObject model)
    {
        examples = DnaPartCatalog.Kinds(model.transform);
        life = model.GetComponent<MoleculeLife>();
        if (life == null) life = model.AddComponent<MoleculeLife>();
        life.Setup(DnaPartCatalog.Groups(model.transform), Index == 0);   // stage 1: separate, loose molecules
        required.Clear(); required.AddRange(examples.Keys);
        found.Clear();
        stageDone = false;
        lastProgressTime = Time.time;
        hintCursor = 0;
        BuildChips();
        RefreshHud();
        if (LevelChanged != null) LevelChanged(Index);
    }

    void OnPartSelected(DnaPartInfo info, Transform group)
    {
        if (life != null && group != null) life.Poke(group);
        if (transitioning || string.IsNullOrEmpty(info.title)) return;
        if (!required.Contains(info.title) || found.Contains(info.title))
        {
            if (picker != null) picker.ShowBadge(found.Contains(info.title) ? "Already discovered" : null);
            return;
        }

        found.Add(info.title);
        lastProgressTime = Time.time;
        if (picker != null) picker.ShowBadge("NEW DISCOVERY!   " + found.Count + " / " + required.Count);
        RefreshHud();
        if (PartDiscovered != null) PartDiscovered(info.title);

        if (found.Count >= required.Count && !stageDone)
        {
            stageDone = true;
            StartCoroutine(CompleteStage(false));
        }
    }

    IEnumerator CompleteStage(bool skipped)
    {
        bool last = Index >= levels.Length - 1;
        if (StageCompleted != null) StageCompleted(Index, skipped);
        if (!skipped)
        {
            if (life != null) life.Celebrate();
            if (spawner != null && spawner.CurrentInteractable != null) spawner.CurrentInteractable.AddSpin(200f);
        }
        if (skipped)
        {
            yield return new WaitForSeconds(0.5f);
            Banner("Wildcard!", "Stage " + (Index + 1) + " skipped. " + CompleteText(Index), last ? 6f : 3f);
            if (StageSkipped != null) StageSkipped(Index);
        }
        else
        {
            yield return new WaitForSeconds(1.6f);            // let the player read the last card
            string bonus = "";
            if (earnWildcards && Wildcards < maxWildcards) { Wildcards++; Save(); bonus = "\n+1 wildcard earned!"; wildPopUntil = Time.time + 0.6f; RefreshHud(); OnWildcardEarned(); }
            Banner("Stage " + (Index + 1) + " complete!", CompleteText(Index) + bonus, last ? 6f : 3.2f);
        }

        if (last)
        {
            JourneyComplete = true;
            Save();
            yield return new WaitForSeconds(2.5f);
            ShowFinish();
            if (JourneyCompleted != null) JourneyCompleted();
            yield break;
        }
        yield return new WaitForSeconds(2.6f);
        yield return MorphTo(Index + 1, true);
    }

    IEnumerator MorphTo(int next, bool announce)
    {
        transitioning = true;
        if (picker != null) { picker.Clear(); picker.Interactable = false; }

        // shrink and spin the current model away (spring on ARInteractable.Presence)
        GameObject old = spawner != null ? spawner.Current : null;
        ARInteractable oldFeel = spawner != null ? spawner.CurrentInteractable : null;
        if (old != null && oldFeel != null)
        {
            oldFeel.PresenceTarget = 0f;
            oldFeel.AddSpin(480f);
            for (float e = 0f; e < morphOutTime * 2.5f && oldFeel != null && oldFeel.Presence > 0.03f; e += Time.deltaTime) yield return null;
        }

        Index = next;
        Save();
        if (spawner != null) spawner.SetPrefab(levels[Index].prefab);   // same spot; the new model pops in with a spring

        GameObject fresh = spawner != null ? spawner.Current : null;
        if (fresh != null)
            for (float e = 0f; e < morphInTime; e += Time.deltaTime) yield return null;

        if (picker != null) picker.Interactable = true;
        transitioning = false;
        lastProgressTime = Time.time;
        RefreshHud();
        if (announce || fresh != null) Banner(StageTitle(Index), IntroText(Index), 5f);
        if (fresh == null) ShowWaitingHint();
    }

    void Update()
    {
        AnimateWildcard();
        AnimatePowerUI();
        if (hintDelay <= 0f || transitioning || stageDone || picker == null || spawner == null || !spawner.HasModel) return;
        if (required.Count == 0 || Time.time - lastProgressTime < hintDelay) return;

        // glow one part that has not been discovered yet
        lastProgressTime = Time.time;
        var missing = required.FindAll(r => !found.Contains(r));
        if (missing.Count == 0) return;
        string pick = missing[hintCursor++ % missing.Count];
        Transform example;
        if (examples.TryGetValue(pick, out example) && example != null)
        {
            picker.FlashHint(example, 3f);
            Banner("Hint", "Something is glowing. Tap it to discover what it is!", 3f);
        }
    }

    // ------------------------------------------------------------ wildcard

    /// <summary>Opens the wildcard picker: skip this level (1 card) or jump to any level (2 cards).</summary>
    public void OnWildcardPressed()
    {
        bool usable = !transitioning && !bursting && spawner != null && spawner.HasModel;
        if (!usable) { wildShakeUntil = Time.time + 0.45f; return; }
        if (Wildcards <= 0)
        {
            wildShakeUntil = Time.time + 0.45f;
            Banner("No wildcards left", "Finish a level on your own to earn one, or ask your teacher.", 2.5f);
            return;
        }
        OpenPower();
    }

    void AnimateWildcard()
    {
        if (wildButton == null || !wildButton.gameObject.activeInHierarchy) return;
        float t = Time.time;
        if (wildArmed && t > wildArmedUntil) { wildArmed = false; if (wildTip != null) wildTip.gameObject.SetActive(false); }

        float scale = 1f + (wildArmed ? 0.09f : 0.035f) * Mathf.Sin(t * (wildArmed ? 10f : 3f));
        if (t < wildPopUntil) scale += 0.35f * Mathf.Sin((1f - (wildPopUntil - t) / 0.6f) * Mathf.PI);
        wildButton.localScale = Vector3.one * scale;

        float shake = t < wildShakeUntil ? Mathf.Sin(t * 60f) * 12f * ((wildShakeUntil - t) / 0.45f) : 0f;
        wildButton.anchoredPosition = new Vector2(92f + shake, -92f);

        float spin = t < wildPopUntil ? 720f * (1f - (wildPopUntil - t) / 0.6f) : Mathf.Sin(t * 1.3f) * 10f;
        wildStar.localEulerAngles = new Vector3(0f, 0f, spin);
    }

    // ------------------------------------------------------------ helpers

    static float EaseOutBack(float x)
    {
        const float c1 = 1.70158f, c3 = c1 + 1f;
        x = Mathf.Clamp01(x) - 1f;
        return 1f + c3 * x * x * x + c1 * x * x;
    }

    string StageTitle(int i)
    {
        string name = i < StageNames.Length ? StageNames[i] : levels[i].title;
        return "Stage " + (i + 1) + " of " + levels.Length + "  ·  " + name;
    }
    string IntroText(int i) { return !string.IsNullOrEmpty(levels[i].intro) ? levels[i].intro : (i < Intros.Length ? Intros[i] : ""); }
    string CompleteText(int i) { return !string.IsNullOrEmpty(levels[i].complete) ? levels[i].complete : (i < Completes.Length ? Completes[i] : "Stage complete!"); }

    void Save()
    {
        if (!rememberProgress) return;
        PlayerPrefs.SetInt(SaveKey, Index);
        PlayerPrefs.SetInt(DoneKey, JourneyComplete ? 1 : 0);
        PlayerPrefs.SetInt(WildKey, Wildcards);
        PlayerPrefs.Save();
    }

    void ShowWaitingHint()
    {
        if (spawner != null && spawner.HasModel) return;
        string welcome = Index > 0 ? "Welcome back! " : "";
        Banner(welcome + StageTitle(Index), ARSupportFallback.NoAR
            ? "3D mode: this phone has no AR. The DNA appears on screen; drag, pinch and twist to explore it."
            : "Move your phone slowly, then tap a surface to place the DNA.", 0f);
    }

    // ------------------------------------------------------------ UI

    void RefreshHud()
    {
        if (hud == null) return;
        bool placed = spawner != null && spawner.HasModel;
        hud.gameObject.SetActive(placed);
        RefreshPowerUI(placed);
        if (wildButton != null)
        {
            wildButton.gameObject.SetActive(placed && showWildcard);
            wildCount.text = Wildcards.ToString();
            bool can = Wildcards > 0;
            wildDisc.color = can ? Color.white : new Color(0.45f, 0.45f, 0.5f, 0.9f);
            wildStar.GetComponent<Image>().color = can ? Color.white : new Color(0.75f, 0.75f, 0.78f);
        }
        stageText.text = StageTitle(Index);
        int total = Mathf.Max(1, required.Count);
        countText.text = JourneyComplete && Index >= levels.Length - 1 && found.Count >= required.Count
            ? "Journey complete – explore freely"
            : found.Count + " / " + required.Count + " discovered";
        progressFill.anchorMax = new Vector2(Mathf.Clamp01(found.Count / (float)total), 1f);
        for (int i = 0; i < chips.Count; i++)
        {
            bool on = i < found.Count;
            chips[i].text = on ? found[i] : "?";
            chips[i].color = on ? new Color(1f, 0.93f, 0.35f) : new Color(1f, 1f, 1f, 0.45f);
            chips[i].transform.parent.GetComponent<Image>().color = on ? new Color(0.16f, 0.22f, 0.36f, 0.95f) : new Color(1f, 1f, 1f, 0.08f);
        }
    }

    void BuildChips()
    {
        if (chipGrid == null) return;
        foreach (Text c in chips) if (c != null) Destroy(c.transform.parent.gameObject);
        chips.Clear();
        for (int i = 0; i < required.Count; i++)
        {
            RectTransform chip = NewRect("Chip", chipGrid);
            chip.gameObject.AddComponent<Image>().raycastTarget = false;
            Text t = NewText(chip, 25, FontStyle.Bold, Color.white, TextAnchor.MiddleCenter);
            Stretch((RectTransform)t.transform, 6f);
            t.resizeTextForBestFit = true; t.resizeTextMinSize = 16; t.resizeTextMaxSize = 25;
            chips.Add(t);
        }
    }

    void Banner(string title, string body, float seconds)
    {
        if (bannerText == null) return;
        bannerText.text = "<b>" + title + "</b>" + (string.IsNullOrEmpty(body) ? "" : "\n<size=34>" + body + "</size>");
        if (bannerRoutine != null) StopCoroutine(bannerRoutine);
        bannerRoutine = StartCoroutine(BannerFade(seconds));
    }

    IEnumerator BannerFade(float seconds)
    {
        for (float a = bannerGroup.alpha; a < 1f; a += Time.deltaTime * 4f) { bannerGroup.alpha = a; yield return null; }
        bannerGroup.alpha = 1f;
        if (seconds <= 0f) yield break;                       // stays until replaced
        yield return new WaitForSeconds(seconds);
        for (float a = 1f; a > 0f; a -= Time.deltaTime * 2f) { bannerGroup.alpha = a; yield return null; }
        bannerGroup.alpha = 0f;
    }

    void ShowFinish()
    {
        if (finishCard == null) return;
        finishCard.gameObject.SetActive(true);
        RefreshHud();
    }

    void BuildUI()
    {
        if (FindFirstObjectByType<EventSystem>() == null)
        {
            var es = new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
            es.GetComponent<InputSystemUIInputModule>().AssignDefaultActions();
        }
        font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        var canvasGo = new GameObject("JourneyUI", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        var canvas = canvasGo.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 4;
        var scaler = canvasGo.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1080f, 1920f);
        scaler.matchWidthOrHeight = 0.5f;
        RectTransform root = (RectTransform)canvasGo.transform;

        // ---- top HUD: stage, progress bar, discovery chips (never blocks touches)
        hud = NewRect("HUD", root);
        hud.anchorMin = hud.anchorMax = new Vector2(0.5f, 1f);
        hud.pivot = new Vector2(0.5f, 1f);
        hud.anchoredPosition = new Vector2(0f, -70f);
        hud.sizeDelta = new Vector2(1010f, 0f);
        var hudBg = hud.gameObject.AddComponent<Image>(); hudBg.color = new Color(0.05f, 0.07f, 0.13f, 0.78f); hudBg.raycastTarget = false;
        var v = hud.gameObject.AddComponent<VerticalLayoutGroup>();
        v.padding = new RectOffset(showWildcard ? 175 : 30, 30, 22, 24); v.spacing = 12f;
        v.childControlWidth = v.childControlHeight = true; v.childForceExpandWidth = true; v.childForceExpandHeight = false;
        hud.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;

        stageText = NewText(hud, 38, FontStyle.Bold, Color.white, TextAnchor.MiddleLeft);
        RectTransform bar = NewRect("Progress", hud);
        bar.gameObject.AddComponent<LayoutElement>().preferredHeight = 14f;
        var barBg = bar.gameObject.AddComponent<Image>(); barBg.color = new Color(1f, 1f, 1f, 0.12f); barBg.raycastTarget = false;
        progressFill = NewRect("Fill", bar);
        progressFill.anchorMin = Vector2.zero; progressFill.anchorMax = new Vector2(0f, 1f);
        progressFill.offsetMin = progressFill.offsetMax = Vector2.zero;
        var fillImg = progressFill.gameObject.AddComponent<Image>(); fillImg.color = new Color(0.45f, 1f, 0.6f); fillImg.raycastTarget = false;
        countText = NewText(hud, 30, FontStyle.Normal, new Color(0.75f, 0.8f, 0.9f), TextAnchor.MiddleLeft);

        chipGrid = NewRect("Chips", hud);
        var grid = chipGrid.gameObject.AddComponent<GridLayoutGroup>();
        grid.cellSize = showWildcard ? new Vector2(258f, 56f) : new Vector2(228f, 56f); grid.spacing = new Vector2(10f, 10f);
        grid.constraint = GridLayoutGroup.Constraint.FixedColumnCount; grid.constraintCount = showWildcard ? 3 : 4;
        hud.gameObject.SetActive(false);

        if (showWildcard) BuildWildcard(root);
        BuildPowerUI(root);                       // Previous button, wildcard picker, wildcard animation

        // ---- story banner in the middle-top (fades in and out, never blocks touches)
        RectTransform banner = NewRect("Banner", root);
        banner.anchorMin = banner.anchorMax = new Vector2(0.5f, 0.62f);
        banner.sizeDelta = new Vector2(960f, 260f);
        bannerGroup = banner.gameObject.AddComponent<CanvasGroup>();
        bannerGroup.alpha = 0f; bannerGroup.blocksRaycasts = false; bannerGroup.interactable = false;
        bannerText = NewText(banner, 46, FontStyle.Normal, Color.white, TextAnchor.MiddleCenter);
        bannerText.supportRichText = true;
        Stretch((RectTransform)bannerText.transform, 0f);
        var outline = bannerText.gameObject.AddComponent<Outline>();
        outline.effectColor = new Color(0f, 0f, 0f, 0.9f); outline.effectDistance = new Vector2(2f, -2f);

        // ---- journey complete card (the only buttons in the game)
        finishCard = NewRect("FinishCard", root);
        finishCard.anchorMin = finishCard.anchorMax = new Vector2(0.5f, 0.5f);
        finishCard.sizeDelta = new Vector2(900f, 560f);
        finishCard.gameObject.AddComponent<Image>().color = new Color(0.05f, 0.07f, 0.13f, 0.95f);
        Text ft = NewText(finishCard, 44, FontStyle.Normal, Color.white, TextAnchor.UpperCenter);
        ft.supportRichText = true;
        ft.text = "<b><color=#FFEE59>Journey complete!</color></b>\n\n<size=34>You discovered every part of DNA, from single building blocks " +
                  "to the double helix. Keep exploring, or start the journey again.</size>";
        var ftr = (RectTransform)ft.transform; ftr.anchorMin = new Vector2(0f, 0.32f); ftr.anchorMax = Vector2.one;
        ftr.offsetMin = new Vector2(50f, 0f); ftr.offsetMax = new Vector2(-50f, -50f);
        MakeButton(finishCard, "Keep exploring", new Vector2(0.27f, 0.15f), () => finishCard.gameObject.SetActive(false));
        MakeButton(finishCard, "Start again", new Vector2(0.73f, 0.15f), Restart);
        finishCard.gameObject.SetActive(false);
    }

    void BuildWildcard(RectTransform root)
    {
        wildButton = NewRect("Wildcard", root);
        wildButton.anchorMin = wildButton.anchorMax = new Vector2(0f, 1f);
        wildButton.pivot = new Vector2(0.5f, 0.5f);
        wildButton.anchoredPosition = new Vector2(92f, -92f);
        wildButton.sizeDelta = new Vector2(132f, 132f);

        // soft glow behind a glossy gold coin
        RectTransform glow = NewRect("Glow", wildButton); Stretch(glow, -16f);
        var glowImg = glow.gameObject.AddComponent<Image>();
        glowImg.sprite = CircleSprite(128, new Color(1f, 0.85f, 0.3f, 0.6f), new Color(1f, 0.6f, 0.1f, 0f), true);
        glowImg.raycastTarget = false;
        wildDisc = wildButton.gameObject.AddComponent<Image>();
        wildDisc.sprite = CircleSprite(160, new Color(1f, 0.88f, 0.36f), new Color(0.93f, 0.45f, 0.05f), false);
        var btn = wildButton.gameObject.AddComponent<Button>();
        btn.targetGraphic = wildDisc;
        btn.onClick.AddListener(OnWildcardPressed);

        wildStar = NewRect("Star", wildButton); Stretch(wildStar, 24f);
        var star = wildStar.gameObject.AddComponent<Image>();
        star.sprite = StarSprite(128); star.raycastTarget = false;
        var starShadow = wildStar.gameObject.AddComponent<Shadow>();
        starShadow.effectColor = new Color(0.45f, 0.2f, 0f, 0.6f); starShadow.effectDistance = new Vector2(2f, -3f);

        // red count badge
        RectTransform badge = NewRect("Count", wildButton);
        badge.anchorMin = badge.anchorMax = new Vector2(1f, 0f);
        badge.anchoredPosition = new Vector2(-12f, 14f); badge.sizeDelta = new Vector2(54f, 54f);
        var bimg = badge.gameObject.AddComponent<Image>();
        bimg.sprite = CircleSprite(64, new Color(0.97f, 0.25f, 0.33f), new Color(0.72f, 0.05f, 0.15f), false);
        bimg.raycastTarget = false;
        wildCount = NewText(badge, 32, FontStyle.Bold, Color.white, TextAnchor.MiddleCenter);
        Stretch((RectTransform)wildCount.transform, 0f);

        Text label = NewText(wildButton, 24, FontStyle.Bold, new Color(1f, 0.9f, 0.55f), TextAnchor.UpperCenter);
        label.text = "WILD";
        var lr = (RectTransform)label.transform;
        lr.anchorMin = lr.anchorMax = new Vector2(0.5f, 0f);
        lr.pivot = new Vector2(0.5f, 1f); lr.anchoredPosition = new Vector2(0f, -6f); lr.sizeDelta = new Vector2(120f, 34f);
        label.gameObject.AddComponent<Outline>().effectColor = new Color(0f, 0f, 0f, 0.85f);

        wildTip = NewRect("Tip", wildButton);
        wildTip.anchorMin = wildTip.anchorMax = new Vector2(0f, 0f);
        wildTip.pivot = new Vector2(0f, 1f);
        wildTip.anchoredPosition = new Vector2(0f, -46f); wildTip.sizeDelta = new Vector2(430f, 70f);
        var tipImg = wildTip.gameObject.AddComponent<Image>(); tipImg.color = new Color(0.05f, 0.07f, 0.13f, 0.94f); tipImg.raycastTarget = false;
        Text tip = NewText(wildTip, 28, FontStyle.Bold, new Color(1f, 0.9f, 0.55f), TextAnchor.MiddleCenter);
        tip.text = "Tap again to skip this stage"; Stretch((RectTransform)tip.transform, 8f);
        wildTip.gameObject.SetActive(false);
        wildButton.gameObject.SetActive(false);
    }

    // Procedural sprites, so no image files are needed
    static Sprite CircleSprite(int size, Color inner, Color outer, bool softEdge)
    {
        var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.wrapMode = TextureWrapMode.Clamp;
        float r = size * 0.5f;
        var px = new Color[size * size];
        for (int y = 0; y < size; y++)
            for (int x = 0; x < size; x++)
            {
                float dx = x + 0.5f - r, dy = y + 0.5f - r, d = Mathf.Sqrt(dx * dx + dy * dy) / r;
                Color c;
                if (softEdge)
                {
                    c = Color.Lerp(inner, outer, d);
                    c.a = Mathf.Clamp01(1f - d) * inner.a;
                }
                else
                {
                    float shade = Mathf.Clamp01(0.55f * d + 0.35f * (-dy / r) * 0.5f + 0.2f);   // brighter at the top
                    c = Color.Lerp(inner, outer, shade);
                    if (d > 0.86f) c = Color.Lerp(c, outer * 0.8f, 0.6f);                     // darker rim
                    c.a = Mathf.Clamp01((1f - d) * r);                                         // anti-aliased edge
                }
                px[y * size + x] = c;
            }
        tex.SetPixels(px); tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f);
    }

    static Sprite StarSprite(int size)
    {
        var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.wrapMode = TextureWrapMode.Clamp;
        var pts = new Vector2[10];
        for (int i = 0; i < 10; i++)
        {
            float ang = Mathf.PI / 2f + i * Mathf.PI / 5f;
            float rad = (i % 2 == 0 ? 0.48f : 0.2f) * size;
            pts[i] = new Vector2(size * 0.5f + Mathf.Cos(ang) * rad, size * 0.5f + Mathf.Sin(ang) * rad);
        }
        var px = new Color[size * size];
        const int ss = 3;                                     // supersampling for smooth edges
        for (int y = 0; y < size; y++)
            for (int x = 0; x < size; x++)
            {
                int hits = 0;
                for (int sy = 0; sy < ss; sy++)
                    for (int sx = 0; sx < ss; sx++)
                        if (Inside(pts, new Vector2(x + (sx + 0.5f) / ss, y + (sy + 0.5f) / ss))) hits++;
                px[y * size + x] = new Color(1f, 1f, 1f, hits / (float)(ss * ss));
            }
        tex.SetPixels(px); tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f);
    }

    static bool Inside(Vector2[] poly, Vector2 p)
    {
        bool inside = false;
        for (int i = 0, j = poly.Length - 1; i < poly.Length; j = i++)
            if ((poly[i].y > p.y) != (poly[j].y > p.y) &&
                p.x < (poly[j].x - poly[i].x) * (p.y - poly[i].y) / (poly[j].y - poly[i].y) + poly[i].x)
                inside = !inside;
        return inside;
    }

    void MakeButton(Transform parent, string label, Vector2 anchor, UnityEngine.Events.UnityAction onClick)
    {
        RectTransform b = NewRect(label, parent);
        b.anchorMin = b.anchorMax = anchor; b.sizeDelta = new Vector2(360f, 120f);
        var img = b.gameObject.AddComponent<Image>(); img.color = new Color(0.16f, 0.22f, 0.36f, 1f);
        var btn = b.gameObject.AddComponent<Button>(); btn.targetGraphic = img; btn.onClick.AddListener(onClick);
        Text t = NewText(b, 38, FontStyle.Bold, Color.white, TextAnchor.MiddleCenter);
        t.text = label; Stretch((RectTransform)t.transform, 0f);
    }

    static RectTransform NewRect(string name, Transform parent)
    {
        var go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent, false);
        return (RectTransform)go.transform;
    }

    static void Stretch(RectTransform rt, float pad)
    {
        rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one;
        rt.offsetMin = new Vector2(pad, pad); rt.offsetMax = new Vector2(-pad, -pad);
    }

    Text NewText(Transform parent, int size, FontStyle style, Color color, TextAnchor align)
    {
        RectTransform rt = NewRect("Text", parent);
        var t = rt.gameObject.AddComponent<Text>();
        t.font = font; t.fontSize = size; t.fontStyle = style; t.color = color; t.alignment = align;
        t.horizontalOverflow = HorizontalWrapMode.Wrap; t.verticalOverflow = VerticalWrapMode.Overflow;
        t.raycastTarget = false;
        return t;
    }
}
