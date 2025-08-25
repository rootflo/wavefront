import React, { useState, useEffect } from 'react';
import { AlertCircle, AlertTriangle, Info, CheckCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { useDesignerStore } from '@/store/designerStore';
import { validateWorkflow, ValidationResult, ValidationIssue, getValidationSummary } from '@/utils/workflowValidation';
import { cn } from '@/lib/utils';

const ValidationPanel: React.FC = () => {
  const { nodes, edges, setSelectedNode, setSelectedEdge, startNodeId, endNodeIds } = useDesignerStore();
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['errors']));

  useEffect(() => {
    if (nodes.length > 0 || edges.length > 0) {
      const result = validateWorkflow(nodes, edges, startNodeId, endNodeIds);
      setValidationResult(result);
    } else {
      setValidationResult(null);
    }
  }, [nodes, edges, startNodeId, endNodeIds]);

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(section)) {
      newExpanded.delete(section);
    } else {
      newExpanded.add(section);
    }
    setExpandedSections(newExpanded);
  };

  const handleIssueClick = (issue: ValidationIssue) => {
    if (issue.nodeId) {
      const node = nodes.find(n => n.id === issue.nodeId);
      if (node) {
        setSelectedNode(node);
      }
    } else if (issue.edgeId) {
      const edge = edges.find(e => e.id === issue.edgeId);
      if (edge) {
        setSelectedEdge(edge);
      }
    }
  };

  const getIssueIcon = (type: ValidationIssue['type']) => {
    switch (type) {
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-500" />;
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-yellow-500" />;
      case 'info':
        return <Info className="w-4 h-4 text-blue-500" />;
      default:
        return <Info className="w-4 h-4 text-gray-500" />;
    }
  };

  const IssueSection: React.FC<{
    title: string;
    issues: ValidationIssue[];
    sectionKey: string;
  }> = ({ title, issues, sectionKey }) => {
    const isExpanded = expandedSections.has(sectionKey);

    if (issues.length === 0) return null;

    return (
      <div className="border-b border-gray-200 last:border-b-0">
        <button
          onClick={() => toggleSection(sectionKey)}
          className="w-full flex items-center justify-between p-3 hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center gap-2">
            {isExpanded ? (
              <ChevronDown className="w-4 h-4 text-gray-500" />
            ) : (
              <ChevronRight className="w-4 h-4 text-gray-500" />
            )}
            <span className="font-medium text-sm text-gray-800">
              {title} ({issues.length})
            </span>
          </div>
        </button>
        
        {isExpanded && (
          <div className="pb-3">
            {issues.map((issue) => (
              <div
                key={issue.id}
                onClick={() => handleIssueClick(issue)}
                className={cn(
                  "mx-3 p-2 rounded cursor-pointer transition-colors",
                  "hover:bg-gray-100 border-l-2",
                  issue.type === 'error' && "border-red-300 bg-red-50",
                  issue.type === 'warning' && "border-yellow-300 bg-yellow-50",
                  issue.type === 'info' && "border-blue-300 bg-blue-50"
                )}
              >
                <div className="flex items-start gap-2">
                  {getIssueIcon(issue.type)}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-800">{issue.message}</p>
                    {(issue.nodeId || issue.edgeId) && (
                      <p className="text-xs text-gray-500 mt-1">
                        {issue.nodeId ? `Node: ${issue.nodeId}` : `Edge: ${issue.edgeId}`}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  if (!validationResult) {
    return (
      <div className="w-80 bg-white border-l border-gray-200 flex items-center justify-center">
        <div className="text-center text-gray-500 p-4">
          <Info className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Create agents to see validation results</p>
        </div>
      </div>
    );
  }

  const { issues, warnings, suggestions, isValid } = validationResult;

  return (
    <div className="w-80 bg-white border-l border-gray-200 flex flex-col">
      {/* Header */}
      <div className={cn(
        "p-4 border-b border-gray-200",
        isValid ? "bg-green-50" : (issues.length > 0 ? "bg-red-50" : "bg-yellow-50")
      )}>
        <div className="flex items-center gap-2 mb-2">
          {isValid ? (
            <CheckCircle className="w-5 h-5 text-green-600" />
          ) : (
            <AlertCircle className="w-5 h-5 text-red-600" />
          )}
          <h3 className="font-semibold text-sm text-gray-800">Workflow Validation</h3>
        </div>
        <p className={cn(
          "text-sm",
          isValid ? "text-green-700" : (issues.length > 0 ? "text-red-700" : "text-yellow-700")
        )}>
          {getValidationSummary(validationResult)}
        </p>
      </div>

      {/* Validation Results */}
      <div className="flex-1 overflow-y-auto">
        <IssueSection
          title="Errors"
          issues={issues}
          sectionKey="errors"
        />
        <IssueSection
          title="Warnings"
          issues={warnings}
          sectionKey="warnings"
        />
        <IssueSection
          title="Suggestions"
          issues={suggestions}
          sectionKey="suggestions"
        />

        {/* Validation Categories Summary */}
        {(issues.length > 0 || warnings.length > 0 || suggestions.length > 0) && (
          <div className="p-3 border-t border-gray-200 bg-gray-50">
            <h4 className="font-medium text-xs text-gray-700 mb-2">Issue Categories</h4>
            <div className="space-y-1">
              {['structure', 'configuration', 'connectivity', 'best_practice'].map(category => {
                const categoryIssues = [
                  ...issues.filter(i => i.category === category),
                  ...warnings.filter(w => w.category === category),
                  ...suggestions.filter(s => s.category === category),
                ];
                
                if (categoryIssues.length === 0) return null;
                
                return (
                  <div key={category} className="flex justify-between text-xs">
                    <span className="text-gray-600 capitalize">
                      {category.replace('_', ' ')}
                    </span>
                    <span className="text-gray-800 font-medium">
                      {categoryIssues.length}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ValidationPanel;
