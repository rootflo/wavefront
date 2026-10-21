import { Panel } from '@xyflow/react';

interface CanvasLegendProps {
  showDataWires: boolean;
}

// Edge colour legend rendered inside the React Flow canvas
export const CanvasLegend = ({ showDataWires }: CanvasLegendProps) => (
  <Panel
    position="bottom-left"
    className="bg-card/95 border-border mb-4 ml-4 flex max-w-[220px] flex-col gap-1.5 rounded-xl border p-3 shadow-lg backdrop-blur-md"
  >
    <h4 className="text-foreground mb-0.5 text-[11px] font-semibold tracking-wider uppercase">Flow Legend</h4>
    <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
      <div className="h-0.5 w-3.5 bg-purple-500"></div>
      <span>Start Trigger</span>
    </div>
    <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
      <div className="h-0.5 w-3.5 bg-slate-500"></div>
      <span>Sequential Flow</span>
    </div>
    <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
      <div className="h-0.5 w-3.5 bg-orange-500"></div>
      <span>Router Branch</span>
    </div>
    <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
      <div className="h-0.5 w-3.5 border-t border-dashed border-blue-500"></div>
      <span>Data Filter ({showDataWires ? 'All shown' : 'Click node to view'})</span>
    </div>
    <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
      <div className="h-0.5 w-3.5 bg-indigo-500"></div>
      <span>ForEach Item (1..N)</span>
    </div>
    <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
      <div className="h-0.5 w-3.5 border-t border-dashed border-indigo-400"></div>
      <span>ForEach Loop Return</span>
    </div>
  </Panel>
);
