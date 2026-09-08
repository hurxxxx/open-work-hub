import {
  ConnectionQualityIndicator,
  ConnectionStateToast,
  ControlBar,
  formatChatMessageLinks,
  GridLayout,
  isTrackReference,
  LiveKitRoom,
  ParticipantName,
  ParticipantTile,
  RoomAudioRenderer,
  TrackMutedIndicator,
  useChat,
  useLocalParticipant,
  useMaybeTrackRefContext,
  useParticipants,
  useTracks,
  VideoTrack,
  type ReceivedChatMessage,
  type TrackReferenceOrPlaceholder,
} from '@livekit/components-react';
import '@livekit/components-styles';
import { MediaDeviceFailure, RoomEvent, Track } from 'livekit-client';
import {
  AlertTriangle,
  ArrowLeft,
  Captions,
  Fullscreen,
  Loader2,
  Maximize2,
  MessageSquare,
  Mic,
  MicOff,
  Minimize2,
  Radio,
  RefreshCw,
  Send,
  Shrink,
  Square,
  Users,
  Video,
  VideoOff,
  X,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { buildAppPath } from '@/src/platform/apps/app-links';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  createVideoChatJoinToken,
  endVideoChatSession,
  startVideoChatCaptions,
  startVideoChatRecording,
  stopVideoChatCaptions,
  stopVideoChatRecording,
  type VideoChatJoinTokenResponse,
  type VideoChatSession,
} from '../api/video-chat-api';

