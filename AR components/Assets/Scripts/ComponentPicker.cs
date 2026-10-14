using System.Collections.Generic;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

/// <summary>
/// Tap-to-identify for the placed DNA model.
///   * Adds colliders to every part of the model when it is spawned (no prefab changes needed).
///   * Tap a part: it is highlighted, a name tag floats over it and an info card explains it.
///   * Tap empty space or the X to close.
/// TouchInteractionManager adds this automatically and decides when a touch is a tap.
/// Part names come from the object names in the models (see DnaPartCatalog below);
/// a ComponentLabel on an object overrides them.
/// 3D text that is part of a model (objects named "Label_<part>", e.g. Label_Adenine_A) can be hidden until
/// that part is tapped (see Baked Labels).
/// </summary>
public class ComponentPicker : MonoBehaviour
{
    public enum BakedLabelMode { ShowOnTap, AlwaysVisible, Hidden }
    public const string LabelPrefix = "Label_";
    public const string ColliderTag = "_Collider";

    [SerializeField] ARModelSpawner spawner;

    [Header("3D text labels inside the model (objects named Label_<part>)")]
    [Tooltip("ShowOnTap: hidden until the part is tapped. AlwaysVisible: never hidden. Hidden: never shown (the floating name tag is used instead)")]
    [SerializeField] BakedLabelMode bakedLabels = BakedLabelMode.ShowOnTap;

    [Header("Highlight")]
    [SerializeField] Color highlightColor = new Color(1f, 0.93f, 0.35f);
    [SerializeField, Range(0f, 1f)] float highlightStrength = 0.6f;

    [Header("Colliders")]
    [Tooltip("Models with more meshes than this get one collider for the whole model (keeps big models fast)")]
    [SerializeField] int maxPartColliders = 400;
    [Tooltip("Meshes bigger than this get a box collider instead of an exact mesh collider (faster to set up on phones)")]
    [SerializeField] int maxMeshColliderVertices = 20000;

    [Header("UI")]
    [SerializeField] bool showNameTag = true;
    [SerializeField] bool showInfoCard = true;

    [Header("Debug")]
    [Tooltip("Write what each tap hits to the Console (turn off for the final build)")]
    [SerializeField] bool debugLog = false;

    [Tooltip("Distance of the info card from the bottom of the screen")]
    [SerializeField] float cardBottom = 40f;

    public bool HasSelection { get { return selectedGroup != null; } }
    /// <summary>False while the game is changing models: taps are ignored.</summary>
    public bool Interactable = true;
    /// <summary>A part was tapped: its info and the part object (group) that was highlighted.</summary>
    public event System.Action<DnaPartInfo, Transform> PartSelected;

    GameObject model;
    Transform selectedGroup;
    readonly List<Renderer> selectedRenderers = new List<Renderer>();
    readonly List<Renderer> bakedLabelRenderers = new List<Renderer>();
    readonly List<Renderer> shownLabels = new List<Renderer>();
    MaterialPropertyBlock block, emptyBlock;
    Camera cam;
    float nextBoundsUpdate;
    Vector3 tagWorldPoint;

    // UI
    RectTransform canvasRect, card, nameTag;
    CanvasGroup nameTagGroup;
    Text cardTitle, cardSubtitle, cardBody, tagText, cardBadge;
    Coroutine hintRoutine;
    readonly List<Renderer> hintRenderers = new List<Renderer>();

    static readonly RaycastHit[] hitBuffer = new RaycastHit[32];
    static readonly int[] colorProps =
    {
        Shader.PropertyToID("baseColorFactor"), // glTFast shaders
        Shader.PropertyToID("_BaseColor"),      // URP Lit / Unlit
        Shader.PropertyToID("_Color"),          // legacy shaders
    };

    Camera Cam { get { if (cam == null) cam = Camera.main; return cam; } }

    void Awake()
    {
        if (spawner == null) spawner = GetComponent<ARModelSpawner>();
        if (spawner == null) spawner = FindFirstObjectByType<ARModelSpawner>();
        block = new MaterialPropertyBlock();
        emptyBlock = new MaterialPropertyBlock();
    }

    void OnEnable()
    {
        if (spawner == null) return;
        spawner.ModelChanged += OnModelChanged;
        if (spawner.Current != null) OnModelChanged(spawner.Current);
    }

    void OnDisable()
    {
        if (spawner != null) spawner.ModelChanged -= OnModelChanged;
        Clear();
    }

    void OnModelChanged(GameObject newModel)
    {
        if (hintRoutine != null) { StopCoroutine(hintRoutine); hintRoutine = null; }
        hintRenderers.Clear();
        Clear();
        model = newModel;
        if (model != null) PrepareColliders(model);
    }

