import { IApiResponse } from '@app/lib/axios';
import { AxiosInstance } from 'axios';

export interface PreprocessingStep {
  preprocess_filter: string;
  values: unknown[];
}

interface ModelUploadResponseData {
  message: string;
  model_id: string;
}

export type ModelUploadResponse = IApiResponse<ModelUploadResponseData>;

export interface ModelData {
  model_id: string;
  model_name: string;
  model_path: string;
  model_type: string;
}
export interface ModelDetails {
  data: ModelData;
}

export type ModelDetailResponse = IApiResponse<ModelDetails>;

export interface ModelListData {
  data: ModelData[];
}

export type ModelListResponse = IApiResponse<ModelListData>;

export interface InferencePayload {
  payload_type: string; // e.g., 'image'
  data: string; // base64 encoded data, e.g., image bytes
  max_expected_variance?: number;
  resize_width?: number;
  resize_height?: number;
  normalize_mean?: number;
  normalize_std?: number;
  gaussian_blur_kernel?: number;
  min_threshold?: number;
  max_threshold?: number;
  preprocessing_steps?: PreprocessingStep[];
}

export interface ModelInferenceResultData {
  clarity_score: number;
  infer_data: unknown; // Type not explicitly defined in backend, so using 'unknown'
  data_type: string;
}

export type ModelInferenceResponse = IApiResponse<ModelInferenceResultData>;

export class ModelInferenceService {
  constructor(private http: AxiosInstance) {}

  // Helper method to convert file to base64
  private fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        const result = reader.result as string;
        resolve(result);
      };
      reader.onerror = (error) => reject(error);
    });
  }

  async uploadModel(modelType: string, modelFile: File): Promise<ModelUploadResponse> {
    const formData = new FormData();
    formData.append('model_type', modelType);
    formData.append('model_file', modelFile);

    const response: ModelUploadResponse = await this.http.post(
      `/v1/:appId/floware/v1/model-repository/model`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response;
  }

  async listAllModels(): Promise<ModelListResponse> {
    const response: ModelListResponse = await this.http.get(`/v1/:appId/floware/v1/model-repository/model`);
    return response;
  }

  async getModel(modelId: string): Promise<ModelDetailResponse> {
    const response: ModelDetailResponse = await this.http.get(
      `/v1/:appId/floware/v1/model-repository/model/${modelId}`
    );
    return response;
  }

  // New method to run inference with image file
  async runInferenceWithImageFile(
    modelId: string,
    imageFile: File,
    options?: Omit<InferencePayload, 'payload_type' | 'data'>
  ): Promise<ModelInferenceResponse> {
    try {
      const base64Data = await this.fileToBase64(imageFile);
      const payload: InferencePayload = {
        payload_type: 'image',
        data: base64Data,
        ...options,
      };

      return await this.runInference(modelId, payload);
    } catch (error) {
      throw new Error(`Failed to process image file: ${error}`);
    }
  }

  async runInference(modelId: string, payload: InferencePayload): Promise<ModelInferenceResponse> {
    const response: ModelInferenceResponse = await this.http.post(
      `/v1/:appId/floware/v1/model-repository/model/${modelId}/infer`,
      payload
    );
    return response;
  }

  async deleteModel(modelId: string): Promise<ModelUploadResponse> {
    const response: ModelUploadResponse = await this.http.delete(
      `/v1/:appId/floware/v1/model-repository/model/${modelId}`
    );
    return response;
  }
}
