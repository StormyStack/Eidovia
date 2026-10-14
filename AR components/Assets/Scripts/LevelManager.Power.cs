using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Wildcard power-ups and the Previous button (part of LevelManager).
///   Wildcard button -> picker:  "Skip this level" costs 1 card, "Jump to any level" (1..5, forward or back) costs 2.
///   Every use plays a full-screen golden card animation.
///   Previous button: back one level, free, but only once every 30 seconds.
///   Inside the mobile app the wildcard count belongs to the server (one wallet per learner):
///   the app sends the total with SetWallet() and pays for every use / earned card on the server.
/// </summary>
public partial class LevelManager
{
    public const int SkipCost = 1, JumpCost = 2;
    const float PreviousCooldown = 30f;
    const string PrevKey = "DNAJourney.PreviousAt";

    /// <summary>mode ("skip" or "jump"), from stage, to stage, cards spent, cards left.</summary>
    public event Action<string, int, int, int, int> WildcardUsed;
    /// <summary>from stage, to stage.</summary>
    public event Action<int, int> PreviousUsed;
    /// <summary>stage that earned a card (finished on one's own).</summary>
    public event Action<int> WildcardEarned;
    /// <summary>True once the mobile app manages the wildcards (server wallet).</summary>
    public bool HostWallet { get; private set; }

    static readonly string[] ShortNames = { "Blocks", "Nucleotide", "Strand", "Two strands", "Helix" };

    RectTransform powerPanel, prevButton, prevCooldown;
    Button skipBtn;
    Text powerTitle, skipText, prevSeconds;
    Image prevDisc, prevArrow, prevFill;
    readonly List<Button> jumpButtons = new List<Button>();
    readonly List<Image> jumpDiscs = new List<Image>();
    float prevShakeUntil;
    bool bursting;

    // burst animation pieces
    RectTransform burstLayer, burstCard, burstRays, burstTitleRt;
    CanvasGroup burstGroup;
    Image burstFlash, burstRaysImg;
    Text burstTitle, burstSub;
    readonly List<RectTransform> sparkles = new List<RectTransform>();

    // ------------------------------------------------------------ actions

    /// <summary>
    /// Wildcard total from the server. added &gt; 0 = new cards (daily gift or from the teacher): plays the gift animation.
    /// Only the total is shown to the learner.
    /// </summary>
    public void SetWallet(int total, int added)
    {
        HostWallet = true;
        int before = Wildcards;
        Wildcards = Mathf.Max(0, total);
        Save();
        if (Wildcards != before) wildPopUntil = Time.time + 0.6f;
        RefreshHud();
        if (powerPanel != null && powerPanel.gameObject.activeSelf) OpenPower();   // refresh the open picker
        if (added <= 0) return;
        string sub = "+" + added + " wildcard" + (added == 1 ? "" : "s") + " for you  ·  " + Wildcards + " in total";
        if (bursting || burstLayer == null) Banner("Gift!", sub, 3f);
        else StartCoroutine(WildcardBurst("GIFT!", sub, false));
    }

    void OnWildcardEarned() { if (WildcardEarned != null) WildcardEarned(Index); }

    void OpenPower()
    {
        if (powerPanel == null) return;
        int next = Mathf.Min(Index + 1, levels.Length - 1);
        bool last = Index >= levels.Length - 1;
        powerTitle.text = "<b>Wildcard power</b>\n<size=34>You have <color=#FFE066>" + Wildcards + "</color> wildcard" + (Wildcards == 1 ? "" : "s") + "</size>";
        skipText.text = last ? "Skip this level  ·  finish the journey\n<size=28>costs " + SkipCost + " card</size>"
                             : "Skip to Level " + (next + 1) + "  ·  " + StageNames[next] + "\n<size=28>costs " + SkipCost + " card</size>";
        skipBtn.interactable = Wildcards >= SkipCost && !stageDone;
        for (int i = 0; i < jumpButtons.Count; i++)
        {
            bool here = i == Index;
            jumpButtons[i].interactable = !here && Wildcards >= JumpCost;
            jumpDiscs[i].color = here ? new Color(0.45f, 1f, 0.6f) : Color.white;
        }
        powerPanel.gameObject.SetActive(true);
        powerPanel.SetAsLastSibling();
    }