    // ------------------------------------------------------------ public API (used by TouchInteractionManager)

    /// <summary>True if the finger is on (or very close to) the placed model.</summary>
    public bool IsModelUnder(Vector2 screenPos)
    {
        RaycastHit hit;
        if (!Interactable) return false;
        bool on = TryHitModel(screenPos, out hit);
        if (debugLog) Debug.Log("[ComponentPicker] touch began at " + screenPos + " on model: " + on + (on ? " (" + hit.collider.name + ")" : ""));
        return on;
    }

    /// <summary>Select the part under the finger. Returns false (and closes the info) if nothing was hit.</summary>
    public bool SelectAt(Vector2 screenPos)
    {
        RaycastHit hit;
        if (!Interactable) return false;
        if (!TryHitModel(screenPos, out hit))
        {
            if (debugLog) Debug.Log("[ComponentPicker] tap at " + screenPos + " hit nothing on " + (model != null ? model.name : "<no model>"));
            Clear(); return false;
        }

        Transform group;
        DnaPartInfo info = DnaPartCatalog.Resolve(hit.collider.transform, model.transform, out group);
        if (debugLog) Debug.Log("[ComponentPicker] tap hit '" + hit.collider.name + "' (" + hit.collider.GetType().Name + ") -> '" + info.title + "' group '" + group.name + "'");
        Select(group, info);
        return true;
    }

    public void Clear()
    {
        RemoveHighlight();
        HideShownLabels();
        selectedGroup = null;
        selectedRenderers.Clear();
        if (card != null) card.gameObject.SetActive(false);
        if (nameTag != null) nameTag.gameObject.SetActive(false);
    }

    // ------------------------------------------------------------ selection

    void Select(Transform group, DnaPartInfo info)
    {
        RemoveHighlight();
        selectedGroup = group;
        selectedRenderers.Clear();
        group.GetComponentsInChildren(false, selectedRenderers);
        nextBoundsUpdate = 0f;

        // 3D text labels that belong to this part
        HideShownLabels();
        bool hasBakedLabel = false;
        string groupName = DnaPartCatalog.Clean(group.name);
        foreach (Renderer r in bakedLabelRenderers)
        {
            if (r == null || !DnaPartCatalog.LabelBelongsTo(r.name, groupName)) continue;
            if (bakedLabels == BakedLabelMode.ShowOnTap) { r.enabled = true; shownLabels.Add(r); }
            if (bakedLabels != BakedLabelMode.Hidden) hasBakedLabel = true;
        }

        EnsureUI();
        cardBadge.gameObject.SetActive(false);
        if (showInfoCard)
        {
            cardTitle.text = info.title;
            cardSubtitle.text = info.subtitle;
            cardSubtitle.gameObject.SetActive(!string.IsNullOrEmpty(info.subtitle));
            cardBody.text = info.description;
            cardBody.gameObject.SetActive(!string.IsNullOrEmpty(info.description));
            card.gameObject.SetActive(true);
        }
        if (showNameTag && !hasBakedLabel)   // the model's own text already names it
        {
            tagText.text = info.title;
            nameTag.gameObject.SetActive(true);
        }

        ApplyHighlight(highlightStrength);
        LateUpdate();
        if (PartSelected != null) PartSelected(info, group);
    }

    void LateUpdate()
    {
        if (selectedGroup == null) return;
        if (model == null) { Clear(); return; }

        // gentle pulse (skipped for very big selections to keep it cheap)
        if (selectedRenderers.Count <= 64)
            ApplyHighlight(highlightStrength * (0.7f + 0.3f * Mathf.Sin(Time.time * 5f)));

        if (nameTag == null || !nameTag.gameObject.activeSelf) return;

        if (Time.time >= nextBoundsUpdate)
        {
            nextBoundsUpdate = Time.time + (selectedRenderers.Count > 200 ? 0.2f : 0f);
            Bounds b;
            if (GetBounds(selectedRenderers, out b)) tagWorldPoint = new Vector3(b.center.x, b.max.y, b.center.z);
            else tagWorldPoint = selectedGroup.position;
        }

        Vector3 sp = Cam != null ? Cam.WorldToScreenPoint(tagWorldPoint) : new Vector3(-1f, -1f, -1f);
        bool visible = sp.z > 0f;
        nameTagGroup.alpha = visible ? 1f : 0f;
        Vector2 local;
        if (visible && RectTransformUtility.ScreenPointToLocalPointInRectangle(canvasRect, sp, null, out local))
            nameTag.anchoredPosition = local + new Vector2(0f, 24f);
    }

