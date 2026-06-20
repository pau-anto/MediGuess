# Accessing the MIMIC-III dataset

> Reference guide for the MediGuess team. MIMIC-III is the **advanced / stretch** data source — the project's core does **not** depend on it. Start the credentialing process early, because step 1 takes several business days.

## Two access paths

MIMIC-III can be used in two ways. For this project, the **cloud (Athena)** path is strongly preferred.

| Path | How it works | For us |
|------|--------------|--------|
| **A — Cloud / Athena** | Data stays in an MIT-hosted S3 bucket. You run SQL queries against it via Athena, without downloading or storing anything yourself. | **Recommended.** Simpler, and directly satisfies the "AWS component" requirement. |
| **B — Local download** | You download the compressed CSVs and work locally (pandas, etc.). | Avoid. Bulky and heavier to handle; MIT itself recommends the cloud. |

**Key advantage of path A:** you run standard SQL queries against MIMIC-III without loading the data into a database, and without paying to store the dataset. This is the officially recommended approach.

## Setup procedure (Athena path)

### 1. Become a credentialed user on PhysioNet

This is the longest step. It breaks down into:

1. **Complete the CITI training** (the report is required later).
   - Register on the CITI Program site.
   - Select **"Massachusetts Institute of Technology Affiliates"** as your organization — this makes the course **free**. Do not create a paid individual-learner account.
   - Use an **academic email** to speed up later verification.
   - Take the **"Data or Specimens Only Research"** course and complete all modules.
   - Download the **training report** (not the certificate) from Records → View-Print-Share.
2. **Create a PhysioNet account** (academic email again).
3. **Submit your application:**
   - Credentialing page → personal information.
   - Training page → upload the CITI **report**.
   - **Reference section (critical):** as a student you must provide your supervisor's name and contact. Enter **Hugo Cornu** (hugo.cornu@protonmail.com), not yourself. Give him a heads-up by email.
   - State a research topic, e.g. *"4IABD academic project: educational diagnostic serious game using MIMIC-III."*
   - Sign the **Data Use Agreement (DUA)** in the dataset's Files section.

> ⏱️ Approval can take several business days and is delayed if the application is incomplete.

### 2. Link your AWS account to PhysioNet

On your PhysioNet profile, "Cloud" page. For AWS, add your **AWS canonical ID** (the numeric account identifier from your AWS profile — **not** your email).

### 3. Request dataset access for that cloud account

Once your AWS account is linked, request MIMIC-III access for it from the dataset page on PhysioNet.

### 4. Deploy the provided CloudFormation template

This creates the query environment **in your own AWS account**: an AWS Glue database, Glue tables (the schema of each table), an Athena workgroup configured for SQL queries, and an S3 bucket for query results. Optionally, an Amazon SageMaker notebook instance with a sample Python notebook.

### 5. Query the data

In the Athena query editor, switch to the MIMIC workgroup and write SQL against the database. For ML: run queries from the SageMaker notebook (or locally via the SDK), pull a DataFrame, and train your model on it.

## Useful links

- [MIMIC — Getting Started](https://mimic.mit.edu/docs/gettingstarted/)
- [MIMIC — Link your cloud account](https://mimic.mit.edu/docs/gettingstarted/cloud/link)
- [PhysioNet MIMIC-III v1.4 dataset page](https://physionet.org/content/mimiciii/1.4/)
- [PhysioNet cloud settings](https://physionet.org/settings/cloud/)
- [AWS tutorial — MIMIC-III with Athena](https://aws.amazon.com/blogs/big-data/perform-biomedical-informatics-without-a-database-using-mimic-iii-data-and-amazon-athena/)
- [MIMIC Code Repository (CloudFormation template + examples)](https://github.com/MIT-LCP/mimic-code)

## Managing costs

With Athena you pay **per query** (by data scanned), not for storing the dataset. A few habits keep costs low on a student project:

- Select only the columns you need (avoid `SELECT *`) and filter early.
- Materialize a clean subset: once your training table is defined, export it once to your own S3 bucket in **Parquet** format. Athena queries on Parquet run about 10× faster than on CSV.
- Delete the CloudFormation stack when you are done, so nothing keeps running.

## Important note on "diagnosis"

MIMIC-III is an **ICU** database, not a ready-made "symptoms → disease" file. It contains diagnoses (ICD codes), vital signs, lab results, notes... but turning that into playable cases takes real SQL work.

**Consequence for our strategy:** it is feasible and showcases skills, which is exactly why MIMIC-III is positioned as an **advanced / stretch** layer, not the core. Keep the patient-profile dataset as the guaranteed baseline, and add MIMIC-III as a "real cases" hard mode if access is granted and time allows.