    void ClosePower() { if (powerPanel != null) powerPanel.gameObject.SetActive(false); }

    void UseSkip()
    {
        if (Wildcards < SkipCost || stageDone || transitioning || bursting) return;
        ClosePower();
        int from = Index;
        Wildcards -= SkipCost;
        Save();
        stageDone = true;
        if (picker != null) picker.Clear();
        RefreshHud();
        if (WildcardUsed != null) WildcardUsed("skip", from, Mathf.Min(from + 1, levels.Length - 1), SkipCost, Wildcards);
        StartCoroutine(SkipRoutine(from));
    }

    IEnumerator SkipRoutine(int from)
    {
        yield return WildcardBurst("WILDCARD!", "Level " + (from + 1) + " skipped", true);
        yield return CompleteStage(true);
    }

    void UseJump(int target)
    {
        if (Wildcards < JumpCost || transitioning || bursting || target == Index || target < 0 || target >= levels.Length) return;
        ClosePower();
        int from = Index;
        Wildcards -= JumpCost;
        Save();
        stageDone = true;                        // no completion while the animation plays
        if (picker != null) picker.Clear();
        RefreshHud();
        if (WildcardUsed != null) WildcardUsed("jump", from, target, JumpCost, Wildcards);
        StartCoroutine(JumpRoutine(from, target));
    }

    IEnumerator JumpRoutine(int from, int target)
    {
        yield return WildcardBurst("POWER JUMP!", "Level " + (from + 1) + "  →  Level " + (target + 1), true);
        if (finishCard != null) finishCard.gameObject.SetActive(false);
        yield return MorphTo(target, true);
    }

    /// <summary>Back one level. Free, once every 30 seconds.</summary>
    public void OnPreviousPressed()
    {
        if (transitioning || bursting || (stageDone && !JourneyComplete) || spawner == null || !spawner.HasModel) { prevShakeUntil = Time.time + 0.45f; return; }
        if (Index <= 0) { prevShakeUntil = Time.time + 0.45f; Banner("This is the first level", "", 2f); return; }
        float wait = PreviousRemaining();
        if (wait > 0f)
        {
            prevShakeUntil = Time.time + 0.45f;
            Banner("Back button is resting", "You can go back again in " + Mathf.CeilToInt(wait) + " s.", 2f);
            return;
        }
        int from = Index;
        PlayerPrefs.SetString(PrevKey, DateTime.UtcNow.Ticks.ToString());
        PlayerPrefs.Save();
        if (PreviousUsed != null) PreviousUsed(from, from - 1);
        stageDone = true;
        if (picker != null) picker.Clear();
        if (finishCard != null) finishCard.gameObject.SetActive(false);
        StartCoroutine(MorphTo(from - 1, true));
    }

    float PreviousRemaining()
    {
        long ticks;
        if (!long.TryParse(PlayerPrefs.GetString(PrevKey, ""), out ticks)) return 0f;
        double since = (DateTime.UtcNow.Ticks - ticks) / (double)TimeSpan.TicksPerSecond;
        if (since < 0) return 0f;                 // clock changed
        return Mathf.Max(0f, PreviousCooldown - (float)since);
    }

    // ------------------------------------------------------------ the golden card animation

