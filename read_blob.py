from azure.storage.blob import BlobServiceClient
from reach_processor import parse_workbook_bytes  # jouw bestaande parser

# 🔑 vul deze in
connection_string = "DefaultEndpointsProtocol=https;AccountName=reachstoragekl;AccountKey=J5l3rhK41c6n48wpTX9EsfA6hj4m8Vx8Pk+jNi49KtAwoGq21Lse//+Svz2tZOfFTSQTof+4BVZF+ASt+EETNw==;EndpointSuffix=core.windows.net"
container_name = "reach-upload"
blob_name = "2026-03-16_140445_Reach Format.xlsx"  # exact zoals in Azure

# 🔌 connectie maken
blob_service_client = BlobServiceClient.from_connection_string(connection_string)
blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)

# 📥 download bestand
blob_data = blob_client.download_blob().readall()

print("✅ Blob gedownload")

# 🧪 payload mock (zoals jouw function verwacht)
payload = {
    "file_id": "manual-test-1",
    "file_name": blob_name,
    "site_url": "local-test",
    "file_path": blob_name,
    "file_link": blob_name,
    "source_type": "blob"
}

# ⚙️ parse uitvoeren
result = parse_workbook_bytes(blob_data, payload)

# 📊 resultaat bekijken
print("SUMMARY:")
print(result["summary"])

print("\nRECORDS:")
for r in result["records"][:3]:  # eerste 3 tonen
    print(r)

print("\nISSUES:")
for i in result["issues"]:
    print(i)