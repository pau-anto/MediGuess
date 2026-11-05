# Infrastructure Azure de MediGuess.
#   Navigateur ──▶ Storage Account (site statique : frontend/)
#        └──▶ Container App (API, image Docker) ──▶ Table Storage (« cases »)

resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location
}

# ---------------------------------------------------------------------------
# Stockage : table des cas (créée par l'API) + site web du front
# ---------------------------------------------------------------------------
resource "azurerm_storage_account" "st" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_account_static_website" "web" {
  storage_account_id = azurerm_storage_account.st.id
  index_document     = "index.html"
}

# ---------------------------------------------------------------------------
# Registre des images Docker
# ---------------------------------------------------------------------------
resource "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = true
}

# ---------------------------------------------------------------------------
# API : Container Apps (environnement standard, pas Express)
# ---------------------------------------------------------------------------
resource "azurerm_container_app_environment" "env" {
  name                = "mediguess-env"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
}

# Clé de signature des jetons de connexion (JWT), générée une fois et
# gardée dans le tfstate : les joueurs restent connectés entre deux déploiements.
resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "azurerm_container_app" "api" {
  name                         = "mediguess-api"
  resource_group_name          = azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.env.id
  revision_mode                = "Single"

  secret {
    name  = "storage-conn"
    value = azurerm_storage_account.st.primary_connection_string
  }
  secret {
    name  = "jwt-secret"
    value = random_password.jwt.result
  }
  secret {
    name  = "acr-password"
    value = azurerm_container_registry.acr.admin_password
  }

  # Accès au registre par le compte admin (pas d'identité managée)
  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  ingress {
    external_enabled = true
    target_port      = 8080
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0 # éteinte quand personne ne joue
    max_replicas = 2

    container {
      name   = "mediguess-api"
      image  = "${azurerm_container_registry.acr.login_server}/mediguess-api:${var.image_tag}"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name        = "AZURE_STORAGE_CONNECTION_STRING"
        secret_name = "storage-conn"
      }
      env {
        name        = "JWT_SECRET"
        secret_name = "jwt-secret"
      }
      env {
        # CORS : seul le front peut appeler l'API
        name  = "ALLOWED_ORIGINS"
        value = trimsuffix(azurerm_storage_account.st.primary_web_endpoint, "/")
      }
    }
  }
}

# ---------------------------------------------------------------------------
# Front : envoi des fichiers dans $web
# api.js est envoyé avec l'URL de l'API injectée : le fichier local garde
# son URL de dev, pas besoin de le modifier à la main.
# ---------------------------------------------------------------------------
locals {
  frontend_dir = "${path.module}/../../frontend"
  api_url      = "https://${azurerm_container_app.api.ingress[0].fqdn}"

  api_js = replace(
    replace(
      file("${local.frontend_dir}/api.js"),
      "/const API_BASE_URL = .*;/", "const API_BASE_URL = \"${local.api_url}\";"
    ),
    "/const USE_MOCK = (true|false);/", "const USE_MOCK = false;"
  )

  front_files = {
    "index.html" = { content = file("${local.frontend_dir}/index.html"), type = "text/html; charset=utf-8" }
    "style.css"  = { content = file("${local.frontend_dir}/style.css"), type = "text/css; charset=utf-8" }
    "app.js"     = { content = file("${local.frontend_dir}/app.js"), type = "application/javascript; charset=utf-8" }
    "api.js"     = { content = local.api_js, type = "application/javascript; charset=utf-8" }
  }
}

resource "azurerm_storage_blob" "front" {
  for_each = local.front_files

  name                   = each.key
  storage_account_name   = azurerm_storage_account.st.name
  storage_container_name = "$web"
  type                   = "Block"
  source_content         = each.value.content
  content_type           = each.value.type
  content_md5            = md5(each.value.content) # renvoie le fichier s'il change

  depends_on = [azurerm_storage_account_static_website.web]
}
