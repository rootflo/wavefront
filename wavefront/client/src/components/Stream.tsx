import { AlertCircle, ArrowRight, CheckCircle2, GitBranch, Play, Sparkles, Wrench } from 'lucide-react';
import React, { type RefObject } from 'react';

/**
 * One row in the run timeline.
 *
 * Covers both producers: workflow runs (node/router fields) and single-agent
 * runs (tool fields). Text deltas are not events - they go straight into the
 * chat bubble - so there is no `content` here.
 */
export interface StreamEvent {
  event_type: string;
  timestamp: number;
  node_name?: string;
  node_type?: string;
  execution_time?: number;
  error?: string;
  router_choice?: string;
  node_output?: string;
  tool_name?: string;
  arguments?: string;
  result?: string | object;
}

interface StreamProps {
  streamingEvents?: StreamEvent[];
  isStreaming?: boolean;
  eventsContainerRef?: RefObject<HTMLDivElement | null>;
}

type Tone = 'neutral' | 'active' | 'success' | 'danger';

interface EventMeta {
  label: string;
  tone: Tone;
  icon: React.ComponentType<{ className?: string }>;
}

/**
 * How each event is introduced to the person watching.
 *
 * The wire names are for the API; nobody reading a run wants to parse
 * `node_started`. Anything not listed here is title-cased as a fallback, so a
 * new event type added server-side degrades to something readable rather than
 * disappearing.
 */
const EVENT_META: Record<string, EventMeta> = {
  agent_started: { label: 'Agent started', tone: 'active', icon: Play },
  tool_called: { label: 'Called tool', tone: 'active', icon: Wrench },
  tool_result: { label: 'Tool finished', tone: 'success', icon: CheckCircle2 },
  tool_failed: { label: 'Tool failed', tone: 'danger', icon: AlertCircle },
  output: { label: 'Response ready', tone: 'success', icon: Sparkles },
  error: { label: 'Run failed', tone: 'danger', icon: AlertCircle },
  workflow_started: { label: 'Workflow started', tone: 'active', icon: Play },
  workflow_completed: { label: 'Workflow completed', tone: 'success', icon: CheckCircle2 },
  workflow_failed: { label: 'Workflow failed', tone: 'danger', icon: AlertCircle },
  node_started: { label: 'Step started', tone: 'active', icon: Play },
  node_completed: { label: 'Step finished', tone: 'success', icon: CheckCircle2 },
  node_failed: { label: 'Step failed', tone: 'danger', icon: AlertCircle },
  router_decision: { label: 'Routing decision', tone: 'neutral', icon: GitBranch },
  edge_traversed: { label: 'Moved on', tone: 'neutral', icon: ArrowRight },
};

const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'frost-text-muted',
  active: 'text-brand',
  success: 'text-emerald-600 dark:text-emerald-400',
  danger: 'text-red-600 dark:text-red-400',
};

const describe = (eventType: string): EventMeta =>
  EVENT_META[eventType] ?? {
    label: eventType.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()),
    tone: 'neutral',
    icon: CheckCircle2,
  };

/** Durations come from the server in seconds, and are often sub-millisecond. */
const formatDuration = (seconds: number): string => {
  if (seconds < 0.001) return '<1 ms';
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
};

