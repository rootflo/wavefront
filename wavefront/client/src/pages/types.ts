export interface IRejectionCriterion {
  criterion: string;
  indicators: string;
  probability: number;
}

export interface IRejectionAssessment {
  criteria: IRejectionCriterion[];
}

export interface IStones {
  stone_types: string[];
}

export interface IStoneType {
  stone_type: string;
  count: number;
  color: string;
  location: string;
}

export interface IStoneItems {
  stone_types: IStoneType[];
}
interface IResource {
  resource_key: string;
  resource_value: string;
  resource_description: string;
  resource_scope: string;
}
export interface IRoleWithResources {
  id: string;
  name: string;
  description: string;
  resources: IResource[];
}
export interface IResourceArray {
  id: string;
  description: string;
  key: string;
  scope: string;
  value: string;
}

export interface IRiskCriterion {
  criterion: string;
  probability: number;
  indicators: string;
}

export interface ItemRiskIdentified {
  criteria: IRiskCriterion[];
}
export interface ILoanDeepDiveItem {
  item_id: string;
  gold_data_id: string;
  type: string;
  sub_type: string | null;
  quantity: number;
  materials_appearance: string;
  stone_weight_percentage: number;
  stone_weight_percentage_rationale: string;
  stone_items: IStoneItems;
  stone_count_total: number;
  stone_count_unique: number;
  stone_weight: number | null;
  risk_assessment: ItemRiskIdentified;
  item_risk_identified: IRiskCriterion[];
  item_risk_identified_count: number;
  item_risk_flag: string;
  item_coordinates: Record<string, unknown> | null;
}
export interface IUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
}

export interface IItems {
  item_count: number;
  item_description: string;
  item_id: string;
  item_type: string;
  item_gross_weight: number;
  item_stone_weight: number;
}
export interface ILoanDeepDiveData {
  id: string;
  image_id: string;
  loan_id: string;
  customer_id: string;
  agent_id: string;
  manager_name: string;
  loan_date: string;
  category: string;
  sub_category: string | null;
  zone: string;
  region: string;
  city: string;
  branch: string;
  loan_amount: string;
  total_gross_weight: number;
  stone_weight: number;
  image_url: string;
  unusual_patterns_detected: boolean;
  unusual_patterns_details: string | null;
  unusual_patterns_tags: string[];
  identical_items_detected: boolean;
  identical_items_detected_count: number;
  image_risk_flag: string;
  clarity_score: number;
  overlap_score: number;
  metadata_1: Record<string, unknown> | null;
  metadata_2: Record<string, unknown> | null;
  metadata_3: Record<string, unknown> | null;
  metadata_4: Record<string, unknown> | null;
  metadata_5: Record<string, unknown> | null;
  filter_1: string | null;
  filter_2: string | null;
  filter_3: string | null;
  filter_4: string | null;
  filter_5: string | null;
  tags: string[];
  image_summary: string;
  created_at: string;
  items: IItems[];
  gold_purity: number;
  gross_weight: number;
  gold_loan_category: string;
  jewellery_items_count: number | null;
}
export interface IRoles {
  id: string;
  name: string;
  description: string;
}
export interface IUserRole {
  id: string;
  name: string;
  email: string;
  first_name: string;
  last_name: string;
  roles: IRoles[];
}

export interface IResourceMeta {
  name: string;
  key: string;
  priority: string;
  path: string;
}

export interface IResources {
  key: string;
  value: string;
  description?: string;
  scope: string;
  meta: IResourceMeta;
}

export interface IZones {
  zone: string;
}

export interface IRiskCount {
  open_count: number;
  closed_count: number;
  all_count: number;
}