    IEnumerator WildcardBurst(string title, string sub, bool spinModel)
    {
        if (burstLayer == null) yield break;
        bursting = true;
        burstLayer.gameObject.SetActive(true);
        burstLayer.SetAsLastSibling();
        burstGroup.alpha = 1f;
        burstTitle.text = title;
        burstSub.text = sub;
        Rect r = burstLayer.rect;
        Vector2 start = new Vector2(-r.width * 0.5f + 92f, r.height * 0.5f - 92f);   // the wildcard button
        Vector2 centre = new Vector2(0f, 120f);
        var vel = new Vector2[sparkles.Count];
        var spin = new float[sparkles.Count];
        bool popped = false;
        const float total = 1.9f;

        for (float t = 0f; t < total; t += Time.unscaledDeltaTime)
        {
            // flash
            float flash = t < 0.12f ? t / 0.12f * 0.75f : Mathf.Max(0f, 0.75f - (t - 0.12f) * 1.6f);
            burstFlash.color = new Color(1f, 0.93f, 0.6f, flash);

            // card: fly in with two flips, hover, then spin away
            if (t < 0.5f)
            {
                float k = EaseOutBack(t / 0.5f);
                burstCard.anchoredPosition = Vector2.LerpUnclamped(start, centre, k);
                burstCard.localScale = Vector3.one * Mathf.LerpUnclamped(0.25f, 1.15f, k);
                burstCard.localEulerAngles = new Vector3(0f, 720f * (t / 0.5f), Mathf.Lerp(-25f, 0f, t / 0.5f));
            }
            else if (t < 1.4f)
            {
                float k = t - 0.5f;
                burstCard.anchoredPosition = centre + new Vector2(0f, Mathf.Sin(k * 6f) * 10f);
                burstCard.localScale = Vector3.one * (1.15f + 0.05f * Mathf.Sin(k * 14f));
                burstCard.localEulerAngles = new Vector3(0f, Mathf.Sin(k * 5f) * 12f, 0f);
            }
            else
            {
                float k = (t - 1.4f) / (total - 1.4f);
                burstCard.localScale = Vector3.one * Mathf.Lerp(1.15f, 0f, k * k);
                burstCard.localEulerAngles = new Vector3(0f, 0f, 540f * k);
            }

            // light rays
            float rayIn = Mathf.Clamp01((t - 0.35f) / 0.3f), rayOut = Mathf.Clamp01((t - 1.35f) / 0.45f);
            burstRays.localScale = Vector3.one * (0.4f + 0.8f * rayIn);
            burstRays.localEulerAngles = new Vector3(0f, 0f, -t * 60f);
            burstRaysImg.color = new Color(1f, 0.85f, 0.35f, 0.85f * rayIn * (1f - rayOut));
            burstRays.anchoredPosition = centre;

            // sparkles burst when the card lands
            if (!popped && t >= 0.5f)
            {
                popped = true;
                for (int i = 0; i < sparkles.Count; i++)
                {
                    float a = (i / (float)sparkles.Count) * Mathf.PI * 2f + UnityEngine.Random.Range(-0.2f, 0.2f);
                    vel[i] = new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * UnityEngine.Random.Range(650f, 1500f);
                    spin[i] = UnityEngine.Random.Range(-720f, 720f);
                    sparkles[i].anchoredPosition = centre;
                    sparkles[i].gameObject.SetActive(true);
                }
                if (spinModel)
                {
                    if (life != null) life.Celebrate();
                    if (spawner != null && spawner.CurrentInteractable != null) spawner.CurrentInteractable.AddSpin(900f);
                }
#if UNITY_ANDROID && !UNITY_EDITOR
                Handheld.Vibrate();
#endif
            }
            if (popped)
            {
                float dt = Time.unscaledDeltaTime, life01 = Mathf.Clamp01((t - 0.5f) / 1.2f);
                for (int i = 0; i < sparkles.Count; i++)
                {
                    vel[i] += new Vector2(0f, -1400f) * dt;
                    vel[i] *= 1f - 1.6f * dt;
                    sparkles[i].anchoredPosition += vel[i] * dt;
                    sparkles[i].localEulerAngles += new Vector3(0f, 0f, spin[i] * dt);
                    sparkles[i].localScale = Vector3.one * (1f - life01) * (0.7f + 0.3f * Mathf.Sin(t * 30f + i));
                }
            }

            // title pops in, subtitle fades in
            float ti = Mathf.Clamp01((t - 0.45f) / 0.35f);
            burstTitleRt.localScale = Vector3.one * (ti <= 0f ? 0f : EaseOutBack(ti) * (t > 1.5f ? Mathf.Lerp(1f, 0f, (t - 1.5f) / 0.4f) : 1f));
            burstSub.color = new Color(1f, 1f, 1f, Mathf.Clamp01((t - 0.7f) / 0.3f) * (t > 1.5f ? Mathf.Lerp(1f, 0f, (t - 1.5f) / 0.4f) : 1f));
            yield return null;
        }

        foreach (var s in sparkles) s.gameObject.SetActive(false);
        burstLayer.gameObject.SetActive(false);
        bursting = false;
    }

