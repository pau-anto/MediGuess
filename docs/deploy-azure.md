# Déployer MediGuess sur Azure (Azure for Students + Terraform)

```
Navigateur ──▶ Storage Account « mediguess2026 » : site statique (frontend/)
     │
     └──▶ Container App « mediguess-api » (backend/, image Docker, scale-to-zero)
                 └──▶ Table Storage « cases » (dans mediguess2026)
```

Toute l'infrastructure est décrite en Terraform dans `infra/azure/`.
Pas de machine virtuelle : Azure lance le conteneur de l'API à la demande et l'éteint
quand personne ne joue.

| Ressource | Nom | Rôle | Coût |
|---|---|---|---|
| Groupe de ressources | `mediguess-rg` | Contient tout le projet | — |
| Compte de stockage | `mediguess2026` | Table `cases` + site web du front | quelques centimes |
| Registre de conteneurs | `mediguessacr2026` | Image Docker de l'API | ~5 $/mois (crédit étudiant) |
| Environnement Container Apps | `mediguess-env` | Support d'exécution de l'API | — |
| Container App | `mediguess-api` | L'API (0 instance au repos) | gratuit (quota mensuel) |

Adresses : `terraform output front_url` (le jeu) et `terraform output api_url` (l'API).

## Fichiers Terraform (`infra/azure/`)

| Fichier | Contenu |
|---|---|
| `providers.tf` | Provider `azurerm` (authentification via `az login`) |
| `variables.tf` | Noms des ressources, région, version de l'image (`image_tag`) |
| `main.tf` | Stockage + site statique, registre, environnement, Container App, envoi du front |
| `outputs.tf` | URL du front, URL de l'API, identifiants du registre |
| `terraform.tfvars` | **Non commité.** `subscription_id` et `acr_name` |

Ce que Terraform fait tout seul :
- l'environnement Container Apps est **standard** (pas *Express*) ;
- la Container App lit le registre avec le compte admin (pas d'identité managée) ;
- `api.js` est envoyé avec la bonne `API_BASE_URL` injectée : le fichier local garde l'URL de dev ;
- le CORS de l'API n'autorise que l'adresse du front.

Ce qu'il ne fait pas : `docker build` / `docker push` de l'image.

---

## 1. Prérequis (une fois)

```powershell
winget install Hashicorp.Terraform
winget install Microsoft.AzureCLI
# + Docker Desktop
az login                                   # compte de l'école, abonnement Azure for Students
az account show --query id -o tsv          # ID à mettre dans terraform.tfvars
```

`infra/azure/terraform.tfvars` :
```hcl
subscription_id = "<ID de l'abonnement>"
acr_name        = "mediguessacr2026"
```

## 2. Premier déploiement

Toujours lancer `docker build` **depuis la racine du repo**.

```powershell
# a) Registre seul (l'image doit exister avant la Container App)
cd C:\ESGI\4annee\Trimestre_2\0_PA\MediGuess\infra\azure
terraform init
terraform apply -target="azurerm_container_registry.acr"

# b) Image de l'API
az acr login -n mediguessacr2026
cd ..\..
docker build -f backend/Dockerfile -t mediguessacr2026.azurecr.io/mediguess-api:v1 .
docker push mediguessacr2026.azurecr.io/mediguess-api:v1

# c) Tout le reste (~5 min)
cd infra\azure
terraform apply
terraform output front_url
```

Vérifier : `<api_url>/health` → `{"status":"ok","cases":2000}`.
La 1re requête après une pause prend quelques secondes (l'API se réveille).

## 3. Mises à jour

**Front modifié** (`frontend/`) :
```powershell
cd infra\azure
terraform apply
```

**Backend ou banque de cas modifiés** : **nouveau tag à chaque fois** (`v2`, `v3`…).
⚠️ Réutiliser un tag déjà déployé ne change rien : Terraform ne voit aucune différence et
l'ancienne version de l'API continue de tourner.
```powershell
cd C:\ESGI\4annee\Trimestre_2\0_PA\MediGuess
docker build -f backend/Dockerfile -t mediguessacr2026.azurecr.io/mediguess-api:v2 .
docker push mediguessacr2026.azurecr.io/mediguess-api:v2
cd infra\azure
terraform apply -var="image_tag=v2"
```
Pour ne pas répéter `-var`, changer le `default` de `image_tag` dans `variables.tf`.

**Fin du projet** : `terraform destroy` supprime tout et arrête tous les coûts.

## 4. Donner le rôle admin à un compte

1. Créer le compte normalement dans le jeu.
2. Portail → compte de stockage `mediguess2026` → **Navigateur de stockage** → **Tables** → `users`.
3. Cocher la ligne du compte (RowKey = pseudo en minuscules) → **Modifier**.
4. Passer `is_admin` à `true` → **Mettre à jour**.
   Pour un compte créé avant cette colonne : **Ajouter une propriété** `is_admin`, type **Boolean**, valeur `true`.
   Ou en une commande dans Cloud Shell (remplacer `nina`) :
   ```bash
   az storage entity merge \
     --connection-string "$(az storage account show-connection-string -n mediguess2026 -g mediguess-rg -o tsv)" \
     --table-name users \
     --entity PartitionKey=mg RowKey=nina is_admin=true is_admin@odata.type=Edm.Boolean
   ```
5. Dans le jeu, recharger la page : le bouton **Administration** et la case **Mode admin** apparaissent.

Pour retirer le rôle : passer `is_admin` à `false` (effet immédiat).

---

## 5. Problèmes rencontrés et solutions

| Symptôme | Cause | Solution |
|---|---|---|
| `backend/... not found` au `docker build` | Commande lancée hors du repo | `cd` à la racine de `MediGuess` avant le build |
| `EOF` / `connection forcibly closed` (Docker, `terraform init`) | Connexion IPv6 coupée par le réseau | Désactiver IPv6 (PowerShell admin : `Disable-NetAdapterBinding -Name "*" -ComponentID ms_tcpip6`) ou partage de connexion du téléphone |
| Téléchargement de `python:3.12-slim` impossible | Idem, Docker Hub | `FROM public.ecr.aws/docker/library/python:3.12-slim` dans le Dockerfile |
| `ExpressEnvironmentManagedIdentityNotSupported` | Formulaire du portail : environnement Express + identité managée | Ne pas créer la Container App depuis le portail : Terraform crée un environnement standard |
| `docker login` → `404 Not Found` | Registre supprimé puis recréé avec le même nom | Prendre un nouveau nom (`acr_name` dans `terraform.tfvars`) |
| `Variables not allowed` dans `terraform.tfvars` | Valeur sans guillemets | `subscription_id = "..."` |
| Terraform demande le provider `aws` | Fichiers DynamoDB (`infra/`) mélangés avec ceux d'Azure | Garder Azure dans `infra/azure/` uniquement |
| `Please run 'az login'` | Azure CLI non connectée | `az login` |
| Warnings `deprecated` (`storage_account_name`…) | Évolution du provider azurerm | Sans conséquence avant azurerm v5 |

⚠️ `terraform.tfstate` contient les clés du stockage et du registre en clair : ne jamais le
commiter ni le partager (déjà dans `.gitignore`).

---

## 6. À faire

- [ ] **Banque de cas avec le vrai modèle** : la banque actuelle (2000 cas) vient d'un RF
  allégé de test (top-1 0.70). Sur la machine où le vrai modèle se charge :
  `python -m ml.src.build_case_bank --n-cases 2000`, puis mise à jour du backend (§3).
- [ ] **Ménage** : supprimer les environnements *Express* ratés restés dans le groupe
  `NetworkWatcherRG` (`managedEnvironment-NetworkWatcherR-...`), s'il en reste.
- [ ] **État Terraform partagé** : si plusieurs membres de l'équipe lancent Terraform, stocker
  le `tfstate` dans Azure (backend `azurerm`) plutôt qu'en local.
- [ ] **Backend** : scoring sur la démarche (#13), feedback par template complet (#14),
  classement des scores (table `scores` dans `mediguess2026`) + saisie du nom en fin de partie.

---

## Dev local
- Rapide (stockage en mémoire) : `uvicorn backend.src.api:app --reload --port 8080`
  avec `API_BASE_URL = "http://127.0.0.1:8080"` dans `frontend/api.js`.
- Comme sur Azure (Docker + Azurite) : `docker compose -f backend/docker-compose.yml up --build`
- Tests : `pytest backend`
- En prod, le CORS n'accepte que le front Azure : un front local ne peut pas appeler l'API Azure.
