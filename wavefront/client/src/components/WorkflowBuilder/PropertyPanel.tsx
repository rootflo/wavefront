import { NODE_TYPES } from '@app/constants/workflow-builder';
import React from 'react';
import { X, Trash2 } from 'lucide-react';
import { Node } from '@xyflow/react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Button } from '@app/components/ui/button';
import { useParams } from 'react-router';
import { useGetLLMConfigs, useGetWorkflows, useGetTools } from '@app/hooks/data/fetch-hooks';
import { AgentProperties } from './propertyPanel/AgentProperties';
import { EntryAgentStatus } from './propertyPanel/EntryAgentStatus';
import { FunctionProperties } from './propertyPanel/FunctionProperties';
import { IteratorProperties } from './propertyPanel/IteratorProperties';
import { RouterProperties } from './propertyPanel/RouterProperties';
import { SubworkflowProperties } from './propertyPanel/SubworkflowProperties';
import { ParserMode } from './propertyPanel/types';

const NODE_TYPE_TITLES: Record<string, string> = {
  [NODE_TYPES.AGENT]: 'Agent Settings',
  [NODE_TYPES.ROUTER]: 'Router Settings',
  [NODE_TYPES.FUNCTION]: 'Function Node Settings',
  [NODE_TYPES.ITERATOR]: 'ForEach Iterator Settings',
  [NODE_TYPES.SUBWORKFLOW]: 'Sub-Workflow Settings',
};

const DEFAULT_NODE_TYPE_TITLE = 'Step Settings';

interface PropertyPanelProps {
  selectedNode: Node | null;
  onClose: () => void;
  onUpdateNode: (id: string, data: Record<string, unknown>) => void;
  onRenameNode?: (oldId: string, newId: string) => void;
  nodes?: Node[];
  onSetStartAgent?: (agentId: string) => void;
  onDeleteNode?: (nodeId: string) => void;
}

export const PropertyPanel = ({
  selectedNode,
  onClose,
  onUpdateNode,
  onRenameNode,
  nodes = [],
  onSetStartAgent,
  onDeleteNode,
}: PropertyPanelProps) => {
  const { app: appId } = useParams<{ app: string }>();
  const { data: rootfloConfigs = [] } = useGetLLMConfigs(appId || '');
  const { data: workflows = [] } = useGetWorkflows(appId || '');
  const { data: tools = [] } = useGetTools(appId || '');

  const [nameInput, setNameInput] = React.useState((selectedNode?.data?.label as string) || selectedNode?.id || '');
  const [parserMode, setParserMode] = React.useState<ParserMode>('builder');

  React.useEffect(() => {
    if (selectedNode) {
      setNameInput((selectedNode.data?.label as string) || selectedNode.id);
    }
  }, [selectedNode]);

  if (!selectedNode) return null;

  const handleChange = (key: string, value: unknown) => {
    onUpdateNode(selectedNode.id, { ...selectedNode.data, [key]: value });
  };

  const handleNameChange = (val: string) => {
    setNameInput(val);
    const sanitized = val.trim().replace(/\s+/g, '_');
    if (sanitized && sanitized !== selectedNode.id && !nodes.some((n) => n.id === sanitized)) {
      onRenameNode?.(selectedNode.id, sanitized);
    }
  };

  const handleNameBlur = () => {
    const sanitized = nameInput.trim().replace(/\s+/g, '_');
    if (!sanitized) {
      setNameInput((selectedNode.data?.label as string) || selectedNode.id);
    } else if (sanitized !== selectedNode.id) {
      onRenameNode?.(selectedNode.id, sanitized);
    }
  };

  const nodeTypeTitle = (selectedNode.type && NODE_TYPE_TITLES[selectedNode.type]) || DEFAULT_NODE_TYPE_TITLE;

  return (
    <aside className="border-border bg-card z-10 flex h-full w-96 shrink-0 flex-col border-l shadow-[-2px_0_10px_rgba(0,0,0,0.05)]">
      <div className="border-border bg-muted/10 flex h-14 shrink-0 items-center justify-between border-b px-4">
        <div>
          <h2 className="text-foreground text-xs font-semibold tracking-wider uppercase">{nodeTypeTitle}</h2>
          <p className="text-muted-foreground max-w-[200px] truncate text-[10px]">{selectedNode.id}</p>
        </div>
        <button className="text-muted-foreground hover:text-foreground hover:bg-muted rounded p-1" onClick={onClose}>
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {/* ENTRY AGENT STATUS / BUTTON FOR AGENTS */}
        {selectedNode.type === NODE_TYPES.AGENT && (
          <EntryAgentStatus selectedNode={selectedNode} onSetStartAgent={onSetStartAgent} />
        )}

        <div>
          <Label className="mb-1 block text-xs">Identifier (Name)</Label>
          <Input
            value={nameInput}
            onChange={(e) => handleNameChange(e.target.value)}
            onBlur={handleNameBlur}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleNameBlur();
              }
            }}
            className="bg-background h-8 text-xs font-medium"
            placeholder="Unique name (e.g. content_creator)..."
          />
          <p className="text-muted-foreground mt-0.5 text-[10px]">Used as reference in workflow connections.</p>
        </div>

        {selectedNode.type === NODE_TYPES.AGENT && (
          <AgentProperties
            selectedNode={selectedNode}
            handleChange={handleChange}
            nodes={nodes}
            rootfloConfigs={rootfloConfigs}
            tools={tools}
            parserMode={parserMode}
            onParserModeChange={setParserMode}
          />
        )}

        {selectedNode.type === NODE_TYPES.ROUTER && (
          <RouterProperties
            selectedNode={selectedNode}
            handleChange={handleChange}
            nodes={nodes}
            rootfloConfigs={rootfloConfigs}
          />
        )}

        {selectedNode.type === NODE_TYPES.FUNCTION && (
          <FunctionProperties selectedNode={selectedNode} handleChange={handleChange} nodes={nodes} tools={tools} />
        )}

        {selectedNode.type === NODE_TYPES.ITERATOR && (
          <IteratorProperties selectedNode={selectedNode} handleChange={handleChange} nodes={nodes} />
        )}

        {selectedNode.type === NODE_TYPES.SUBWORKFLOW && (
          <SubworkflowProperties
            selectedNode={selectedNode}
            handleChange={handleChange}
            nodes={nodes}
            workflows={workflows}
          />
        )}

        {/* DELETE ACTION BUTTON */}
        <div className="border-border border-t pt-4">
          <Button
            variant="outline"
            size="sm"
            className="text-destructive border-destructive/20 hover:bg-destructive/10 w-full gap-1.5 text-xs"
            onClick={() => onDeleteNode?.(selectedNode.id)}
          >
            <Trash2 size={13} /> Delete this {selectedNode.type?.replace('Node', '') || 'Step'}
          </Button>
        </div>
      </div>
    </aside>
  );
};