    // ------------------------------------------------------------ per frame

    void RefreshPowerUI(bool placed)
    {
        if (prevButton != null) prevButton.gameObject.SetActive(placed);
    }

    void AnimatePowerUI()
    {
        if (prevButton == null || !prevButton.gameObject.activeInHierarchy) return;
        float wait = PreviousRemaining();
        bool ready = wait <= 0f && Index > 0;
        prevCooldown.gameObject.SetActive(wait > 0f);
        if (wait > 0f)
        {
            prevFill.fillAmount = wait / PreviousCooldown;
            prevSeconds.text = Mathf.CeilToInt(wait).ToString();
        }
        prevDisc.color = ready ? Color.white : new Color(0.55f, 0.58f, 0.66f, 0.95f);
        prevArrow.color = ready ? Color.white : new Color(1f, 1f, 1f, 0.45f);
        float shake = Time.time < prevShakeUntil ? Mathf.Sin(Time.time * 60f) * 12f * ((prevShakeUntil - Time.time) / 0.45f) : 0f;
        prevButton.anchoredPosition = new Vector2(92f + shake, -262f);
    }

    // ------------------------------------------------------------ UI

    void BuildPowerUI(RectTransform root)
    {
        BuildPreviousButton(root);
        if (showWildcard) { BuildPowerPanel(root); BuildBurst(root); }
    }

    void BuildPreviousButton(RectTransform root)
    {
        prevButton = NewRect("Previous", root);
        prevButton.anchorMin = prevButton.anchorMax = new Vector2(0f, 1f);
        prevButton.anchoredPosition = new Vector2(92f, -262f);
        prevButton.sizeDelta = new Vector2(112f, 112f);
        prevDisc = prevButton.gameObject.AddComponent<Image>();
        prevDisc.sprite = CircleSprite(128, new Color(0.36f, 0.5f, 0.86f), new Color(0.12f, 0.18f, 0.4f), false);
        var btn = prevButton.gameObject.AddComponent<Button>();
        btn.targetGraphic = prevDisc;
        btn.onClick.AddListener(OnPreviousPressed);

        RectTransform arrow = NewRect("Arrow", prevButton); Stretch(arrow, 30f);
        arrow.anchoredPosition = new Vector2(-4f, 0f);
        prevArrow = arrow.gameObject.AddComponent<Image>();
        prevArrow.sprite = ArrowSprite(96); prevArrow.raycastTarget = false;

        prevCooldown = NewRect("Cooldown", prevButton); Stretch(prevCooldown, 0f);
        prevFill = prevCooldown.gameObject.AddComponent<Image>();
        prevFill.sprite = CircleSprite(128, new Color(0f, 0f, 0f, 0.62f), new Color(0f, 0f, 0f, 0.62f), false);
        prevFill.type = Image.Type.Filled; prevFill.fillMethod = Image.FillMethod.Radial360; prevFill.fillOrigin = 2; prevFill.fillClockwise = false;
        prevFill.raycastTarget = false;
        prevSeconds = NewText(prevCooldown, 38, FontStyle.Bold, Color.white, TextAnchor.MiddleCenter);
        Stretch((RectTransform)prevSeconds.transform, 0f);
        prevCooldown.gameObject.SetActive(false);

        Text label = NewText(prevButton, 22, FontStyle.Bold, new Color(0.8f, 0.87f, 1f), TextAnchor.UpperCenter);
        label.text = "BACK";
        var lr = (RectTransform)label.transform;
        lr.anchorMin = lr.anchorMax = new Vector2(0.5f, 0f);
        lr.pivot = new Vector2(0.5f, 1f); lr.anchoredPosition = new Vector2(0f, -4f); lr.sizeDelta = new Vector2(120f, 30f);
        label.gameObject.AddComponent<Outline>().effectColor = new Color(0f, 0f, 0f, 0.85f);
        prevButton.gameObject.SetActive(false);
    }

