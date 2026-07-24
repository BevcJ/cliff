export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[];

export type Database = {
  public: {
    Tables: {
      company_review_state: { Row: Record<string, Json>; Insert: Record<string, Json>; Update: Record<string, Json> };
      inspection_collections: { Row: Record<string, Json>; Insert: Record<string, Json>; Update: Record<string, Json> };
      inspection_company_snapshots: { Row: Record<string, Json>; Insert: Record<string, Json>; Update: Record<string, Json> };
    };
    Views: Record<string, never>;
    Functions: {
      inspection_list_collections: { Args: Record<string, never>; Returns: unknown[] };
      inspection_get_filter_options: { Args: { p_collection_date: string }; Returns: Json };
      inspection_get_counts: { Args: { p_collection_date: string; p_filters?: Json }; Returns: Json };
      inspection_list_companies: {
        Args: {
          p_collection_date: string;
          p_filters?: Json;
          p_workflow?: string;
          p_sort_field?: string;
          p_sort_direction?: string;
          p_page?: number;
          p_page_size?: number;
        };
        Returns: Json;
      };
      inspection_get_company: { Args: { p_collection_date: string; p_company_key: string }; Returns: Json };
      inspection_update_status: {
        Args: { p_collection_date: string; p_company_key: string; p_fit_status: string; p_outreach_status: string };
        Returns: Json;
      };
      inspection_update_status_with_last_outreach: {
        Args: {
          p_collection_date: string;
          p_company_key: string;
          p_fit_status: string;
          p_outreach_status: string;
          p_last_outreach_date: string;
        };
        Returns: Json;
      };
      inspection_update_last_outreach: {
        Args: { p_collection_date: string; p_company_key: string; p_last_outreach_date: string | null };
        Returns: Json;
      };
      inspection_update_star: {
        Args: { p_collection_date: string; p_company_key: string; p_is_starred: boolean };
        Returns: Json;
      };
      inspection_update_notes: {
        Args: { p_collection_date: string; p_company_key: string; p_notes: string; p_communication_history: string };
        Returns: Json;
      };
    };
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
};
