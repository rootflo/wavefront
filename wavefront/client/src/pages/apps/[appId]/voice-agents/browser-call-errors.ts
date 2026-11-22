import { DeviceError } from '@pipecat-ai/client-js';

/**
 * Why a browser call could not start (or dropped). Each kind maps to one user-facing message and
 * says whether retrying makes sense (a retry always creates a fresh room - join tokens are one-time).
 */
export type BrowserCallErrorKind =
  | 'mic_denied'
  | 'mic_unavailable'
  | 'room_expired'
  | 'room_invalid'
  | 'room_already_joined'
  | 'sticky_required'
  | 'connection_failed'
  | 'create_room_failed';

export interface BrowserCallError {
  kind: BrowserCallErrorKind;
  title: string;
  message: string;
}

const ERRORS: Record<BrowserCallErrorKind, Omit<BrowserCallError, 'kind'>> = {
  mic_denied: {
    title: 'Microphone access blocked',
    message:
      'Allow microphone access for this site in your browser settings (the lock icon next to the address bar), then try again.',
  },
  mic_unavailable: {
    title: 'No usable microphone',
    message:
      'We could not open a microphone. Check that one is connected and not in use by another app, then try again.',
  },
  room_expired: {
    title: 'Room expired',
    message: 'This voice room has expired. Start a new session to continue.',
  },
  room_invalid: {
    title: 'Room is no longer valid',
    message: 'This voice room could not be verified. Start a new session to continue.',
  },
  room_already_joined: {
    title: 'Session already in use',
    message: 'This room already has an active connection. Start a new session to continue.',
  },
  sticky_required: {
    title: 'Connection routing error',
    message: 'Your connection was routed to a different voice server. Try again to start a new session.',
  },
  connection_failed: {
    title: "Couldn't establish a voice connection",
    message:
      'The voice connection could not be established. This is usually a network or firewall issue (WebRTC / UDP may be blocked). Check your network and try again.',
  },
  create_room_failed: {
    title: "Couldn't start the session",
    message: 'The voice room could not be created. Try again in a moment.',
  },
};

export const describeBrowserCallError = (kind: BrowserCallErrorKind, detail?: string): BrowserCallError => {
  const base = ERRORS[kind];
  return { kind, title: base.title, message: detail ? `${base.message} (${detail})` : base.message };
};

/** Signaling error bodies look like `{ "error": "<code>", "message": "..." }`. */
const readErrorCode = async (response: Response): Promise<string | undefined> => {
  try {
    const body = (await response.clone().json()) as { error?: unknown; meta?: { error?: unknown } };
    if (typeof body.error === 'string') return body.error;
    if (typeof body.meta?.error === 'string') return body.meta.error;
  } catch {
    // Non-JSON body: fall back to the HTTP status.
  }
  return undefined;
};

const kindForSignalingResponse = async (response: Response): Promise<BrowserCallErrorKind> => {
  const code = await readErrorCode(response);
  if (code === 'room_expired' || response.status === 410) return 'room_expired';
  if (code === 'room_already_joined') return 'room_already_joined';
  if (code === 'sticky_required') return 'sticky_required';
  if (code === 'invalid_join_token' || response.status === 401 || response.status === 403) return 'room_invalid';
  if (response.status === 404) return 'room_invalid';
  return 'connection_failed';
};

const isMicPermissionError = (error: unknown): boolean => {
  if (error instanceof DeviceError) {
    return error.type === 'permissions' && error.devices.includes('mic');
  }
  const name = (error as { name?: string } | null)?.name;
  return name === 'NotAllowedError' || name === 'SecurityError';
};

const isMicUnavailableError = (error: unknown): boolean => {
  if (error instanceof DeviceError) {
    return error.devices.includes('mic') && error.type !== 'permissions';
  }
  const name = (error as { name?: string } | null)?.name;
  return name === 'NotFoundError' || name === 'NotReadableError' || name === 'OverconstrainedError';
};

/**
 * Map whatever `PipecatClient.connect()` / the transport threw to a user-facing error.
 *
 * The SmallWebRTC transport wraps a rejected offer in a `TransportStartError` whose `cause` is the raw
 * fetch `Response`, so the HTTP status and the stable error code can be recovered from there.
 */