    void BuildPowerPanel(RectTransform root)
    {
        powerPanel = NewRect("WildcardPower", root); Stretch(powerPanel, 0f);
        var dim = powerPanel.gameObject.AddComponent<Image>(); dim.color = new Color(0f, 0f, 0f, 0.6f);
        powerPanel.gameObject.AddComponent<Button>().onClick.AddListener(ClosePower);        // tap outside closes

        RectTransform card = NewRect("Card", powerPanel);
        card.anchorMin = card.anchorMax = new Vector2(0.5f, 0.5f);
        card.sizeDelta = new Vector2(940f, 980f);
        var cardImg = card.gameObject.AddComponent<Image>();
        cardImg.sprite = RoundedSprite(94, 98, 14, new Color(0.1f, 0.13f, 0.24f), new Color(0.05f, 0.07f, 0.13f), new Color(1f, 0.82f, 0.3f));
        cardImg.type = Image.Type.Sliced;
        card.gameObject.AddComponent<Button>();                                             // swallow taps on the card

        RectTransform starRt = NewRect("Star", card);
        starRt.anchorMin = starRt.anchorMax = new Vector2(0.5f, 1f); starRt.anchoredPosition = new Vector2(0f, -95f); starRt.sizeDelta = new Vector2(110f, 110f);
        var starImg = starRt.gameObject.AddComponent<Image>(); starImg.sprite = StarSprite(128); starImg.color = new Color(1f, 0.85f, 0.3f); starImg.raycastTarget = false;

        powerTitle = NewText(card, 52, FontStyle.Normal, Color.white, TextAnchor.UpperCenter);
        powerTitle.supportRichText = true;
        Place((RectTransform)powerTitle.transform, new Vector2(0f, 255f), new Vector2(860f, 140f));

        skipBtn = GoldButton(card, new Vector2(0f, 95f), new Vector2(800f, 160f), out skipText);
        skipBtn.onClick.AddListener(UseSkip);

        Text jumpHead = NewText(card, 36, FontStyle.Bold, new Color(1f, 0.9f, 0.55f), TextAnchor.MiddleCenter);
        jumpHead.supportRichText = true;
        jumpHead.text = "Power jump to any level\n<size=28><color=#C9D3EA>forward or back  ·  costs " + JumpCost + " cards</color></size>";
        Place((RectTransform)jumpHead.transform, new Vector2(0f, -55f), new Vector2(860f, 100f));

        jumpButtons.Clear(); jumpDiscs.Clear();
        int n = Mathf.Max(1, levels.Length);
        float spacing = 168f, x0 = -spacing * (n - 1) * 0.5f;
        for (int i = 0; i < n; i++)
        {
            int target = i;
            RectTransform b = NewRect("Jump" + (i + 1), card);
            Place(b, new Vector2(x0 + spacing * i, -185f), new Vector2(128f, 128f));
            var disc = b.gameObject.AddComponent<Image>();
            disc.sprite = CircleSprite(128, new Color(1f, 0.88f, 0.36f), new Color(0.93f, 0.45f, 0.05f), false);
            var bt = b.gameObject.AddComponent<Button>(); bt.targetGraphic = disc;
            var cb = bt.colors; cb.disabledColor = new Color(0.4f, 0.4f, 0.45f, 0.7f); bt.colors = cb;
            bt.onClick.AddListener(() => UseJump(target));
            Text num = NewText(b, 56, FontStyle.Bold, new Color(0.3f, 0.14f, 0f), TextAnchor.MiddleCenter);
            num.text = (i + 1).ToString(); Stretch((RectTransform)num.transform, 0f);
            Text name = NewText(card, 22, FontStyle.Normal, new Color(0.78f, 0.83f, 0.95f), TextAnchor.UpperCenter);
            name.text = i < ShortNames.Length ? ShortNames[i] : "Level " + (i + 1);
            Place((RectTransform)name.transform, new Vector2(x0 + spacing * i, -275f), new Vector2(160f, 34f));
            jumpButtons.Add(bt); jumpDiscs.Add(disc);
        }

        Text close = NewText(card, 34, FontStyle.Bold, new Color(0.78f, 0.83f, 0.95f), TextAnchor.MiddleCenter);
        close.text = "Close";
        RectTransform closeRt = (RectTransform)close.transform;
        Place(closeRt, new Vector2(0f, -400f), new Vector2(300f, 90f));
        close.raycastTarget = true;
        closeRt.gameObject.AddComponent<Button>().onClick.AddListener(ClosePower);
        powerPanel.gameObject.SetActive(false);
    }

