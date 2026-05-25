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
  description = "Subdomain to publish the dev static site under."
  type        = string
  default     = "vhf-dev"
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

variable "live_origin_domain_name" {
  description = "Public HTTPS origin domain for read-only live radio API routes. Do not include a scheme."
  type        = string
  default     = "optiplex.tailbea63b.ts.net"
}

variable "live_origin_https_port" {
  description = "HTTPS port for the read-only live radio origin."
  type        = number
  default     = 10000
}

variable "dev_live_origin_domain_name" {
  description = "Optional dev override for the read-only live radio origin domain."
  type        = string
  default     = null
}

variable "dev_live_origin_https_port" {
  description = "Optional dev override for the read-only live radio origin HTTPS port."
  type        = number
  default     = null
}

variable "project_name" {
  description = "Short name used in AWS resource names."
  type        = string
  default     = "talkingboats"
}

variable "raw_retention_days" {
  description = "Days to retain raw/ audio objects before S3 lifecycle expiry."
  type        = number
  default     = 60
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
