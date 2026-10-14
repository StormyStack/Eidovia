package expo.modules.eidoviaunity

import android.content.Context
import android.view.ViewGroup
import android.widget.FrameLayout
import expo.modules.kotlin.AppContext
import expo.modules.kotlin.viewevent.EventDispatcher
import expo.modules.kotlin.views.ExpoView

/** <UnityView/>: shows the shared Unity player inside the React Native screen. */
class EidoviaUnityView(context: Context, appContext: AppContext) : ExpoView(context, appContext) {
  override val shouldUseAndroidLayout = true

  private val onUnityMessage by EventDispatcher<Map<String, String>>()
  private var attached = false

  override fun onAttachedToWindow() {
    super.onAttachedToWindow()
    attachUnity()
  }

  private fun attachUnity() {
    if (attached) return
    val activity = appContext.currentActivity ?: return
    val player = UnityBridge.ensurePlayer(activity)
    val frame: FrameLayout = player.frameLayout
    (frame.parent as? ViewGroup)?.removeView(frame)
    addView(frame, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
    attached = true
    UnityBridge.views.add(this)
    player.onResume()
    player.windowFocusChanged(true)
    frame.requestFocus()
  }

  override fun onDetachedFromWindow() {
    UnityBridge.views.remove(this)
    if (attached) {
      UnityBridge.player?.let { p ->
        p.onPause()
        (p.frameLayout.parent as? ViewGroup)?.removeView(p.frameLayout)
      }
      attached = false
    }
    super.onDetachedFromWindow()
  }

  override fun onWindowFocusChanged(hasWindowFocus: Boolean) {
    super.onWindowFocusChanged(hasWindowFocus)
    if (attached) UnityBridge.player?.windowFocusChanged(hasWindowFocus)
  }

  fun dispatch(message: String) {
    onUnityMessage(mapOf("message" to message))
  }
}
