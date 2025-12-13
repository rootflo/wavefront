import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@app/components/ui/form';
import { Textarea } from '@app/components/ui/textarea';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useParams } from 'react-router';
import { z } from 'zod';

const inferenceSchema = z.object({
  inferenceInput: z.string(),
  inferenceVariables: z
    .string()
    .optional()
    .refine(
      (val) => {
        if (!val || val.trim() === '') return true;
        try {
          JSON.parse(val);
          return true;
        } catch {
          return false;
        }
      },
      { message: 'Invalid JSON format' }
    ),
});

type InferenceFormValues = z.infer<typeof inferenceSchema>;

interface InferencePopupProps {
  onClose: (newRunId?: string) => void;
  renderModal?: boolean; // If false, don't render the modal wrapper (for use inside Dialog)
}

const InferencePopup: React.FC<InferencePopupProps> = ({ onClose, renderModal = true }) => {
  const { app: appId, workflowPipelineId } = useParams<{ app: string; workflowPipelineId: string }>();

  const { notifyError, notifySuccess } = useNotifyStore();

  const form = useForm<InferenceFormValues>({
    resolver: zodResolver(inferenceSchema),
    defaultValues: {
      inferenceInput: '',
      inferenceVariables: '{}',
    },
  });

  const [submitInProgress, setSubmitInProgress] = useState(false);
  // Image upload state
  const [uploadedImage, setUploadedImage] = useState<{
    file: File;
    base64: string;
    mimeType: string;
  } | null>(null);
  const [uploadingImage, setUploadingImage] = useState(false);

  // Document upload state
  const [uploadedDocuments, setUploadedDocuments] = useState<
    Array<{
      file: File;
      base64: string;
      base64Content: string;
      mimeType: string;
      documentType: 'pdf' | 'txt';
    }>
  >([]);
  const [uploadingDocument, setUploadingDocument] = useState(false);

  // Ref for auto-scrolling events container
  const eventsContainerRef = useRef<HTMLDivElement>(null);

  // Helper function to format file size
  const formatFileSize = (bytes: number): string => {
    const mb = bytes / (1024 * 1024);
    if (mb < 1) {
      const kb = bytes / 1024;
      return `${kb.toFixed(2)} KB`;
    }
    return `${mb.toFixed(2)} MB`;
  };

  // Auto-scroll to bottom of events when new events arrive
  useEffect(() => {
    if (eventsContainerRef.current) {
      eventsContainerRef.current.scrollTop = eventsContainerRef.current.scrollHeight;
    }
  }, []);

  const handleImageUpload = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      // Validate file type
      const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
      if (!allowedTypes.includes(file.type)) {
        notifyError('Please select a valid image file (JPEG, PNG, GIF, or WebP)');
        return;
      }

      // Validate file size (10MB limit)
      const maxSize = 10 * 1024 * 1024; // 10MB
      if (file.size > maxSize) {
        notifyError('Image file size must be less than 10MB');
        return;
      }

      setUploadingImage(true);

      const reader = new FileReader();
      reader.onload = (e) => {
        const result = e.target?.result as string;
        if (result) {
          setUploadedImage({
            file,
            base64: result,
            mimeType: file.type,
          });
        }
        setUploadingImage(false);
      };
      reader.onerror = () => {
        notifyError('Failed to read image file');
        setUploadingImage(false);
      };
      reader.readAsDataURL(file);
    },
    [notifyError]
  );

  const handleDocumentUpload = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files || []);
      if (files.length === 0) return;

      // Validate file types and sizes
      const allowedTypes = ['application/pdf', 'text/plain'];
      const maxSize = 50 * 1024 * 1024; // 50MB

      for (const file of files) {
        if (!allowedTypes.includes(file.type)) {
          notifyError(`File ${file.name} is not a supported document type (PDF or TXT)`);
          return;
        }
        if (file.size > maxSize) {
          notifyError(`File ${file.name} is too large (max 50MB)`);
          return;
        }
      }

      setUploadingDocument(true);

      const processFiles = async () => {
        const newDocuments: Array<{
          file: File;
          base64: string;
          base64Content: string;
          mimeType: string;
          documentType: 'pdf' | 'txt';
        }> = [];

        for (const file of files) {
          try {
            const base64 = await new Promise<string>((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = (e) => resolve(e.target?.result as string);
              reader.onerror = reject;
              reader.readAsDataURL(file);
            });

            // Extract just the base64 content (remove data:type;base64, prefix)
            const base64Content = base64.split(',')[1];

            newDocuments.push({
              file,
              base64,
              base64Content,
              mimeType: file.type,
              documentType: file.type === 'application/pdf' ? 'pdf' : 'txt',
            });
          } catch {
            notifyError(`Failed to process file ${file.name}`);
            setUploadingDocument(false);
            return;
          }
        }

        setUploadedDocuments((prev) => [...prev, ...newDocuments]);
        setUploadingDocument(false);
      };

      processFiles();
    },
    [notifyError]
  );

  const handleRemoveImage = useCallback(() => {
    setUploadedImage(null);
  }, []);

  const handleRemoveDocument = useCallback((index: number) => {
    setUploadedDocuments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const onSubmit = async (data: InferenceFormValues) => {
    if (!appId) return;
    setSubmitInProgress(true);
    try {
      let variables = {};
      if (data.inferenceVariables?.trim()) {
        try {
          variables = JSON.parse(data.inferenceVariables);
        } catch {
          notifyError('Invalid JSON in variables field');
          setSubmitInProgress(false);
          return;
        }
      }

      // Prepare inputs based on what's provided
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let inputs: string | any[];

      // Handle different input combinations
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const messageInputs: any[] = [];

      // Add image if uploaded
      if (uploadedImage) {
        // Extract base64 content from data URL (remove data:type;base64, prefix)
        const imageBase64Content = uploadedImage.base64.split(',')[1];
        const imageMessage = {
          image_base64: imageBase64Content,
          mime_type: uploadedImage.mimeType,
        };
        messageInputs.push(imageMessage);
      }

      // Add all documents if uploaded
      if (uploadedDocuments.length > 0) {
        uploadedDocuments.forEach((doc) => {
          const documentMessage = {
            document_type: doc.documentType,
            document_base64: doc.base64Content,
            mime_type: doc.mimeType,
            metadata: {
              filename: doc.file.name,
              size: doc.file.size,
            },
          };
          messageInputs.push(documentMessage);
        });
      }

      // Add text input if provided
      if (data.inferenceInput?.trim()) {
        messageInputs.push(data.inferenceInput.trim());
      }

      // Determine final inputs format
      if (messageInputs.length > 0) {
        inputs = messageInputs.length === 1 && typeof messageInputs[0] === 'string' ? messageInputs[0] : messageInputs;
      } else {
        // This shouldn't happen due to validation, but fallback
        inputs = '';
      }

      // Run inference
      const response = await floConsoleService.workflowService.submitJobToPipeline(
        workflowPipelineId as string,
        inputs,
        variables
      );
      notifySuccess('Inference submitted successfully');

      // Extract run ID from response if available
      const responseData = response.data?.data as unknown as Record<string, unknown>;
      const runId = (responseData?.workflow_run_id || responseData?.id) as string | undefined;
      onClose(runId);
    } catch (error) {
      console.error('Error running inference:', error);
      notifyError('Failed to run inference');
    } finally {
      setSubmitInProgress(false);
    }
  };

  const content = (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        {/* Image Upload */}
        <div>
          <label htmlFor="imageInput" className="block pb-3 text-base font-normal text-[#282828]">
            Image Upload (Optional)
          </label>
          {!uploadedImage ? (
            <div className="flex w-full items-center">
              <input
                type="file"
                id="imageInput"
                accept="image/*"
                onChange={handleImageUpload}
                className="hidden"
                disabled={uploadingImage}
              />
              <label
                htmlFor="imageInput"
                className="flex w-full cursor-pointer items-center justify-center gap-4 rounded-xl border border-dashed border-[#AEB3BB] px-16 py-5 text-base font-normal text-black"
              >
                {uploadingImage ? (
                  <>
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent"></div>
                    Processing...
                  </>
                ) : (
                  <>
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    Select Image
                  </>
                )}
              </label>
            </div>
          ) : (
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
              <div className="flex items-start space-x-3">
                <img src={uploadedImage.base64} alt="Uploaded" className="h-16 w-16 rounded-lg object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-gray-900">{uploadedImage.file.name}</p>
                  <p className="text-xs text-gray-500">
                    {uploadedImage.mimeType} • {formatFileSize(uploadedImage.file.size)}
                  </p>
                </div>
                <button
                  onClick={handleRemoveImage}
                  className="rounded-full p-1 text-red-500 hover:bg-red-50"
                  title="Remove image"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}
          <p className="pt-3 text-sm font-normal text-[#878787]">
            Upload an image to test vision-capable workflows. Supported formats: JPEG, PNG, GIF, WebP (max 10MB)
          </p>
        </div>

        {/* Document Upload */}
        <div>
          <label htmlFor="documentInput" className="block pb-3 text-base font-normal text-[#282828]">
            Document Upload (Optional)
          </label>
          <div className="flex w-full items-center">
            <input
              type="file"
              id="documentInput"
              accept=".pdf,.txt,application/pdf,text/plain"
              onChange={handleDocumentUpload}
              className="hidden"
              disabled={uploadingDocument}
              multiple
            />
            <label
              htmlFor="documentInput"
              className="flex w-full cursor-pointer items-center justify-center gap-4 rounded-xl border border-dashed border-[#AEB3BB] px-16 py-5 text-base font-normal text-black"
            >
              {uploadingDocument ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent"></div>
                  Processing...
                </>
              ) : (
                <>
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Select Document(s)
                </>
              )}
            </label>
          </div>

          {uploadedDocuments.length > 0 && (
            <div className="mt-3 flex flex-col gap-2">
              {uploadedDocuments.map((doc, index) => (
                <div key={index} className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <div className="flex items-start space-x-3">
                    <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-blue-50">
                      {doc.documentType === 'pdf' ? (
                        <svg className="h-8 w-8 text-red-500" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
                        </svg>
                      ) : (
                        <svg className="h-8 w-8 text-blue-500" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
                        </svg>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-gray-900">{doc.file.name}</p>
                      <p className="text-xs text-gray-500">
                        {doc.mimeType} • {formatFileSize(doc.file.size)}
                      </p>
                      <p className="text-xs text-gray-500">Document Type: {doc.documentType.toUpperCase()}</p>
                    </div>
                    <button
                      onClick={() => handleRemoveDocument(index)}
                      className="rounded-full p-1 text-red-500 hover:bg-red-50"
                      title="Remove document"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <p className="pt-3 text-sm font-normal text-[#878787]">
            Upload document(s) to include in your prompt. Supported formats: PDF, TXT (max 50MB each)
          </p>
        </div>

        {/* Variables Input */}
        <FormField
          control={form.control}
          name="inferenceVariables"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Variables (JSON)</FormLabel>
              <FormControl>
                <Textarea {...field} rows={3} className="font-mono" placeholder='{"key": "value"}' />
              </FormControl>
              <FormDescription>Optional JSON object with variables for the workflow</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Text Input */}
        <FormField
          control={form.control}
          name="inferenceInput"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Text Input {uploadedImage || uploadedDocuments.length > 0 ? '(Optional)' : ''}</FormLabel>
              <FormControl>
                <Textarea {...field} rows={3} placeholder="Enter your input text..." />
              </FormControl>
              <FormDescription>
                {uploadedImage || uploadedDocuments.length > 0
                  ? 'Optional text input to accompany your uploaded files'
                  : 'Enter the text input for your workflow'}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Action Buttons */}
        <div className="flex justify-end gap-3">
          <Button type="button" variant="outline" onClick={() => onClose()} disabled={submitInProgress}>
            Cancel
          </Button>
          <Button type="submit" loading={submitInProgress} className="bg-[#101010] text-white hover:bg-[#1a1a1a]">
            Submit Job
          </Button>
        </div>
      </form>
    </Form>
  );

  if (!renderModal) {
    return <>{content}</>;
  }

  return (
    <div className="bg-opacity-50 fixed inset-0 z-50 flex items-center justify-center bg-black">
      <div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-6 flex items-center justify-between">
          <button
            onClick={() => onClose()}
            className="rounded-full p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        {content}
      </div>
    </div>
  );
};

export default InferencePopup;
