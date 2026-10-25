import floConsoleService from '@app/api';
import { toneClass } from '@app/lib/tones';
import { Button } from '@app/components/ui/button';
import { Switch } from '@app/components/ui/switch';
import { Badge } from '@app/components/ui/badge';
import { useGetVoiceAgentTools, useGetAgentTools } from '@app/hooks';
import { getVoiceAgentToolsKey, getAgentToolsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { VoiceAgentToolWithAssociation } from '@app/types/tool';
import { useQueryClient } from '@tanstack/react-query';
import { Plus, X } from 'lucide-react';
import React, { useState } from 'react';

/** A tool picked before the agent exists; it is attached once the agent is created. */
export interface PendingAgentTool {
  toolId: string;
  isEnabled: boolean;
}

type VoiceAgentToolsManagerProps =
  | { appId: string; agentId: string }
  | {
      appId: string;
      agentId?: undefined;
      pendingTools: PendingAgentTool[];
      onPendingToolsChange: (tools: PendingAgentTool[]) => void;
    };

const VoiceAgentToolsManager: React.FC<VoiceAgentToolsManagerProps> = (props) => {
  const { appId, agentId } = props;
  // Without an agent yet, attach / toggle / detach only edit the pending list
  const pending = props.agentId === undefined ? props : undefined;
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [loadingToolId, setLoadingToolId] = useState<string | null>(null);

  // Fetch all tools
  const { data: allTools = [], isLoading: allToolsLoading } = useGetVoiceAgentTools(appId);

  // Fetch tools attached to this agent
  const { data: savedAgentTools = [], isLoading: agentToolsLoading } = useGetAgentTools(appId, agentId);

  const agentTools: VoiceAgentToolWithAssociation[] = pending
    ? pending.pendingTools.flatMap(({ toolId, isEnabled }) => {
        const tool = allTools.find((t) => t.id === toolId);
        return tool ? [{ ...tool, association: { id: '', is_enabled: isEnabled, priority: 0 } }] : [];
      })
    : savedAgentTools;

  const attachedToolIds = new Set(agentTools.map((t) => t.id));
  const availableTools = allTools.filter((t) => !attachedToolIds.has(t.id));

  const handleToggleEnabled = async (toolId: string, currentEnabled: boolean) => {
    if (pending) {
      pending.onPendingToolsChange(
        pending.pendingTools.map((t) => (t.toolId === toolId ? { ...t, isEnabled: !currentEnabled } : t))
      );
      return;
    }
    if (!agentId) return;
    setLoadingToolId(toolId);
    try {
      await floConsoleService.toolService.updateAgentTool(agentId, toolId, {
        is_enabled: !currentEnabled,
      });
      notifySuccess(`Tool ${!currentEnabled ? 'enabled' : 'disabled'} successfully`);
      queryClient.invalidateQueries({ queryKey: getAgentToolsKey(appId, agentId) });
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to toggle tool');
    } finally {
      setLoadingToolId(null);
    }
  };

  const handleAttachTool = async (toolId: string) => {
    if (pending) {
      pending.onPendingToolsChange([...pending.pendingTools, { toolId, isEnabled: true }]);
      return;
    }
    if (!agentId) return;
    setLoadingToolId(toolId);
    try {
      await floConsoleService.toolService.attachToolToAgent(agentId, {
        tool_id: toolId,
        is_enabled: true,
        priority: 0,
      });
      notifySuccess('Tool attached successfully');
      queryClient.invalidateQueries({ queryKey: getAgentToolsKey(appId, agentId) });
      queryClient.invalidateQueries({ queryKey: getVoiceAgentToolsKey(appId) });
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to attach tool');
    } finally {
      setLoadingToolId(null);
    }
  };

  const handleDetachTool = async (toolId: string) => {
    if (pending) {
      pending.onPendingToolsChange(pending.pendingTools.filter((t) => t.toolId !== toolId));
      return;
    }
    if (!agentId) return;
    setLoadingToolId(toolId);
    try {
      await floConsoleService.toolService.detachToolFromAgent(agentId, toolId);
      notifySuccess('Tool detached successfully');
      queryClient.invalidateQueries({ queryKey: getAgentToolsKey(appId, agentId) });
      queryClient.invalidateQueries({ queryKey: getVoiceAgentToolsKey(appId) });
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to detach tool');
    } finally {
      setLoadingToolId(null);
    }
  };

  const getToolTypeColor = (type: string) => {
    if (type === 'api') return toneClass.info;
    if (type === 'app') return toneClass.emerald;
    return toneClass.violet;
  };

  if (allToolsLoading || agentToolsLoading) {
    return (
      <div className="flex justify-center py-4">
        <div className="frost-text-muted text-sm">Loading tools...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Attached Tools */}
      <div>
        <h4 className="mb-3 text-sm font-semibold">Attached Tools ({agentTools.length})</h4>
        {agentTools.length === 0 ? (
          <div className="frost-text-muted rounded-md border border-dashed p-4 text-center text-sm">
            {pending
              ? 'No tools picked yet. Tools you attach below are added when the agent is created.'
              : 'No tools attached to this agent yet. Add tools from the available tools below.'}
          </div>
        ) : (
          <div className="space-y-2">
            {agentTools.map((tool) => (
              <div
                key={tool.id}
                className="frost-glass border-frost-border hover:bg-frost-glass-strong flex items-center justify-between rounded-md border p-3"
              >
                <div className="flex flex-1 items-center gap-3">
                  <Badge className={getToolTypeColor(tool.tool_type)}>{tool.tool_type.toUpperCase()}</Badge>
                  <div className="flex-1">
                    <div className="font-medium">{tool.display_name}</div>
                    <div className="frost-text-muted text-xs">Function: {tool.name}</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span className="frost-text-muted text-sm">
                      {tool.association.is_enabled ? 'Enabled' : 'Disabled'}
                    </span>
                    <Switch
                      checked={tool.association.is_enabled}
                      onCheckedChange={() => handleToggleEnabled(tool.id, tool.association.is_enabled)}
                      disabled={loadingToolId === tool.id}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDetachTool(tool.id)}
                    disabled={loadingToolId === tool.id}
                    title="Detach tool"
                  >
                    <X className="h-4 w-4 text-red-600" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Available Tools */}
      <div>
        <h4 className="mb-3 text-sm font-semibold">Available Tools ({availableTools.length})</h4>
        {availableTools.length === 0 ? (
          <div className="frost-text-muted rounded-md border border-dashed p-4 text-center text-sm">
            {allTools.length === 0
              ? 'No tools available. Create tools first from the Tools page.'
              : 'All available tools are already attached to this agent.'}
          </div>
        ) : (
          <div className="space-y-2">
            {availableTools.map((tool) => (
              <div
                key={tool.id}
                className="frost-glass border-frost-border hover:bg-frost-glass-strong flex items-center justify-between rounded-md border p-3"
              >
                <div className="flex flex-1 items-center gap-3">
                  <Badge className={getToolTypeColor(tool.tool_type)}>{tool.tool_type.toUpperCase()}</Badge>
                  <div className="flex-1">
                    <div className="font-medium">{tool.display_name}</div>
                    <div className="frost-text-muted text-xs">Function: {tool.name}</div>
                    <div className="frost-text-muted mt-1 text-xs">{tool.description}</div>
                  </div>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleAttachTool(tool.id)}
                  disabled={loadingToolId === tool.id}
                >
                  <Plus className="mr-1 h-4 w-4" />
                  Attach
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default VoiceAgentToolsManager;