export function VideoChatRoomPage() {
  const { t } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [join, setJoin] = useState<VideoChatJoinTokenResponse | null>(null);
  const [session, setSession] = useState<VideoChatSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deviceWarning, setDeviceWarning] = useState<string | null>(null);
  const [mobilePanel, setMobilePanel] = useState<
    'participants' | 'chat' | null
  >(null);

  const roomsPath = useMemo(() => buildAppPath('video-chat'), []);

  const loadJoinToken = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    setDeviceWarning(null);
    try {
      const response = await createVideoChatJoinToken(token, sessionId);
      setJoin(response);
      setSession(response.session);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : t('apps:videoChat.errors.joinFailed'),
      );
    } finally {
      setLoading(false);
    }
  }, [sessionId, t, token]);

  useEffect(() => {
    void loadJoinToken();
  }, [loadJoinToken]);

  if (!sessionId) {
    return null;
  }

  async function runSessionAction(
    key: string,
    action: () => Promise<VideoChatSession>,
    fallbackMessage: string,
  ) {
    setBusyAction(key);
    setError(null);
    try {
      const nextSession = await action();
      setSession(nextSession);
      if (key === 'end') {
        navigate(roomsPath);
      }
    } catch (actionError) {
      setError(
        actionError instanceof Error ? actionError.message : fallbackMessage,
      );
    } finally {
      setBusyAction(null);
    }
  }

  const activeSession = session ?? join?.session ?? null;
  const recordingActive =
    activeSession?.recording_status === 'recording' ||
    activeSession?.recording_status === 'starting';
  const captionsActive =
    activeSession?.captions_status === 'on' ||
    activeSession?.captions_status === 'starting';
  const canEndRoom =
    Boolean(activeSession?.started_by_id) &&
    activeSession?.started_by_id === user?.id;

  function handleEndRoom() {
    if (!sessionId) return;
    if (!window.confirm(t('apps:videoChat.endRoomConfirm'))) return;

    const roomSessionId = sessionId;
    void runSessionAction(
      'end',
      () => endVideoChatSession(token, roomSessionId),
      t('apps:videoChat.errors.endFailed'),
    );
  }

  function describeMediaDeviceFailure(
    failure: MediaDeviceFailure | undefined,
    kind: MediaDeviceKind | undefined,
  ): string {
    const deviceLabel =
      kind === 'audioinput'
        ? t('apps:videoChat.devices.microphone')
        : kind === 'videoinput'
          ? t('apps:videoChat.devices.camera')
          : t('apps:videoChat.devices.media');
    if (failure === MediaDeviceFailure.DeviceInUse) {
      return t('apps:videoChat.errors.deviceInUse', { device: deviceLabel });
    }
    if (failure === MediaDeviceFailure.PermissionDenied) {
      return t('apps:videoChat.errors.devicePermissionDenied', {
        device: deviceLabel,
      });
    }
    if (failure === MediaDeviceFailure.NotFound) {
      return t('apps:videoChat.errors.deviceNotFound', { device: deviceLabel });
    }
    return t('apps:videoChat.errors.deviceUnavailable', {
      device: deviceLabel,
    });
  }

  function handleControlBarDeviceError(source: Track.Source, error: Error) {
    const kind =
      source === Track.Source.Microphone
        ? 'audioinput'
        : source === Track.Source.Camera
          ? 'videoinput'
          : undefined;
    setDeviceWarning(
      describeMediaDeviceFailure(MediaDeviceFailure.getFailure(error), kind),
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-neutral-950 text-white">
      <header className="flex flex-col gap-3 border-b border-white/10 bg-neutral-950 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => navigate(roomsPath)}
            title={t('apps:videoChat.backToRooms')}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--ui-radius-sm)] border border-white/15 bg-white/8 text-white transition-colors hover:bg-white/14"
          >
            <ArrowLeft size={17} />
          </button>
          <Video size={18} className="text-white/65" />
          <div className="min-w-0">
            <h1 className="truncate app-text-body font-semibold">
              {activeSession?.title ?? t('apps:videoChat.room')}
            </h1>
            <p className="truncate app-text-caption text-white/50">
              {activeSession?.room_name ?? t('apps:videoChat.loading')}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void loadJoinToken()}
            disabled={loading}
            title={t('apps:videoChat.refresh')}
            className="inline-flex h-9 w-9 items-center justify-center rounded-[var(--ui-radius-sm)] border border-white/15 bg-white/8 text-white transition-colors hover:bg-white/14 disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            type="button"
            onClick={() =>
              void runSessionAction(
                'recording',
                () =>
                  recordingActive
                    ? stopVideoChatRecording(token, sessionId)
                    : startVideoChatRecording(token, sessionId),
                t('apps:videoChat.errors.recordingFailed'),
              )
            }
            disabled={busyAction != null}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-[var(--ui-radius-sm)] border border-white/15 bg-white/8 px-3 app-text-body font-medium text-white transition-colors hover:bg-white/14 disabled:opacity-50"
          >
            {busyAction === 'recording' ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Radio size={15} />
            )}
            <span>
              {recordingActive
                ? t('apps:videoChat.stopRecording')
                : t('apps:videoChat.startRecording')}
            </span>
          </button>
          <button
            type="button"
            onClick={() =>
              void runSessionAction(
                'captions',
                () =>
                  captionsActive
                    ? stopVideoChatCaptions(token, sessionId)
                    : startVideoChatCaptions(token, sessionId),
                t('apps:videoChat.errors.captionsFailed'),
              )
            }
            disabled={busyAction != null}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-[var(--ui-radius-sm)] border border-white/15 bg-white/8 px-3 app-text-body font-medium text-white transition-colors hover:bg-white/14 disabled:opacity-50"
          >
            {busyAction === 'captions' ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Captions size={15} />
            )}
            <span>
              {captionsActive
                ? t('apps:videoChat.stopCaptions')
                : t('apps:videoChat.startCaptions')}
            </span>
          </button>
          <button
            type="button"
            onClick={() => navigate(roomsPath)}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-[var(--ui-radius-sm)] border border-app-danger-border bg-app-danger/15 px-3 app-text-body font-semibold text-app-danger-text transition-colors hover:bg-app-danger/25 disabled:opacity-50"
          >
            <X size={15} />
            <span>{t('apps:videoChat.leaveRoom')}</span>
          </button>
          {canEndRoom ? (
            <button
              type="button"
              onClick={handleEndRoom}
              disabled={busyAction != null}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-[var(--ui-radius-sm)] border border-app-danger-border bg-red-600/25 px-3 app-text-body font-semibold text-red-50 transition-colors hover:bg-red-600/35 disabled:opacity-50"
            >
              {busyAction === 'end' ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Square size={15} />
              )}
              <span>{t('apps:videoChat.endRoom')}</span>
            </button>
          ) : null}
        </div>
      </header>

      {error ? (
        <div className="border-b border-app-danger-border bg-app-danger/12 px-4 py-2 app-text-body text-app-danger-text">
          {error}
        </div>
      ) : null}

      {deviceWarning ? (
        <div className="flex items-start gap-2 border-b border-app-warning-border/30 bg-amber-400/12 px-4 py-2 app-text-body text-amber-50">
          <AlertTriangle
            size={16}
            className="mt-0.5 shrink-0 text-app-warning-text"
          />
          <span>{deviceWarning}</span>
        </div>
      ) : null}

      <main className="min-h-0 flex-1">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 size={28} className="animate-spin text-white/45" />
          </div>
        ) : join ? (
          <LiveKitRoom
            audio={false}
            connect
            data-lk-theme="default"
            options={{ adaptiveStream: true, dynacast: true }}
            serverUrl={join.livekit_url}
            token={join.token}
            video={false}
            className="h-full"
            onConnected={() => setDeviceWarning(null)}
            onDisconnected={() => setSession((current) => current)}
            onError={(roomError) => {
              setDeviceWarning(
                t('apps:videoChat.errors.connectionOrDeviceFailed', {
                  message: roomError.message,
                }),
              );
            }}
            onMediaDeviceFailure={(failure, kind) => {
              setDeviceWarning(describeMediaDeviceFailure(failure, kind));
            }}
          >
            <div className="relative flex h-full min-h-0 flex-col xl:flex-row">
              <div className="min-h-0 flex-1">
                <VideoChatConference
                  onDeviceError={handleControlBarDeviceError}
                />
              </div>
              <VideoChatMobileActions onOpenPanel={setMobilePanel} />
              <VideoChatSidePanel className="hidden xl:flex" />
              <VideoChatMobilePanel
                activePanel={mobilePanel}
                onClose={() => setMobilePanel(null)}
                onSelectPanel={setMobilePanel}
              />
            </div>
          </LiveKitRoom>
        ) : (
          <div className="flex h-full items-center justify-center px-6 text-center app-text-body text-white/60">
            {t('apps:videoChat.callUnavailable')}
          </div>
        )}
      </main>
    </div>
  );
}

