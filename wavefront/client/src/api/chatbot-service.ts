import { IApiResponse } from '@app/lib/axios';
import {
  Chatbot,
  ChatbotData,
  ChatbotDeleteResponse,
  ChatbotDetailResponse,
  ChatbotListData,
  ChatbotListResponse,
  ChatbotResponse,
  CreateChatbotRequest,
  UpdateChatbotRequest,
} from '@app/types/chatbot';
import { AxiosInstance } from 'axios';

export class ChatbotService {
  constructor(private http: AxiosInstance) {}

  async createChatbot(data: CreateChatbotRequest): Promise<ChatbotResponse> {
    const response: IApiResponse<ChatbotData> = await this.http.post(`/v1/:appId/floware/v1/chatbots`, data);
    return response;
  }

  async getChatbot(chatbotId: string): Promise<ChatbotDetailResponse> {
    const response: IApiResponse<{ chatbot: Chatbot }> = await this.http.get(
      `/v1/:appId/floware/v1/chatbots/${chatbotId}`
    );
    return response;
  }

  async updateChatbot(chatbotId: string, data: UpdateChatbotRequest): Promise<ChatbotResponse> {
    const response: IApiResponse<ChatbotData> = await this.http.patch(
      `/v1/:appId/floware/v1/chatbots/${chatbotId}`,
      data
    );
    return response;
  }

  async deleteChatbot(chatbotId: string): Promise<ChatbotDeleteResponse> {
    const response: IApiResponse<{ message: string }> = await this.http.delete(
      `/v1/:appId/floware/v1/chatbots/${chatbotId}`
    );
    return response;
  }

  async listAllChatbots(namespace?: string): Promise<ChatbotListResponse> {
    const response: IApiResponse<ChatbotListData> = await this.http.get(`/v1/:appId/floware/v1/chatbots`, {
      params: namespace ? { namespace } : undefined,
    });
    return response;
  }
}
