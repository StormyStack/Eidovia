/**
 * Expo config plugin: links the exported Unity library into the Android app on `expo prebuild`.
 *
 * Expects the Unity export (Unity: "Eidovia > Export for Mobile App") at
 *   <app>/unity/builds/android   (contains unityLibrary/, settings.gradle, gradle.properties)
 *
 * It adds to the generated android/ project:
 *   settings.gradle      include ':unityLibrary' (+ its sub-libraries, e.g. xrmanifest.androidlib)
 *   build.gradle         Unity's build-tools for every module, Unity's noCompress list for the app,
 *                        compressed .dex files (smaller APK),
 *                        flatDir repository for Unity's .aar files (ARCore etc.)
 *                        (unityLibrary keeps Unity's own NDK; React Native uses the standard NDK)
 *   gradle.properties    Unity's unity.* properties, minSdk 29 (Android 10), the CPU types Unity built
 *                        (ARMv7 + ARM64), libc++ pickFirst,
 *                        legacy native-lib packaging (as Unity's own launcher), more Gradle memory
 *   strings.xml          game_view_content_description (required by Unity 6)
 *   AndroidManifest.xml  usesCleartextTraffic, only with the option { "cleartextHttp": true }
 *                        (needed while the gateway is plain http:// in the LAN)
 */
const fs = require('fs');
const path = require('path');
const {
  AndroidConfig,
  createRunOncePlugin,
  withAndroidManifest,
  withGradleProperties,
  withProjectBuildGradle,
  withSettingsGradle,
  withStringsXml,
} = require('expo/config-plugins');

const pkg = require('../package.json');
const MARK_BEGIN = '// @eidovia-unity begin';
const MARK_END = '// @eidovia-unity end';

function exportDirOf(config, props) {
  const rel = (props && props.exportDir) || 'unity/builds/android';
  return { rel, abs: path.resolve(config._internal?.projectRoot ?? process.cwd(), rel) };
}

