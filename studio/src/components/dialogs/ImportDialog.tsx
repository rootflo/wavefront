import React, { useState, useRef } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Upload, FileText, AlertCircle, CheckCircle } from 'lucide-react';
import { useDesignerStore } from '@/store/designerStore';
import { validateAriumYAML, readFileAsText } from '@/utils/yamlImport';

interface ImportDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

const ImportDialog: React.FC<ImportDialogProps> = ({ isOpen, onClose }) => {
  const { importFromYAML } = useDesignerStore();
  const [yamlContent, setYamlContent] = useState('');
  const [validationResult, setValidationResult] = useState<{ isValid: boolean; error?: string } | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const content = await readFileAsText(file);
      setYamlContent(content);
      setImportError(null);
      
      // Validate the content
      const validation = validateAriumYAML(content);
      setValidationResult(validation);
    } catch (error) {
      setImportError(`Failed to read file: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const handleYamlChange = (content: string) => {
    setYamlContent(content);
    setImportError(null);
    
    if (content.trim()) {
      const validation = validateAriumYAML(content);
      setValidationResult(validation);
    } else {
      setValidationResult(null);
    }
  };

  const handleImport = async () => {
    if (!yamlContent.trim()) {
      setImportError('Please provide YAML content to import');
      return;
    }

    setIsImporting(true);
    setImportError(null);

    try {
      await importFromYAML(yamlContent);
      onClose();
      resetDialog();
    } catch (error) {
      setImportError(`Import failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsImporting(false);
    }
  };

  const resetDialog = () => {
    setYamlContent('');
    setValidationResult(null);
    setImportError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleClose = () => {
    resetDialog();
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="w-5 h-5" />
            Import Workflow from YAML
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* File Upload */}
          <div>
            <Label>Upload YAML File</Label>
            <div className="flex items-center gap-2 mt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-2"
              >
                <FileText className="w-4 h-4" />
                Choose File
              </Button>
              <span className="text-sm text-gray-500">or paste YAML content below</span>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".yaml,.yml"
              onChange={handleFileUpload}
              className="hidden"
            />
          </div>

          {/* YAML Content */}
          <div>
            <Label>YAML Content</Label>
            <Textarea
              value={yamlContent}
              onChange={(e) => handleYamlChange(e.target.value)}
              placeholder="Paste your Arium workflow YAML here..."
              rows={15}
              className="mt-2 font-mono text-sm"
            />
          </div>

          {/* Validation Result */}
          {validationResult && (
            <div className={`p-3 rounded-lg border ${
              validationResult.isValid 
                ? 'bg-green-50 border-green-200' 
                : 'bg-red-50 border-red-200'
            }`}>
              <div className="flex items-center gap-2">
                {validationResult.isValid ? (
                  <CheckCircle className="w-4 h-4 text-green-600" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-red-600" />
                )}
                <span className={`font-medium text-sm ${
                  validationResult.isValid ? 'text-green-800' : 'text-red-800'
                }`}>
                  {validationResult.isValid ? 'YAML is valid!' : 'YAML validation failed'}
                </span>
              </div>
              {validationResult.error && (
                <p className="text-sm text-red-700 mt-1">{validationResult.error}</p>
              )}
            </div>
          )}

          {/* Import Error */}
          {importError && (
            <div className="p-3 rounded-lg border bg-red-50 border-red-200">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-600" />
                <span className="font-medium text-sm text-red-800">Import Error</span>
              </div>
              <p className="text-sm text-red-700 mt-1">{importError}</p>
            </div>
          )}

          {/* Instructions */}
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
            <h4 className="font-medium text-sm text-blue-800 mb-2">Import Instructions</h4>
            <ul className="text-sm text-blue-700 space-y-1">
              <li>• Upload a YAML file exported from Flo AI Studio or created manually</li>
              <li>• The YAML must include an "arium" section with agents and workflow definition</li>
              <li>• Importing will replace your current workflow - export first if needed</li>
              <li>• Router configurations and tool references will be preserved</li>
            </ul>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button 
            onClick={handleImport} 
            disabled={!yamlContent.trim() || (validationResult && !validationResult.isValid) || isImporting}
          >
            {isImporting ? 'Importing...' : 'Import Workflow'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ImportDialog;
