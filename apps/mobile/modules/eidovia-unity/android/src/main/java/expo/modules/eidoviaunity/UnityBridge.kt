package expo.modules.eidoviaunity

import android.app.Activity
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.unity3d.player.IUnityPlayerLifecycleEvents
import com.unity3d.player.UnityPlayer
import com.unity3d.player.UnityPlayerForActivityOrService

/**
 * One Unity player for the whole app (Unity can only run once per process).
 * Unity C# calls [onUnityMessage]; React Native calls [post]. Messages sent before
 * Unity is running are queued and delivered once it starts.
 */
object UnityBridge {
  private const val TAG = "EidoviaUnity"
  private val main = Handler(Looper.getMainLooper())

  @Volatile internal var module: EidoviaUnityModule? = null
  internal var player: UnityPlayerForActivityOrService? = null
    private set
  internal val views = mutableSetOf<EidoviaUnityView>()
  private val pending = ArrayList<Triple<String, String, String>>()
  private var ready = false

  fun ensurePlayer(activity: Activity): UnityPlayerForActivityOrService {
    player?.let { return it }
    Log.i(TAG, "starting Unity")
    val p = UnityPlayerForActivityOrService(activity, object : IUnityPlayerLifecycleEvents {
      override fun onUnityPlayerUnloaded() { Log.i(TAG, "Unity unloaded") }
      override fun onUnityPlayerQuitted() { Log.i(TAG, "Unity quit"); player = null; ready = false }
    })
    player = p
    return p
  }

  /** React Native -> Unity: UnitySendMessage(gameObject, method, message). */
  fun post(gameObject: String, method: String, message: String) {
    main.post {
      if (player == null || !ready) {
        pending.add(Triple(gameObject, method, message))
        if (pending.size > 50) pending.removeAt(0)
      } else {
        UnityPlayer.UnitySendMessage(gameObject, method, message)
      }
    }
  }

  private fun flush() {
    val queued = ArrayList(pending)
    pending.clear()
    queued.forEach { (g, m, msg) -> UnityPlayer.UnitySendMessage(g, m, msg) }
  }

  /** Unity -> React Native. Called from C# (MobileBridge.Send) on Unity's thread. */
  @JvmStatic
  fun onUnityMessage(message: String) {
    main.post {
      if (!ready && message.contains("\"ready\"")) { ready = true; flush() }
      module?.emit(message)
      views.forEach { it.dispatch(message) }
    }
  }

  fun pause() { main.post { player?.onPause() } }

  fun resume() { main.post { player?.onResume() } }

  fun focus(hasFocus: Boolean) { main.post { player?.windowFocusChanged(hasFocus) } }
}
