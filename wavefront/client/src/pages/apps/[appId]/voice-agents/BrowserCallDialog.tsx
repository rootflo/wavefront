import floConsoleService from '@app/api';
import { Alert, AlertDescription, AlertTitle } from '@app/components/ui/alert';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Switch } from '@app/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { appEnv } from '@app/config/env';
import { useGetVoiceAgents } from '@app/hooks';
import { TOKEN_KEY } from '@app/lib/constants';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { CreateVoiceAgentRoomRequest, VoiceAgent, VoiceAgentRoom, VoiceAgentRoomAgent } from '@app/types/voice-agent';
import { PipecatClient } from '@pipecat-ai/client-js';
import { SmallWebRTCTransport } from '@pipecat-ai/small-webrtc-transport';
import { AlertTriangle, ArrowRightLeft, Mic, MicOff, PhoneOff } from 'lucide-react';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AgentSwitchError,
  BrowserCallError,
  classifyBrowserCallError,
  describeAgentSwitchError,
  describeBrowserCallError,
  parseAgentSwitchMessage,
} from './browser-call-errors';

type CallStatus = 'idle' | 'connecting' | 'connected' | 'ended' | 'error';

// The server gives up on a join that never completes after 60s; surface the failure a little sooner.
const CONNECT_TIMEOUT_MS = 45_000;
// The server aborts a swap after 15s; give up waiting a little later.
const SWITCH_TIMEOUT_MS = 20_000;
const ICE_SERVERS: RTCIceServer[] = [{ urls: 'stun:stun.l.google.com:19302' }];

interface BrowserCallDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  agent: VoiceAgent;
  appId: string;
  /** When true, render panel content only (parent owns the Dialog shell). */
  embedded?: boolean;
  /** Disable Connect / Hang up until agent detail has loaded. */
  actionsDisabled?: boolean;
}

/**
 * Where the browser should POST its SDP offer. When floware proxies signaling the URL is relative to the
 * console gateway and needs the user's bearer token; otherwise it is the public call_processing URL and the
 * one-time join token is the credential.
 */
const buildSignalingRequest = (room: VoiceAgentRoom, appId: string) => {
  const base = room.signaling_url.replace(/\/+$/, '');
  const viaFloware = !!room.signaling_via_floware;
  const endpoint = viaFloware ? `${appEnv.baseURL}/v1/${appId}${base}/offer` : `${base}/offer`;
  const headers = new Headers();
  if (viaFloware) {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) headers.set('Authorization', `Bearer ${token}`);
  }
  return {
    endpoint,
    headers,
    requestData: {
      room_id: room.room_id,
      voice_agent_id: room.voice_agent_id,
      join_token: room.join_token,
    },
  };
};

const withTimeout = <T,>(promise: Promise<T>, ms: number): Promise<T> =>
  new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Timed out waiting for the voice connection')), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      }
    );
  });