    /// <summary>Small highlighted line above the card title (e.g. "NEW DISCOVERY"). Null hides it.</summary>
    public void ShowBadge(string text)
    {
        if (cardBadge == null) return;
        cardBadge.text = text ?? "";
        cardBadge.gameObject.SetActive(!string.IsNullOrEmpty(text) && card != null && card.gameObject.activeSelf);
    }

    /// <summary>Make a part glow for a moment without selecting it (used for hints).</summary>
    public void FlashHint(Transform group, float seconds = 2.5f)
    {
        if (group == null) return;
        if (hintRoutine != null) { StopCoroutine(hintRoutine); EndHint(); }
        hintRoutine = StartCoroutine(HintGlow(group, seconds));
    }

    System.Collections.IEnumerator HintGlow(Transform group, float seconds)
    {
        hintRenderers.Clear();
        group.GetComponentsInChildren(false, hintRenderers);
        float t = 0f;
        while (t < seconds && group != null)
        {
            float k = 0.75f * (0.5f + 0.5f * Mathf.Sin(t * 9f));
            foreach (Renderer r in hintRenderers)
                if (r != null && r.enabled && !selectedRenderers.Contains(r)) Tint(r, new Color(0.35f, 1f, 0.9f), k);
            t += Time.deltaTime;
            yield return null;
        }
        EndHint();
        hintRoutine = null;
    }

    void EndHint()
    {
        foreach (Renderer r in hintRenderers)
        {
            if (r == null || selectedRenderers.Contains(r)) continue;
            int count = r.sharedMaterials.Length;
            for (int i = 0; i < count; i++) r.SetPropertyBlock(emptyBlock, i);
        }
        hintRenderers.Clear();
    }

    void Tint(Renderer r, Color c, float amount)
    {
        Material[] mats = r.sharedMaterials;
        for (int i = 0; i < mats.Length; i++)
        {
            Material mat = mats[i];
            if (mat == null) continue;
            foreach (int prop in colorProps)
            {
                if (!mat.HasProperty(prop)) continue;
                block.Clear();
                block.SetColor(prop, Color.Lerp(mat.GetColor(prop), c, amount));
                r.SetPropertyBlock(block, i);
                break;
            }
        }
    }

    // ------------------------------------------------------------ raycasting

    bool TryHitModel(Vector2 screenPos, out RaycastHit best)
    {
        best = default(RaycastHit);
        if (model == null || Cam == null) return false;

        // exact point first, then a small ring around the finger (atoms and bonds are tiny on a phone)
        if (RaycastModel(screenPos, out best)) return true;
        float r = Mathf.Max(20f, (Screen.dpi > 0f ? Screen.dpi : 160f) * 0.12f);
        for (int ring = 1; ring <= 2; ring++)
            for (int i = 0; i < 8; i++)
            {
                float a = i * Mathf.PI / 4f;
                Vector2 p = screenPos + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * r * ring * 0.5f;
                if (RaycastModel(p, out best)) return true;
            }
        return false;
    }

    bool RaycastModel(Vector2 screenPos, out RaycastHit best)
    {
        best = default(RaycastHit);
        Ray ray = Cam.ScreenPointToRay(screenPos);
        int n = Physics.RaycastNonAlloc(ray, hitBuffer, 30f, ~0, QueryTriggerInteraction.Collide);
        float bestDist = float.MaxValue;
        Transform root = model.transform;
        for (int i = 0; i < n; i++)
        {
            RaycastHit h = hitBuffer[i];
            if (h.distance < bestDist && h.collider.transform.IsChildOf(root))
            {
                bestDist = h.distance;
                best = h;
            }
        }
        return bestDist < float.MaxValue;
    }

    void HideShownLabels()
    {
        foreach (Renderer r in shownLabels) if (r != null) r.enabled = false;
        shownLabels.Clear();
    }

