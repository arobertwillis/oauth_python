# Master Config Client

A lightweight Python client for the Master Configuration REST API.

## Installation

```bash
pip install -e .
```

## Usage

```python
from master_config_client import MasterConfigClient

# Initialize with base URL and access token
client = MasterConfigClient(
    base_url="http://localhost:8000/api/config",
    token="YOUR_AZURE_AD_TOKEN"
)

# List files
files = client.list_files()

# Download a file
content = client.download_file("cepe/settings.json")

# Upload a file
client.upload_file("cepe/settings.json", '{"key": "value"}', schema_name="app_settings")

# Synchronize an entire component (REQ-11.5)
# This downloads the component folder + shared files to a local dated directory
local_dir = client.sync("cepe", shared_files=["shared/global.json"])
print(f"Batch config ready at: {local_dir}")
```