export const classifyBrowserCallError = async (error: unknown): Promise<BrowserCallError> => {
  if (isMicPermissionError(error)) return describeBrowserCallError('mic_denied');
  if (isMicUnavailableError(error)) return describeBrowserCallError('mic_unavailable');

  const cause = (error as { cause?: unknown } | null)?.cause;
  for (const candidate of [error, cause]) {
    if (typeof Response !== 'undefined' && candidate instanceof Response) {
      return describeBrowserCallError(await kindForSignalingResponse(candidate));
    }
  }
  if (isMicPermissionError(cause)) return describeBrowserCallError('mic_denied');

  return describeBrowserCallError('connection_failed');
};

/**
 * Why a mid-call agent switch failed. These are the stable `code`s of the server's `agent_switch_failed`
 * message. A failed switch never ends the call: the previous agent keeps running.
 */
export type AgentSwitchErrorCode =
  | 'agent_not_allowed'
  | 'agent_unavailable'
  | 'swap_in_progress'
  | 'swap_limit_reached'
  | 'already_active'
  | 'swap_failed'
  | 'invalid_request'
  | 'timeout';

export interface AgentSwitchError {
  code: AgentSwitchErrorCode | string;
  title: string;
  message: string;
}

const AGENT_SWITCH_ERRORS: Record<AgentSwitchErrorCode, Omit<AgentSwitchError, 'code'>> = {
  agent_not_allowed: {
    title: "Can't switch to that agent",
    message: 'That agent is not available in this session. Pick another agent.',
  },
  agent_unavailable: {
    title: 'Agent unavailable',
    message: 'That agent is not active right now. Pick another agent; the current agent is still on the call.',
  },
  swap_in_progress: {
    title: 'Switch already in progress',
    message: 'Wait a moment for the current switch to finish, then try again.',
  },
  swap_limit_reached: {
    title: 'Switch limit reached',
    message: 'This session reached its limit on agent switches. Start a new session to switch again.',
  },
  already_active: {
    title: 'Already talking to this agent',
    message: 'That agent is already on the call.',
  },
  swap_failed: {
    title: "Couldn't switch agents",
    message: 'The switch failed, so you are still talking to the previous agent. Try again in a moment.',
  },
  invalid_request: {
    title: "Couldn't switch agents",
    message: 'The switch request was not valid. Pick an agent and try again.',
  },
  timeout: {
    title: 'Agent switch timed out',
    message: 'The switch took too long. You may still be talking to the previous agent; try again.',
  },
};

export const describeAgentSwitchError = (code: string | undefined, serverMessage?: string): AgentSwitchError => {
  const known = code && code in AGENT_SWITCH_ERRORS ? AGENT_SWITCH_ERRORS[code as AgentSwitchErrorCode] : undefined;
  const base = known ?? AGENT_SWITCH_ERRORS.swap_failed;
  return {
    code: code ?? 'swap_failed',
    title: base.title,
    message: known || !serverMessage ? base.message : `${base.message} (${serverMessage})`,
  };
};

/** Server -> browser messages about agent switching (RTVI server messages). */
export type AgentSwitchServerMessage =
  | { type: 'agent_switching'; agent_id: string }
  | { type: 'agent_changed'; agent_id: string; agent_name?: string }
  | { type: 'agent_switch_failed'; code?: string; message?: string };

export const parseAgentSwitchMessage = (data: unknown): AgentSwitchServerMessage | null => {
  if (!data || typeof data !== 'object') return null;
  const msg = data as Record<string, unknown>;
  switch (msg.type) {
    case 'agent_switching':
      return typeof msg.agent_id === 'string' ? { type: 'agent_switching', agent_id: msg.agent_id } : null;
    case 'agent_changed':
      return typeof msg.agent_id === 'string'
        ? {
            type: 'agent_changed',
            agent_id: msg.agent_id,
            agent_name: typeof msg.agent_name === 'string' ? msg.agent_name : undefined,
          }
        : null;
    case 'agent_switch_failed':
      return {
        type: 'agent_switch_failed',
        code: typeof msg.code === 'string' ? msg.code : undefined,
        message: typeof msg.message === 'string' ? msg.message : undefined,
      };
    default:
      return null;
  }
};
