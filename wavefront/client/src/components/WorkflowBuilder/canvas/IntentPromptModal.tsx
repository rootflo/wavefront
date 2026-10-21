import { Node } from '@xyflow/react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@app/components/ui/dialog';

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

// Intent prompt modal (on connecting router to agent or clicking route edge). Closing it (Esc / X) is Skip.
export const IntentPromptModal = ({ intentPrompt, nodes, onChange, onSave, onSkip }: IntentPromptModalProps) => {
  const sourceLabel = nodes.find((n) => n.id === intentPrompt.sourceId)?.data?.label || intentPrompt.sourceId;
  const targetLabel = nodes.find((n) => n.id === intentPrompt.targetId)?.data?.label || intentPrompt.targetId;

  return (
    <Dialog open onOpenChange={(open) => !open && onSkip()}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle className="text-sm">Define Routing Condition</DialogTitle>
          <DialogDescription className="text-xs">
            When should <strong>{sourceLabel as string}</strong> route to <strong>{targetLabel as string}</strong>?
          </DialogDescription>
        </DialogHeader>
        <textarea
          autoFocus
          aria-label="Routing condition"
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
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            className="hover:bg-muted text-muted-foreground rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
            onClick={onSkip}
          >
            Skip
          </button>
          <button
            type="button"
            className="rounded-lg bg-orange-600 px-3.5 py-1.5 text-xs font-medium text-white transition-colors hover:bg-orange-700"
            onClick={onSave}
          >
            Save Rule (↵)
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
