import floConsoleService from '@app/api';
import { InferencePayload, ModelInferenceResultData, PreprocessingStep } from '@app/api/model-inference-service';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useGetModel } from '@app/hooks';
import { getModelsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { Plus, Trash2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
const defaultJsonPayload = `{
  "max_expected_variance": 1000,
  "resize_width": 256,
  "resize_height": 256,
  "normalize_mean": "0.485,0.456,0.406",
  "normalize_std": "0.229,0.224,0.225",
  "gaussian_blur_kernel": 3,
  "min_threshold": 50, 
  "max_threshold": 150
}`;

const ModelDetail: React.FC = () => {
  const { app: appId, modelId } = useParams<{ app: string; modelId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  // Fetch model
  const { data: model } = useGetModel(appId, modelId);

  // State for delete confirmation
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Test Inference Dialog state
  const [showTestInferenceDialog, setShowTestInferenceDialog] = useState(false);

  // Inference state
  const [inferenceImageFile, setInferenceImageFile] = useState<File | null>(null);
  const [jsonPayload, setJsonPayload] = useState<string>(defaultJsonPayload);
  const [inferenceResult, setInferenceResult] = useState<ModelInferenceResultData | null>(null);
  const [runningInference, setRunningInference] = useState(false);
  const [preprocessingSteps, setPreprocessingSteps] = useState<PreprocessingStep[]>([]);

  const handleRunInference = async () => {
    if (!modelId || !inferenceImageFile) {
      notifyError('Please select an image file for inference and ensure Model ID is set.');
      return;
    }
    setRunningInference(true);
    try {
      const payloadOptions: Omit<InferencePayload, 'payload_type' | 'data'> = jsonPayload
        ? JSON.parse(jsonPayload)
        : {};

      const customPayload: Omit<InferencePayload, 'payload_type' | 'data'> = {
        ...payloadOptions,
        preprocessing_steps: preprocessingSteps,
      };

      const response = await floConsoleService.modelInferenceService.runInferenceWithImageFile(
        modelId,
        inferenceImageFile,
        customPayload
      );

      setInferenceResult(response.data.data ?? null);
      notifySuccess('Inference successful!');
    } catch (error) {
      console.error('Error running inference:', error);
    } finally {
      setRunningInference(false);
    }
  };

  const handleCloseTestDialog = () => {
    setShowTestInferenceDialog(false);
    // Reset inference state when closing
    setInferenceImageFile(null);
    setJsonPayload(defaultJsonPayload);
    setInferenceResult(null);
    setPreprocessingSteps([]);
  };

  const handleDelete = async () => {
    if (!modelId || !model) return;

    try {
      await floConsoleService.modelInferenceService.deleteModel(modelId);
      notifySuccess('Model deleted successfully');
      queryClient.invalidateQueries({ queryKey: getModelsKey(appId || '') });
      navigate(`/apps/${appId}/model-inference`);
    } catch (error) {
      console.error('Error deleting model:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete model');
    }
  };

  const formatInferenceResult = (result: ModelInferenceResultData): string => {
    return JSON.stringify(
      {
        ...result,
        infer_data: typeof result.infer_data === 'number' ? Math.round(result.infer_data * 100) : result.infer_data,
      },
      null,
      2
    );
  };

  return (
    <div className="h-full bg-white px-8 pt-8 pb-[200px]">
      <Breadcrumb className="mb-6">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button type="button" onClick={() => navigate('/apps')} className="hover:text-foreground cursor-pointer">
                Apps
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button
                type="button"
                onClick={() => navigate(`/apps/${appId}/model-inference`)}
                className="hover:text-foreground cursor-pointer"
              >
                Model Inference
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{model?.model_name || modelId}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="flex w-full flex-col gap-10 pb-5">
        <div className="flex items-center justify-between">
          <p className="text-2xl leading-normal font-semibold text-black">{model?.model_name}</p>
          <div className="flex gap-4">
            <Button variant="outline" onClick={() => setShowTestInferenceDialog(true)}>
              Model Inference
            </Button>
            <Button variant="destructive" onClick={() => setShowDeleteConfirm(true)}>
              Delete
            </Button>
          </div>
        </div>

        <div className="flex w-full max-w-4xl flex-col gap-6">
          <div className="flex w-full flex-col gap-6 rounded-lg border border-gray-200 bg-white p-6">
            <h3 className="text-lg font-semibold text-gray-900">Model Information</h3>
            <div className="flex flex-col gap-4 rounded-md border border-gray-200 bg-gray-50 p-4">
              <div className="flex justify-between gap-3">
                <span className="text-sm font-medium text-gray-600">Model Name:</span>
                <span className="text-sm font-semibold text-black">{model?.model_name}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-sm font-medium text-gray-600">Model ID:</span>
                <span className="text-sm font-semibold text-black">{model?.model_id}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-sm font-medium text-gray-600">Model Type:</span>
                <span className="text-sm font-semibold text-black">{model?.model_type}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-sm font-medium text-gray-600">Model Path:</span>
                <span className="text-sm font-semibold text-black">{model?.model_path}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Test Inference Dialog */}
      <Dialog open={showTestInferenceDialog} onOpenChange={setShowTestInferenceDialog}>
        <DialogContent className="max-h-[90vh] overflow-y-auto lg:max-w-6xl">
          <DialogHeader>
            <DialogTitle>Model Inference</DialogTitle>
            <DialogDescription>Run inference on an image using this model</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-6 py-4 lg:grid-cols-2">
            <div className="flex flex-col gap-6">
              <div>
                <Label htmlFor="inferenceImageFile" className="mb-2">
                  Upload Image for Inference
                </Label>
                <div className="flex items-center gap-2">
                  <Input
                    type="file"
                    id="inferenceImageFile"
                    accept="image/*"
                    onChange={(e) => setInferenceImageFile(e.target.files ? e.target.files[0] : null)}
                    className="w-full cursor-pointer rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-black outline-none file:cursor-pointer file:text-blue-500"
                  />
                  {inferenceImageFile && (
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() => setInferenceImageFile(null)}
                      title="Remove image"
                    >
                      <Trash2 color="#DD5252" />
                    </Button>
                  )}
                </div>
              </div>

              <div>
                <Label htmlFor="jsonPayload" className="mb-2">
                  Inference Parameters (JSON)
                </Label>
                <CodeMirror
                  id="jsonPayload"
                  value={jsonPayload}
                  onChange={(value: string) => setJsonPayload(value)}
                  theme="dark"
                  height="400px"
                  extensions={[langs.json()]}
                  className="w-full"
                />
              </div>
            </div>

            <div>
              <div className="flex items-start justify-between pb-2">
                <Label className="mb-2">Preprocessing Steps</Label>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => setPreprocessingSteps([...preprocessingSteps, { preprocess_filter: '', values: [] }])}
                >
                  <Plus />
                </Button>
              </div>

              <div className="space-y-2">
                {preprocessingSteps.map((step, index) => (
                  <div key={index} className="flex items-center space-x-2 rounded-lg">
                    <span className="font-mono text-xs text-gray-600">{index + 1}.</span>
                    <Select
                      value={step.preprocess_filter || undefined}
                      onValueChange={(value) => {
                        const newSteps = [...preprocessingSteps];
                        newSteps[index].preprocess_filter = value;
                        setPreprocessingSteps(newSteps);
                      }}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Select Filter" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gray">Grayscale</SelectItem>
                        <SelectItem value="canny">Canny Edge Detection</SelectItem>
                        <SelectItem value="gaussian_blur">Gaussian Blur</SelectItem>
                        <SelectItem value="kernel_sharpening">Kernel Sharpening</SelectItem>
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() => {
                        const newSteps = preprocessingSteps.filter((_, i) => i !== index);
                        setPreprocessingSteps(newSteps);
                      }}
                    >
                      <Trash2 color="#DD5252" />
                    </Button>
                  </div>
                ))}

                {inferenceResult && (
                  <div className="flex flex-col items-start gap-4 rounded-md border border-gray-200 bg-gray-50 p-4">
                    <Label>Inference Result</Label>
                    <div className="w-full text-sm text-black">
                      <pre className="whitespace-pre-wrap">{formatInferenceResult(inferenceResult)}</pre>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={handleCloseTestDialog}>
              Close
            </Button>
            <Button onClick={handleRunInference} loading={runningInference} disabled={!inferenceImageFile}>
              {runningInference ? 'Running...' : 'Run Inference'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DeleteConfirmationDialog
        isOpen={showDeleteConfirm}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteConfirm(false)}
        title="Delete Model"
        message={`Are you sure you want to delete the model '${
          model?.model_name || model?.model_id
        }'? This action cannot be undone.`}
      />
    </div>
  );
};

export default ModelDetail;
