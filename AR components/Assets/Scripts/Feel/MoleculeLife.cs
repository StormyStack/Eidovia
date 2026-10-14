using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Makes a DNA model feel alive. Every tappable part (sugar, base, backbone, ...) gets a small damped spring:
///   * idle: parts drift with smooth, spatially coherent noise, so neighbours move together and nothing tears apart,
///   * Poke(): a tap kicks the tapped part and sends a ripple through nearby parts, which then settle.
/// Offsets are kept tiny relative to the model so bonds still look connected. LevelManager adds it to each model.
/// </summary>
public class MoleculeLife : MonoBehaviour
{
    [Tooltip("Idle drift, as a fraction of the model size")]
    public float idleAmount = 0.006f;
    [Tooltip("Idle drift speed")]
    public float idleSpeed = 0.35f;
    [Tooltip("How far a tap pushes the tapped part, as a fraction of the model size")]
    public float pokeAmount = 0.03f;
    [Tooltip("Ripple reach, as a fraction of the model size")]
    public float rippleReach = 0.35f;
    [Tooltip("Ripple travel speed, model sizes per second")]
    public float rippleSpeed = 1.6f;
    public float stiffness = 90f;
    public float damping = 9f;
    [Tooltip("Extra wobble for separate molecules (Level 1) that are not bonded to anything")]
    public float looseRotation = 6f;

    class Part
    {
        public Transform t;
        public Vector3 restLocalPos;
        public Quaternion restLocalRot;
        public Vector3 restModelPos;       // position in model space, for noise and ripple distance
        public Vector3 offset, vel;        // spring state, in model space
        public float seed;
    }

    struct Wave { public Vector3 origin; public float start; public float strength; }

    readonly List<Part> parts = new List<Part>();
    readonly List<Wave> waves = new List<Wave>();
    float size = 0.3f;
    bool loose;

    /// <summary>Call once after the model is spawned, with its tappable part groups.</summary>
    public void Setup(IEnumerable<Transform> groups, bool looseMolecules)
    {
        parts.Clear();
        loose = looseMolecules;
        Bounds b = new Bounds(transform.position, Vector3.zero); bool any = false;
        foreach (Renderer r in GetComponentsInChildren<Renderer>())
        {
            if (!r.enabled) continue;
            if (!any) { b = r.bounds; any = true; } else b.Encapsulate(r.bounds);
        }
        // model size in model space (independent of the current pinch / presence scale)
        float s = Mathf.Max(1e-4f, transform.lossyScale.x);
        size = Mathf.Max(1e-3f, (any ? b.size.magnitude : 0.3f) / s);

        foreach (Transform g in groups)
        {
            if (g == null || g == transform) continue;
            parts.Add(new Part
            {
                t = g,
                restLocalPos = g.localPosition,
                restLocalRot = g.localRotation,
                restModelPos = transform.InverseTransformPoint(g.position),
                seed = Random.value * 100f,
            });
        }
    }

    /// <summary>A tap on this part: kick it and ripple outwards.</summary>
    public void Poke(Transform group, float strength = 1f)
    {
        if (!loose) strength *= 0.45f;                 // bonded structures: smaller kick so bonds never look torn
        Part p = Find(group);
        Vector3 origin = p != null ? p.restModelPos : transform.InverseTransformPoint(group.position);
        // the tapped part jumps up/out a little
        if (p != null)
        {
            Vector3 outward = new Vector3(p.restModelPos.x, 0f, p.restModelPos.z);
            Vector3 dir = (Vector3.up * 0.8f + (outward.sqrMagnitude > 1e-8f ? outward.normalized * 0.5f : Vector3.zero)).normalized;
            p.vel += dir * pokeAmount * size * stiffness * 0.12f * strength;
        }
        waves.Add(new Wave { origin = origin, start = Time.time, strength = strength });
        if (waves.Count > 6) waves.RemoveAt(0);
    }

    /// <summary>Everything gets a soft shake (e.g. celebration when a stage is complete).</summary>
    public void Celebrate()
    {
        float k = loose ? 0.06f : 0.025f;
        foreach (Part p in parts) p.vel += Random.onUnitSphere * pokeAmount * size * stiffness * k;
    }

    Part Find(Transform g)
    {
        foreach (Part p in parts) if (p.t == g) return p;
        foreach (Part p in parts) if (g != null && g.IsChildOf(p.t)) return p;
        return null;
    }

    void LateUpdate()
    {
        float dt = Mathf.Min(Time.deltaTime, 1f / 30f);
        if (dt <= 0f || parts.Count == 0) return;
        float now = Time.time;
        float reach = rippleReach * size;

        // retire old ripples
        for (int i = waves.Count - 1; i >= 0; i--)
            if ((now - waves[i].start) * rippleSpeed * size > reach * 1.5f) waves.RemoveAt(i);

        foreach (Part p in parts)
        {
            if (p.t == null) continue;

            // ripple: a ring that expands from the tap and nudges parts it passes
            foreach (Wave w in waves)
            {
                float d = Vector3.Distance(p.restModelPos, w.origin);
                if (d < 1e-5f || d > reach) continue;
                float front = (now - w.start) * rippleSpeed * size;
                float band = Mathf.Exp(-Mathf.Pow((d - front) / (0.06f * size), 2f));
                if (band < 0.01f) continue;
                float fall = 1f - d / reach;
                Vector3 dir = (p.restModelPos - w.origin) / d + Vector3.up * 0.6f;
                p.vel += dir.normalized * band * fall * w.strength * pokeAmount * size * stiffness * 0.9f * dt;
            }

            // damped spring back to rest (semi-implicit Euler)
            p.vel += (-stiffness * p.offset - damping * p.vel) * dt;
            p.offset += p.vel * dt;

            // coherent idle drift: noise sampled at the part's position, so neighbours drift together
            Vector3 q = p.restModelPos / size * 2.2f;
            float tt = now * idleSpeed;
            Vector3 idle = new Vector3(
                Mathf.PerlinNoise(q.x + tt, q.y + 11.3f) - 0.5f,
                Mathf.PerlinNoise(q.y + tt, q.z + 37.1f) - 0.5f,
                Mathf.PerlinNoise(q.z + tt, q.x + 71.7f) - 0.5f) * (2f * idleAmount * size * (loose ? 2.2f : 1f));

            Transform parent = p.t.parent != null ? p.t.parent : transform;
            Vector3 world = transform.TransformVector(p.offset + idle);
            p.t.localPosition = p.restLocalPos + parent.InverseTransformVector(world);

            if (loose)
            {
                float a = looseRotation;
                Quaternion wob = Quaternion.Euler(
                    (Mathf.PerlinNoise(p.seed, tt) - 0.5f) * a + p.vel.z / (size * 0.02f + 1e-5f) * 0.4f,
                    (Mathf.PerlinNoise(tt, p.seed) - 0.5f) * a,
                    (Mathf.PerlinNoise(p.seed + 5f, tt) - 0.5f) * a - p.vel.x / (size * 0.02f + 1e-5f) * 0.4f);
                p.t.localRotation = p.restLocalRot * wob;
            }
        }
    }

    void OnDisable()
    {
        foreach (Part p in parts)
            if (p.t != null) { p.t.localPosition = p.restLocalPos; p.t.localRotation = p.restLocalRot; }
    }
}