function VideoChatConference({
  onDeviceError,
}: {
  onDeviceError: (source: Track.Source, error: Error) => void;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [focusedTrackKey, setFocusedTrackKey] = useState<string | null>(null);
  const [fullscreenTrackKey, setFullscreenTrackKey] = useState<string | null>(
    null,
  );
  const [fullscreenSupported, setFullscreenSupported] = useState(false);
  const [isStageFullscreen, setIsStageFullscreen] = useState(false);
  const tracks = useTracks(
    [
      { source: Track.Source.Camera, withPlaceholder: true },
      { source: Track.Source.ScreenShare, withPlaceholder: false },
    ],
    { updateOnlyOn: [RoomEvent.ActiveSpeakersChanged], onlySubscribed: false },
  );
  const normalizedTracks = useMemo(
    () => normalizeVideoChatTracks(tracks),
    [tracks],
  );
  const focusedTrack = useMemo(() => {
    if (!focusedTrackKey) return null;
    return (
      normalizedTracks.find(
        (track) => trackReferenceKey(track) === focusedTrackKey,
      ) ?? null
    );
  }, [focusedTrackKey, normalizedTracks]);
  const thumbnailTracks = useMemo(
    () =>
      focusedTrackKey
        ? normalizedTracks.filter(
            (track) => trackReferenceKey(track) !== focusedTrackKey,
          )
        : [],
    [focusedTrackKey, normalizedTracks],
  );

  useEffect(() => {
    const stage = stageRef.current;
    setFullscreenSupported(
      Boolean(
        document.fullscreenEnabled &&
          stage &&
          typeof stage.requestFullscreen === 'function',
      ),
    );

    function handleFullscreenChange() {
      const active = document.fullscreenElement === stageRef.current;
      setIsStageFullscreen(active);
      if (!active) {
        setFullscreenTrackKey(null);
        setFocusedTrackKey(null);
      }
    }

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    handleFullscreenChange();
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);

  const exitStageFullscreen = useCallback(async () => {
    if (document.fullscreenElement === stageRef.current) {
      await document.exitFullscreen();
    }
    setFullscreenTrackKey(null);
    setFocusedTrackKey(null);
  }, []);

  const handleFocusChange = useCallback(
    (trackKey: string | null) => {
      setFocusedTrackKey(trackKey);
      if (trackKey && isStageFullscreen) {
        setFullscreenTrackKey(trackKey);
      }
      if (!trackKey) {
        void exitStageFullscreen();
      }
    },
    [exitStageFullscreen, isStageFullscreen],
  );

  const requestStageFullscreen = useCallback(async (trackKey: string) => {
    const stage = stageRef.current;
    setFocusedTrackKey(trackKey);
    setFullscreenTrackKey(trackKey);
    if (!stage || !document.fullscreenEnabled) return;

    if (document.fullscreenElement !== stage) {
      try {
        await stage.requestFullscreen({ navigationUI: 'hide' });
      } catch {
        setFullscreenTrackKey(null);
      }
    }
  }, []);

  useEffect(() => {
    if (
      focusedTrackKey &&
      !normalizedTracks.some(
        (track) => trackReferenceKey(track) === focusedTrackKey,
      )
    ) {
      setFocusedTrackKey(null);
    }
    if (
      fullscreenTrackKey &&
      !normalizedTracks.some(
        (track) => trackReferenceKey(track) === fullscreenTrackKey,
      )
    ) {
      setFullscreenTrackKey(null);
    }
  }, [focusedTrackKey, fullscreenTrackKey, normalizedTracks]);

  return (
    <div className="lk-video-conference h-full">
      <div className="lk-video-conference-inner">
        <div
          ref={stageRef}
          className="lk-grid-layout-wrapper min-w-0 bg-neutral-950 [&:fullscreen]:h-screen [&:fullscreen]:w-screen"
        >
          {focusedTrack ? (
            <VideoChatFocusLayout
              focusedTrack={focusedTrack}
              thumbnailTracks={thumbnailTracks}
              focusedTrackKey={focusedTrackKey}
              fullscreenSupported={fullscreenSupported}
              fullscreenTrackKey={fullscreenTrackKey}
              isStageFullscreen={isStageFullscreen}
              onFocusChange={handleFocusChange}
              onDeviceError={onDeviceError}
              onExitFullscreen={exitStageFullscreen}
              onRequestFullscreen={requestStageFullscreen}
            />
          ) : (
            <GridLayout tracks={normalizedTracks}>
              <VideoChatParticipantTile
                focusedTrackKey={focusedTrackKey}
                fullscreenSupported={fullscreenSupported}
                fullscreenTrackKey={fullscreenTrackKey}
                isStageFullscreen={isStageFullscreen}
                onFocusChange={handleFocusChange}
                onDeviceError={onDeviceError}
                onExitFullscreen={exitStageFullscreen}
                onRequestFullscreen={requestStageFullscreen}
              />
            </GridLayout>
          )}
        </div>
        <ControlBar
          controls={{ chat: false }}
          saveUserChoices={false}
          onDeviceError={({ source, error }) => onDeviceError(source, error)}
        />
      </div>
      <RoomAudioRenderer />
      <ConnectionStateToast />
    </div>
  );
}

function VideoChatFocusLayout({
  focusedTrack,
  thumbnailTracks,
  focusedTrackKey,
  fullscreenSupported,
  fullscreenTrackKey,
  isStageFullscreen,
  onFocusChange,
  onDeviceError,
  onExitFullscreen,
  onRequestFullscreen,
}: {
  focusedTrack: TrackReferenceOrPlaceholder;
  thumbnailTracks: TrackReferenceOrPlaceholder[];
  focusedTrackKey: string | null;
  fullscreenSupported: boolean;
  fullscreenTrackKey: string | null;
  isStageFullscreen: boolean;
  onFocusChange: (trackKey: string | null) => void;
  onDeviceError: (source: Track.Source, error: Error) => void;
  onExitFullscreen: () => Promise<void>;
  onRequestFullscreen: (trackKey: string) => Promise<void>;
}) {
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col bg-neutral-950">
      <div
        className={`min-h-0 w-full min-w-0 flex-1 ${
          isStageFullscreen ? 'p-0' : 'p-2 pb-1 md:p-4 md:pb-3'
        }`}
      >
        <VideoChatParticipantTile
          trackRef={focusedTrack}
          focusedTrackKey={focusedTrackKey}
          fullscreenSupported={fullscreenSupported}
          fullscreenTrackKey={fullscreenTrackKey}
          isStageFullscreen={isStageFullscreen}
          onFocusChange={onFocusChange}
          onDeviceError={onDeviceError}
          onExitFullscreen={onExitFullscreen}
          onRequestFullscreen={onRequestFullscreen}
          variant="focus"
        />
      </div>
      {!isStageFullscreen && thumbnailTracks.length > 0 ? (
        <div className="w-full min-w-0 shrink-0 border-t border-white/10 bg-black/20">
          <div className="flex h-24 w-full min-w-0 gap-2 overflow-x-auto px-2 py-2 md:h-32 md:px-4">
            {thumbnailTracks.map((track) => (
              <VideoChatParticipantTile
                key={trackReferenceKey(track)}
                trackRef={track}
                focusedTrackKey={focusedTrackKey}
                fullscreenSupported={fullscreenSupported}
                fullscreenTrackKey={fullscreenTrackKey}
                isStageFullscreen={isStageFullscreen}
                onFocusChange={onFocusChange}
                onDeviceError={onDeviceError}
                onExitFullscreen={onExitFullscreen}
                onRequestFullscreen={onRequestFullscreen}
                variant="thumbnail"
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function normalizeVideoChatTracks(
  tracks: TrackReferenceOrPlaceholder[],
): TrackReferenceOrPlaceholder[] {
  const cameraTracksByParticipant = new Map<
    string,
    TrackReferenceOrPlaceholder
  >();
  const screenShareTracks: TrackReferenceOrPlaceholder[] = [];

  for (const track of tracks) {
    if (track.source === Track.Source.ScreenShare) {
      if (trackHasLiveMedia(track)) {
        screenShareTracks.push(track);
      }
      continue;
    }

    if (track.source !== Track.Source.Camera) {
      continue;
    }

    const participantKey =
      track.participant.sid || track.participant.identity || 'participant';
    const current = cameraTracksByParticipant.get(participantKey);
    cameraTracksByParticipant.set(
      participantKey,
      current ? pickPreferredCameraTrack(current, track) : track,
    );
  }

  return [...cameraTracksByParticipant.values(), ...screenShareTracks];
}

function trackHasLiveMedia(track: TrackReferenceOrPlaceholder): boolean {
  return isTrackReference(track) && Boolean(track.publication.track);
}

function pickPreferredCameraTrack(
  current: TrackReferenceOrPlaceholder,
  candidate: TrackReferenceOrPlaceholder,
): TrackReferenceOrPlaceholder {
  if (trackHasLiveMedia(candidate)) return candidate;
  if (trackHasLiveMedia(current)) return current;
  if (!isTrackReference(candidate) && isTrackReference(current))
    return candidate;
  return current;
}

function trackReferenceKey(trackRef: TrackReferenceOrPlaceholder): string {
  const participantKey =
    trackRef.participant.sid || trackRef.participant.identity || 'participant';
  return `${participantKey}:${trackRef.source}`;
}

function toError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value));
}

function VideoChatParticipantTile({
  trackRef: explicitTrackRef,
  focusedTrackKey,
  fullscreenSupported = false,
  fullscreenTrackKey,
  isStageFullscreen = false,
  onFocusChange,
  onDeviceError,
  onExitFullscreen,
  onRequestFullscreen,
  variant = 'grid',
}: {
  trackRef?: TrackReferenceOrPlaceholder;
  focusedTrackKey: string | null;
  fullscreenSupported?: boolean;
  fullscreenTrackKey?: string | null;
  isStageFullscreen?: boolean;
  onFocusChange: (trackKey: string | null) => void;
  onDeviceError: (source: Track.Source, error: Error) => void;
  onExitFullscreen?: () => Promise<void>;
  onRequestFullscreen?: (trackKey: string) => Promise<void>;
  variant?: 'grid' | 'focus' | 'thumbnail';
}) {
  const { t } = useTranslation(['apps']);
  const contextTrackRef = useMaybeTrackRefContext();
  const trackRef = explicitTrackRef ?? contextTrackRef;
  const { isCameraEnabled, isMicrophoneEnabled, localParticipant } =
    useLocalParticipant();
  const [pendingDevice, setPendingDevice] = useState<
    'camera' | 'microphone' | null
  >(null);

  if (!trackRef) {
    return <ParticipantTile />;
  }

  const trackKey = trackReferenceKey(trackRef);
  const isFocused = focusedTrackKey === trackKey;
  const isLocalCamera =
    trackRef.source === Track.Source.Camera &&
    (trackRef.participant.sid === localParticipant.sid ||
      trackRef.participant.identity === localParticipant.identity);
  const isThumbnail = variant === 'thumbnail';
  const isFullscreen = isStageFullscreen && fullscreenTrackKey === trackKey;
  const showLocalControls = isLocalCamera && !isThumbnail;
  const tileClassName = isThumbnail
    ? 'group h-full min-w-40 flex-[0_0_10rem] cursor-pointer overflow-hidden rounded-[var(--ui-radius-sm)] bg-neutral-900'
    : 'group h-full min-h-0 w-full min-w-0 bg-neutral-950';

  async function toggleMicrophone() {
    setPendingDevice('microphone');
    try {
      await localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });
    } catch (error) {
      onDeviceError(Track.Source.Microphone, toError(error));
    } finally {
      setPendingDevice(null);
    }
  }

  async function toggleCamera() {
    setPendingDevice('camera');
    try {
      await localParticipant.setCameraEnabled(!isCameraEnabled);
    } catch (error) {
      onDeviceError(Track.Source.Camera, toError(error));
    } finally {
      setPendingDevice(null);
    }
  }

  function handleThumbnailKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onFocusChange(trackKey);
  }

  return (
    <ParticipantTile
      trackRef={trackRef}
      className={tileClassName}
      onClick={isThumbnail ? () => onFocusChange(trackKey) : undefined}
      onKeyDown={isThumbnail ? handleThumbnailKeyDown : undefined}
      role={isThumbnail ? 'button' : undefined}
      tabIndex={isThumbnail ? 0 : undefined}
      title={isThumbnail ? t('apps:videoChat.expandParticipant') : undefined}
    >
      {isTrackReference(trackRef) &&
      (trackRef.publication?.kind === 'video' ||
        trackRef.source === Track.Source.Camera ||
        trackRef.source === Track.Source.ScreenShare) ? (
        <VideoTrack trackRef={trackRef} />
      ) : null}
      <div className="lk-participant-placeholder">
        <Users
          aria-hidden="true"
          className={`h-full w-auto text-white/28 ${
            isThumbnail ? 'p-[18%]' : 'p-[14%]'
          }`}
          strokeWidth={1.35}
        />
      </div>
      <div
        className={`lk-participant-metadata ${isThumbnail ? 'app-text-caption' : ''}`}
      >
        <div className="lk-participant-metadata-item min-w-0">
          <TrackMutedIndicator
            trackRef={{
              participant: trackRef.participant,
              source: Track.Source.Microphone,
            }}
            show="muted"
          />
          <ParticipantName className="min-w-0 truncate" />
        </div>
        <ConnectionQualityIndicator className="lk-participant-metadata-item" />
      </div>
      {showLocalControls ? (
        <div className="absolute left-3 top-3 z-20 flex gap-2">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              void toggleMicrophone();
            }}
            disabled={pendingDevice != null}
            aria-pressed={!isMicrophoneEnabled}
            title={
              isMicrophoneEnabled
                ? t('apps:videoChat.muteMicrophone')
                : t('apps:videoChat.unmuteMicrophone')
            }
            className={`inline-flex h-10 w-10 items-center justify-center rounded-[var(--ui-radius-sm)] border text-white shadow-lg backdrop-blur transition-colors disabled:opacity-55 ${
              isMicrophoneEnabled
                ? 'border-white/20 bg-black/55 hover:bg-black/70'
                : 'border-app-danger-border/50 bg-app-danger/90 hover:bg-app-danger'
            }`}
          >
            {pendingDevice === 'microphone' ? (
              <Loader2 size={17} className="animate-spin" />
            ) : isMicrophoneEnabled ? (
              <Mic size={17} />
            ) : (
              <MicOff size={17} />
            )}
          </button>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              void toggleCamera();
            }}
            disabled={pendingDevice != null}
            aria-pressed={!isCameraEnabled}
            title={
              isCameraEnabled
                ? t('apps:videoChat.turnCameraOff')
                : t('apps:videoChat.turnCameraOn')
            }
            className={`inline-flex h-10 w-10 items-center justify-center rounded-[var(--ui-radius-sm)] border text-white shadow-lg backdrop-blur transition-colors disabled:opacity-55 ${
              isCameraEnabled
                ? 'border-white/20 bg-black/55 hover:bg-black/70'
                : 'border-app-danger-border/50 bg-app-danger/90 hover:bg-app-danger'
            }`}
          >
            {pendingDevice === 'camera' ? (
              <Loader2 size={17} className="animate-spin" />
            ) : isCameraEnabled ? (
              <Video size={17} />
            ) : (
              <VideoOff size={17} />
            )}
          </button>
        </div>
      ) : null}
      {!isThumbnail ? (
        <div className="absolute right-3 top-3 z-20 flex gap-2 opacity-100 md:opacity-0 md:group-hover:opacity-100">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              if (isFocused) {
                void onExitFullscreen?.();
              }
              onFocusChange(isFocused ? null : trackKey);
            }}
            title={
              isFocused
                ? t('apps:videoChat.collapseParticipant')
                : t('apps:videoChat.expandParticipant')
            }
            className="inline-flex h-10 w-10 items-center justify-center rounded-[var(--ui-radius-sm)] border border-white/20 bg-black/55 text-white shadow-lg backdrop-blur transition-colors hover:bg-black/70"
          >
            {isFocused ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
          </button>
          {fullscreenSupported && onRequestFullscreen && onExitFullscreen ? (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                void (isFullscreen
                  ? onExitFullscreen()
                  : onRequestFullscreen(trackKey));
              }}
              aria-pressed={isFullscreen}
              title={
                isFullscreen
                  ? t('apps:videoChat.exitFullscreen')
                  : t('apps:videoChat.enterFullscreen')
              }
              className="inline-flex h-10 w-10 items-center justify-center rounded-[var(--ui-radius-sm)] border border-white/20 bg-black/55 text-white shadow-lg backdrop-blur transition-colors hover:bg-black/70"
            >
              {isFullscreen ? <Shrink size={17} /> : <Fullscreen size={17} />}
            </button>
          ) : null}
        </div>
      ) : null}
    </ParticipantTile>
  );
}

