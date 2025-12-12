import { IApiResponse } from "@app/lib/axios";
import {
  CreateMessageProcessorRequest,
  ExecuteMessageProcessorData,
  ExecuteMessageProcessorRequest,
  ExecuteMessageProcessorResponse,
  MessageProcessorData,
  MessageProcessorListData,
  MessageProcessorListResponse,
  MessageProcessorResponse,
  UpdateMessageProcessorRequest,
} from "@app/types/message-processor";
import { AxiosInstance } from "axios";

export class MessageProcessorService {
  constructor(private http: AxiosInstance) {}

  async createMessageProcessor(
    data: CreateMessageProcessorRequest
  ): Promise<MessageProcessorResponse> {
    const response: IApiResponse<MessageProcessorData> = await this.http.post(
      `/v1/:appId/floware/v1/message-processors`,
      data
    );
    return response;
  }

  async getMessageProcessor(
    processorId: string
  ): Promise<MessageProcessorResponse> {
    const response: IApiResponse<MessageProcessorData> = await this.http.get(
      `/v1/:appId/floware/v1/message-processors/${processorId}`
    );
    return response;
  }

  async updateMessageProcessor(
    processorId: string,
    data: UpdateMessageProcessorRequest
  ): Promise<MessageProcessorResponse> {
    const response: IApiResponse<MessageProcessorData> = await this.http.put(
      `/v1/:appId/floware/v1/message-processors/${processorId}`,
      data
    );
    return response;
  }

  async deleteMessageProcessor(
    processorId: string
  ): Promise<MessageProcessorResponse> {
    const response: IApiResponse<MessageProcessorData> = await this.http.delete(
      `/v1/:appId/floware/v1/message-processors/${processorId}`
    );
    return response;
  }

  async listMessageProcessors(): Promise<MessageProcessorListResponse> {
    const response: IApiResponse<MessageProcessorListData> =
      await this.http.get(`/v1/:appId/floware/v1/message-processors`);
    return response;
  }

  async executeMessageProcessor(
    processorId: string,
    data: ExecuteMessageProcessorRequest
  ): Promise<ExecuteMessageProcessorResponse> {
    const response: IApiResponse<ExecuteMessageProcessorData> =
      await this.http.post(
        `/v1/:appId/floware/v1/message-processors/${processorId}/execute`,
        data
      );
    return response;
  }
}