    void BuildBurst(RectTransform root)
    {
        burstLayer = NewRect("WildcardBurst", root); Stretch(burstLayer, 0f);
        burstGroup = burstLayer.gameObject.AddComponent<CanvasGroup>();
        burstGroup.blocksRaycasts = true;
        burstFlash = burstLayer.gameObject.AddComponent<Image>(); burstFlash.color = new Color(1f, 1f, 1f, 0f);

        burstRays = NewRect("Rays", burstLayer);
        burstRays.anchorMin = burstRays.anchorMax = new Vector2(0.5f, 0.5f); burstRays.sizeDelta = new Vector2(1500f, 1500f);
        burstRaysImg = burstRays.gameObject.AddComponent<Image>(); burstRaysImg.sprite = RaysSprite(256, 14); burstRaysImg.raycastTarget = false;

        for (int i = 0; i < 28; i++)
        {
            RectTransform s = NewRect("Sparkle", burstLayer);
            s.anchorMin = s.anchorMax = new Vector2(0.5f, 0.5f);
            float size = UnityEngine.Random.Range(34f, 70f); s.sizeDelta = new Vector2(size, size);
            var img = s.gameObject.AddComponent<Image>(); img.sprite = StarSprite(64); img.raycastTarget = false;
            img.color = i % 3 == 0 ? Color.white : new Color(1f, 0.82f + 0.15f * (i % 2), 0.3f);
            s.gameObject.SetActive(false);
            sparkles.Add(s);
        }

        burstCard = NewRect("Card", burstLayer);
        burstCard.anchorMin = burstCard.anchorMax = new Vector2(0.5f, 0.5f); burstCard.sizeDelta = new Vector2(340f, 470f);
        var cimg = burstCard.gameObject.AddComponent<Image>();
        cimg.sprite = RoundedSprite(68, 94, 12, new Color(1f, 0.9f, 0.45f), new Color(0.93f, 0.45f, 0.05f), new Color(1f, 0.98f, 0.85f));
        cimg.type = Image.Type.Sliced; cimg.raycastTarget = false;
        RectTransform cstar = NewRect("Star", burstCard); Stretch(cstar, 60f);
        cstar.offsetMin = new Vector2(60f, 110f); cstar.offsetMax = new Vector2(-60f, -110f);
        var csi = cstar.gameObject.AddComponent<Image>(); csi.sprite = StarSprite(128); csi.raycastTarget = false;
        csi.gameObject.AddComponent<Shadow>().effectColor = new Color(0.5f, 0.22f, 0f, 0.7f);
        Text ctext = NewText(burstCard, 40, FontStyle.Bold, new Color(0.45f, 0.2f, 0f), TextAnchor.LowerCenter);
        ctext.text = "WILDCARD"; Stretch((RectTransform)ctext.transform, 26f);

        burstTitle = NewText(burstLayer, 110, FontStyle.Bold, new Color(1f, 0.9f, 0.35f), TextAnchor.MiddleCenter);
        burstTitleRt = (RectTransform)burstTitle.transform;
        burstTitleRt.anchorMin = burstTitleRt.anchorMax = new Vector2(0.5f, 0.5f);
        burstTitleRt.anchoredPosition = new Vector2(0f, -250f); burstTitleRt.sizeDelta = new Vector2(1040f, 160f);
        var to = burstTitle.gameObject.AddComponent<Outline>(); to.effectColor = new Color(0.45f, 0.18f, 0f, 1f); to.effectDistance = new Vector2(4f, -4f);
        burstSub = NewText(burstLayer, 46, FontStyle.Bold, Color.white, TextAnchor.MiddleCenter);
        var sr = (RectTransform)burstSub.transform;
        sr.anchorMin = sr.anchorMax = new Vector2(0.5f, 0.5f); sr.anchoredPosition = new Vector2(0f, -360f); sr.sizeDelta = new Vector2(1000f, 80f);
        burstSub.gameObject.AddComponent<Outline>().effectColor = new Color(0f, 0f, 0f, 0.9f);
        burstLayer.gameObject.SetActive(false);
    }

