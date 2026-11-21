export type AccountType = "SUPERUSER" | "RETAILER" | "VENDOR";

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  account_type: AccountType | null;
  retailer_id: number | null;
  permissions: string[];
}

export interface DashboardStats {
  account_type: AccountType;
  devices: {
    total: number;
    active: number;
    inactive: number;
    online: number;
    locked: number;
    released: number;
    pending_enrollment: number;
  };
  entitlements: {
    allocated: number;
    distributed: number;
    consumed: number;
    available: number | null;
    expired: number;
  };
  retailers_count?: number;
  vendors_count?: number;
  expiring_allocations?: number;
}

export interface RetailerItem {
  id: string;
  account_id: number;
  username: string;
  full_name: string;
  business_name: string;
  contact_person: string;
  address: string;
  mobile: string;
  email: string;
  status: string;
  is_active: boolean;
  entitlement_quota: number | null;
  entitlements_consumed: number;
  last_ip?: string | null;
  last_device?: string;
  last_active_at?: string | null;
  created_at: string;
}

export interface AccountAccessItem {
  id: number;
  username: string;
  account_type: AccountType | null;
  is_active: boolean;
  last_ip: string | null;
  last_device: string;
  last_user_agent: string;
  last_active_at: string | null;
}

export interface VendorItem extends RetailerItem {
  retailer_id: string;
  retailer_account_id: number;
  retailer_business_name: string;
}

export interface DeviceItem {
  id: string;
  device_identifier: string;
  registration_reference: string;
  imei_masked: string;
  manufacturer: string;
  model: string;
  android_version: string;
  sdk_version: number;
  app_version: string;
  enrollment_method: string;
  enrollment_status: string;
  ownership_status: string;
  connection_status: string;
  restriction_status: string;
  is_disabled: boolean;
  emi_amount: string;
  emi_due_date: string;
  pending_emi_count: string;
  dealer_name: string;
  dealer_mobile: string;
  dealer_company: string;
  last_latitude: number | null;
  last_longitude: number | null;
  last_location_accuracy: number | null;
  last_location_at: string | null;
  network_type: string;
  wifi_ssid: string;
  network_operator: string;
  ip_address: string;
  camera_disabled: boolean;
  gps_forced_on: boolean;
  network_restricted: boolean;
  frp_accounts?: string;
  effective_frp_accounts?: string[];
  has_photo: boolean;
  last_photo_at: string | null;
  last_seen: string | null;
  registration_date: string | null;
  released_at: string | null;
  customer_id: string | null;
  customer_name: string | null;
  customer_mobile_masked: string;
  retailer_id: number | null;
  retailer_username: string | null;
  vendor_id: number | null;
  vendor_username: string | null;
}

export interface CustomerItem {
  id: string;
  full_name: string;
  mobile_masked: string;
  email_masked: string;
  retailer_id: number | null;
  vendor_id: number | null;
  device_count: number;
  created_at: string;
}

export interface AllocationItem {
  id: string;
  allocated_to_id: number;
  allocated_to_username: string;
  allocated_by_username: string;
  allocated_quantity: number;
  distributed_quantity: number;
  consumed_quantity: number;
  available_quantity: number;
  issued_at: string;
  expires_at: string;
  status: string;
  notes: string;
}

export interface TransferItem {
  id: string;
  sender_username: string;
  receiver_username: string;
  quantity: number;
  transferred_by_username: string;
  transfer_date: string;
  reason: string;
  status: string;
}

export interface ConsumptionItem {
  id: string;
  device_id: string;
  device_identifier: string;
  registration_reference: string;
  consumed_at: string;
}

export interface CommandItem {
  id: string;
  device_id: string;
  device_identifier: string;
  device_model: string;
  command_type: string;
  command_status: string;
  created_by: string | null;
  issued_at: string;
  execution_result: string;
}

export interface AuditItem {
  id: number;
  event: string;
  result: string;
  actor: string | null;
  target_type: string;
  target_id: string;
  source_ip: string | null;
  client_device?: string;
  user_agent?: string;
  timestamp: string;
}

export interface SigningKeyItem {
  key_id: string;
  category: string;
  algorithm: string;
  version: number;
  status: string;
  expires_at: string | null;
  created_at: string;
}