function VideoChatSidePanel({ className = 'flex' }: { className?: string }) {
  return (
    <aside
      className={`${className} h-80 shrink-0 flex-col border-t border-white/10 bg-neutral-900 xl:h-full xl:w-80 xl:border-l xl:border-t-0`}
    >
      <VideoChatParticipantList />
      <VideoChatRealtimeChat />
    </aside>
  );
}

function VideoChatMobileActions({
  onOpenPanel,
}: {
  onOpenPanel: (panel: 'participants' | 'chat') => void;
}) {
  const { t } = useTranslation(['apps']);
  const participants = useParticipants();

  return (
    <div className="absolute bottom-24 right-3 z-20 flex flex-col gap-2 xl:hidden">
      <button
        type="button"
        onClick={() => onOpenPanel('participants')}
        title={t('apps:videoChat.openParticipantsPanel')}
        className="inline-flex h-11 min-w-11 items-center justify-center gap-1 rounded-[var(--ui-radius-sm)] border border-white/20 bg-black/60 px-3 app-text-body font-semibold text-white shadow-lg backdrop-blur transition-colors hover:bg-black/75"
      >
        <Users size={17} />
        <span>{participants.length}</span>
      </button>
      <button
        type="button"
        onClick={() => onOpenPanel('chat')}
        title={t('apps:videoChat.openChatPanel')}
        className="inline-flex h-11 w-11 items-center justify-center rounded-[var(--ui-radius-sm)] border border-white/20 bg-black/60 text-white shadow-lg backdrop-blur transition-colors hover:bg-black/75"
      >
        <MessageSquare size={17} />
      </button>
    </div>
  );
}