    Button GoldButton(Transform parent, Vector2 pos, Vector2 size, out Text label)
    {
        RectTransform b = NewRect("Skip", parent);
        Place(b, pos, size);
        var img = b.gameObject.AddComponent<Image>();
        img.sprite = RoundedSprite(80, 16, 7, new Color(1f, 0.88f, 0.36f), new Color(0.93f, 0.5f, 0.07f), new Color(1f, 0.96f, 0.8f));
        img.type = Image.Type.Sliced;
        var btn = b.gameObject.AddComponent<Button>(); btn.targetGraphic = img;
        var cb = btn.colors; cb.disabledColor = new Color(0.4f, 0.4f, 0.45f, 0.7f); btn.colors = cb;
        label = NewText(b, 40, FontStyle.Bold, new Color(0.3f, 0.14f, 0f), TextAnchor.MiddleCenter);
        label.supportRichText = true;
        Stretch((RectTransform)label.transform, 10f);
        return btn;
    }

    static void Place(RectTransform rt, Vector2 pos, Vector2 size)
    {
        rt.anchorMin = rt.anchorMax = new Vector2(0.5f, 0.5f);
        rt.pivot = new Vector2(0.5f, 0.5f);
        rt.anchoredPosition = pos; rt.sizeDelta = size;
    }

    // procedural sprites
    static Sprite ArrowSprite(int size)
    {
        var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.wrapMode = TextureWrapMode.Clamp;
        var tri = new[] { new Vector2(size * 0.18f, size * 0.5f), new Vector2(size * 0.78f, size * 0.12f), new Vector2(size * 0.78f, size * 0.88f) };
        var px = new Color[size * size];
        const int ss = 3;
        for (int y = 0; y < size; y++)
            for (int x = 0; x < size; x++)
            {
                int hits = 0;
                for (int sy = 0; sy < ss; sy++)
                    for (int sx = 0; sx < ss; sx++)
                        if (Inside(tri, new Vector2(x + (sx + 0.5f) / ss, y + (sy + 0.5f) / ss))) hits++;
                px[y * size + x] = new Color(1f, 1f, 1f, hits / (float)(ss * ss));
            }
        tex.SetPixels(px); tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f);
    }

    static Sprite RaysSprite(int size, int rays)
    {
        var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.wrapMode = TextureWrapMode.Clamp;
        var px = new Color[size * size];
        float r = size * 0.5f;
        for (int y = 0; y < size; y++)
            for (int x = 0; x < size; x++)
            {
                float dx = x + 0.5f - r, dy = y + 0.5f - r, d = Mathf.Sqrt(dx * dx + dy * dy) / r;
                float a = Mathf.Atan2(dy, dx);
                float beam = Mathf.Pow(Mathf.Max(0f, Mathf.Cos(a * rays * 0.5f)), 8f);
                float fall = Mathf.Clamp01(1f - d) * Mathf.Clamp01(d * 4f);
                float glow = Mathf.Clamp01(1f - d * 2.2f) * 0.6f;
                px[y * size + x] = new Color(1f, 1f, 1f, Mathf.Clamp01(beam * fall + glow));
            }
        tex.SetPixels(px); tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f);
    }

    /// <summary>Rounded rectangle with a vertical gradient and a light border, 9-sliced by the radius.</summary>
    static Sprite RoundedSprite(int w, int h, int radius, Color top, Color bottom, Color border)
    {
        var tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
        tex.wrapMode = TextureWrapMode.Clamp;
        var px = new Color[w * h];
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                float cx = Mathf.Clamp(x + 0.5f, radius, w - radius), cy = Mathf.Clamp(y + 0.5f, radius, h - radius);
                float dist = Vector2.Distance(new Vector2(x + 0.5f, y + 0.5f), new Vector2(cx, cy));
                float alpha = Mathf.Clamp01(radius - dist + 0.5f);
                Color c = Color.Lerp(bottom, top, y / (float)(h - 1));
                if (dist > radius - 3f) c = Color.Lerp(c, border, 0.8f);
                c.a *= alpha;
                px[y * w + x] = c;
            }
        tex.SetPixels(px); tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, w, h), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect,
                             new Vector4(radius, radius, radius, radius));
    }
}
