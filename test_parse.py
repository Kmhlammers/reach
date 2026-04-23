from pathlib import Path
import json
from reach_processor import parse_workbook_bytes

payload = {
    "file_id": "test-file-003",
    "file_name": "REACH Format_TianjinHuatai.xlsx",
    "site_url": "https://dummy.sharepoint.com/sites/test",
    "file_path": "/Shared Documents/ReachUpload/test.xlsx",
    "file_link": "https://dummy.sharepoint.com/test.xlsx",
    "source_type": "sharepoint",
}

file_bytes = Path("REACH Format_TianjinHuatai.xlsx").read_bytes()

result = parse_workbook_bytes(file_bytes, payload)

print(json.dumps(result, indent=2, default=str))