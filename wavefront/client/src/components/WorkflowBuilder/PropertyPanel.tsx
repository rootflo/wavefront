import { NODE_TYPES } from '@app/constants/workflow-builder';
import React from 'react';
import { X, Trash2 } from 'lucide-react';
import { Node } from '@xyflow/react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Button } from '@app/components/ui/button';
import { useParams } from 'react-router';
import { useGetLLMConfigs, useGetWorkflows, useGetTools } from '@app/hooks';
import { AgentProperties } from './propertyPanel/AgentProperties';
import { EntryAgentStatus } from './propertyPanel/EntryAgentStatus';
import { FunctionProperties } from './propertyPanel/FunctionProperties';
import { IteratorProperties } from './propertyPanel/IteratorProperties';
import { RouterProperties } from './propertyPanel/RouterProperties';
import { SubworkflowProperties } from './propertyPanel/SubworkflowProperties';
import { ParserMode } from './propertyPanel/types';
import { isExecutableNode, sanitizeNodeName, validateNodeName } from './graphUtils';

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
  // Merges `patch` into the node's current data
  onUpdateNode: (id: string, patch: Record<string, unknown>) => void;
  onRenameNode?: (oldId: string, newId: string) => void;
  nodes?: Node[];
  startNodeId?: string;
  onSetStartAgent?: (agentId: string) => void;
  onDeleteNode?: (nodeId: string) => void;
}

export const PropertyPanel = ({
  selectedNode,
  onClose,
  onUpdateNode,
  onRenameNode,
  nodes = [],
  startNodeId,
  onSetStartAgent,
  onDeleteNode,
}: PropertyPanelProps) => {
  const { app: appId } = useParams<{ app: string }>();
  const { data: rootfloConfigs = [] } = useGetLLMConfigs(appId || '');
  const { data: workflows = [] } = useGetWorkflows(appId || '');
  const { data: tools = [] } = useGetTools(appId || '');

  const selectedId = selectedNode?.id ?? '';
  const [nameInput, setNameInput] = React.useState(selectedId);
  const [nameError, setNameError] = React.useState<string | null>(null);
  const [parserMode, setParserMode] = React.useState<ParserMode>('builder');

  // Reset the name field when another node is selected or this one is renamed
  React.useEffect(() => {
    setNameInput(selectedId);
    setNameError(null);
  }, [selectedId]);

  if (!selectedNode) return null;

  const handleChange = (key: string, value: unknown) => onUpdateNode(selectedNode.id, { [key]: value });

  const handleChanges = (patch: Record<string, unknown>) => onUpdateNode(selectedNode.id, patch);

  // Renames are committed on blur / Enter only, so references are never re-keyed to half-typed names.
  // Returns whether the input now matches the node name.
  const commitName = (): boolean => {
    const sanitized = sanitizeNodeName(nameInput);
    if (sanitized === selectedNode.id) {
      setNameInput(selectedNode.id);
      setNameError(null);
      return true;
    }
    const error = validateNodeName(sanitized, nodes, selectedNode.id);
    if (error) {
      setNameError(error);
      return false;
    }
    setNameError(null);
    onRenameNode?.(selectedNode.id, sanitized);
    return true;
  };

  const handleNameBlur = () => {
    // An invalid name is discarded on blur; the error stays visible to explain why
    if (!commitName()) setNameInput(selectedNode.id);
  };

  const handleNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitName();
    } else if (e.key === 'Escape') {
      setNameInput(selectedNode.id);
      setNameError(null);
    }
  };

  const nodeTypeTitle = (selectedNode.type && NODE_TYPE_TITLES[selectedNode.type]) || DEFAULT_NODE_TYPE_TITLE;

  return (
    <aside className="border-border bg-card z-10 flex h-full w-96 max-w-[100vw] shrink-0 flex-col border-l shadow-[-2px_0_10px_rgba(0,0,0,0.05)] max-md:fixed max-md:inset-y-0 max-md:right-0 max-md:z-50">
      <div className="border-border bg-muted/10 flex h-14 shrink-0 items-center justify-between border-b px-4">
        <div>
          <h2 className="text-foreground text-xs font-semibold tracking-wider uppercase">{nodeTypeTitle}</h2>
          <p className="text-muted-foreground max-w-[200px] truncate text-[10px]">{selectedNode.id}</p>
        </div>
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground hover:bg-muted rounded p-1"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {/* ENTRY STEP STATUS / BUTTON FOR EXECUTABLE STEPS */}
        {isExecutableNode(selectedNode) && (
          <EntryAgentStatus
            selectedNode={selectedNode}
            isStartNode={selectedNode.id === startNodeId}
            onSetStartAgent={onSetStartAgent}
          />
        )}

        <div>
          <Label className="mb-1 block text-xs">Identifier (Name)</Label>
          <Input
            value={nameInput}
            onChange={(e) => {
              setNameInput(e.target.value);
              setNameError(null);
            }}
            onBlur={handleNameBlur}
            onKeyDown={handleNameKeyDown}
            aria-invalid={!!nameError}
            className={`bg-background h-8 text-xs font-medium ${nameError ? 'border-destructive' : ''}`}
            placeholder="Unique name (e.g. content_creator)..."
          />
          {nameError ? (
            <p className="text-destructive mt-0.5 text-[10px]">{nameError}</p>
          ) : (
            <p className="text-muted-foreground mt-0.5 text-[10px]">Used as reference in workflow connections.</p>
          )}
        </div>

        {selectedNode.type === NODE_TYPES.AGENT && (
          <AgentProperties
            key={selectedNode.id}
            selectedNode={selectedNode}
            handleChange={handleChange}
            handleChanges={handleChanges}
            nodes={nodes}
            rootfloConfigs={rootfloConfigs}
            tools={tools}
            parserMode={parserMode}
            onParserModeChange={setParserMode}
          />
        )}

        {selectedNode.type === NODE_TYPES.ROUTER && (
          <RouterProperties
            key={selectedNode.id}
            selectedNode={selectedNode}
            handleChange={handleChange}
            handleChanges={handleChanges}
            nodes={nodes}
            rootfloConfigs={rootfloConfigs}
          />
        )}

        {selectedNode.type === NODE_TYPES.FUNCTION && (
          <FunctionProperties
            key={selectedNode.id}
            selectedNode={selectedNode}
            handleChange={handleChange}
            handleChanges={handleChanges}
            nodes={nodes}
            tools={tools}
          />
        )}

        {selectedNode.type === NODE_TYPES.ITERATOR && (
          <IteratorProperties
            key={selectedNode.id}
            selectedNode={selectedNode}
            handleChange={handleChange}
            handleChanges={handleChanges}
            nodes={nodes}
          />
        )}

        {selectedNode.type === NODE_TYPES.SUBWORKFLOW && (
          <SubworkflowProperties
            key={selectedNode.id}
            selectedNode={selectedNode}
            handleChange={handleChange}
            handleChanges={handleChanges}
            nodes={nodes}
            workflows={workflows}
          />
        )}

        {/* DELETE ACTION BUTTON */}
        <div className="border-border border-t pt-4">
          <Button
            type="button"
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
