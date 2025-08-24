import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Download, Copy, Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useDesignerStore } from '@/store/designerStore';
import { generateAriumYAML, downloadYAML } from '@/utils/yamlExport';

const YamlPreviewDrawer: React.FC = () => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [yamlContent, setYamlContent] = useState('');
  const [copied, setCopied] = useState(false);
  
  const { nodes, edges, workflowName, workflowDescription, workflowVersion } = useDesignerStore();

  // Update YAML content when workflow changes
  useEffect(() => {
    if (nodes.length > 0) {
      try {
        const yaml = generateAriumYAML({
          nodes,
          edges,
          workflowName,
          workflowDescription,
          workflowVersion,
        });
        setYamlContent(yaml);
      } catch (error) {
        setYamlContent(`# Error generating YAML preview:\n# ${error}`);
      }
    } else {
      setYamlContent('# Create agents and connect them to see YAML preview\n# Drag agents from the sidebar to get started');
    }
  }, [nodes, edges, workflowName, workflowDescription, workflowVersion]);

  const handleExport = () => {
    if (nodes.length > 0) {
      const yaml = generateAriumYAML({
        nodes,
        edges,
        workflowName,
        workflowDescription,
        workflowVersion,
      });
      downloadYAML(yaml, `${workflowName.replace(/\s+/g, '-').toLowerCase()}.yaml`);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(yamlContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy YAML:', error);
    }
  };

  const toggleDrawer = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <>
      {/* Floating Toggle Widget */}
      {!isExpanded && (
        <button
          onClick={toggleDrawer}
          className="yaml-widget fixed top-1/2 right-4 bg-white border border-gray-200 rounded-lg p-3 hover:bg-gray-50 shadow-lg z-50 hover:shadow-xl"
          title="Show YAML preview"
        >
          <div className="flex flex-col items-center gap-1">
            <Eye className="w-4 h-4 text-blue-600" />
            <span className="text-xs font-medium text-gray-600">YAML</span>
          </div>
        </button>
      )}

      {/* Expanded Drawer */}
      {isExpanded && (
        <div className="fixed top-0 right-0 h-full w-96 bg-white border-l border-gray-200 shadow-lg z-50">
          {/* Close Button */}
          <button
            onClick={toggleDrawer}
            className="absolute left-0 top-1/2 transform -translate-y-1/2 -translate-x-full bg-white border border-r-0 border-gray-200 rounded-l-md p-2 hover:bg-gray-50 transition-colors"
            title="Close YAML preview"
          >
            <ChevronRight className="w-4 h-4 text-gray-600" />
          </button>

          {/* Drawer Content */}
          <div className="h-full flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-gray-50">
              <div className="flex items-center gap-2">
                <Eye className="w-4 h-4 text-gray-600" />
                <h3 className="font-semibold text-sm text-gray-800">YAML Preview</h3>
              </div>
              <button
                onClick={toggleDrawer}
                className="p-1 hover:bg-gray-200 rounded transition-colors"
                title="Close preview"
              >
                <EyeOff className="w-4 h-4 text-gray-600" />
              </button>
            </div>

            {/* Actions */}
            <div className="p-3 border-b border-gray-200 bg-gray-50">
              <div className="flex gap-2">
                <Button
                  onClick={handleExport}
                  disabled={nodes.length === 0}
                  className="flex-1 h-8 text-xs"
                  size="sm"
                >
                  <Download className="w-3 h-3 mr-1" />
                  Export YAML
                </Button>
                <Button
                  onClick={handleCopy}
                  variant="outline"
                  size="sm"
                  className="h-8 px-2"
                  title="Copy to clipboard"
                >
                  <Copy className="w-3 h-3" />
                  {copied && <span className="ml-1 text-xs">✓</span>}
                </Button>
              </div>
            </div>

            {/* YAML Content */}
            <div className="flex-1 overflow-hidden">
              <pre className="yaml-content h-full overflow-auto p-3 text-xs font-mono bg-gray-900 text-gray-100 leading-relaxed">
                <code>{yamlContent}</code>
              </pre>
            </div>

            {/* Footer */}
            <div className="p-3 border-t border-gray-200 bg-gray-50">
              <div className="text-xs text-gray-500 text-center">
                {nodes.length} agent{nodes.length !== 1 ? 's' : ''} • {edges.length} connection{edges.length !== 1 ? 's' : ''}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default YamlPreviewDrawer;
