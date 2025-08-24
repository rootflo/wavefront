import React, { useState } from 'react';
import { ReactFlowProvider } from 'reactflow';
import { useDesignerStore } from '@/store/designerStore';
import { Button } from '@/components/ui/button';
import { Plus, Settings, Route, Upload, CheckCircle } from 'lucide-react';
import FlowCanvas from '@/components/flow/FlowCanvas';
import Sidebar from '@/components/sidebar/Sidebar';
import AgentEditor from '@/components/editors/AgentEditor';
import RouterEditor from '@/components/editors/RouterEditor';
import EdgeEditor from '@/components/editors/EdgeEditor';
import YamlPreviewDrawer from '@/components/drawer/YamlPreviewDrawer';
import ImportDialog from '@/components/dialogs/ImportDialog';
import ValidationPanel from '@/components/panels/ValidationPanel';
import './App.css';

// Simplified Config Editor Modal
const ConfigEditorModal: React.FC<{ isOpen: boolean; onClose: () => void }> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;
  
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-96">
        <h2 className="text-lg font-semibold mb-4">Configuration</h2>
        <p className="text-sm text-gray-600 mb-4">
          Configuration editor coming soon! For now, tools and LLMs are pre-configured.
        </p>
        <Button onClick={onClose}>Close</Button>
      </div>
    </div>
  );
};

const ToolbarComponent: React.FC<{
  showValidation: boolean;
  setShowValidation: (show: boolean) => void;
}> = ({ showValidation, setShowValidation }) => {
  const { openAgentEditor, openRouterEditor } = useDesignerStore();
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [isImportOpen, setIsImportOpen] = useState(false);

  return (
    <>
      <div className="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <h1 className="text-lg font-semibold text-gray-800">Flo AI Studio</h1>
          <div className="text-sm text-gray-600">Visual Workflow Designer</div>
        </div>
        <div className="flex items-center space-x-2">
          <Button variant="outline" size="sm" onClick={() => openAgentEditor()}>
            <Plus className="w-4 h-4 mr-1" />
            Agent
          </Button>
          <Button variant="outline" size="sm" onClick={() => openRouterEditor()}>
            <Route className="w-4 h-4 mr-1" />
            Router
          </Button>
          <Button variant="outline" size="sm" onClick={() => setIsImportOpen(true)}>
            <Upload className="w-4 h-4 mr-1" />
            Import
          </Button>
          <Button 
            variant="outline" 
            size="sm" 
            onClick={() => setShowValidation(!showValidation)}
            className={showValidation ? "bg-green-50 border-green-200" : ""}
          >
            <CheckCircle className="w-4 h-4 mr-1" />
            Validate
          </Button>
          <Button variant="outline" size="sm" onClick={() => setIsConfigOpen(true)}>
            <Settings className="w-4 h-4 mr-1" />
            Config
          </Button>

        </div>
      </div>
      <ConfigEditorModal isOpen={isConfigOpen} onClose={() => setIsConfigOpen(false)} />
      <ImportDialog isOpen={isImportOpen} onClose={() => setIsImportOpen(false)} />
    </>
  );
};

function App() {
  const [showValidation, setShowValidation] = useState(true);

  return (
    <div className="h-screen flex flex-col bg-gray-100">
      <ToolbarComponent showValidation={showValidation} setShowValidation={setShowValidation} />
      <div className="flex-1 flex overflow-hidden">
        <Sidebar />
        <div className="flex-1 relative">
          <ReactFlowProvider>
            <FlowCanvas />
          </ReactFlowProvider>
        </div>
        {showValidation && <ValidationPanel />}
      </div>
      
      {/* Modals */}
      <AgentEditor />
      <RouterEditor />
      <EdgeEditor />
      
      {/* YAML Preview Drawer */}
      <YamlPreviewDrawer />
    </div>
  );
}

export default App;