function VideoChatMobilePanel({
  activePanel,
  onClose,
  onSelectPanel,
}: {
  activePanel: 'participants' | 'chat' | null;
  onClose: () => void;
  onSelectPanel: (panel: 'participants' | 'chat') => void;
}) {
  const { t } = useTranslation(['apps']);

  if (!activePanel) return null;

  return (
    <div
      className="absolute inset-0 z-40 flex items-end bg-black/60 px-2 pb-2 pt-16 xl:hidden"
      onClick={onClose}
    >
      <section
        className="flex h-[78%] max-h-[560px] min-h-0 w-full flex-col overflow-hidden rounded-[var(--ui-radius-md)] border border-white/15 bg-neutral-900 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-white/10 p-2">
          <button
            type="button"
            onClick={() => onSelectPanel('participants')}
            className={`inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-[var(--ui-radius-sm)] px-3 app-text-body font-semibold transition-colors ${
              activePanel === 'participants'
                ? 'bg-white text-neutral-950'
                : 'bg-white/8 text-white hover:bg-white/14'
            }`}
          >
            <Users size={15} />
            <span>{t('apps:videoChat.participants')}</span>
          </button>
          <button
            type="button"
            onClick={() => onSelectPanel('chat')}
            className={`inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-[var(--ui-radius-sm)] px-3 app-text-body font-semibold transition-colors ${
              activePanel === 'chat'
                ? 'bg-white text-neutral-950'
                : 'bg-white/8 text-white hover:bg-white/14'
            }`}
          >
            <MessageSquare size={15} />
            <span>{t('apps:videoChat.chat')}</span>
          </button>
          <button
            type="button"
            onClick={onClose}
            title={t('apps:videoChat.closePanel')}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--ui-radius-sm)] bg-white/8 text-white transition-colors hover:bg-white/14"
          >
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1">
          {activePanel === 'participants' ? (
            <VideoChatParticipantList
              className="flex h-full min-h-0 flex-col p-3"
              listClassName="min-h-0 flex-1 space-y-1 overflow-y-auto"
            />
          ) : (
            <VideoChatRealtimeChat showHeader={false} />
          )}
        </div>
      </section>
    </div>
  );
}

