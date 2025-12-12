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
            <h3 className="text-sm font-medium text-gray-700">Real-time Events:</h3>
            <span className="text-xs text-gray-500">
              {streamingEvents.length} event{streamingEvents.length !== 1 ? 's' : ''}
              {isStreaming && <span className="ml-1 text-blue-600">• Live</span>}
            </span>
          </div>
          <div
            ref={eventsContainerRef}
            className="max-h-64 overflow-y-auto scroll-smooth rounded-lg border border-gray-200 bg-gray-50 p-3"
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
                          ? 'bg-blue-100 text-blue-800'
                          : event.event_type === 'workflow_failed' ||
                              event.event_type === 'node_failed' ||
                              event.event_type === 'error'
                            ? 'bg-red-100 text-red-800'
                            : event.event_type === 'output'
                              ? 'bg-green-100 text-green-800'
                              : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {event.event_type}
                    </span>
                    <span className="text-gray-500">{new Date(event.timestamp * 1000).toLocaleTimeString()}</span>
                  </div>
                  {'node_name' in event && event.node_name && (
                    <div className="mt-1 text-gray-600">
                      Node: <span className="font-medium">{event.node_name}</span>
                      {'node_type' in event && event.node_type && (
                        <span className="text-gray-500"> ({event.node_type})</span>
                      )}
                    </div>
                  )}
                  {'execution_time' in event && event.execution_time && (
                    <div className="text-gray-500">Execution time: {event.execution_time}s</div>
                  )}
                  {'error' in event && event.error && (
                    <div className="mt-1 rounded bg-red-50 p-2 text-red-600">Error: {event.error}</div>
                  )}
                  {'router_choice' in event && event.router_choice && (
                    <div className="mt-1 text-blue-600">Router choice: {event.router_choice}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
          {isStreaming && (
            <div className="mt-2 flex items-center gap-2 text-sm text-blue-600">
              <div className="flex gap-1">
                <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-600 [animation-delay:0ms]"></div>
                <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-600 [animation-delay:150ms]"></div>
                <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-600 [animation-delay:300ms]"></div>
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
