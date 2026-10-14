using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;

/// <summary>
/// Places one DNA model on a detected surface and moves it there when asked.
/// Put it on XR Origin (next to AR Raycast Manager). Input comes from TouchInteractionManager,
/// the prefab comes from LevelManager.
/// </summary>
[RequireComponent(typeof(ARRaycastManager))]
public class ARModelSpawner : MonoBehaviour
{
    [SerializeField] GameObject prefab;                 // set by LevelManager; can be left empty
    [SerializeField] bool hidePlanesAfterPlacing = true; // planes stay (and keep working) but become invisible
    [SerializeField] float editorDistance = 1.0f;       // Editor only: fallback when there are no AR planes
    [SerializeField] float noArDistance = 1.1f;         // 3D mode (phone without AR): distance of the model from the camera

    public GameObject Current { get; private set; }
    public ARInteractable CurrentInteractable { get; private set; }
    public bool HasModel { get { return Current != null; } }
    public bool HasPrefab { get { return prefab != null; } }
    public event Action<GameObject> ModelChanged;

    ARRaycastManager raycaster;
    ARPlaneManager planeManager;
    Camera cam;
    float nextPlaneCheck;
    static readonly List<ARRaycastHit> hits = new List<ARRaycastHit>();

    Camera Cam
    {
        get { if (cam == null) cam = Camera.main; return cam; }
    }

    void Awake()
    {
        raycaster = GetComponent<ARRaycastManager>();
        planeManager = GetComponent<ARPlaneManager>();
        if (planeManager == null) planeManager = FindFirstObjectByType<ARPlaneManager>();
    }

    /// <summary>First call places the model, later calls move it. Returns false if no surface is under the finger.</summary>
    public bool PlaceOrMove(Vector2 screenPos)
    {
        Vector3 point;
        if (!TryGetSurfacePoint(screenPos, out point)) return false;

        if (Current == null) Spawn(prefab, point, FacingCamera(point));
        else if (CurrentInteractable != null) CurrentInteractable.MoveTo(point);   // glides there
        else Current.transform.position = point;
        return true;
    }

    /// <summary>Swap to another prefab. If a model is already placed, the new one appears at the same spot.</summary>
    public void SetPrefab(GameObject newPrefab)
    {
        prefab = newPrefab;
        if (Current == null) return;

        Vector3 pos = CurrentInteractable != null ? CurrentInteractable.RestPosition : Current.transform.position;
        Quaternion rot = Current.transform.rotation;
        Destroy(Current);
        Current = null;
        Spawn(prefab, pos, rot);
    }

    /// <summary>Hook to a "Reset" button if you want one: removes the model so the next tap places it again.</summary>
    public void RemoveModel()
    {
        if (Current != null) Destroy(Current);
        Current = null;
        CurrentInteractable = null;
        SetPlanesVisible(true);
        if (ModelChanged != null) ModelChanged(null);
    }

    public bool TryGetSurfacePoint(Vector2 screenPos, out Vector3 point)
    {
        if (ARSupportFallback.NoAR)
        {
            // 3D mode: no surfaces, so use a plane facing the camera at the model's distance
            Ray r = Cam.ScreenPointToRay(screenPos);
            float d = Current != null ? Vector3.Dot(Current.transform.position - Cam.transform.position, Cam.transform.forward) : noArDistance;
            if (d < 0.3f) d = noArDistance;
            Plane screenPlane = new Plane(-Cam.transform.forward, Cam.transform.position + Cam.transform.forward * d);
            float e;
            if (screenPlane.Raycast(r, out e)) { point = r.GetPoint(e); return true; }
            point = Cam.transform.position + Cam.transform.forward * d;
            return true;
        }
        if (raycaster != null && raycaster.Raycast(screenPos, hits, TrackableType.PlaneWithinPolygon))
        {
            point = hits[0].pose.position;
            return true;
        }
#if UNITY_EDITOR
        // No AR in the Editor: use an imaginary floor 1.2 m below the camera so you can still test with the mouse.
        Ray ray = Cam.ScreenPointToRay(screenPos);
        Plane floor = new Plane(Vector3.up, new Vector3(0f, Cam.transform.position.y - 1.2f, 0f));
        float enter;
        if (floor.Raycast(ray, out enter) && enter < 10f) { point = ray.GetPoint(enter); return true; }
        point = Cam.transform.position + Cam.transform.forward * editorDistance;
        return true;
#else
        point = Vector3.zero;
        return false;
#endif
    }

    Quaternion FacingCamera(Vector3 pos)
    {
        Vector3 toCam = Cam.transform.position - pos;
        toCam.y = 0f;
        return toCam.sqrMagnitude > 1e-4f ? Quaternion.LookRotation(toCam) : Quaternion.identity;
    }

    void Spawn(GameObject pf, Vector3 pos, Quaternion rot)
    {
        if (pf == null) { Debug.LogWarning("[ARModelSpawner] No prefab assigned (fill the Levels list on LevelManager)."); return; }

        Current = Instantiate(pf, pos, rot);
        CurrentInteractable = Current.GetComponent<ARInteractable>();
        if (CurrentInteractable == null) CurrentInteractable = Current.AddComponent<ARInteractable>();
        CurrentInteractable.PopIn();                                   // springs in instead of appearing
        if (ModelChanged != null) ModelChanged(Current);
    }

    void Update()
    {
        if (!hidePlanesAfterPlacing || planeManager == null || Time.time < nextPlaneCheck) return;
        nextPlaneCheck = Time.time + 0.5f;
        SetPlanesVisible(Current == null);   // also catches planes detected after placing
    }

    void SetPlanesVisible(bool visible)
    {
        if (planeManager == null) return;
        foreach (ARPlane plane in planeManager.trackables)
            foreach (Renderer r in plane.GetComponentsInChildren<Renderer>())
                r.enabled = visible;
    }
}
