using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.EnhancedTouch;
using Touch = UnityEngine.InputSystem.EnhancedTouch.Touch;
using TouchPhase = UnityEngine.InputSystem.TouchPhase;

/// <summary>
/// Touch controls (new Input System):
///   1 finger tap   : place the model on a surface / move it there
///   tap on a part  : show its name and info (ComponentPicker); tap empty space to close it
///   1 finger drag  : slide the model along the surface (also works when the drag starts on the model)
///   2 finger pinch : resize
///   2 finger twist : rotate around the vertical axis
/// Touches that start on a UI button are ignored. Put it on XR Origin next to ARModelSpawner.
/// In the Editor the mouse acts as one finger (place and drag only).
/// </summary>
public class TouchInteractionManager : MonoBehaviour
{
    [SerializeField] ARModelSpawner spawner;
    [SerializeField] bool enableScale = true;
    [SerializeField] bool enableRotate = true;
    [SerializeField] ComponentPicker picker;            // added automatically if empty
    [SerializeField] bool enablePartInfo = true;

    bool twoFingerUsed;      // after a pinch, ignore the leftover finger until all fingers are lifted
    bool pinching;
    int pinchIdA = -1, pinchIdB = -1;
    float lastDistance, lastAngle;
    int blockedTouchId = -1; // a touch that started on a UI button
    bool touchOnModel;       // current touch started on the model: tap = select, drag = move
    bool dragging;
    Vector2 touchStart;

    static readonly List<RaycastResult> uiHits = new List<RaycastResult>();

    void Awake()
    {
        if (spawner == null) spawner = FindFirstObjectByType<ARModelSpawner>();
        if (enablePartInfo)
        {
            if (picker == null) picker = FindFirstObjectByType<ComponentPicker>();
            if (picker == null) picker = gameObject.AddComponent<ComponentPicker>();
        }
    }

    float DragThreshold
    {
        get { return Mathf.Max(18f, (Screen.dpi > 0f ? Screen.dpi : 160f) * 0.12f); }
    }

    void OnEnable()
    {
        EnhancedTouchSupport.Enable();
#if UNITY_EDITOR
        TouchSimulation.Enable();
#endif
    }

    void OnDisable()
    {
#if UNITY_EDITOR
        TouchSimulation.Disable();
#endif
        EnhancedTouchSupport.Disable();
    }

    void Update()
    {
        if (spawner == null) return;

        var touches = Touch.activeTouches;
        if (touches.Count == 0)
        {
            twoFingerUsed = false;
            pinching = false;
            blockedTouchId = -1;
            touchOnModel = false;
            return;
        }

        if (touches.Count >= 2)
        {
            HandleTwoFingers(touches[0], touches[1]);
            return;
        }

        pinching = false;
        if (!twoFingerUsed) HandleOneFinger(touches[0]);
    }

    void HandleOneFinger(Touch t)
    {
        if (t.phase == TouchPhase.Began)
        {
            touchOnModel = false;
            dragging = false;
            touchStart = t.screenPosition;
            if (IsOverUI(t.screenPosition)) blockedTouchId = t.touchId;
        }
        if (t.touchId == blockedTouchId) return;

        bool picking = enablePartInfo && picker != null && spawner.HasModel;

        switch (t.phase)
        {
            case TouchPhase.Began:
                if (picking && picker.IsModelUnder(t.screenPosition))
                {
                    touchOnModel = true;          // wait: a tap selects, a drag moves
                    return;
                }
                if (picking && picker.HasSelection)
                {
                    picker.Clear();               // first tap on empty space only closes the info
                    blockedTouchId = t.touchId;
                    return;
                }
                spawner.PlaceOrMove(t.screenPosition);
                break;

            case TouchPhase.Moved:
                if (touchOnModel && !dragging)
                {
                    if ((t.screenPosition - touchStart).magnitude < DragThreshold) return;
                    dragging = true;
                }
                spawner.PlaceOrMove(t.screenPosition);
                break;

            case TouchPhase.Ended:
                if (touchOnModel && !dragging && picking) picker.SelectAt(touchStart);
                touchOnModel = false;
                break;

            case TouchPhase.Canceled:
                touchOnModel = false;
                break;
        }
    }

    void HandleTwoFingers(Touch a, Touch b)
    {
        twoFingerUsed = true;
        ARInteractable target = spawner.CurrentInteractable;
        if (target == null) return;

        Vector2 pa = a.screenPosition, pb = b.screenPosition;
        float distance = Vector2.Distance(pa, pb);
        float angle = Mathf.Atan2(pb.y - pa.y, pb.x - pa.x) * Mathf.Rad2Deg;

        // (re)start the gesture when it begins or when the pair of fingers changes
        if (!pinching || a.touchId != pinchIdA || b.touchId != pinchIdB)
        {
            pinching = true;
            pinchIdA = a.touchId; pinchIdB = b.touchId;
            lastDistance = distance; lastAngle = angle;
            return;
        }

        if (enableScale && lastDistance > 1f && distance > 1f)
            target.ScaleBy(distance / lastDistance);
        if (enableRotate)
            target.RotateBy(-Mathf.DeltaAngle(lastAngle, angle));   // twist anticlockwise = model turns anticlockwise

        lastDistance = distance;
        lastAngle = angle;
    }

    static bool IsOverUI(Vector2 screenPos)
    {
        if (EventSystem.current == null) return false;
        var data = new PointerEventData(EventSystem.current) { position = screenPos };
        uiHits.Clear();
        EventSystem.current.RaycastAll(data, uiHits);
        return uiHits.Count > 0;
    }
}