const BrowserCallDialog: React.FC<BrowserCallDialogProps> = ({
  isOpen,
  onOpenChange,
  agent,
  appId,
  embedded = false,
  actionsDisabled = false,
}) => {
  const { notifyError } = useNotifyStore();
  const { data: allAgents = [] } = useGetVoiceAgents(appId);
  const [status, setStatus] = useState<CallStatus>('idle');
  const [error, setError] = useState<BrowserCallError | null>(null);
  const [micEnabled, setMicEnabled] = useState(true);
  // Room create options (sent with POST /rooms)
  const [carryHistoryOnSwap, setCarryHistoryOnSwap] = useState(true);
  const [roomContextHandlesLanguage, setRoomContextHandlesLanguage] = useState(false);
  const [limitHotSwapAgents, setLimitHotSwapAgents] = useState(false);
  const [allowedAgentIds, setAllowedAgentIds] = useState<string[]>([]);
  // Agent hot-swap: the room's allowlist (initial agent first), who is talking now, and swap progress.
  const [roomAgents, setRoomAgents] = useState<VoiceAgentRoomAgent[]>([]);
  const [activeAgentId, setActiveAgentId] = useState<string>(agent.id);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [switchingToId, setSwitchingToId] = useState<string | null>(null);
  const [switchError, setSwitchError] = useState<AgentSwitchError | null>(null);

  const otherActiveAgents = useMemo(
    () => allAgents.filter((a) => a.id !== agent.id && a.status === 'active' && !a.is_deleted),
    [allAgents, agent.id]
  );

  const clientRef = useRef<PipecatClient | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // Bumped on every start/teardown so late results from an abandoned attempt are ignored.
  const attemptRef = useRef(0);
  // True only while a call is established, so late transport events can't clobber connecting/error states.
  const liveRef = useRef(false);
  const switchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearSwitchTimer = () => {
    if (switchTimerRef.current) clearTimeout(switchTimerRef.current);
    switchTimerRef.current = null;
  };

  const resetSwitchState = () => {
    clearSwitchTimer();
    setSwitchingToId(null);
    setSwitchError(null);
    setSelectedAgentId('');
  };

  const showSwitchError = (switchErr: AgentSwitchError) => {
    clearSwitchTimer();
    setSwitchingToId(null);
    setSwitchError(switchErr);
    notifyError(switchErr.title);
  };

  const handleServerMessage = (attempt: number, data: unknown) => {
    if (attempt !== attemptRef.current) return;
    const message = parseAgentSwitchMessage(data);
    if (!message) return;
    switch (message.type) {
      case 'agent_switching':
        setSwitchError(null);
        setSwitchingToId(message.agent_id);
        break;
      case 'agent_changed':
        clearSwitchTimer();
        setActiveAgentId(message.agent_id);
        if (message.agent_name) {
          const { agent_id, agent_name } = message;
          setRoomAgents((current) => current.map((a) => (a.id === agent_id ? { ...a, name: agent_name } : a)));
        }
        setSwitchingToId(null);
        setSwitchError(null);
        setSelectedAgentId('');
        break;
      case 'agent_switch_failed':
        showSwitchError(describeAgentSwitchError(message.code, message.message));
        break;
    }
  };

  const teardown = async () => {
    attemptRef.current += 1;
    liveRef.current = false;
    clearSwitchTimer();
    const client = clientRef.current;
    clientRef.current = null;
    if (audioRef.current) audioRef.current.srcObject = null;
    if (client) {
      try {
        // Closes the peer connection and releases the microphone.
        await client.disconnect();
      } catch {
        // Already disconnected.
      }
    }
  };

  useEffect(() => {
    return () => {
      void teardown();
    };
    // Unmount-only cleanup; teardown only touches refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Parent Dialog (e.g. operations) owns open state; tear down when it closes.
  useEffect(() => {
    if (embedded && !isOpen) {
      void teardown();
      setStatus('idle');
      setError(null);
      resetSwitchState();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [embedded, isOpen]);

  const fail = (attempt: number, callError: BrowserCallError, toast = true) => {
    if (attempt !== attemptRef.current) return;
    setError(callError);
    setStatus('error');
    if (toast) notifyError(callError.title);
  };

  const handleConnect = async () => {
    if (actionsDisabled) return;
    await teardown();
    const attempt = attemptRef.current;
    setError(null);
    setMicEnabled(true);
    resetSwitchState();
    setRoomAgents([]);
    setActiveAgentId(agent.id);
    setStatus('connecting');

    let room: VoiceAgentRoom | undefined;
    try {
      const roomOptions: CreateVoiceAgentRoomRequest = {
        carry_history_on_swap: carryHistoryOnSwap,
        room_context_handles_language: roomContextHandlesLanguage,
      };
      if (limitHotSwapAgents) {
        roomOptions.allowed_agent_ids = allowedAgentIds;
      }
      const response = await floConsoleService.voiceAgentService.createRoom(agent.id, roomOptions);
      room = response.data?.data;
    } catch (err) {
      // The shared axios instance already toasts API failures.
      fail(attempt, describeBrowserCallError('create_room_failed', extractErrorMessage(err)), false);
      return;
    }
    if (attempt !== attemptRef.current) return;
    if (!room) {
      fail(attempt, describeBrowserCallError('create_room_failed'));
      return;
    }
    setRoomAgents(room.agents ?? []);
    setActiveAgentId(room.voice_agent_id);

    const client = new PipecatClient({
      transport: new SmallWebRTCTransport({
        iceServers: ICE_SERVERS,
        // Gather candidates before the offer so the call does not depend on trickle-ICE PATCHes
        // reaching the same call_processing replica.
        waitForICEGathering: true,
      }),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTrackStarted: (track, participant) => {
          if (participant?.local || track.kind !== 'audio' || !audioRef.current) return;
          audioRef.current.srcObject = new MediaStream([track]);
          void audioRef.current.play().catch(() => undefined);
        },
        onDisconnected: () => {
          if (attempt !== attemptRef.current) return;
          // Server-side idle / max-duration limits end the session; so does the user hanging up
          // (which bumps attemptRef first and is ignored above).
          if (liveRef.current) setStatus('ended');
        },
        onServerMessage: (data: unknown) => handleServerMessage(attempt, data),
        onTransportStateChanged: (state) => {
          if (attempt !== attemptRef.current || state !== 'error') return;
          if (!liveRef.current) return;
          setError(describeBrowserCallError('connection_failed'));
          setStatus('error');
        },
      },
    });
    clientRef.current = client;

    try {
      await withTimeout(
        client.connect({ webrtcRequestParams: buildSignalingRequest(room, appId) }),
        CONNECT_TIMEOUT_MS
      );
      if (attempt !== attemptRef.current) return;
      liveRef.current = true;
      setStatus('connected');
    } catch (err) {
      const callError = await classifyBrowserCallError(err);
      if (attempt !== attemptRef.current) return;
      await teardown();
      // teardown() invalidated this attempt; re-assert the error state directly.
      setError(callError);
      setStatus('error');
      notifyError(callError.title);
    }
  };

  const handleHangUp = async () => {
    await teardown();
    setStatus('idle');
  };

  const handleToggleMic = () => {
    const next = !micEnabled;
    clientRef.current?.enableMic(next);
    setMicEnabled(next);
  };

  const handleSwitchAgent = () => {
    const client = clientRef.current;
    if (!client || !liveRef.current || !selectedAgentId || switchingToId) return;
    setSwitchError(null);
    // Optimistic pending state; the server confirms with `agent_switching` / `agent_changed`
    // or rejects with `agent_switch_failed` (the previous agent keeps running).
    setSwitchingToId(selectedAgentId);
    clearSwitchTimer();
    const attempt = attemptRef.current;
    switchTimerRef.current = setTimeout(() => {
      if (attempt !== attemptRef.current) return;
      showSwitchError(describeAgentSwitchError('timeout'));
    }, SWITCH_TIMEOUT_MS);
    try {
      client.sendClientMessage('switch_agent', { agent_id: selectedAgentId });
    } catch {
      showSwitchError(describeAgentSwitchError('swap_failed'));
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      void teardown();
      setStatus('idle');
      setError(null);
      resetSwitchState();
    }
    onOpenChange(open);
  };

  const isBusy = status === 'connecting';
  const isLive = status === 'connected';
  const activeAgent = roomAgents.find((a) => a.id === activeAgentId);
  const activeAgentName = activeAgent?.name ?? (activeAgentId === agent.id ? agent.name : 'the agent');
  const switchableAgents = roomAgents.filter((a) => a.id !== activeAgentId);
  const isSwitching = switchingToId !== null;
  const switchingToName = roomAgents.find((a) => a.id === switchingToId)?.name;

  const body = (
    <div className="space-y-4 py-4" aria-live="polite">
      {!embedded && (
        <p className="frost-text-muted text-sm">
          Speak with <strong>{isLive ? activeAgentName : agent.name}</strong> using your microphone. No phone number is
          needed.
        </p>
      )}

      {(status === 'idle' || status === 'ended' || status === 'error') && (
        <div className="space-y-4">
          <p className="frost-text-muted text-sm">
            Your browser will ask for microphone access when you connect. Each session uses a new one-time room.
          </p>

          <div className="space-y-3 rounded-md border p-3">
            <p className="text-sm font-medium">Session options</p>

            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 space-y-0.5">
                <Label htmlFor="carry-history" className="cursor-pointer text-sm font-normal">
                  Carry history on agent switch
                </Label>
                <p className="text-muted-foreground text-xs">
                  Pass the conversation so far to the next agent when you hot-swap
                </p>
              </div>
              <Switch
                id="carry-history"
                checked={carryHistoryOnSwap}
                onCheckedChange={setCarryHistoryOnSwap}
                disabled={actionsDisabled || isBusy}
              />
            </div>

            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 space-y-0.5">
                <Label htmlFor="room-language" className="cursor-pointer text-sm font-normal">
                  App controls language
                </Label>
                <p className="text-muted-foreground text-xs">
                  Drive language via room context instead of the agent&apos;s own language switching
                </p>
              </div>
              <Switch
                id="room-language"
                checked={roomContextHandlesLanguage}
                onCheckedChange={setRoomContextHandlesLanguage}
                disabled={actionsDisabled || isBusy}
              />
            </div>

            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 space-y-0.5">
                <Label htmlFor="limit-hot-swap" className="cursor-pointer text-sm font-normal">
                  Limit agents for hot-swap
                </Label>
                <p className="text-muted-foreground text-xs">
                  {otherActiveAgents.length === 0
                    ? 'No other active agents available to switch to'
                    : 'By default every active agent can be switched to mid-call'}
                </p>
              </div>
              <Switch
                id="limit-hot-swap"
                checked={limitHotSwapAgents}
                onCheckedChange={(enabled) => {
                  setLimitHotSwapAgents(enabled);
                  if (!enabled) setAllowedAgentIds([]);
                }}
                disabled={actionsDisabled || isBusy || otherActiveAgents.length === 0}
              />
            </div>

            {limitHotSwapAgents && otherActiveAgents.length > 0 && (
              <div className="max-h-28 space-y-2 overflow-y-auto rounded-md border p-2">
                {otherActiveAgents.map((a) => {
                  const checked = allowedAgentIds.includes(a.id);
                  return (
                    <label key={a.id} className="flex cursor-pointer items-center gap-2 text-sm">
                      <Checkbox
                        checked={checked}
                        disabled={actionsDisabled || isBusy}
                        onCheckedChange={(next) => {
                          setAllowedAgentIds((prev) => (next ? [...prev, a.id] : prev.filter((id) => id !== a.id)));
                        }}
                      />
                      <span className="truncate">{a.name}</span>
                    </label>
                  );
                })}
                <p className="text-muted-foreground text-xs">
                  Leave none selected to allow only this agent (no hot-swap)
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {isBusy && <p className="frost-text-muted text-sm">Connecting to {agent.name}...</p>}

      {isLive && (
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium">
            {isSwitching
              ? `Switching to ${switchingToName ?? 'another agent'}...`
              : `Connected to ${activeAgentName}. Start speaking.`}
          </p>
          <Button type="button" variant="outline" size="sm" onClick={handleToggleMic}>
            {micEnabled ? <Mic /> : <MicOff />}
            {micEnabled ? 'Mute' : 'Unmute'}
          </Button>
        </div>
      )}

      {isLive && switchableAgents.length > 0 && (
        <div className="space-y-2">
          <p className="frost-text-muted text-xs">Switch agent (the call stays connected)</p>
          <div className="flex items-center gap-2">
            <Select value={selectedAgentId} onValueChange={setSelectedAgentId} disabled={isSwitching}>
              <SelectTrigger aria-label="Agent to switch to">
                <SelectValue placeholder="Choose an agent" />
              </SelectTrigger>
              <SelectContent>
                {switchableAgents.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant="outline"
              onClick={handleSwitchAgent}
              disabled={!selectedAgentId || isSwitching}
              loading={isSwitching}
            >
              <ArrowRightLeft />
              Switch
            </Button>
          </div>
        </div>
      )}

      {isLive && switchError && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{switchError.title}</AlertTitle>
          <AlertDescription>{switchError.message}</AlertDescription>
        </Alert>
      )}

      {status === 'ended' && (
        <Alert variant="info">
          <AlertTitle>Call ended</AlertTitle>
          <AlertDescription>
            The session finished (idle or time limit reached). Start a new session to keep talking.
          </AlertDescription>
        </Alert>
      )}

      {status === 'error' && error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{error.title}</AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}

      {/* Plays the agent's voice; the transport does not attach remote audio itself. */}
      <audio ref={audioRef} autoPlay />
    </div>
  );

  const footer = (
    <div className="mt-auto flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      {isLive ? (
        <Button type="button" variant="destructive" onClick={handleHangUp} disabled={actionsDisabled}>
          <PhoneOff />
          Hang up
        </Button>
      ) : (
        <>
          {!embedded && (
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Close
            </Button>
          )}
          <Button type="button" onClick={handleConnect} disabled={actionsDisabled || isBusy} loading={isBusy}>
            {status === 'error' ? 'Retry' : status === 'ended' ? 'Start new session' : 'Connect'}
          </Button>
        </>
      )}
    </div>
  );

  if (embedded) {
    return (
      <div className="flex h-full min-h-0 flex-col">
        {body}
        {footer}
      </div>
    );
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Talk in browser</DialogTitle>
          <DialogDescription>
            Speak with <strong>{isLive ? activeAgentName : agent.name}</strong> using your microphone. No phone number
            is needed.
          </DialogDescription>
        </DialogHeader>
        {body}
        <DialogFooter>{footer}</DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default BrowserCallDialog;
