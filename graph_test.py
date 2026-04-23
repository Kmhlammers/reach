import requests

from get_token import get_access_token

token = get_access_token()

url = "https://graph.microsoft.com/v1.0/sites/preconfoodgroup.sharepoint.com:/sites/EUDR-Reach"
headers = {
    "Authorization": f"Bearer {token}"
}

resp = requests.get(url, headers=headers)
print(resp.status_code)
print(resp.text)