function readProperties(file) {
  const out = {};
  if (!fs.existsSync(file)) return out;
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([^#=\s][^=]*?)\s*=\s*(.*)$/);
    if (m) out[m[1]] = m[2];
  }
  return out;
}

function unitySubprojects(exportAbs) {
  const settings = path.join(exportAbs, 'settings.gradle');
  const found = new Set([':unityLibrary']);
  if (fs.existsSync(settings)) {
    const text = fs.readFileSync(settings, 'utf8');
    for (const m of text.matchAll(/['"](:?unityLibrary[^'"]*)['"]/g)) {
      found.add(m[1].startsWith(':') ? m[1] : ':' + m[1]);
    }
  }
  return [...found];
}

function strip(contents) {
  const re = new RegExp(`\\n?${MARK_BEGIN}[\\s\\S]*?${MARK_END}\\n?`, 'g');
  return contents.replace(re, '\n');
}

const withUnitySettings = (config, props) =>
  withSettingsGradle(config, (cfg) => {
    const { rel, abs } = exportDirOf(cfg, props);
    if (!fs.existsSync(path.join(abs, 'unityLibrary'))) {
      console.warn(`[eidovia-unity] Unity export not found at ${abs}. Run "Eidovia > Export for Mobile App" in Unity first.`);
    }
    const kotlin = cfg.modResults.language === 'kt';
    const lines = unitySubprojects(abs).map((p) => {
      const dir = p.slice(1).split(':').join('/');
      return kotlin
        ? `include("${p}")\nproject("${p}").projectDir = File(eidoviaUnityDir, "${dir}")`
        : `include '${p}'\nproject('${p}').projectDir = new File(eidoviaUnityDir, '${dir}')`;
    });
    const header = kotlin
      ? `val eidoviaUnityDir = File(rootDir, "../${rel}")`
      : `def eidoviaUnityDir = new File(rootDir, '../${rel}')`;
    cfg.modResults.contents = `${strip(cfg.modResults.contents)}\n${MARK_BEGIN}\n${header}\n${lines.join('\n')}\n${MARK_END}\n`;
    return cfg;
  });

const UNITY_NO_COMPRESS = ['.unity3d', '.ress', '.resource', '.obb', '.bundle', '.unityexp'];

const withUnityProjectGradle = (config, props) =>
  withProjectBuildGradle(config, (cfg) => {
    const { rel, abs } = exportDirOf(cfg, props);
    if (cfg.modResults.language === 'kt') throw new Error('[eidovia-unity] build.gradle.kts is not supported');
    const unityProps = readProperties(path.join(abs, 'gradle.properties'));
    const buildTools = unityProps['unity.buildToolsVersion'];
    const noCompress = [...UNITY_NO_COMPRESS, ...(unityProps.unityStreamingAssets || '').split(/[,\s]+/).filter(Boolean)];

    let contents = strip(cfg.modResults.contents);
    {
      const rootBlock = [
        MARK_BEGIN,
        // modules that do not pick build-tools get AGP's default; use the version Unity installed instead
        `def eidoviaUnityBuildTools = '${buildTools || ''}'`,
        'subprojects {',
        // React Native's root plugin sets react.newArchEnabled on every subproject; a nested project
        // (:unityLibrary:xrmanifest.androidlib) only inherits it from its parent and cannot be set, so give it its own
        "  if (it.parent != rootProject) { it.ext.set('react.newArchEnabled', 'true') }",
        "  plugins.withId('com.android.library') {",
        '    if (eidoviaUnityBuildTools) android.buildToolsVersion = eidoviaUnityBuildTools',
        '  }',
        "  plugins.withId('com.android.application') {",
        '    if (eidoviaUnityBuildTools) android.buildToolsVersion = eidoviaUnityBuildTools',
        `    android.androidResources.noCompress.addAll(${JSON.stringify(noCompress).replace(/"/g, "'")})`,
        // compress the app's Java/Kotlin code (.dex) inside the APK: about 12 MB smaller download
        '    android.packagingOptions.dex.useLegacyPackaging = true',
        '  }',
        '}',
        MARK_END,
      ].join('\n');
      const anchor = 'apply plugin: "expo-root-project"';
      contents = contents.includes(anchor) ? contents.replace(anchor, `${rootBlock}\n${anchor}`) : `${contents}\n${rootBlock}\n`;
    }
    const repoBlock = `allprojects {\n  repositories {\n    flatDir { dirs "\${rootDir}/../${rel}/unityLibrary/libs" }\n  }\n}`;
    cfg.modResults.contents = `${contents}\n${MARK_BEGIN}\n${repoBlock}\n${MARK_END}\n`;
    return cfg;
  });

const withCleartextHttp = (config, props) =>
  withAndroidManifest(config, (cfg) => {
    if (props && props.cleartextHttp) {
      AndroidConfig.Manifest.getMainApplicationOrThrow(cfg.modResults).$['android:usesCleartextTraffic'] = 'true';
    }
    return cfg;
  });

const withUnityGradleProperties = (config, props) =>
  withGradleProperties(config, (cfg) => {
    const { abs } = exportDirOf(cfg, props);
    const unityProps = readProperties(path.join(abs, 'gradle.properties'));
    const set = (key, value) => {
      const item = cfg.modResults.find((p) => p.type === 'property' && p.key === key);
      if (item) item.value = String(value);
      else cfg.modResults.push({ type: 'property', key, value: String(value) });
    };
    // everything Unity's unityLibrary/build.gradle reads (unity.*, unityStreamingAssets, ...)
    for (const [key, value] of Object.entries(unityProps)) {
      if (key.startsWith('unity') ) set(key, value);
    }
    if (!('unityStreamingAssets' in unityProps)) set('unityStreamingAssets', '');
    const unityMin = parseInt(unityProps['unity.minSdkVersion'] || '29', 10);
    set('android.minSdkVersion', Math.max(29, isNaN(unityMin) ? 29 : unityMin));
    // React Native builds the same CPU types as the Unity export (Eidovia: armeabi-v7a + arm64-v8a)
    const abis = String(unityProps['unity.abiFilters'] || 'arm64-v8a').split(/[\s,;]+/).filter(Boolean);
    set('reactNativeArchitectures', abis.join(','));
    set('android.packagingOptions.pickFirsts', 'lib/**/libc++_shared.so,lib/**/libfbjni.so');
    set('expo.useLegacyPackaging', 'true');                 // Unity's launcher packs native libs the same way
    set('org.gradle.jvmargs', '-Xmx4096m -XX:MaxMetaspaceSize=1024m');
    return cfg;
  });

const withUnityStrings = (config) =>
  withStringsXml(config, (cfg) => {
    cfg.modResults = AndroidConfig.Strings.setStringItem(
      [{ $: { name: 'game_view_content_description', translatable: 'false' }, _: 'Game view' }],
      cfg.modResults
    );
    return cfg;
  });

function withEidoviaUnity(config, props = {}) {
  config = withUnitySettings(config, props);
  config = withUnityProjectGradle(config, props);
  config = withUnityGradleProperties(config, props);
  config = withUnityStrings(config);
  config = withCleartextHttp(config, props);
  return config;
}

module.exports = createRunOncePlugin(withEidoviaUnity, pkg.name, pkg.version);
