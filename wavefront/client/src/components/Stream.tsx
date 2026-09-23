import React, { type RefObject } from 'react';

interface StreamProps {
  listenEventsEnabled: boolean;
  streamingEvents?: Array<{
    event_type: string;
    timestamp: number;
    node_name?: string;
    node_type?: string;
    execution_time?: number;
    error?: string;
    router_choice?: string;
    node_output?: string;
  }>;
  isStreaming?: boolean;
  eventsContainerRef?: RefObject<HTMLDivElement | null>;
}

const Stream: React.FC<StreamProps> = ({ listenEventsEnabled, streamingEvents, isStreaming, eventsContainerRef }) => {
  return (
    <div className="mt-4">
      {listenEventsEnabled && streamingEvents && streamingEvents.length > 0 && (
        <>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="frost-text text-sm font-medium">Real-time Events:</h3>
            <span className="frost-text-muted text-xs">
              {streamingEvents.length} event{streamingEvents.length !== 1 ? 's' : ''}
              {isStreaming && <span className="text-brand ml-1">• Live</span>}
            </span>
          </div>
          <div
            ref={eventsContainerRef}
            className="frost-panel ring-frost-border max-h-64 overflow-y-auto scroll-smooth rounded-lg border p-3 ring-1"
          >
            <div className="space-y-2">
              {streamingEvents.map((event, index) => (
                <div
                  key={event.event_type + index}
                  className={`text-xs transition-all duration-300 ${
                    index === streamingEvents.length - 1 && isStreaming ? 'animate-pulse' : ''
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span
                      className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${
                        event.event_type === 'workflow_started' || event.event_type === 'workflow_completed'
                          ? 'bg-brand/15 text-brand ring-brand/25 ring-1'
                          : event.event_type === 'workflow_failed' ||
                              event.event_type === 'node_failed' ||
                              event.event_type === 'error'
                            ? 'bg-red-500/15 text-red-600 ring-1 ring-red-500/20 dark:text-red-400'
                            : event.event_type === 'output'
                              ? 'bg-emerald-400/15 text-emerald-700 ring-1 ring-emerald-400/20 dark:text-emerald-400'
                              : 'frost-control frost-text ring-frost-border ring-1'
                      }`}
                    >
                      {event.event_type}
                    </span>
                    <span className="frost-text-subtle">{new Date(event.timestamp * 1000).toLocaleTimeString()}</span>
                  </div>
                  {'node_name' in event && event.node_name && (
                    <div className="frost-text-muted mt-1">
                      Node: <span className="frost-text font-medium">{event.node_name}</span>
                      {'node_type' in event && event.node_type && (
                        <span className="frost-text-subtle"> ({event.node_type})</span>
                      )}
                    </div>
                  )}
                  {'execution_time' in event && event.execution_time && (
                    <div className="frost-text-subtle">Execution time: {event.execution_time}s</div>
                  )}
                  {'error' in event && event.error && (
                    <div className="mt-1 rounded bg-red-500/10 p-2 text-red-600 dark:text-red-400">
                      Error: {event.error}
                    </div>
                  )}
                  {'router_choice' in event && event.router_choice && (
                    <div className="text-brand mt-1">Router choice: {event.router_choice}</div>
                  )}
                  {'node_output' in event && event.node_output && (
                    <div className="frost-control ring-frost-border mt-1 rounded border p-2 ring-1">
                      <span className="frost-text-muted font-medium">Output: </span>
                      <span className="frost-text break-words whitespace-pre-wrap">{event.node_output}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
          {isStreaming && (
            <div className="text-brand mt-2 flex items-center gap-2 text-sm">
              <div className="flex gap-1">
                <div className="bg-brand h-1.5 w-1.5 animate-pulse rounded-full [animation-delay:0ms]"></div>
                <div className="bg-brand h-1.5 w-1.5 animate-pulse rounded-full [animation-delay:150ms]"></div>
                <div className="bg-brand h-1.5 w-1.5 animate-pulse rounded-full [animation-delay:300ms]"></div>
              </div>
              <p className="text-xs">Streaming live events...</p>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default Stream;
