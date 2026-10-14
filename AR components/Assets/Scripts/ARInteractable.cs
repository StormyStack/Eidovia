using UnityEngine;

/// <summary>
/// Sits on the root of a placed DNA model (ARModelSpawner adds it). Gives the model a smooth, physical feel:
///   * moves glide to the finger (critically damped), pinch-scale eases in, twist leaves a spin that slows down,
///   * "presence" spring: the model pops in when placed and shrinks/grows during stage morphs,
///   * a gentle idle float and breathing so it never looks frozen.
/// All motion is applied in LateUpdate from target values, so input never fights the animation.
/// </summary>
public class ARInteractable : MonoBehaviour
{
    [Tooltip("Smallest size, as a multiple of the prefab's own size")]
    public float minScale = 0.3f;
    [Tooltip("Largest size, as a multiple of the prefab's own size")]
    public float maxScale = 3f;

    [Header("Feel")]
    [Tooltip("Seconds to glide to a new position (0 = snap)")]
    public float moveSmoothTime = 0.09f;
    [Tooltip("Seconds for pinch-scale to settle")]
    public float scaleSmoothTime = 0.08f;
    [Tooltip("How fast a flick-spin slows down (higher = stops sooner)")]
    public float spinFriction = 2.2f;
    [Tooltip("Max spin speed after a twist, degrees per second")]
    public float maxSpin = 540f;
    [Tooltip("Spring stiffness of the pop-in / morph animation")]
    public float presenceStiffness = 140f;
    [Tooltip("Damping of the pop-in / morph animation (lower = more bounce)")]
    public float presenceDamping = 13f;
    [Tooltip("Idle float height as a fraction of the model size")]
    public float floatAmount = 0.012f;
    public float floatSpeed = 0.9f;
    [Tooltip("Idle breathing as a fraction of the scale")]
    public float breathAmount = 0.006f;

    Vector3 baseScale;
    float factor = 1f, shownFactor = 1f, factorVel;
    Vector3 restPos, posVel, targetPos;
    float spinVel, lastTwistTime = -1f;
    float presence = 1f, presenceVel, presenceTarget = 1f;
    float modelSize = 0.3f, phase;

    public float CurrentFactor { get { return factor; } }
    /// <summary>Where the model rests (without the idle float).</summary>
    public Vector3 RestPosition { get { return restPos; } }
    /// <summary>0 = hidden, 1 = fully shown. The game animates it with a spring.</summary>
    public float Presence { get { return presence; } }
    public float PresenceTarget { get { return presenceTarget; } set { presenceTarget = Mathf.Max(0f, value); } }
    public bool IsSettled { get { return Mathf.Abs(presence - presenceTarget) < 0.02f && Mathf.Abs(presenceVel) < 0.05f; } }

    void Awake()
    {
        baseScale = transform.localScale;
        restPos = targetPos = transform.position;
        phase = Random.value * 10f;
        Bounds b;
        if (TryBounds(out b)) modelSize = Mathf.Max(0.05f, b.size.magnitude);
    }

    // ------------------------------------------------------------ input API

    public void MoveTo(Vector3 worldPos) { targetPos = worldPos; }

    public void Teleport(Vector3 worldPos) { targetPos = restPos = worldPos; posVel = Vector3.zero; }

    public void ScaleBy(float multiplier)
    {
        factor = Mathf.Clamp(factor * multiplier, minScale, maxScale);
    }

    public void RotateBy(float degrees)
    {
        transform.Rotate(0f, degrees, 0f, Space.World);
        float dt = Mathf.Max(Time.deltaTime, 1e-4f);
        spinVel = Mathf.Clamp(Mathf.Lerp(spinVel, degrees / dt, 0.35f), -maxSpin, maxSpin);   // remembered for the flick
        lastTwistTime = Time.time;
    }

    /// <summary>Extra spin, e.g. for celebrations or morphs (degrees per second).</summary>
    public void AddSpin(float degreesPerSecond) { spinVel = Mathf.Clamp(spinVel + degreesPerSecond, -maxSpin * 2f, maxSpin * 2f); lastTwistTime = -1f; }

    public void ResetSize() { factor = 1f; }

    /// <summary>Start hidden and pop in (used when the model is spawned).</summary>
    public void PopIn() { presence = 0f; presenceVel = 0f; presenceTarget = 1f; }

    // ------------------------------------------------------------ motion

    void LateUpdate()
    {
        float dt = Time.deltaTime;
        if (dt <= 0f) return;

        // glide to the target position
        restPos = moveSmoothTime > 0f ? Vector3.SmoothDamp(restPos, targetPos, ref posVel, moveSmoothTime) : targetPos;

        // pinch scale eases in
        shownFactor = Mathf.SmoothDamp(shownFactor, factor, ref factorVel, scaleSmoothTime);

        // spin inertia once the fingers have let go
        bool twisting = Time.time - lastTwistTime < 0.06f;
        if (!twisting && Mathf.Abs(spinVel) > 0.5f)
        {
            transform.Rotate(0f, spinVel * dt, 0f, Space.World);
            spinVel *= Mathf.Exp(-spinFriction * dt);
        }
        else if (!twisting) spinVel = 0f;

        // presence spring (semi-implicit Euler, stable for these values)
        presenceVel += (presenceStiffness * (presenceTarget - presence) - presenceDamping * presenceVel) * dt;
        presence += presenceVel * dt;
        if (presenceTarget <= 0f && presence < 0f) { presence = 0f; presenceVel = 0f; }

        // idle float and breathing (fade out while hidden)
        float t = Time.time * floatSpeed + phase;
        float shown = Mathf.Clamp01(presence);
        float bob = Mathf.Sin(t) * 0.6f + Mathf.Sin(t * 1.7f + 1.3f) * 0.4f;
        transform.position = restPos + Vector3.up * (bob * floatAmount * modelSize * shown * shownFactor);
        float breathe = 1f + breathAmount * Mathf.Sin(t * 1.3f + 0.7f);
        transform.localScale = baseScale * (shownFactor * Mathf.Max(0f, presence) * breathe);
    }

    bool TryBounds(out Bounds b)
    {
        b = new Bounds();
        bool any = false;
        foreach (Renderer r in GetComponentsInChildren<Renderer>())
        {
            if (!any) { b = r.bounds; any = true; } else b.Encapsulate(r.bounds);
        }
        return any;
    }
}
