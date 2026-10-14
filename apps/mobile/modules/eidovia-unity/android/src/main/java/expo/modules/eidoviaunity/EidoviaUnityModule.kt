package expo.modules.eidoviaunity

import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class EidoviaUnityModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("EidoviaUnity")

    Events("onUnityMessage")

    OnCreate { UnityBridge.module = this@EidoviaUnityModule }
    OnDestroy { if (UnityBridge.module === this@EidoviaUnityModule) UnityBridge.module = null }

    /** React Native -> Unity (UnitySendMessage). Queued until Unity reports "ready". */
    Function("postMessage") { gameObject: String, methodName: String, message: String ->
      UnityBridge.post(gameObject, methodName, message)
    }

    Function("isRunning") { UnityBridge.player != null }

    OnActivityEntersForeground { if (UnityBridge.views.isNotEmpty()) UnityBridge.resume() }
    OnActivityEntersBackground { UnityBridge.pause() }

    View(EidoviaUnityView::class) {
      Events("onUnityMessage")
    }
  }

  fun emit(message: String) {
    sendEvent("onUnityMessage", mapOf("message" to message))
  }
}
