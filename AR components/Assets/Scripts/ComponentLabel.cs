using UnityEngine;

/// <summary>
/// Optional. Put this on any object inside a DNA prefab to set (or override) the name and text that appear
/// when the user taps it. Objects without it are named automatically from their object names
/// (Sugar_01, A_Base_03_G, Phosphate_Group, BasePair_04 ...), see DnaPartCatalog in ComponentPicker.cs.
/// </summary>
public class ComponentLabel : MonoBehaviour
{
    public string title = "Component";
    [Tooltip("Small grey line under the title (optional)")]
    public string subtitle;
    [TextArea(3, 8)]
    public string description;
}