function VideoChatParticipantList({
  className = 'border-b border-white/10 p-3',
  listClassName = 'max-h-28 space-y-1 overflow-y-auto xl:max-h-44',
}: {
  className?: string;
  listClassName?: string;
}) {
  const { t } = useTranslation(['apps']);
  const participants = useParticipants();

  return (
    <section className={className}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex min-w-0 items-center gap-2 app-text-body font-semibold text-white">
          <Users size={16} className="shrink-0 text-white/60" />
          <span className="truncate">{t('apps:videoChat.participants')}</span>
        </h2>
        <span className="rounded-[var(--ui-radius-sm)] bg-white/10 px-2 py-0.5 app-text-caption text-white/70">
          {participants.length}
        </span>
      </div>
      {participants.length === 0 ? (
        <p className="app-text-caption text-white/45">
          {t('apps:videoChat.participantsEmpty')}
        </p>
      ) : (
        <ul className={listClassName}>
          {participants.map((participant) => {
            const name =
              participant.name ||
              participant.identity ||
              t('apps:videoChat.unknownParticipant');
            return (
              <li
                key={participant.sid || participant.identity}
                className="flex min-h-8 items-center gap-2 rounded-[var(--ui-radius-sm)] px-2 py-1 app-text-body text-white/85"
              >
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    participant.isSpeaking ? 'bg-emerald-300' : 'bg-white/25'
                  }`}
                />
                <span className="min-w-0 flex-1 truncate">
                  {name}
                  {participant.isLocal ? (
                    <span className="ml-1 app-text-caption text-white/45">
                      {t('apps:videoChat.you')}
                    </span>
                  ) : null}
                </span>
                <span className="flex shrink-0 items-center gap-1 text-white/55">
                  {participant.isMicrophoneEnabled ? (
                    <Mic
                      size={14}
                      aria-label={t('apps:videoChat.microphoneOn')}
                    />
                  ) : (
                    <MicOff
                      size={14}
                      aria-label={t('apps:videoChat.microphoneOff')}
                    />
                  )}
                  {participant.isCameraEnabled ? (
                    <Video
                      size={14}
                      aria-label={t('apps:videoChat.cameraOn')}
                    />
                  ) : (
                    <VideoOff
                      size={14}
                      aria-label={t('apps:videoChat.cameraOff')}
                    />
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function VideoChatRealtimeChat({
  showHeader = true,
}: {
  showHeader?: boolean;
}) {
  const { t } = useTranslation(['apps']);
  const { chatMessages, send, isSending } = useChat();
  const [message, setMessage] = useState('');
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [chatMessages]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed || isSending) return;
    await send(trimmed);
    setMessage('');
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      {showHeader ? (
        <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
          <MessageSquare size={16} className="text-white/60" />
          <h2 className="min-w-0 truncate app-text-body font-semibold text-white">
            {t('apps:videoChat.chat')}
          </h2>
        </div>
      ) : null}
      <div
        ref={listRef}
        className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-3"
      >
        {chatMessages.length === 0 ? (
          <p className="pt-3 text-center app-text-caption text-white/45">
            {t('apps:videoChat.chatEmpty')}
          </p>
        ) : (
          chatMessages.map((entry, index) => (
            <VideoChatMessage
              key={entry.id ?? `${entry.timestamp}-${index}`}
              entry={entry}
            />
          ))
        )}
      </div>
      <form
        className="flex gap-2 border-t border-white/10 p-3"
        onSubmit={handleSubmit}
      >
        <input
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onInput={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
          onKeyUp={(event) => event.stopPropagation()}
          placeholder={t('apps:videoChat.chatPlaceholder')}
          className="min-w-0 flex-1 rounded-[var(--ui-radius-sm)] border border-white/15 bg-white/8 px-3 py-2 app-text-body text-white outline-none placeholder:text-white/35 focus:border-white/35"
          disabled={isSending}
        />
        <button
          type="submit"
          disabled={isSending || message.trim().length === 0}
          title={t('apps:videoChat.sendMessage')}
          className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--ui-radius-sm)] bg-white text-neutral-950 transition-colors hover:bg-white/85 disabled:opacity-45"
        >
          <Send size={16} />
        </button>
      </form>
    </section>
  );
}

function VideoChatMessage({ entry }: { entry: ReceivedChatMessage }) {
  const { t } = useTranslation(['apps']);
  const isLocal = Boolean(entry.from?.isLocal);
  const senderName =
    entry.from?.name ||
    entry.from?.identity ||
    t('apps:videoChat.unknownParticipant');

  return (
    <div className={`flex ${isLocal ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[82%] ${isLocal ? 'items-end' : 'items-start'} flex flex-col gap-1`}
      >
        {!isLocal ? (
          <span className="max-w-full truncate app-text-caption text-white/45">
            {senderName}
          </span>
        ) : null}
        <div
          className={`rounded-[var(--ui-radius-md)] px-3 py-2 app-text-body leading-relaxed ${
            isLocal ? 'bg-white text-neutral-950' : 'bg-white/10 text-white'
          }`}
        >
          <span className="break-words">
            {formatChatMessageLinks(entry.message)}
          </span>
        </div>
        <UserDateTime
          className="text-[12px] text-white/35"
          display="time"
          value={entry.timestamp}
        />
      </div>
    </div>
  );
}