    void PrepareColliders(GameObject m)
    {
        bakedLabelRenderers.Clear();
        shownLabels.Clear();
        foreach (Renderer r in m.GetComponentsInChildren<Renderer>(true))
        {
            if (!DnaPartCatalog.Clean(r.name).StartsWith(LabelPrefix)) continue;
            bakedLabelRenderers.Add(r);
            if (bakedLabels != BakedLabelMode.AlwaysVisible) r.enabled = false;
        }

        MeshFilter[] filters = m.GetComponentsInChildren<MeshFilter>(true);

        // Models can bring their own invisible tap targets (objects named "..._Collider..."):
        // then only those get colliders, which is fast and easy to hit even for thin parts.
        bool hasProxies = false;
        foreach (MeshFilter f in filters)
        {
            if (f.sharedMesh == null || !f.name.Contains(ColliderTag)) continue;
            hasProxies = true;
            Renderer pr = f.GetComponent<Renderer>();
            if (pr != null) pr.enabled = false;
            if (f.GetComponent<Collider>() == null)
            {
                BoxCollider box = f.gameObject.AddComponent<BoxCollider>();
                box.center = f.sharedMesh.bounds.center;
                box.size = f.sharedMesh.bounds.size;
            }
        }
        if (hasProxies)
        {
            if (debugLog) Debug.Log("[ComponentPicker] '" + m.name + "' uses its own tap targets");
            return;
        }

        if (debugLog) Debug.Log("[ComponentPicker] preparing '" + m.name + "': " + filters.Length + " meshes, " +
            m.GetComponentsInChildren<Renderer>(true).Length + " renderers, " + bakedLabelRenderers.Count + " labels, existing colliders " +
            m.GetComponentsInChildren<Collider>(true).Length);

        if (filters.Length > maxPartColliders)
        {
            // Too many pieces (e.g. the Level 5 helix): one box around everything.
            if (m.GetComponent<Collider>() != null) return;
            Bounds world;
            if (!GetBounds(new List<Renderer>(m.GetComponentsInChildren<Renderer>()), out world)) return;
            Transform t = m.transform;
            Bounds local = new Bounds(t.InverseTransformPoint(world.center), Vector3.zero);
            Vector3 e = world.extents;
            for (int i = 0; i < 8; i++)
                local.Encapsulate(t.InverseTransformPoint(world.center + Vector3.Scale(e, new Vector3(
                    (i & 1) == 0 ? -1 : 1, (i & 2) == 0 ? -1 : 1, (i & 4) == 0 ? -1 : 1))));
            BoxCollider box = m.AddComponent<BoxCollider>();
            box.center = local.center;
            box.size = local.size;
            return;
        }

        foreach (MeshFilter f in filters)
        {
            Mesh mesh = f.sharedMesh;
            Renderer rend = f.GetComponent<Renderer>();
            if (mesh == null || f.GetComponent<Collider>() != null || rend == null) continue;
            if (bakedLabelRenderers.Contains(rend) && !rend.enabled) continue;   // hidden labels are not tappable

            if (mesh.isReadable && mesh.vertexCount <= maxMeshColliderVertices)
            {
                f.gameObject.AddComponent<MeshCollider>().sharedMesh = mesh;   // exact shape
            }
            else
            {
                // mesh data is not readable in the build: use a box around the mesh instead
                Bounds b = mesh.bounds;
                Vector3 size = b.size;
                float minSide = Mathf.Max(size.x, Mathf.Max(size.y, size.z)) * 0.15f;  // flat rings still get some thickness
                BoxCollider box = f.gameObject.AddComponent<BoxCollider>();
                box.center = b.center;
                box.size = Vector3.Max(size, new Vector3(minSide, minSide, minSide));
            }
        }
        if (debugLog)
        {
            int mc = m.GetComponentsInChildren<MeshCollider>(true).Length, bc = m.GetComponentsInChildren<BoxCollider>(true).Length;
            Debug.Log("[ComponentPicker] '" + m.name + "' now has " + mc + " mesh colliders, " + bc + " box colliders. Scale " + m.transform.lossyScale);
        }
    }

    static bool GetBounds(List<Renderer> renderers, out Bounds bounds)
    {
        bounds = new Bounds();
        bool any = false;
        foreach (Renderer r in renderers)
        {
            if (r == null || !r.enabled) continue;
            if (!any) { bounds = r.bounds; any = true; }
            else bounds.Encapsulate(r.bounds);
        }
        return any;
    }

    // ------------------------------------------------------------ highlight

    void ApplyHighlight(float amount)
    {
        foreach (Renderer r in selectedRenderers)
        {
            if (r == null) continue;
            Material[] mats = r.sharedMaterials;
            for (int i = 0; i < mats.Length; i++)
            {
                Material mat = mats[i];
                if (mat == null) continue;
                foreach (int prop in colorProps)
                {
                    if (!mat.HasProperty(prop)) continue;
                    block.Clear();
                    block.SetColor(prop, Color.Lerp(mat.GetColor(prop), highlightColor, amount));
                    r.SetPropertyBlock(block, i);
                    break;
                }
            }
        }
    }

    void RemoveHighlight()
    {
        foreach (Renderer r in selectedRenderers)
        {
            if (r == null) continue;
            int count = r.sharedMaterials.Length;
            for (int i = 0; i < count; i++) r.SetPropertyBlock(emptyBlock, i);
        }
    }

