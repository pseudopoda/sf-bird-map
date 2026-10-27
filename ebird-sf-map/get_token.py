"""Run this ONCE on your own computer to get a Gmail refresh token.
Needs client_secret.json (downloaded from Google Cloud) in the same folder."""
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",
    scopes=["https://www.googleapis.com/auth/gmail.readonly"],
)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("\nCLIENT_ID:    ", creds.client_id)
print("CLIENT_SECRET:", creds.client_secret)
print("REFRESH_TOKEN:", creds.refresh_token)
