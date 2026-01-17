import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import { Switch } from '@app/components/ui/switch';
import { Badge } from '@app/components/ui/badge';
import { useGetVoiceAgentTools, useGetAgentTools } from '@app/hooks';
import { getVoiceAgentToolsKey, getAgentToolsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { useQueryClient } from '@tanstack/react-query';
import { Plus, X } from 'lucide-react';
import React, { useState } from 'react';

interface VoiceAgentToolsManagerProps {
  appId: string;
  agentId: string;
}

const VoiceAgentToolsManager: React.FC<VoiceAgentToolsManagerProps> = ({ appId, agentId }) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [loadingToolId, setLoadingToolId] = useState<string | null>(null);

  // Fetch all tools
  const { data: allTools = [], isLoading: allToolsLoading } = useGetVoiceAgentTools(appId);

  // Fetch tools attached to this agent
  const { data: agentTools = [], isLoading: agentToolsLoading } = useGetAgentTools(appId, agentId);

  const attachedToolIds = new Set(agentTools.map((t) => t.id));
  const availableTools = allTools.filter((t) => !attachedToolIds.has(t.id));

  const handleToggleEnabled = async (toolId: string, currentEnabled: boolean) => {
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
    return type === 'api' ? 'bg-blue-100 text-blue-800' : 'bg-purple-100 text-purple-800';
  };

  if (allToolsLoading || agentToolsLoading) {
    return (
      <div className="flex justify-center py-4">
        <div className="text-sm text-gray-500">Loading tools...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Attached Tools */}
      <div>
        <h4 className="mb-3 text-sm font-semibold">Attached Tools ({agentTools.length})</h4>
        {agentTools.length === 0 ? (
          <div className="rounded-md border border-dashed p-4 text-center text-sm text-gray-500">
            No tools attached to this agent yet. Add tools from the available tools below.
          </div>
        ) : (
          <div className="space-y-2">
            {agentTools.map((tool) => (
              <div
                key={tool.id}
                className="flex items-center justify-between rounded-md border bg-white p-3 hover:bg-gray-50"
              >
                <div className="flex flex-1 items-center gap-3">
                  <Badge className={getToolTypeColor(tool.tool_type)}>{tool.tool_type.toUpperCase()}</Badge>
                  <div className="flex-1">
                    <div className="font-medium">{tool.display_name}</div>
                    <div className="text-xs text-gray-500">Function: {tool.name}</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-600">
                      {tool.association.is_enabled ? 'Enabled' : 'Disabled'}
                    </span>
                    <Switch
                      checked={tool.association.is_enabled}
                      onCheckedChange={() => handleToggleEnabled(tool.id, tool.association.is_enabled)}
                      disabled={loadingToolId === tool.id}
                    />
                  </div>
                  <Button
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
          <div className="rounded-md border border-dashed p-4 text-center text-sm text-gray-500">
            {allTools.length === 0
              ? 'No tools available. Create tools first from the Tools page.'
              : 'All available tools are already attached to this agent.'}
          </div>
        ) : (
          <div className="space-y-2">
            {availableTools.map((tool) => (
              <div
                key={tool.id}
                className="flex items-center justify-between rounded-md border bg-gray-50 p-3 hover:bg-gray-100"
              >
                <div className="flex flex-1 items-center gap-3">
                  <Badge className={getToolTypeColor(tool.tool_type)}>{tool.tool_type.toUpperCase()}</Badge>
                  <div className="flex-1">
                    <div className="font-medium">{tool.display_name}</div>
                    <div className="text-xs text-gray-500">Function: {tool.name}</div>
                    <div className="mt-1 text-xs text-gray-600">{tool.description}</div>
                  </div>
                </div>
                <Button
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
