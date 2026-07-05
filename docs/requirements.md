# Master Configuration System Requirements

This document outlines the requirements for the Master Configuration file upload system. 

## 1. File Storage & Versioning
- **REQ-1.1:** The system MUST support uploading configuration files (e.g., JSON, YAML) to a designated "master folder" (`data/master_config/`).
- **REQ-1.2:** The master folder MUST be a file-based Git repository.
- **REQ-1.3:** All file modifications (uploads, updates, deletions) MUST be automatically backed up by committing them to the local Git repository.
- **REQ-1.4:** The Git commit history MUST record the actual user who uploaded or modified the file (e.g., by extracting the user's name and email from their Azure AD JWT authentication token).

## 2. Flexible File Management
- **REQ-2.1:** The system MUST support uploading files to arbitrary subdirectories within the master folder.
- **REQ-2.2:** The upload mechanism MUST be flexible enough to handle different types of configuration files.
- **REQ-2.3:** It MUST be possible to upload a file *without* assigning a specific validation schema (schema-less upload). In this case, the system should only perform basic syntax checking (e.g., ensuring valid JSON or YAML) if applicable.

## 3. Schema Validation & Recognition
- **REQ-3.1:** The system MUST support validating uploaded files against predefined schemas (e.g., JSON Schema) to prevent incorrect files from being uploaded.
- **REQ-3.2:** The schemas MUST be maintained in a dedicated location (`data/schemas/`) separate from the master configurations.
- **REQ-3.3:** The system MUST be able to automatically recognize and assign a schema to a file based on its filename. This mapping should be configurable (e.g., mapping `*.settings.json` to the `app_settings` schema).

## 4. Deep / Custom Validation
- **REQ-4.1:** The system MUST support the creation of custom schema validation classes (Python plugins).
- **REQ-4.2:** These custom validation classes MUST allow developers to perform in-depth programmatic validation beyond basic JSON Schema structure (e.g., verifying database connection strings, checking business logic rules).
- **REQ-4.3:** The custom validators must be executed dynamically during the file upload process.

## 5. Interface
- **REQ-5.1:** The system MUST expose a RESTful API service to facilitate file uploads, downloads, and deletions.
- **REQ-5.2:** The system MUST provide a user interface built using Jinja2 templates on top of the REST service to allow human users to easily interact with the master configuration.

## 6. Environment Synchronization & Deployment
- **REQ-6.1:** Each environment (e.g., staging, production) MUST maintain its own unique master configuration Git repository.
- **REQ-6.2:** The system MUST provide a mechanism to synchronize configuration files between environments at deployment time.
- **REQ-6.3:** The system MUST provide a mechanism to back-sync and update a non-production environment using configuration data from the production environment.
- **REQ-6.4:** The deployment mechanism MUST detect conflicts between deployment releases and end-user modifications. It MUST explicitly fail and prevent overriding any configuration file that has been modified directly by an end user in the target environment.
- **REQ-6.5:** The system MUST provide a configuration comparison tool (diffing mechanism) to detect changes, surface conflicts, and allow administrators to safely manage these differences prior to deployment.