    // ------------------------------------------------------------ UI (built at runtime, same style as LevelManager)

    void EnsureUI()
    {
        if (canvasRect != null) return;

        if (FindFirstObjectByType<EventSystem>() == null)
        {
            var es = new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
            es.GetComponent<InputSystemUIInputModule>().AssignDefaultActions();
        }

        var canvasGo = new GameObject("ComponentInfoUI", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        var canvas = canvasGo.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 5;
        var scaler = canvasGo.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1080f, 1920f);
        scaler.matchWidthOrHeight = 0.5f;
        canvasRect = (RectTransform)canvasGo.transform;

        Font font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        // ---- floating name tag (does not block touches)
        nameTag = NewRect("NameTag", canvasRect);
        nameTag.anchorMin = nameTag.anchorMax = new Vector2(0.5f, 0.5f);
        nameTag.pivot = new Vector2(0.5f, 0f);
        nameTagGroup = nameTag.gameObject.AddComponent<CanvasGroup>();
        nameTagGroup.blocksRaycasts = false;
        var tagBg = nameTag.gameObject.AddComponent<Image>();
        tagBg.color = new Color(0.05f, 0.07f, 0.13f, 0.88f);
        tagBg.raycastTarget = false;
        var tagLayout = nameTag.gameObject.AddComponent<HorizontalLayoutGroup>();
        tagLayout.padding = new RectOffset(28, 28, 14, 14);
        tagLayout.childControlWidth = tagLayout.childControlHeight = true;
        var tagFit = nameTag.gameObject.AddComponent<ContentSizeFitter>();
        tagFit.horizontalFit = tagFit.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
        tagText = NewText(nameTag, font, 40, FontStyle.Bold, highlightColor, TextAnchor.MiddleCenter);
        tagText.horizontalOverflow = HorizontalWrapMode.Overflow;
        nameTag.gameObject.SetActive(false);

        // ---- info card above the Previous / Next buttons (blocks touches so tapping it never moves the model)
        card = NewRect("InfoCard", canvasRect);
        card.anchorMin = card.anchorMax = new Vector2(0.5f, 0f);
        card.pivot = new Vector2(0.5f, 0f);
        card.anchoredPosition = new Vector2(0f, cardBottom);
        card.sizeDelta = new Vector2(1000f, 0f);
        card.gameObject.AddComponent<Image>().color = new Color(0.05f, 0.07f, 0.13f, 0.92f);
        var layout = card.gameObject.AddComponent<VerticalLayoutGroup>();
        layout.padding = new RectOffset(44, 110, 34, 40);
        layout.spacing = 10f;
        layout.childControlWidth = layout.childControlHeight = true;
        layout.childForceExpandWidth = true;
        layout.childForceExpandHeight = false;
        card.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;

        cardBadge = NewText(card, font, 30, FontStyle.Bold, new Color(0.45f, 1f, 0.6f), TextAnchor.UpperLeft);
        cardBadge.gameObject.SetActive(false);
        cardTitle = NewText(card, font, 54, FontStyle.Bold, highlightColor, TextAnchor.UpperLeft);
        cardSubtitle = NewText(card, font, 32, FontStyle.Italic, new Color(0.72f, 0.76f, 0.86f), TextAnchor.UpperLeft);
        cardBody = NewText(card, font, 37, FontStyle.Normal, Color.white, TextAnchor.UpperLeft);
        cardBody.lineSpacing = 1.1f;

        // close button (top right, outside the layout)
        RectTransform close = NewRect("Close", card);
        close.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
        close.anchorMin = close.anchorMax = new Vector2(1f, 1f);
        close.pivot = new Vector2(1f, 1f);
        close.anchoredPosition = new Vector2(-14f, -14f);
        close.sizeDelta = new Vector2(96f, 96f);
        var closeImg = close.gameObject.AddComponent<Image>();
        closeImg.color = new Color(1f, 1f, 1f, 0.08f);
        var closeBtn = close.gameObject.AddComponent<Button>();
        closeBtn.targetGraphic = closeImg;
        closeBtn.onClick.AddListener(Clear);
        Text x = NewText(close, font, 52, FontStyle.Normal, Color.white, TextAnchor.MiddleCenter);
        x.text = "×";
        var xr = (RectTransform)x.transform;
        xr.anchorMin = Vector2.zero; xr.anchorMax = Vector2.one; xr.offsetMin = xr.offsetMax = Vector2.zero;

        card.gameObject.SetActive(false);
    }

