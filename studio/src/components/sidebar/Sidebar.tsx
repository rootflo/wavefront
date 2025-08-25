import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Bot, Wrench, Search, Plus, Route } from 'lucide-react';
import { useDesignerStore } from '@/store/designerStore';
import { Agent, Tool, Router } from '@/types/agent';

const Sidebar: React.FC = () => {
  const { 
    config, 
    addAgent, 
    addTool, 
    addRouter, 
    openAgentEditor, 
    openRouterEditor, 
    onConnect,
    setStartNode,
    addEndNode
  } = useDesignerStore();
  const [searchTerm, setSearchTerm] = useState('');

  const filteredTools = config.availableTools.filter((tool) =>
    tool.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    tool.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleAddAgent = () => {
    openAgentEditor();
  };

  const handleAddRouter = () => {
    openRouterEditor();
  };

  const handleAddTool = (tool: Tool) => {
    const position = {
      x: Math.random() * 400 + 100,
      y: Math.random() * 400 + 100,
    };
    addTool(tool, position);
  };

  const createQuickAgent = (template: string) => {
    const templates = {
      analyzer: {
        name: 'Content Analyzer',
        role: 'Content Analyst',
        job: 'Analyze content and extract key insights, themes, and important information.',
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
      },
      summarizer: {
        name: 'Summarizer',
        role: 'Summary Generator',
        job: 'Create concise, actionable summaries from analysis and content.',
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
      },
      classifier: {
        name: 'Classifier',
        role: 'Content Classifier',
        job: 'Classify content into predefined categories and route accordingly.',
        model: { provider: 'anthropic' as const, name: 'claude-3-5-sonnet-20240620' },
      },
      researcher: {
        name: 'Researcher',
        role: 'Research Specialist',
        job: 'Research topics and gather comprehensive information using available tools.',
        model: { provider: 'openai' as const, name: 'gpt-4o' },
        tools: ['web_search'],
      },
      planner: {
        name: 'Planner Agent',
        role: 'Task Planner',
        job: 'You are an expert project planner who breaks down complex tasks into detailed, sequential steps. Create comprehensive execution plans with clear dependencies and assigned agents. When given a task, analyze it thoroughly and create a structured plan that can be executed step by step. Focus on logical sequencing, resource allocation, and clear deliverables for each step.',
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
        settings: { temperature: 0.3, reasoning_pattern: 'COT' as const },
      },
      executor: {
        name: 'Executor Agent',
        role: 'Task Executor',
        job: 'You are a task executor who implements plans step by step. Execute development tasks, research activities, or any assigned work with precision and attention to detail. Report on progress, identify blockers, and ensure each step is completed thoroughly before moving to the next. Focus on delivering high-quality results that meet the specified requirements.',
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
        settings: { temperature: 0.5, reasoning_pattern: 'DIRECT' as const },
      },
      critic: {
        name: 'Critic Agent',
        role: 'Quality Critic',
        job: 'You are a constructive critic who reviews work and provides actionable feedback. Analyze outputs for accuracy, completeness, clarity, and areas for improvement. Provide specific, detailed feedback that helps improve the quality of work. Focus on: logical consistency, thoroughness, clarity of communication, and alignment with requirements. Be constructive and specific in your criticism.',
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
        settings: { temperature: 0.3, reasoning_pattern: 'COT' as const },
      },
      finalizer: {
        name: 'Finalizer Agent',
        role: 'Quality Finalizer',
        job: 'You are the final agent responsible for polishing and finalizing work. Take refined outputs and ensure they meet high quality standards. Format professionally, add final touches, ensure consistency, and prepare the final deliverable. Focus on presentation, completeness, and professional polish while maintaining the core substance of the work.',
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
        settings: { temperature: 0.5, reasoning_pattern: 'DIRECT' as const },
      },
    };

    const template_config = templates[template as keyof typeof templates];
    if (template_config) {
      const agent: Agent = {
        id: `agent_${Date.now()}`,
        ...template_config,
      };

      const position = {
        x: Math.random() * 400 + 100,
        y: Math.random() * 400 + 100,
      };

      addAgent(agent, position);
    }
  };

  const createQuickRouter = (template: string) => {
    const routerTemplates = {
      smart: {
        name: 'Smart Router',
        description: 'Intelligent routing based on content analysis using LLM',
        type: 'smart' as const,
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
        settings: { temperature: 0.3, fallback_strategy: 'first' as const },
        routing_options: {
          'technical_agent': 'Handle technical questions and documentation',
          'business_agent': 'Handle business questions and strategy',
          'general_agent': 'Handle general questions and conversations',
        },
      },
      classifier: {
        name: 'Task Classifier',
        description: 'Classify tasks based on keywords and examples',
        type: 'task_classifier' as const,
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
        settings: { temperature: 0.2, fallback_strategy: 'first' as const },
      },
      conversation: {
        name: 'Conversation Router',
        description: 'Route based on conversation flow analysis',
        type: 'conversation_analysis' as const,
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
        settings: { temperature: 0.1, fallback_strategy: 'first' as const, analysis_depth: 3 },
        routing_logic: {
          'planner': 'Route here when planning is needed',
          'executor': 'Route here when execution is needed',
          'reviewer': 'Route here when review is needed',
        },
      },
      reflection: {
        name: 'Reflection Router',
        description: 'A→B→A pattern for reflection workflows',
        type: 'reflection' as const,
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
        settings: { temperature: 0.2, fallback_strategy: 'first' as const, allow_early_exit: false },
        flow_pattern: ['main_agent', 'critic', 'main_agent'],
      },
      plan_execute: {
        name: 'Plan Execute Router',
        description: 'Cursor-style plan-and-execute workflows',
        type: 'plan_execute' as const,
        model: { provider: 'openai' as const, name: 'gpt-4o-mini' },
        settings: { temperature: 0.1, fallback_strategy: 'first' as const },
      },
    };

    const template_config = routerTemplates[template as keyof typeof routerTemplates];
    if (template_config) {
      const router: Router = {
        id: `router_${Date.now()}`,
        ...template_config,
      };

      const position = {
        x: Math.random() * 400 + 100,
        y: Math.random() * 400 + 100,
      };

      addRouter(router, position);
    }
  };

  const createPlanExecuteWorkflow = () => {
    const timestamp = Date.now();
    
    // Create planner agent
    const planner: Agent = {
      id: `planner_${timestamp}`,
      name: 'Planner',
      role: 'Task Planner',
      job: 'You are an expert project planner who breaks down complex tasks into detailed, sequential steps. Create comprehensive execution plans with clear dependencies and assigned agents. When given a task, analyze it thoroughly and create a structured plan that can be executed step by step.',
      model: { provider: 'openai', name: 'gpt-4o-mini' },
      settings: { temperature: 0.3, reasoning_pattern: 'COT' },
    };

    // Create executor agent
    const executor: Agent = {
      id: `executor_${timestamp}`,
      name: 'Executor',
      role: 'Task Executor',
      job: 'You are a task executor who implements plans step by step. Execute development tasks, research activities, or any assigned work with precision and attention to detail. Report on progress and ensure each step is completed thoroughly.',
      model: { provider: 'openai', name: 'gpt-4o-mini' },
      settings: { temperature: 0.5, reasoning_pattern: 'DIRECT' },
    };

    // Create reviewer agent
    const reviewer: Agent = {
      id: `reviewer_${timestamp}`,
      name: 'Reviewer',
      role: 'Quality Reviewer',
      job: 'You are a quality reviewer who validates completed work. Review implementations for correctness, completeness, and quality. Provide final approval or request improvements. Ensure all requirements are met.',
      model: { provider: 'openai', name: 'gpt-4o-mini' },
      settings: { temperature: 0.2, reasoning_pattern: 'COT' },
    };

    // Create plan-execute router
    const planExecuteRouter: Router = {
      id: `plan_execute_router_${timestamp}`,
      name: 'Plan Execute Router',
      description: 'Coordinates plan-and-execute workflow pattern',
      type: 'plan_execute',
      model: { provider: 'openai', name: 'gpt-4o-mini' },
      settings: { temperature: 0.2, fallback_strategy: 'first' },
    };

    // Add agents and router to the workflow
    addAgent(planner, { x: 100, y: 100 });
    addAgent(executor, { x: 400, y: 100 });
    addAgent(reviewer, { x: 700, y: 100 });
    addRouter(planExecuteRouter, { x: 400, y: 250 });

    // Create edges for plan-execute pattern (agents connect through router)
    setTimeout(() => {
      // Agents connect through the router - router coordinates the workflow
      
      // Planner → Router
      onConnect({
        source: `planner_${timestamp}`,
        target: `plan_execute_router_${timestamp}`,
        sourceHandle: null,
        targetHandle: null,
      });
      
      // Router → Executor
      onConnect({
        source: `plan_execute_router_${timestamp}`,
        target: `executor_${timestamp}`,
        sourceHandle: null,
        targetHandle: null,
      });
      
      // Router → Reviewer
      onConnect({
        source: `plan_execute_router_${timestamp}`,
        target: `reviewer_${timestamp}`,
        sourceHandle: null,
        targetHandle: null,
      });
      
      // Executor → Router (for coordination)
      onConnect({
        source: `executor_${timestamp}`,
        target: `plan_execute_router_${timestamp}`,
        sourceHandle: null,
        targetHandle: null,
      });

      // Set initial start and end nodes for plan-execute workflow
      setStartNode(`planner_${timestamp}`);
      addEndNode(`reviewer_${timestamp}`);
      
      // The router connections will be converted to proper YAML workflow edges
      // with router fields by the YAML export logic
    }, 100);
  };

  const createReflectionWorkflow = () => {
    const timestamp = Date.now();
    
    // Create main agent
    const mainAgent: Agent = {
      id: `main_agent_${timestamp}`,
      name: 'Main Agent',
      role: 'Main Agent',
      job: 'You are the main agent responsible for analyzing tasks and creating initial solutions. When you receive input, analyze it thoroughly and provide an initial response. If you receive feedback from the critic, incorporate it to improve your work.',
      model: { provider: 'openai', name: 'gpt-4o-mini' },
      settings: { temperature: 0.7, reasoning_pattern: 'COT' },
    };

    // Create critic agent
    const critic: Agent = {
      id: `critic_${timestamp}`,
      name: 'Critic',
      role: 'Quality Critic',
      job: 'You are a constructive critic who reviews work and provides actionable feedback. Analyze outputs for accuracy, completeness, clarity, and areas for improvement. Provide specific, detailed feedback that helps improve the quality of work.',
      model: { provider: 'openai', name: 'gpt-4o-mini' },
      settings: { temperature: 0.3, reasoning_pattern: 'COT' },
    };

    // Create finalizer agent
    const finalizer: Agent = {
      id: `finalizer_${timestamp}`,
      name: 'Finalizer',
      role: 'Quality Finalizer',
      job: 'You are the final agent responsible for polishing and finalizing work. Take refined outputs and ensure they meet high quality standards. Format professionally and prepare the final deliverable.',
      model: { provider: 'openai', name: 'gpt-4o-mini' },
      settings: { temperature: 0.5, reasoning_pattern: 'DIRECT' },
    };

    // Create reflection router
    const reflectionRouter: Router = {
      id: `reflection_router_${timestamp}`,
      name: 'Reflection Router',
      description: 'Coordinates A→B→A→C reflection workflow pattern',
      type: 'reflection',
      model: { provider: 'openai', name: 'gpt-4o-mini' },
      settings: { temperature: 0.2, fallback_strategy: 'first', allow_early_exit: false },
      flow_pattern: ['main_agent', 'critic', 'main_agent', 'finalizer'],
    };

    // Add agents and router to the workflow
    addAgent(mainAgent, { x: 100, y: 100 });
    addAgent(critic, { x: 400, y: 100 });
    addAgent(finalizer, { x: 700, y: 100 });
    addRouter(reflectionRouter, { x: 400, y: 250 });

    // Create edges for reflection pattern (agents connect through router)
    setTimeout(() => {
      // Agents connect through the router - router is the coordination hub
      
      // Main Agent → Router
      onConnect({
        source: `main_agent_${timestamp}`,
        target: `reflection_router_${timestamp}`,
        sourceHandle: null,
        targetHandle: null,
      });
      
      // Router → Critic
      onConnect({
        source: `reflection_router_${timestamp}`,
        target: `critic_${timestamp}`,
        sourceHandle: null,
        targetHandle: null,
      });
      
      // Router → Finalizer
      onConnect({
        source: `reflection_router_${timestamp}`,
        target: `finalizer_${timestamp}`,
        sourceHandle: null,
        targetHandle: null,
      });
      
      // Critic → Router (for reflection back)
      onConnect({
        source: `critic_${timestamp}`,
        target: `reflection_router_${timestamp}`,
        sourceHandle: null,
        targetHandle: null,
      });

      // Set initial start and end nodes for reflection workflow
      setStartNode(`main_agent_${timestamp}`);
      addEndNode(`finalizer_${timestamp}`);
      
      // The router connections will be converted to proper YAML workflow edges
      // with router fields by the YAML export logic
    }, 100);
  };

  return (
    <div className="w-80 bg-white border-r border-gray-200 overflow-y-auto">
      <div className="p-4 space-y-6">
        {/* Quick Start */}
        <div>
          <h3 className="font-medium text-sm text-gray-700 mb-3">Quick Start</h3>
          <div className="text-sm text-gray-600 mb-4">
            Welcome to Flo AI Studio! Create agents and connect them to build powerful AI workflows.
          </div>
          <div className="grid grid-cols-2 gap-2 mb-4">
            <Button
              onClick={handleAddAgent}
              variant="outline"
              size="sm"
            >
              <Bot className="w-4 h-4 mr-1" />
              Agent
            </Button>
            <Button
              onClick={handleAddRouter}
              variant="outline"
              size="sm"
            >
              <Route className="w-4 h-4 mr-1" />
              Router
            </Button>
          </div>
        </div>

        {/* Quick Templates */}
        <div>
          <h3 className="font-medium text-sm text-gray-700 mb-3">Agent Templates</h3>
          
          {/* Core Agents */}
          <div className="mb-4">
            <h4 className="font-medium text-xs text-gray-600 mb-2">Core Agents</h4>
            <div className="space-y-2">
              {[
                { key: 'analyzer', name: 'Content Analyzer', desc: 'Analyze and extract insights' },
                { key: 'summarizer', name: 'Summarizer', desc: 'Create concise summaries' },
                { key: 'classifier', name: 'Classifier', desc: 'Classify and route content' },
                { key: 'researcher', name: 'Researcher', desc: 'Research with tools' },
              ].map((template) => (
                <div
                  key={template.key}
                  className="p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => createQuickAgent(template.key)}
                >
                  <div className="flex items-center mb-1">
                    <Bot className="w-4 h-4 text-blue-600 mr-2" />
                    <span className="font-medium text-sm">{template.name}</span>
                  </div>
                  <p className="text-xs text-gray-600">{template.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Advanced Pattern Agents */}
          <div>
            <h4 className="font-medium text-xs text-gray-600 mb-2">Advanced Pattern Agents</h4>
            <div className="space-y-2">
              {[
                { key: 'planner', name: 'Planner Agent', desc: 'Break down tasks into execution plans' },
                { key: 'executor', name: 'Executor Agent', desc: 'Execute plans step by step' },
                { key: 'critic', name: 'Critic Agent', desc: 'Provide constructive feedback' },
                { key: 'finalizer', name: 'Finalizer Agent', desc: 'Polish and finalize outputs' },
              ].map((template) => (
                <div
                  key={template.key}
                  className="p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => createQuickAgent(template.key)}
                >
                  <div className="flex items-center mb-1">
                    <Bot className="w-4 h-4 text-purple-600 mr-2" />
                    <span className="font-medium text-sm">{template.name}</span>
                  </div>
                  <p className="text-xs text-gray-600">{template.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Router Templates */}
        <div>
          <h3 className="font-medium text-sm text-gray-700 mb-3">Router Templates</h3>
          <div className="space-y-2">
            {[
              { key: 'smart', name: 'Smart Router', desc: 'LLM-powered intelligent routing based on content' },
              { key: 'classifier', name: 'Task Classifier', desc: 'Route based on task categories and keywords' },
              { key: 'conversation', name: 'Conversation Router', desc: 'Route based on conversation context analysis' },
              { key: 'reflection', name: 'Reflection Router', desc: 'A→B→A→C reflection patterns (needs main+critic agents)' },
              { key: 'plan_execute', name: 'Plan Execute Router', desc: 'Plan-and-execute workflows (needs planner+executor agents)' },
            ].map((template) => (
              <div
                key={template.key}
                className="p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors"
                onClick={() => createQuickRouter(template.key)}
              >
                <div className="flex items-center mb-1">
                  <Route className="w-4 h-4 text-purple-600 mr-2" />
                  <span className="font-medium text-sm">{template.name}</span>
                </div>
                <p className="text-xs text-gray-600">{template.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Available Tools */}
        <div>
          <h3 className="font-medium text-sm text-gray-700 mb-3">Available Tools</h3>
          <div className="relative mb-3">
            <Search className="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
            <Input
              placeholder="Search tools..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>

          <div className="space-y-2 max-h-60 overflow-y-auto">
            {filteredTools.map((tool) => (
              <div
                key={tool.name}
                className="p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors"
                onClick={() => handleAddTool(tool)}
              >
                <div className="flex items-center mb-1">
                  <Wrench className="w-4 h-4 text-orange-600 mr-2" />
                  <span className="font-medium text-sm">{tool.name}</span>
                </div>
                <p className="text-xs text-gray-600 line-clamp-2">{tool.description}</p>
              </div>
            ))}
          </div>

          {filteredTools.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              <Wrench className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No tools found</p>
            </div>
          )}
        </div>

        {/* Quick Workflow Templates */}
        <div>
          <h3 className="font-medium text-sm text-gray-700 mb-3">Quick Workflows</h3>
          <div className="space-y-2">
            <button
              onClick={() => createPlanExecuteWorkflow()}
              className="w-full p-3 border border-green-200 rounded-lg bg-green-50 hover:bg-green-100 transition-colors text-left"
            >
              <div className="flex items-center mb-1">
                <Plus className="w-4 h-4 text-green-600 mr-2" />
                <span className="font-medium text-sm text-green-800">Plan-Execute Workflow</span>
              </div>
              <p className="text-xs text-green-700">Creates planner + executor + reviewer agents with plan-execute router</p>
            </button>
            
            <button
              onClick={() => createReflectionWorkflow()}
              className="w-full p-3 border border-indigo-200 rounded-lg bg-indigo-50 hover:bg-indigo-100 transition-colors text-left"
            >
              <div className="flex items-center mb-1">
                <Plus className="w-4 h-4 text-indigo-600 mr-2" />
                <span className="font-medium text-sm text-indigo-800">Reflection Workflow</span>
              </div>
              <p className="text-xs text-indigo-700">Creates main + critic + finalizer agents with reflection router</p>
            </button>
          </div>
        </div>

        {/* Getting Started */}
        <div className="border rounded-lg p-4 bg-blue-50">
          <h4 className="font-medium text-sm mb-2 text-blue-800">Getting Started</h4>
          <ol className="text-sm text-blue-700 space-y-1">
            <li>1. Try quick workflows above for advanced patterns</li>
            <li>2. Or create agents using templates below</li>
            <li>3. Connect agents by dragging from output to input</li>
            <li>4. Add routers for intelligent routing</li>
            <li>5. Export as YAML when ready</li>
          </ol>
          <div className="mt-3 p-2 bg-blue-100 rounded text-xs text-blue-800">
            💡 <strong>Smart Routing:</strong> Reflection & Plan-Execute routers automatically track execution context to prevent infinite loops and manage complex flow patterns intelligently.
          </div>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
