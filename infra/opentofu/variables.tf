variable "aws_region" {
  description = "Primary AWS region for S3 and Route 53 changes."
  type        = string
  default     = "us-west-2"
}

variable "root_domain" {
  description = "Existing Route 53 hosted zone root domain."
  type        = string
  default     = "robertboscacci.com"
}

variable "site_subdomain" {
  description = "Subdomain to publish the static site under."
  type        = string
  default     = "vhf"
}

variable "dev_site_subdomain" {
  description = "Subdomain to publish the tailnet-only dev site under."
  type        = string
  default     = "vhf-dev"
}

variable "ais_live_subdomain" {
  description = "Subdomain for the public AIS websocket API Gateway custom domain."
  type        = string
  default     = "ais-live"
}

variable "ais_ingest_token_sha256" {
  description = "SHA-256 hex digest of the AIS ingest token. The raw token lives in AWS Secrets Manager, not OpenTofu state."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.ais_ingest_token_sha256))
    error_message = "ais_ingest_token_sha256 must be a lowercase 64-character SHA-256 hex digest."
  }
}

variable "dev_tailnet_ipv4_addresses" {
  description = "Tailnet IPv4 addresses for the dev site DNS record."
  type        = list(string)
  default     = ["100.124.5.39"]
}

variable "dev_tailnet_ipv6_addresses" {
  description = "Tailnet IPv6 addresses for the dev site DNS record."
  type        = list(string)
  default     = ["fd7a:115c:a1e0::2601:597"]
}

variable "resource_site_subdomain" {
  description = "Legacy subdomain stem used in bucket names. Keep stable when changing public DNS."
  type        = string
  default     = "talkingboats"
}

variable "dev_resource_site_subdomain" {
  description = "Legacy dev subdomain stem used in bucket names. Keep stable when changing public DNS."
  type        = string
  default     = "dev.talkingboats"
}

variable "project_name" {
  description = "Short name used in AWS resource names."
  type        = string
  default     = "talkingboats"
}

variable "raw_retention_days" {
  description = "Days to retain unstarred raw/ audio objects before S3 lifecycle expiry."
  type        = number
  default     = 90
}

variable "force_destroy_buckets" {
  description = "Allow OpenTofu to destroy non-empty project buckets. Keep false unless intentionally tearing down."
  type        = bool
  default     = false
}

variable "public_site_bucket_name" {
  description = "Optional override for the public static-site bucket name."
  type        = string
  default     = null
}

variable "raw_audio_bucket_name" {
  description = "Optional override for the private raw-audio bucket name."
  type        = string
  default     = null
}

variable "dev_public_site_bucket_name" {
  description = "Optional override for the dev public static-site bucket name."
  type        = string
  default     = null
}

variable "dev_raw_audio_bucket_name" {
  description = "Optional override for the dev private raw-audio bucket name."
  type        = string
  default     = null
}
