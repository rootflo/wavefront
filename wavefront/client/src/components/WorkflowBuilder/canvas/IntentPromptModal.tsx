import { Node } from '@xyflow/react';

export interface IntentPromptState {
  sourceId: string;
  targetId: string;
  currentText: string;
}

interface IntentPromptModalProps {
  intentPrompt: IntentPromptState;
  nodes: Node[];
  onChange: (intentPrompt: IntentPromptState) => void;
  onSave: () => void;
  onSkip: () => void;
}

// Intent prompt modal (on connecting router to agent or clicking route edge)
export const IntentPromptModal = ({ intentPrompt, nodes, onChange, onSave, onSkip }: IntentPromptModalProps) => (
  <div className="bg-background/60 absolute inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-xs">
    <div className="bg-card border-border animate-in fade-in zoom-in-95 flex w-[420px] flex-col overflow-hidden rounded-2xl border shadow-2xl duration-150">
      <div className="border-b border-orange-500/20 bg-orange-500/10 px-5 py-3.5">
        <h3 className="text-xs font-semibold tracking-wider text-orange-600 uppercase dark:text-orange-400">
          Define Routing Condition
        </h3>
        {(() => {
          const sourceLabel = nodes.find((n) => n.id === intentPrompt.sourceId)?.data?.label || intentPrompt.sourceId;
          const targetLabel = nodes.find((n) => n.id === intentPrompt.targetId)?.data?.label || intentPrompt.targetId;
          return (
            <p className="text-foreground/80 mt-1 text-xs">
              When should <strong>{sourceLabel as string}</strong> route to <strong>{targetLabel as string}</strong>?
            </p>
          );
        })()}
      </div>
      <div className="flex flex-col gap-3 p-5">
        <textarea
          autoFocus
          className="bg-background border-border text-foreground h-24 w-full resize-none rounded-lg border px-3 py-2 text-xs leading-relaxed focus:border-orange-500 focus:outline-none"
          placeholder="e.g. When the user asks for technical documentation or code examples..."
          value={intentPrompt.currentText}
          onChange={(e) => onChange({ ...intentPrompt, currentText: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSave();
            }
          }}
        />
        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            className="hover:bg-muted text-muted-foreground rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
            onClick={onSkip}
          >
            Skip
          </button>
          <button
            className="rounded-lg bg-orange-600 px-3.5 py-1.5 text-xs font-medium text-white transition-colors hover:bg-orange-700"
            onClick={onSave}
          >
            Save Rule (↵)
          </button>
        </div>
      </div>
    </div>
  </div>
);
