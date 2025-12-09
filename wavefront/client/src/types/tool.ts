import { IApiResponse } from "@app/lib/axios";

export interface Tool {
  name: string;
  description: string;
  parameters: Record<
    string,
    {
      type: string;
      description: string;
    }
  >;
  category: string;
}
export interface ToolDetails {
  name: string;
  parameters: {
    [key: string]: {
      type: string;
      description: string;
    };
  };
  description: string;
  required: string[];
  prefill_parameter_names: string[];
  category: string;
  prefilled_value: {
    [key: string]: string;
  };
  resource_name: string;
}

export interface ToolsDetailsData {
  name: string;
  prefilled_values: Array<{
    [key: string]: string;
  }>;
  display_name: string;
  description: string;
}

export interface ToolNamesData {
  message: string;
  data: {
    tool_details: ToolDetails;
    count: number;
  };
}

export interface ToolDetailsData {
  message: string;
  data: {
    tool: Tool;
  };
}

export type ToolNamesResponse = IApiResponse<ToolNamesData>;
export type ToolDetailsResponse = IApiResponse<ToolDetailsData>;
