import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Alert, FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Banner } from '../components/Banner';
import { ModuleCard } from '../components/ModuleCard';
import { LoadingState, MessageState } from '../components/StateView';
import type { ScreenProps } from '../navigation/types';
import { Api, ApiError, toApiError } from '../services/ApiClient';
import type { ModuleSummary } from '../services/types';
import { useAuthStore } from '../store/authStore';
import { layout, palette, spacing, typography } from '../theme';

type LoadMode = 'initial' | 'refresh' | 'retry';

/** 401s are handled globally (authStore signs out → Login), and cancels are intentional. */
const isSilent = (error: ApiError) => error.code === 'CANCELLED' || error.status === 401;

export function HomeScreen({ navigation }: ScreenProps<'Home'>) {
  const username = useAuthStore((s) => s.profile?.username);
  const logout = useAuthStore((s) => s.logout);
  const insets = useSafeAreaInsets();

  const [modules, setModules] = useState<ModuleSummary[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const listRequest = useRef<AbortController | null>(null);
  const openRequest = useRef<AbortController | null>(null);
  const hasData = useRef(false);

  // ── Logout (header button) ──
  const confirmLogout = useCallback(() => {
    Alert.alert('Log out?', 'You will need to log in again to continue.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Log out', style: 'destructive', onPress: () => void logout() },
    ]);
  }, [logout]);

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <Pressable
          onPress={confirmLogout}
          accessibilityRole="button"
          accessibilityLabel="Log out"
          hitSlop={10}
          style={styles.headerButton}
          testID="logout-button"
        >
          <Ionicons name="log-out-outline" size={22} color={palette.primary} />
          <Text style={styles.headerButtonText}>Log out</Text>
        </Pressable>
      ),
    });
  }, [navigation, confirmLogout]);

  // ── Module list ──
  const load = useCallback(async (mode: LoadMode) => {
    listRequest.current?.abort();
    const controller = new AbortController();
    listRequest.current = controller;

    if (mode === 'refresh') setRefreshing(true);
    else setStatus('loading');
    setLoadError(null);

    try {
      const list = await Api.getModules(controller.signal);
      if (controller.signal.aborted) return;
      hasData.current = true;
      setModules(list);
      setStatus('ready');
    } catch (error) {
      const apiError = toApiError(error);
      if (controller.signal.aborted || isSilent(apiError)) return;
      setLoadError(apiError);
      // A failed pull-to-refresh keeps the list already on screen
      setStatus(hasData.current ? 'ready' : 'error');
    } finally {
      if (listRequest.current === controller) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load('initial');
    return () => {
      listRequest.current?.abort();
      openRequest.current?.abort();
    };
  }, [load]);

  // ── Open a module: fetch its config, then go to ARGame ──
  const openModule = useCallback(
    async (module: ModuleSummary) => {
      if (openingId) return;
      setOpeningId(module.module_id);
      setActionError(null);
      const controller = new AbortController();
      openRequest.current = controller;
      try {
        const config = await Api.getModuleConfig(module.module_id, controller.signal);
        if (controller.signal.aborted) return;
        navigation.navigate('ARGame', { config, title: module.title });
      } catch (error) {
        const apiError = toApiError(error);
        if (controller.signal.aborted || isSilent(apiError)) return;
        setActionError(
          apiError.code === 'MODULE_NOT_FOUND'
            ? 'This module is no longer available. Pull down to refresh the list.'
            : apiError.message,
        );
      } finally {
        if (openRequest.current === controller) setOpeningId(null);
      }
    },
    [navigation, openingId],
  );

  const greeting = username ? `Hi, ${username}!` : 'Hi there!';

  const header = (
    <View>
      <Text style={styles.greeting} testID="home-greeting" accessibilityRole="header">
        {greeting}
      </Text>
      <Text style={styles.subtitle}>Choose a module to start learning in AR.</Text>
      {actionError ? <Banner tone="error" message={actionError} onDismiss={() => setActionError(null)} testID="home-action-error" /> : null}
      {status === 'ready' && loadError ? (
        <Banner tone="error" message={`Couldn't refresh: ${loadError.message}`} onDismiss={() => setLoadError(null)} testID="home-refresh-error" />
      ) : null}
      {status === 'ready' && modules.length > 0 ? (
        <Text style={styles.sectionLabel}>
          {modules.length} {modules.length === 1 ? 'module' : 'modules'}
        </Text>
      ) : null}
    </View>
  );

  const empty =
    status === 'loading' ? (
      <LoadingState message="Loading modules…" testID="home-loading" />
    ) : status === 'error' && loadError ? (
      <MessageState
        tone="error"
        icon={loadError.code === 'NETWORK_ERROR' || loadError.code === 'TIMEOUT' ? 'cloud-offline-outline' : 'alert-circle-outline'}
        title="Couldn't load modules"
        message={loadError.message}
        actionLabel="Try again"
        onAction={() => void load('retry')}
        testID="home-error"
      />
    ) : (
      <MessageState
        icon="cube-outline"
        title="No modules yet"
        message="There are no AR modules to show right now. Pull down to check again."
        testID="home-empty"
      />
    );

  return (
    <View style={styles.screen}>
      <FlatList
        testID="home-list"
        style={styles.list}
        contentContainerStyle={[styles.content, { paddingBottom: spacing.xl + insets.bottom }]}
        data={status === 'ready' ? modules : []}
        keyExtractor={(item) => item.module_id}
        renderItem={({ item }) => (
          <ModuleCard
            module={item}
            onPress={openModule}
            busy={openingId === item.module_id}
            disabled={openingId !== null && openingId !== item.module_id}
          />
        )}
        ListHeaderComponent={header}
        ListEmptyComponent={empty}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load('refresh')}
            colors={[palette.primary]}
            tintColor={palette.primary}
          />
        }
      />

      {/* Floating chat button */}
      <Pressable
        onPress={() => navigation.navigate('Chat', {})}
        accessibilityRole="button"
        accessibilityLabel="Open AI Tutor chat"
        hitSlop={8}
        testID="chat-fab"
        style={({ pressed }) => [
          styles.chatFab,
          { bottom: spacing.xl + insets.bottom },
          pressed && styles.chatFabPressed,
        ]}
      >
        <Ionicons name="chatbubble-ellipses" size={26} color={palette.onPrimary} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.background },
  list: { flex: 1, backgroundColor: palette.background },
  content: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xl,
    width: '100%',
    maxWidth: layout.maxContentWidth,
    alignSelf: 'center',
    flexGrow: 1,
  },
  greeting: { ...typography.display },
  subtitle: { ...typography.bodyMuted, marginTop: spacing.xs, marginBottom: spacing.xl },
  sectionLabel: { ...typography.caption, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: spacing.sm },
  headerButton: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, paddingVertical: spacing.xs },
  headerButtonText: { ...typography.label, color: palette.primary },
  // Floating chat action button
  chatFab: {
    position: 'absolute',
    right: spacing.xl,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: palette.primary,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#0F172A',
    shadowOpacity: 0.18,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  chatFabPressed: { backgroundColor: palette.primaryPressed },
});
