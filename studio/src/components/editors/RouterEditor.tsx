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
import { Router } from '@/types/agent';

const RouterEditor: React.FC = () => {
  const {
    isRouterEditorOpen,
    closeRouterEditor,
    selectedNode,
    updateRouter,
    addRouter,
    config,
  } = useDesignerStore();

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    type: 'smart' as 'smart' | 'task_classifier' | 'conversation_analysis' | 'reflection' | 'plan_execute' | 'custom',
    provider: 'openai' as 'openai' | 'anthropic' | 'gemini' | 'ollama',
    modelName: 'gpt-4o-mini',
    temperature: 0.3,
    fallbackStrategy: 'first' as 'first' | 'last' | 'random',
    routingOptions: {} as Record<string, string>,
    taskCategories: {} as Record<string, {
      description: string;
      keywords: string[];
      examples: string[];
    }>,
    flowPattern: [] as string[],
    allowEarlyExit: false,
  });

  const [routingOptionKey, setRoutingOptionKey] = useState('');
  const [routingOptionValue, setRoutingOptionValue] = useState('');
  const [taskCategoryKey, setTaskCategoryKey] = useState('');
  const [taskCategoryDesc, setTaskCategoryDesc] = useState('');
  const [taskKeywords, setTaskKeywords] = useState('');
  const [taskExamples, setTaskExamples] = useState('');
  const [flowAgent, setFlowAgent] = useState('');
  const [isNewRouter, setIsNewRouter] = useState(false);

  useEffect(() => {
    if (selectedNode && selectedNode.type === 'router') {
      const routerData = selectedNode.data as any;
      const router = routerData.router;
      setIsNewRouter(false);
      
      setFormData({
        name: router.name || '',
        description: router.description || '',
        type: router.type || 'smart',
        provider: router.model?.provider || 'openai',
        modelName: router.model?.name || 'gpt-4o-mini',
        temperature: router.settings?.temperature || 0.3,
        fallbackStrategy: router.settings?.fallback_strategy || 'first',
        routingOptions: router.routing_options || {},
        taskCategories: router.task_categories || {},
        flowPattern: router.flow_pattern || [],
        allowEarlyExit: router.settings?.allow_early_exit || false,
      });
      
      // Clear the input fields when editing
      setRoutingOptionKey('');
      setRoutingOptionValue('');
    } else if (isRouterEditorOpen) {
      setIsNewRouter(true);
      setFormData({
        name: '',
        description: '',
        type: 'smart',
        provider: 'openai',
        modelName: 'gpt-4o-mini',
        temperature: 0.3,
        fallbackStrategy: 'first',
        routingOptions: {},
        taskCategories: {},
        flowPattern: [],
        allowEarlyExit: false,
      });
    }
  }, [selectedNode, isRouterEditorOpen]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    const router: Router = {
      id: isNewRouter ? `router_${Date.now()}` : selectedNode!.id,
      name: formData.name,
      description: formData.description,
      type: formData.type,
      model: formData.type !== 'custom' ? {
        provider: formData.provider,
        name: formData.modelName,
      } : undefined,
      settings: formData.type !== 'custom' ? {
        temperature: formData.temperature,
        fallback_strategy: formData.fallbackStrategy,
        ...(formData.type === 'reflection' && { allow_early_exit: formData.allowEarlyExit }),
      } : undefined,
      routing_options: (formData.type === 'smart' || formData.type === 'conversation_analysis') 
        ? formData.routingOptions : undefined,
      task_categories: formData.type === 'task_classifier' 
        ? formData.taskCategories : undefined,
      flow_pattern: formData.type === 'reflection' 
        ? formData.flowPattern : undefined,
    };

    if (isNewRouter) {
      addRouter(router, { x: 100, y: 100 });
    } else {
      updateRouter(router.id!, router);
    }

    closeRouterEditor();
  };

  const addRoutingOption = () => {
    const trimmedKey = routingOptionKey.trim();
    const trimmedValue = routingOptionValue.trim();
    
    if (trimmedKey && trimmedValue) {
      // Check if key already exists
      if (formData.routingOptions[trimmedKey]) {
        alert(`Routing option "${trimmedKey}" already exists. Please use a different name.`);
        return;
      }
      
      setFormData(prev => ({
        ...prev,
        routingOptions: {
          ...prev.routingOptions,
          [trimmedKey]: trimmedValue,
        },
      }));
      setRoutingOptionKey('');
      setRoutingOptionValue('');
    }
  };

  const removeRoutingOption = (key: string) => {
    setFormData(prev => {
      const newOptions = { ...prev.routingOptions };
      delete newOptions[key];
      return { ...prev, routingOptions: newOptions };
    });
  };

  const addTaskCategory = () => {
    if (taskCategoryKey && taskCategoryDesc) {
      setFormData(prev => ({
        ...prev,
        taskCategories: {
          ...prev.taskCategories,
          [taskCategoryKey]: {
            description: taskCategoryDesc,
            keywords: taskKeywords.split(',').map(k => k.trim()).filter(k => k),
            examples: taskExamples.split(',').map(e => e.trim()).filter(e => e),
          },
        },
      }));
      setTaskCategoryKey('');
      setTaskCategoryDesc('');
      setTaskKeywords('');
      setTaskExamples('');
    }
  };

  const removeTaskCategory = (key: string) => {
    setFormData(prev => {
      const newCategories = { ...prev.taskCategories };
      delete newCategories[key];
      return { ...prev, taskCategories: newCategories };
    });
  };

  const addFlowAgent = () => {
    if (flowAgent) {
      setFormData(prev => ({
        ...prev,
        flowPattern: [...prev.flowPattern, flowAgent],
      }));
      setFlowAgent('');
    }
  };

  const removeFlowAgent = (index: number) => {
    setFormData(prev => ({
      ...prev,
      flowPattern: prev.flowPattern.filter((_, i) => i !== index),
    }));
  };

  const availableModels = config.availableLLMs.filter(
    (llm) => llm.provider === formData.provider
  );

  return (
    <Dialog open={isRouterEditorOpen} onOpenChange={closeRouterEditor}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isNewRouter ? 'Create New Router' : 'Edit Router'}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="name">Router Name *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                placeholder="e.g., Content Router"
                required
              />
            </div>
            <div>
              <Label>Router Type</Label>
              <Select
                value={formData.type}
                onValueChange={(value) => setFormData(prev => ({ ...prev, type: value as any }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="smart">Smart Router</SelectItem>
                  <SelectItem value="task_classifier">Task Classifier</SelectItem>
                  <SelectItem value="conversation_analysis">Conversation Analysis</SelectItem>
                  <SelectItem value="reflection">Reflection Router</SelectItem>
                  <SelectItem value="plan_execute">Plan Execute Router</SelectItem>
                  <SelectItem value="custom">Custom Router</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label htmlFor="description">Description *</Label>
            <Textarea
              id="description"
              value={formData.description}
              onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
              placeholder="Describe how this router works..."
              rows={3}
              required
            />
          </div>

          {formData.type !== 'custom' && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>LLM Provider</Label>
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

              <div className="grid grid-cols-2 gap-4">
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
                  <Label>Fallback Strategy</Label>
                  <Select
                    value={formData.fallbackStrategy}
                    onValueChange={(value) => setFormData(prev => ({ ...prev, fallbackStrategy: value as any }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="first">First Option</SelectItem>
                      <SelectItem value="last">Last Option</SelectItem>
                      <SelectItem value="random">Random Option</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </>
          )}

          {/* Smart Router and Conversation Analysis Configuration */}
          {(formData.type === 'smart' || formData.type === 'conversation_analysis') && (
            <div>
              <Label>Routing Options</Label>
              <div className="space-y-2">
                <div className="grid grid-cols-12 gap-2 items-center">
                  <Input
                    placeholder="Agent/Tool name (e.g., technical_agent)"
                    value={routingOptionKey}
                    onChange={(e) => setRoutingOptionKey(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && routingOptionKey.trim() && routingOptionValue.trim()) {
                        e.preventDefault();
                        addRoutingOption();
                      }
                    }}
                    className="col-span-4"
                  />
                  <Input
                    placeholder="Description of when to route here"
                    value={routingOptionValue}
                    onChange={(e) => setRoutingOptionValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && routingOptionKey.trim() && routingOptionValue.trim()) {
                        e.preventDefault();
                        addRoutingOption();
                      }
                    }}
                    className="col-span-6"
                  />
                  <Button 
                    type="button" 
                    onClick={addRoutingOption} 
                    variant="outline"
                    disabled={!routingOptionKey.trim() || !routingOptionValue.trim()}
                    className="col-span-2"
                  >
                    Add
                  </Button>
                </div>
                
                {/* Helpful instructions */}
                <div className="text-xs text-gray-500 mt-1">
                  Add routing targets and descriptions. Example: "technical_agent" → "Handle technical questions and documentation"
                </div>
                
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {Object.keys(formData.routingOptions).length === 0 ? (
                    <div className="text-sm text-gray-500 italic p-2">
                      No routing options added yet. Add agents or tools that this router should route to.
                    </div>
                  ) : (
                    Object.entries(formData.routingOptions).map(([key, value]) => (
                      <div key={key} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                        <div className="text-sm">
                          <span className="font-medium">{key}:</span> {value}
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => removeRoutingOption(key)}
                          className="text-red-600 hover:text-red-800"
                        >
                          ×
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Task Classifier Configuration */}
          {formData.type === 'task_classifier' && (
            <div>
              <Label>Task Categories</Label>
              <div className="space-y-4">
                <div className="border rounded-lg p-4 bg-gray-50">
                  <h4 className="font-medium text-sm mb-3">Add New Category</h4>
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-2">
                      <Input
                        placeholder="Category name (e.g., math_solver)"
                        value={taskCategoryKey}
                        onChange={(e) => setTaskCategoryKey(e.target.value)}
                      />
                      <Input
                        placeholder="Description"
                        value={taskCategoryDesc}
                        onChange={(e) => setTaskCategoryDesc(e.target.value)}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <Input
                        placeholder="Keywords (comma-separated)"
                        value={taskKeywords}
                        onChange={(e) => setTaskKeywords(e.target.value)}
                      />
                      <Input
                        placeholder="Examples (comma-separated)"
                        value={taskExamples}
                        onChange={(e) => setTaskExamples(e.target.value)}
                      />
                    </div>
                    <Button type="button" onClick={addTaskCategory} variant="outline" size="sm">
                      Add Category
                    </Button>
                  </div>
                </div>
                
                <div className="space-y-2 max-h-40 overflow-y-auto">
                  {Object.entries(formData.taskCategories).map(([key, category]) => (
                    <div key={key} className="p-3 bg-white border rounded">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium text-sm">{key}</span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => removeTaskCategory(key)}
                          className="text-red-600 hover:text-red-800"
                        >
                          ×
                        </Button>
                      </div>
                      <p className="text-xs text-gray-600 mb-1">{category.description}</p>
                      <div className="text-xs text-gray-500">
                        <span>Keywords: {category.keywords.join(', ')}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Reflection Router Configuration */}
          {formData.type === 'reflection' && (
            <div>
              <Label>Flow Pattern</Label>
              <div className="space-y-2">
                <div className="flex gap-2">
                  <Input
                    placeholder="Agent name (e.g., main_agent, critic)"
                    value={flowAgent}
                    onChange={(e) => setFlowAgent(e.target.value)}
                    className="flex-1"
                  />
                  <Button type="button" onClick={addFlowAgent} variant="outline">
                    Add
                  </Button>
                </div>
                
                <div className="p-3 bg-gray-50 rounded">
                  <Label className="text-xs text-gray-600">Pattern: {formData.flowPattern.join(' → ') || 'No pattern defined'}</Label>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {formData.flowPattern.map((agent, index) => (
                      <span key={index} className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded">
                        {agent}
                        <button
                          type="button"
                          onClick={() => removeFlowAgent(index)}
                          className="ml-1 text-blue-600 hover:text-blue-800"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="allowEarlyExit"
                    checked={formData.allowEarlyExit}
                    onChange={(e) => setFormData(prev => ({ ...prev, allowEarlyExit: e.target.checked }))}
                    className="rounded"
                  />
                  <Label htmlFor="allowEarlyExit" className="text-sm">Allow early exit from pattern</Label>
                </div>
              </div>
            </div>
          )}

          {/* Plan Execute Router Configuration */}
          {formData.type === 'plan_execute' && (
            <div>
              <Label>Plan Execute Configuration</Label>
              <div className="p-4 bg-blue-50 rounded-lg">
                <h4 className="font-medium text-sm text-blue-800 mb-2">Plan Execute Router</h4>
                <p className="text-sm text-blue-700 mb-3">
                  This router implements Cursor-style plan-and-execute workflows. It automatically coordinates 
                  between planning, execution, and review phases.
                </p>
                <div className="text-xs text-blue-600">
                  • Planner: Creates detailed execution plans<br />
                  • Executor: Executes individual steps<br />
                  • Reviewer: Reviews and validates completed work
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeRouterEditor}>
              Cancel
            </Button>
            <Button type="submit">
              {isNewRouter ? 'Create Router' : 'Update Router'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default RouterEditor;