const formatTime = (timestamp: number): string =>
  new Date(timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

/** The name of whatever this event is about: a tool, or a workflow node. */
const subjectOf = (event: StreamEvent): string | undefined => event.tool_name ?? event.node_name;

const asText = (value: string | object): string => (typeof value === 'string' ? value : JSON.stringify(value, null, 2));

const Detail: React.FC<{ label: string; value: string; danger?: boolean }> = ({ label, value, danger }) => (
  <div
    className={`mt-1.5 rounded-md border px-2.5 py-1.5 ${
      danger ? 'border-red-500/20 bg-red-500/10' : 'frost-control ring-frost-border border-transparent ring-1'
    }`}
  >
    <p className={`text-[10px] font-medium tracking-wide uppercase ${danger ? 'text-red-500' : 'frost-text-subtle'}`}>
      {label}
    </p>
    <p
      className={`mt-0.5 max-h-24 overflow-y-auto font-mono text-[11px] leading-relaxed wrap-break-word whitespace-pre-wrap ${
        danger ? 'text-red-600 dark:text-red-400' : 'frost-text-muted'
      }`}
    >
      {value}
    </p>
  </div>
);

const Stream: React.FC<StreamProps> = ({ streamingEvents, isStreaming, eventsContainerRef }) => {
  // Not gated on the streaming toggle: a finished run's timeline stays
  // readable even after streaming is switched back off.
  if (!streamingEvents || streamingEvents.length === 0) return null;

  // Wall-clock span of the run so far. Read off the frames themselves because
  // no single event carries a total.
  const elapsed = streamingEvents[streamingEvents.length - 1].timestamp - streamingEvents[0].timestamp;

  return (
    <div className="frost-control ring-frost-border mt-2 overflow-hidden rounded-lg ring-1">
      <div className="border-frost-border flex items-center justify-between border-b px-3 py-2">
        <p className="frost-text text-xs font-medium">Run details</p>
        <div className="frost-text-subtle flex items-center gap-2 text-[11px]">
          <span>
            {streamingEvents.length} step{streamingEvents.length !== 1 ? 's' : ''}
          </span>
          {elapsed > 0 && (
            <>
              <span aria-hidden>·</span>
              <span>{formatDuration(elapsed)}</span>
            </>
          )}
          {isStreaming && (
            <span className="text-brand inline-flex items-center gap-1 font-medium">
              <span className="bg-brand h-1.5 w-1.5 animate-pulse rounded-full" />
              Live
            </span>
          )}
        </div>
      </div>

      <div ref={eventsContainerRef} className="max-h-64 overflow-y-auto scroll-smooth px-3 py-2">
        {streamingEvents.map((event, index) => {
          const meta = describe(event.event_type);
          const Icon = meta.icon;
          const subject = subjectOf(event);
          const isLast = index === streamingEvents.length - 1;

          return (
            <div key={`${event.event_type}-${event.timestamp}-${index}`} className="flex gap-2.5">
              {/* Rail: icon plus the line connecting it to the next step. */}
              <div className="flex flex-col items-center">
                <Icon className={`h-3.5 w-3.5 shrink-0 ${TONE_CLASSES[meta.tone]}`} />
                {/* Tinted from the text colour, not the border token: that one
                    is near-white in light mode and would vanish here. */}
                {!isLast && <div className="bg-frost-text-subtle/30 my-1 w-px flex-1" />}
              </div>

              <div className={isLast ? 'min-w-0 flex-1 pb-1' : 'min-w-0 flex-1 pb-3'}>
                <div className="flex items-baseline justify-between gap-2">
                  <p className="frost-text min-w-0 truncate text-xs">
                    {meta.label}
                    {subject && <span className="frost-text-muted font-mono"> {subject}</span>}
                    {event.node_type && <span className="frost-text-subtle"> ({event.node_type})</span>}
                  </p>
                  <span className="frost-text-subtle shrink-0 text-[11px] tabular-nums">
                    {event.execution_time !== undefined
                      ? formatDuration(event.execution_time)
                      : formatTime(event.timestamp)}
                  </span>
                </div>

                {event.error && <Detail label="Error" value={event.error} danger />}
                {event.arguments && <Detail label="Arguments" value={event.arguments} />}
                {event.tool_name && event.result !== undefined && (
                  <Detail label="Returned" value={asText(event.result)} />
                )}
                {event.router_choice && <Detail label="Routed to" value={event.router_choice} />}
                {event.node_output && <Detail label="Output" value={event.node_output} />}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Stream;
