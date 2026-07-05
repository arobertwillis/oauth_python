# Master Configuration System Requirements

This document outlines the requirements for the Master Configuration file upload system. 

## 1. File Storage & Versioning
- **REQ-1.1:** The system MUST support uploading configuration files (e.g., JSON, YAML) to a designated "master folder" (`data/master_config/`).
- **REQ-1.2:** The master folder MUST be a file-based Git repository.
- **REQ-1.3:** All file modifications (uploads, updates, deletions) MUST be automatically backed up by committing them to the local Git repository.
- **REQ-1.4:** The Git commit history MUST record the actual user who uploaded or modified the file (e.g., by extracting the user's name and email from their Azure AD JWT authentication token).
- **REQ-1.5:** The system MUST surface audit metadata in the UI/API for every file, prominently displaying exactly when it was last updated and by whom.
- **REQ-1.6:** File uploads MUST be transactional: if the Git commit fails after the file has been written to disk, the file write MUST be rolled back so the working tree remains consistent with the Git history.
- **REQ-1.7:** Git MUST be used to manage concurrency. Concurrent modifications to the same file MUST be serialized through Git's commit mechanism, ensuring that no write is silently lost.
- **REQ-1.8:** Deleted files MUST remain fully recoverable from the Git history. The system MUST NOT perform hard resets or history-rewriting operations (e.g., `git filter-branch`, force-push) that would permanently remove deleted file data.
- **REQ-1.9:** The master configuration Git repository MUST reside on a filesystem that is independently backed up (e.g., via scheduled snapshots, replication, or enterprise backup tooling). The system documentation MUST clearly state this as a deployment prerequisite.

## 2. Flexible File Management
- **REQ-2.1:** The system MUST support uploading files to arbitrary subdirectories within the master folder.
- **REQ-2.2:** The upload mechanism MUST be flexible enough to handle different types of configuration files.
- **REQ-2.3:** It MUST be possible to upload a file *without* assigning a specific validation schema (schema-less upload). In this case, the system should only perform basic syntax checking (e.g., ensuring valid JSON or YAML) if applicable.
- **REQ-2.4:** The root of the master configuration folder MUST contain a top-level configuration file (e.g., `master_configuration.json`) that dictates global configuration parameters including: the environment name, a configuration version identifier, the list of registered component folders, and for each component the list of shared files it depends on.
- **REQ-2.5:** Critical system files (e.g., `master_configuration.json`) MUST be protected from accidental deletion via the API or UI. The system MUST reject delete requests for protected files with a clear error message.
- **REQ-2.6:** The system MUST enforce a maximum file upload size of 1 GB. Uploads exceeding this limit MUST be rejected with a clear error message before any processing occurs.

## 3. Schema Validation & Recognition
- **REQ-3.1:** The system MUST support validating uploaded files against predefined schemas (e.g., JSON Schema) to prevent incorrect files from being uploaded.
- **REQ-3.2:** The schemas MUST be maintained in a dedicated location (`data/schemas/`) separate from the master configurations.
- **REQ-3.3:** The system MUST be able to automatically recognize and assign a schema to a file based on its filename. This mapping should be configurable (e.g., mapping `*.settings.json` to the `app_settings` schema).
- **REQ-3.4:** The system MUST provide REST API endpoints and UI views to manage (create, update, delete, list) schemas, so that schemas can be maintained without direct filesystem access.

## 4. Deep / Custom Validation
- **REQ-4.1:** The system MUST support the creation of custom schema validation classes (Python plugins).
- **REQ-4.2:** These custom validation classes MUST allow developers to perform in-depth programmatic validation beyond basic JSON Schema structure (e.g., verifying database connection strings, checking business logic rules).
- **REQ-4.3:** The custom validators must be executed dynamically during the file upload process.

## 5. Interface
- **REQ-5.1:** The system MUST expose a RESTful API service to facilitate file uploads, downloads, and deletions.
- **REQ-5.2:** The system MUST provide a user interface built using Jinja2 templates on top of the REST service to allow human users to easily interact with the master configuration.
- **REQ-5.3:** All clients and synchronization jobs MUST utilize the REST API for uploading and downloading configuration files.
- **REQ-5.4:** The REST API MUST expose interactive OpenAPI/Swagger documentation to facilitate client integration and testing.
- **REQ-5.5:** The REST API layer MUST be strictly secured, enforcing authentication (e.g., Azure AD OAuth2) and authorization for all endpoints.
- **REQ-5.6:** The REST API layer MUST produce detailed application logs for every request and action to facilitate monitoring, debugging, and audit tracking.

## 6. Environment Synchronization & Deployment
- **REQ-6.1:** Each environment (e.g., staging, production) MUST maintain its own unique master configuration Git repository.
- **REQ-6.2:** The system MUST provide a mechanism to synchronize configuration files between environments at deployment time.
- **REQ-6.3:** The system MUST provide a mechanism to back-sync and update a non-production environment using configuration data from the production environment.
- **REQ-6.4:** The deployment mechanism MUST detect conflicts between deployment releases and end-user modifications. It MUST explicitly fail and prevent overriding any configuration file that has been modified directly by an end user in the target environment.
- **REQ-6.5:** The system MUST provide a configuration comparison tool (diffing mechanism) to detect changes, surface conflicts, and allow administrators to safely manage these differences prior to deployment.
- **REQ-6.6:** When a conflict is detected (REQ-6.4), the system MUST provide a resolution mechanism allowing administrators to explicitly accept the incoming change, keep the existing version, or perform a manual merge before the deployment can proceed.
- **REQ-6.7:** The system MUST support bulk uploading of an entire component folder in a single operation to facilitate automated deployments.

## 7. History & Rollback
- **REQ-7.1:** The system MUST provide an interface (API and UI) to view the historical versions of a specific configuration file by querying the Git history.
- **REQ-7.2:** The system MUST allow users to easily restore/rollback a file to any of its previous versions if a deployment or user change breaks the system.

## 8. Runtime Execution & Component Isolation
- **REQ-8.1:** Configuration files MUST be logically organized into folders dedicated to particular system components, while allowing for shared files that are utilized by multiple components. Specifically, the system MUST support the following initial component folders: `cepe/`, `wasabi/`, `gvmerge/`, and `shared/`.
- **REQ-8.2:** System components MUST NOT run directly against the "master configuration" folder. This guarantees that live updates to the master configuration do not impact running batches or cause inconsistencies mid-execution.
- **REQ-8.3:** A background synchronization job (sync job) MUST be implemented to copy the master configuration down to a local, dated folder (e.g., timestamped snapshot) for actual use by the system components during runtime.
- **REQ-8.4:** When synchronizing a component's configuration, the REST API MUST support bulk downloading (e.g., downloading an entire component folder) so the client does not have to explicitly list every required file.
- **REQ-8.5:** Unlike component-specific files, shared configuration files MUST be explicitly requested by the client during the synchronization process.
- **REQ-8.6:** The system MUST define a snapshot retention policy (e.g., number of dated snapshots to keep) and automatically prune older snapshots to prevent unbounded disk usage.

## 9. Tool Configuration (Self-Configuration)
- **REQ-9.1:** The `master_configuration` tool itself MUST be configurable via environment variables (or a `.env` file) to dictate its operational parameters without modifying source code.
- **REQ-9.2:** The tool MUST allow administrators to dynamically set the location of the master configuration repository (`MASTER_CONFIG_DIR`) and the validation schemas directory (`SCHEMAS_DIR`).
- **REQ-9.3:** The tool MUST expose security and authentication settings, including Azure AD Tenant ID, Client ID, and whether API authentication is strictly enforced.
- **REQ-9.4:** The tool MUST support configuring the location of the schema mapping definitions (e.g., `SCHEMA_MAPPING_FILE`), which map filename regex patterns to specific validation schemas.
- **REQ-9.5:** If pushing to an upstream Git remote is enabled, the tool MUST allow configuration of Git credentials (e.g., `GIT_PAT` or `GIT_SSH_KEY_PATH`).

## 10. Testing & Quality Assurance
- **REQ-10.1:** The system MUST have full automated test coverage specifically targeting the REST API layer.
- **REQ-10.2:** The automated test suite MUST verify all upload paths, including creating and validating test configuration files *with* a strict schema (both valid and invalid payloads) and files uploaded *without* a specific schema.

## 11. Python Client Library
- **REQ-11.1:** The solution MUST provide a lightweight Python client library, packaged and distributable as a `pip` installable package, that wraps the REST API for programmatic use by other systems and components.
- **REQ-11.2:** The client library MUST support all core operations: uploading files, downloading individual files, bulk downloading a component folder, listing files, and querying file history.
- **REQ-11.3:** The client library MUST handle authentication (e.g., accepting an Azure AD token or credentials) transparently, so consuming applications do not need to manage raw HTTP headers.
- **REQ-11.4:** The client library MUST be kept minimal with few dependencies, suitable for embedding in batch jobs, CI/CD pipelines, and other Python-based components.