    static RectTransform NewRect(string name, Transform parent)
    {
        var go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent, false);
        return (RectTransform)go.transform;
    }

    static Text NewText(Transform parent, Font font, int size, FontStyle style, Color color, TextAnchor align)
    {
        RectTransform rt = NewRect("Text", parent);
        var t = rt.gameObject.AddComponent<Text>();
        t.font = font;
        t.fontSize = size;
        t.fontStyle = style;
        t.color = color;
        t.alignment = align;
        t.horizontalOverflow = HorizontalWrapMode.Wrap;
        t.verticalOverflow = VerticalWrapMode.Overflow;
        t.raycastTarget = false;
        return t;
    }
}

/// <summary>What the info card shows for one tapped part.</summary>
public struct DnaPartInfo
{
    public string title;
    public string subtitle;
    public string description;

    public DnaPartInfo(string title, string subtitle, string description)
    {
        this.title = title; this.subtitle = subtitle; this.description = description;
    }
}

/// <summary>
/// Turns object names from the DNA models into names and short explanations.
/// Walks up from the tapped mesh (e.g. "A_Sugar_03_Oxygen") to the first object that is a whole component
/// (e.g. "A_Sugar_03") and highlights that whole component.
/// </summary>
public static class DnaPartCatalog
{
    const string RxStrand = @"^(?:(?<strand>[AB])_)?";
    static readonly Regex rxBase = new Regex(RxStrand + @"Base(?:_(?<num>\d+))?_(?<b>[ATGC])$");
    static readonly Regex rxBaseFull = new Regex(@"^(?<name>Adenine|Thymine|Guanine|Cytosine)_(?<b>[ATGC])$");
    static readonly Regex rxSugar = new Regex(RxStrand + @"(?:Deoxyribose_)?Sugar(?:_(?<num>\d+))?$");
    static readonly Regex rxPhosphate = new Regex(RxStrand + @"Phosphate(?:_(?<num>\d+)|_Group)?$");
    static readonly Regex rxBackboneBond = new Regex(RxStrand + @"Phosphodiester_Bond(?:_(?<num>\d+))?$");
    static readonly Regex rxMarker = new Regex(RxStrand + @"Marker_(?<end>[35])prime$");
    static readonly Regex rxBasePair = new Regex(@"^BasePair_(?<num>\d+)$");
    static readonly Regex rxBackbone = new Regex(@"^Backbone_(?<strand>[AB])$");
    static readonly Regex rxNucleotide = new Regex(RxStrand + @"Nucleotide(?:_(?<num>\d+))?(?:_(?<kind>[A-Za-z]+))?$");
    static readonly Regex rxStrandRoot = new Regex(@"^(?:DNA_Strand|Polynucleotide_Strand|Strand_(?<strand>[AB]))$");
    static readonly Regex rxDoubleStrand = new Regex(@"^DNA_Double_Strand|Double_Strand_Combined|DoubleStrand$");
    static readonly Regex rxHydrogenBonds = new Regex(@"^Hydrogen_Bonds$");
    static readonly Regex rxHelix = new Regex(@"Double_?Helix$", RegexOptions.IgnoreCase);
    static readonly Regex rxCloneSuffix = new Regex(@"(\(Clone\)|\s*\(\d+\))+$");

    /// <summary>Every tappable part object (group) in the model.</summary>
    public static List<Transform> Groups(Transform modelRoot)
    {
        var set = new HashSet<Transform>();
        var list = new List<Transform>();
        foreach (MeshFilter mf in modelRoot.GetComponentsInChildren<MeshFilter>(true))
        {
            Transform group;
            Resolve(mf.transform, modelRoot, out group);
            if (group != modelRoot && set.Add(group)) list.Add(group);
        }
        // keep only the outermost groups so nested ones are not moved twice
        list.RemoveAll(g => { for (Transform p = g.parent; p != null && p != modelRoot; p = p.parent) if (set.Contains(p)) return true; return false; });
        return list;
    }

    /// <summary>Every kind of part (by title) that can be tapped in this model, with one example object each.</summary>
    public static Dictionary<string, Transform> Kinds(Transform modelRoot)
    {
        var kinds = new Dictionary<string, Transform>();
        foreach (MeshFilter mf in modelRoot.GetComponentsInChildren<MeshFilter>(true))
        {
            Transform group;
            DnaPartInfo info = Resolve(mf.transform, modelRoot, out group);
            if (group == modelRoot || string.IsNullOrEmpty(info.title) || kinds.ContainsKey(info.title)) continue;
            kinds.Add(info.title, group);
        }
        return kinds;
    }

