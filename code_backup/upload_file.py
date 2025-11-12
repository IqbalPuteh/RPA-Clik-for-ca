import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# If modifying these scopes, delete the file token.json.
# Using 'drive' scope grants full access to all files on your drive.
SCOPES = ['https://www.googleapis.com/auth/drive'] 

# Replace with the ID of the Shared Drive folder you provided
# Your Shared Drive ID: 1R8YLbExcw2L9zq-RUXWrapO0rIehK8ui
SHARED_DRIVE_FOLDER_ID = '1qIApzUHagAmouW0Q2p4R9R9Vwyhs8nxq' 
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

def authenticate_user():
    """Handles the OAuth 2.0 authentication flow."""
    creds = None
    # 1. Check for existing token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # 2. If token is invalid or missing, initiate login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Access token expired, refreshing...")
            creds.refresh(Request())
        else:
            print("Launching browser for initial authentication. Please sign in to your Google Account...")
            # Use the credentials.json file downloaded from Google Cloud Console
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the new/refreshed credentials
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            print(f"Authentication complete. Token saved to {TOKEN_FILE}.")
    return creds

# --- MAIN EXECUTION ---

try:
    # 1. Authenticate as the user
    credentials = authenticate_user()
    service = build('drive', 'v3', credentials=credentials)

    # 2. Prepare file metadata
    file_metadata = {
        'name': 'example.pdf',
        # Set the parent folder to the Shared Drive ID
        'parents': [SHARED_DRIVE_FOLDER_ID] 
    }
    # Ensure 'example.pdf' exists in the same directory!
    media = MediaFileUpload('example.pdf', mimetype='application/pdf')

    print(f"Uploading file to Shared Drive ID: {SHARED_DRIVE_FOLDER_ID} using your quota...")
    
    # 3. Upload file (using supportsAllDrives=True because it's a Shared Drive)
    file = service.files().create(
        body=file_metadata, 
        media_body=media, 
        fields='id, webViewLink',
        supportsAllDrives=True
    ).execute()
    
    file_id = file.get('id')
    web_link = file.get('webViewLink')
    print("✅ Upload successful. File ID:", file_id)

    # 4. Set permission so anyone with the link can view
    permission = {
        'type': 'anyone',
        'role': 'reader'
    }
    service.permissions().create(
        fileId=file_id, 
        body=permission,
        supportsAllDrives=True
    ).execute()
    print("✅ Permissions set to 'anyone with the link can view'.")

    # 5. Display links
    download_link = f"https://drive.google.com/uc?id={file_id}&export=download"

    print("\n--- Links ---")
    print("Web viewer link:", web_link)
    print("Direct download link:", download_link)

except FileNotFoundError as e:
    print(f"\nFATAL ERROR: Authentication failed. Make sure your JSON file is named '{CREDENTIALS_FILE}' and is in the same directory.")
    print(f"Details: {e}")
except Exception as e:
    print(f"\nAn error occurred during API operations: {e}")