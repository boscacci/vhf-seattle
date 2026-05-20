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
  default     = "talkingboats"
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