    public static DnaPartInfo Resolve(Transform hit, Transform modelRoot, out Transform group)
    {
        // tapping a visible 3D label counts as tapping the part it names
        string hitName = Clean(hit.name);
        if (hitName.StartsWith(ComponentPicker.LabelPrefix))
        {
            Transform target = FindLabelTarget(hitName, modelRoot);
            if (target != null) hit = target;
        }

        string piece = PieceName(Clean(hit.name));

        for (Transform t = hit; t != null; t = t.parent)
        {
            ComponentLabel label = t.GetComponent<ComponentLabel>();
            if (label != null)
            {
                group = t;
                return new DnaPartInfo(label.title, label.subtitle, label.description);
            }

            DnaPartInfo info;
            if (TryMatch(t, out info))
            {
                group = t;
                if (piece != null && t != hit) info.subtitle = Join(info.subtitle, "You tapped: " + piece);
                return info;
            }
            if (t == modelRoot) break;
        }

        group = modelRoot;
        return new DnaPartInfo(Clean(modelRoot.name).Replace('_', ' '), null, null);
    }

    static bool TryMatch(Transform t, out DnaPartInfo info)
    {
        string n = Clean(t.name);
        Match m;

        if ((m = rxBase.Match(n)).Success || (m = rxBaseFull.Match(n)).Success)
        {
            info = BaseInfo(m.Groups["b"].Value[0]);
            info.subtitle = Context(m);
            return true;
        }
        if ((m = rxSugar.Match(n)).Success)
        {
            info = new DnaPartInfo("Deoxyribose sugar", Context(m),
                "A 5-carbon sugar. \"Deoxy\" means it has one oxygen less than ribose (no -OH on carbon 2'). " +
                "The base attaches to carbon 1' and the phosphate to carbon 5'.");
            return true;
        }
        if ((m = rxPhosphate.Match(n)).Success)
        {
            info = new DnaPartInfo("Phosphate group", Context(m),
                "One phosphorus atom bonded to four oxygen atoms. It is negatively charged and links one sugar " +
                "to the next, forming the sugar-phosphate backbone.");
            return true;
        }
        if ((m = rxBackboneBond.Match(n)).Success)
        {
            info = new DnaPartInfo("Phosphodiester bond", Context(m),
                "Joins the 3' carbon of one sugar to the 5' carbon of the next sugar through a phosphate group. " +
                "A chain of these bonds makes the sugar-phosphate backbone.");
            return true;
        }
        if ((m = rxMarker.Match(n)).Success)
        {
            bool five = m.Groups["end"].Value == "5";
            info = five
                ? new DnaPartInfo("5' end", StrandOnly(m),
                    "The end of the strand where the 5' carbon of the last sugar has a free phosphate group. " +
                    "DNA is built in the 5' to 3' direction.")
                : new DnaPartInfo("3' end", StrandOnly(m),
                    "The end of the strand where the last sugar has a free -OH group on its 3' carbon. " +
                    "New nucleotides are always added at this end.");
            return true;
        }
        if ((m = rxBasePair.Match(n)).Success)
        {
            int bonds = 0;
            foreach (Transform c in t) if (c.name.StartsWith("HBond")) bonds++;
            if (bonds == 0)
            {
                info = new DnaPartInfo("Base pair", "Base pair " + int.Parse(m.Groups["num"].Value),
                    "Two bases, one from each strand, held together by hydrogen bonds: adenine pairs with thymine " +
                    "(2 bonds) and guanine pairs with cytosine (3 bonds). Base pairs are the rungs of the DNA ladder.");
                return true;
            }
            string pair = bonds == 2 ? "2 bonds: an A-T pair" : bonds == 3 ? "3 bonds: a G-C pair" : bonds + " bonds";
            info = new DnaPartInfo("Hydrogen bonds", "Base pair " + int.Parse(m.Groups["num"].Value) + " - " + pair,
                "Weak bonds between complementary bases on opposite strands. A-T pairs share 2 hydrogen bonds and " +
                "G-C pairs share 3. They hold the two strands together but are weak enough to \"unzip\" when DNA is copied.");
            return true;
        }
        if ((m = rxBackbone.Match(n)).Success)
        {
            info = new DnaPartInfo("Sugar-phosphate backbone", "Strand " + m.Groups["strand"].Value,
                "Alternating deoxyribose sugars and phosphate groups linked by phosphodiester bonds. The two backbones " +
                "are the outside rails of the twisted ladder, and they run in opposite directions (antiparallel).");
            return true;
        }
        if (rxHydrogenBonds.IsMatch(n))
        {
            info = new DnaPartInfo("Hydrogen bonds", null,
                "Weak bonds between complementary bases: 2 for A-T, 3 for G-C. They hold the two strands together.");
            return true;
        }
        if ((m = rxNucleotide.Match(n)).Success)
        {
            info = new DnaPartInfo("Nucleotide", Context(m),
                "The building block of DNA: one phosphate group + one deoxyribose sugar + one nitrogenous base.");
            return true;
        }
        if ((m = rxStrandRoot.Match(n)).Success)
        {
            info = new DnaPartInfo("DNA strand (polynucleotide)", StrandOnly(m),
                "Nucleotides joined by phosphodiester bonds. The sugar-phosphate backbone runs along one side and the " +
                "bases stick out. A strand has a direction: a 5' end and a 3' end.");
            return true;
        }
        if (rxDoubleStrand.IsMatch(n))
        {
            info = new DnaPartInfo("Double-stranded DNA", null,
                "Two complementary strands running in opposite directions (antiparallel), held together by hydrogen " +
                "bonds between base pairs.");
            return true;
        }
        if (rxHelix.IsMatch(n))
        {
            info = new DnaPartInfo("DNA double helix", null,
                "Two antiparallel strands twisted into a right-handed spiral. The sugar-phosphate backbones are on " +
                "the outside and the base pairs are stacked inside like the steps of a twisted ladder " +
                "(about 10 base pairs per turn). The wide and narrow gaps between the strands are the major and minor grooves.");
            return true;
        }

        info = default(DnaPartInfo);
        return false;
    }

