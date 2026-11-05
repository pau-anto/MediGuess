variable "subscription_id" {
  description = "ID de l'abonnement Azure for Students (az account show --query id -o tsv)"
  type        = string
}

variable "location" {
  type    = string
  default = "francecentral"
}

variable "resource_group_name" {
  type    = string
  default = "mediguess-rg"
}

variable "storage_account_name" {
  description = "Unique au monde : minuscules et chiffres, 3 à 24 caractères"
  type        = string
  default     = "mediguess2026"
}

variable "acr_name" {
  description = "Unique au monde : lettres et chiffres"
  type        = string
  default     = "mediguessacr"
}

variable "image_tag" {
  description = "Version de l'image de l'API à déployer (v1, v2...)"
  type        = string
  default     = "v1"
}
