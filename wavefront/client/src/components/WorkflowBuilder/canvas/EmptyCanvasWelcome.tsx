import { Plus, Bot } from 'lucide-react';
import { Button } from '@app/components/ui/button';

interface EmptyCanvasWelcomeProps {
  onLoadLinearTemplate: () => void;
  onLoadRouterTemplate: () => void;
  onAddAgent: () => void;
}

// Empty canvas welcome card with quick-start templates
export const EmptyCanvasWelcome = ({
  onLoadLinearTemplate,
  onLoadRouterTemplate,
  onAddAgent,
}: EmptyCanvasWelcomeProps) => (
  <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center p-4">
    <div className="bg-card/95 border-border pointer-events-auto flex max-w-md flex-col items-center gap-4 rounded-2xl border border-dashed p-8 text-center shadow-2xl backdrop-blur-md">
      <div className="bg-primary/10 text-primary flex h-12 w-12 items-center justify-center rounded-xl shadow-xs">
        <Bot size={24} />
      </div>
      <div>
        <h3 className="text-foreground text-sm font-semibold">Canvas is Empty</h3>
        <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
          Drag components from the sidebar or jumpstart with a pre-configured template:
        </p>
      </div>

      <div className="flex w-full flex-col gap-2 pt-1">
        <Button
          size="sm"
          variant="outline"
          onClick={onLoadLinearTemplate}
          className="border-border h-9 w-full justify-start gap-2 text-xs hover:border-emerald-500/50 hover:bg-emerald-500/5"
        >
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          <strong>Linear Pipeline:</strong> Content Creator ➔ Editor
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onLoadRouterTemplate}
          className="border-border h-9 w-full justify-start gap-2 text-xs hover:border-orange-500/50 hover:bg-orange-500/5"
        >
          <span className="h-2 w-2 rounded-full bg-orange-500" />
          <strong>Smart Routing:</strong> Triage ➔ Intent Router ➔ 2 Specialists
        </Button>
      </div>

      <div className="border-border/60 w-full border-t pt-3">
        <Button size="sm" onClick={onAddAgent} className="w-full gap-1.5 text-xs font-medium">
          <Plus size={13} /> Add Blank Agent
        </Button>
      </div>
    </div>
  </div>
);