    static DnaPartInfo BaseInfo(char b)
    {
        switch (b)
        {
            case 'A': return new DnaPartInfo("Adenine (A)", null,
                "A purine base: two fused rings containing nitrogen. Adenine always pairs with thymine (A-T) " +
                "using 2 hydrogen bonds.");
            case 'G': return new DnaPartInfo("Guanine (G)", null,
                "A purine base: two fused rings containing nitrogen. Guanine always pairs with cytosine (G-C) " +
                "using 3 hydrogen bonds.");
            case 'C': return new DnaPartInfo("Cytosine (C)", null,
                "A pyrimidine base: one ring containing nitrogen. Cytosine always pairs with guanine (C-G) " +
                "using 3 hydrogen bonds.");
            default: return new DnaPartInfo("Thymine (T)", null,
                "A pyrimidine base: one ring containing nitrogen. Found only in DNA (RNA uses uracil instead). " +
                "Thymine always pairs with adenine (T-A) using 2 hydrogen bonds.");
        }
    }

    /// <summary>The atom / piece of a component that was actually touched, from the mesh name.</summary>
    static string PieceName(string n)
    {
        if (Regex.IsMatch(n, @"_Carbon(_B)?$")) return "carbon atoms (C)";
        if (Regex.IsMatch(n, @"_Oxygen(_B)?$")) return "oxygen atoms (O)";
        if (Regex.IsMatch(n, @"_Phosphorus(_B)?$")) return "phosphorus atom (P)";
        if (n.EndsWith("_Ring")) return "nitrogen-containing ring";
        if (Regex.IsMatch(n, @"_Bonds(_B)?$")) return "covalent bonds";
        return null;
    }

    static string Context(Match m)
    {
        string s = StrandOnly(m);
        Group num = m.Groups["num"];
        if (num.Success) s = Join(s, "Nucleotide " + int.Parse(num.Value));
        return s;
    }

    static string StrandOnly(Match m)
    {
        Group strand = m.Groups["strand"];
        return strand.Success ? "Strand " + strand.Value : null;
    }

    static string Join(string a, string b)
    {
        if (string.IsNullOrEmpty(a)) return b;
        if (string.IsNullOrEmpty(b)) return a;
        return a + "  ·  " + b;
    }

    public static string Clean(string n) { return rxCloneSuffix.Replace(n, "").Trim(); }

    /// <summary>"Label_Adenine_A" and "Label_Adenine_A_2" both belong to the part "Adenine_A".</summary>
    public static bool LabelBelongsTo(string labelName, string partName)
    {
        string n = Clean(labelName);
        string want = ComponentPicker.LabelPrefix + partName;
        return n == want || n.StartsWith(want + "_");
    }

    static Transform FindLabelTarget(string labelName, Transform modelRoot)
    {
        string part = labelName.Substring(ComponentPicker.LabelPrefix.Length);
        Transform[] all = modelRoot.GetComponentsInChildren<Transform>(true);
        for (int attempt = 0; attempt < 2; attempt++)
        {
            foreach (Transform t in all)
                if (Clean(t.name) == part) return t;
            part = Regex.Replace(part, @"_\d+$", "");   // Label_X_2 -> X
        }
        return null;
    }
}
