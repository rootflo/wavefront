import React, { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useDesignerStore } from '@/store/designerStore';
import { Agent } from '@/types/agent';

const AgentEditor: React.FC = () => {
  const {
    isAgentEditorOpen,
    closeAgentEditor,
    selectedNode,
    updateAgent,
    addAgent,
    config,
  } = useDesignerStore();

  const [formData, setFormData] = useState({
    name: '',
    role: '',
    job: '',
    provider: 'openai' as const,
    modelName: 'gpt-4o-mini',
    temperature: 0.7,
    maxRetries: 3,
    reasoningPattern: 'DIRECT' as const,
    tools: [] as string[],
  });

  const [isNewAgent, setIsNewAgent] = useState(false);

  useEffect(() => {
    if (selectedNode && selectedNode.type === 'agent') {
      const agentData = selectedNode.data as any;
      const agent = agentData.agent;
      setIsNewAgent(false);
      
      setFormData({
        name: agent.name || '',
        role: agent.role || '',
        job: agent.job || '',
        provider: agent.model.provider || 'openai',
        modelName: agent.model.name || 'gpt-4o-mini',
        temperature: agent.settings?.temperature || 0.7,
        maxRetries: agent.settings?.max_retries || 3,
        reasoningPattern: agent.settings?.reasoning_pattern || 'DIRECT',
        tools: agent.tools || [],
      });
    } else if (isAgentEditorOpen) {
      setIsNewAgent(true);
      setFormData({
        name: '',
        role: '',
        job: '',
        provider: 'openai',
        modelName: 'gpt-4o-mini',
        temperature: 0.7,
        maxRetries: 3,
        reasoningPattern: 'DIRECT',
        tools: [],
      });
    }
  }, [selectedNode, isAgentEditorOpen]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    const agent: Agent = {
      id: isNewAgent ? `agent_${Date.now()}` : selectedNode!.id,
      name: formData.name,
      role: formData.role || undefined,
      job: formData.job,
      model: {
        provider: formData.provider,
        name: formData.modelName,
      },
      settings: {
        temperature: formData.temperature,
        max_retries: formData.maxRetries,
        reasoning_pattern: formData.reasoningPattern,
      },
      tools: formData.tools.length > 0 ? formData.tools : undefined,
    };

    if (isNewAgent) {
      addAgent(agent, { x: 100, y: 100 });
    } else {
      updateAgent(agent.id, agent);
    }

    closeAgentEditor();
  };

  const availableModels = config.availableLLMs.filter(
    (llm) => llm.provider === formData.provider
  );

  const handleToolToggle = (toolName: string) => {
    setFormData(prev => ({
      ...prev,
      tools: prev.tools.includes(toolName)
        ? prev.tools.filter(t => t !== toolName)
        : [...prev.tools, toolName]
    }));
  };

  return (
    <Dialog open={isAgentEditorOpen} onOpenChange={closeAgentEditor}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isNewAgent ? 'Create New Agent' : 'Edit Agent'}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                placeholder="e.g., Content Analyzer"
                required
              />
            </div>
            <div>
              <Label htmlFor="role">Role</Label>
              <Input
                id="role"
                value={formData.role}
                onChange={(e) => setFormData(prev => ({ ...prev, role: e.target.value }))}
                placeholder="e.g., Data Analyst"
              />
            </div>
          </div>

          <div>
            <Label htmlFor="job">Job Description *</Label>
            <Textarea
              id="job"
              value={formData.job}
              onChange={(e) => setFormData(prev => ({ ...prev, job: e.target.value }))}
              placeholder="Describe what this agent does..."
              rows={3}
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Provider</Label>
              <Select
                value={formData.provider}
                onValueChange={(value) => {
                  setFormData(prev => ({ 
                    ...prev, 
                    provider: value as any,
                    modelName: config.availableLLMs.find(llm => llm.provider === value)?.name || ''
                  }));
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai">OpenAI</SelectItem>
                  <SelectItem value="anthropic">Anthropic</SelectItem>
                  <SelectItem value="gemini">Google Gemini</SelectItem>
                  <SelectItem value="ollama">Ollama</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Model</Label>
              <Select
                value={formData.modelName}
                onValueChange={(value) => setFormData(prev => ({ ...prev, modelName: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((model) => (
                    <SelectItem key={model.name} value={model.name}>
                      {model.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label>Temperature</Label>
              <Input
                type="number"
                step="0.1"
                min="0"
                max="2"
                value={formData.temperature}
                onChange={(e) => setFormData(prev => ({ ...prev, temperature: parseFloat(e.target.value) }))}
              />
            </div>
            <div>
              <Label>Max Retries</Label>
              <Input
                type="number"
                min="0"
                max="10"
                value={formData.maxRetries}
                onChange={(e) => setFormData(prev => ({ ...prev, maxRetries: parseInt(e.target.value) }))}
              />
            </div>
            <div>
              <Label>Reasoning Pattern</Label>
              <Select
                value={formData.reasoningPattern}
                onValueChange={(value) => setFormData(prev => ({ ...prev, reasoningPattern: value as any }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="DIRECT">Direct</SelectItem>
                  <SelectItem value="COT">Chain of Thought</SelectItem>
                  <SelectItem value="REACT">ReAct</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label>Available Tools</Label>
            <div className="grid grid-cols-2 gap-2 mt-2 max-h-32 overflow-y-auto">
              {config.availableTools.map((tool) => (
                <label key={tool.name} className="flex items-center space-x-2 text-sm">
                  <input
                    type="checkbox"
                    checked={formData.tools.includes(tool.name)}
                    onChange={() => handleToolToggle(tool.name)}
                    className="rounded"
                  />
                  <span>{tool.name}</span>
                </label>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeAgentEditor}>
              Cancel
            </Button>
            <Button type="submit">
              {isNewAgent ? 'Create Agent' : 'Update Agent'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default AgentEditor;
