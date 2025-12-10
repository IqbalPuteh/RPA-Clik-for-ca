from fastapi import FastAPI, HTTPException, status, Request, Depends
import uvicorn, asyncio
from playwright.async_api import async_playwright  
from config import USERNAME, PASSWORD, LOGIN_URL, HEADLESS 
import logging
import time
import os
import mimetypes
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from config_helper import load_settings, update_env
from fastapi.responses import HTMLResponse
import sqlite3
from contextlib import closing
from datetime import datetime

# --- GOOGLE DRIVE IMPORTS ---
from google.auth.transport.requests import Request as GoogleRequest  
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- GOOGLE DRIVE CONFIGURATION ---
SHARED_DRIVE_FOLDER_ID = '1qIApzUHagAmouW0Q2p4R9R9Vwyhs8nxq' 
SCOPES = ['https://www.googleapis.com/auth/drive'] 
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

# --- GOOGLE DRIVE AUTHENTICATION FUNCTION ---
async def authenticate_user():
    """Handles the OAuth 2.0 authentication flow."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())  # Use the aliased GoogleRequest
        else:
            print("Launching browser for initial authentication. Please sign in...")
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            print(f"Authentication complete. Token saved to {TOKEN_FILE}.")
    return creds

# --- GOOGLE DRIVE UPLOAD FUNCTION ---
async def upload_to_drive(file_path: str, message_id: str):
    credentials = await authenticate_user()
    
    def _do_upload():
        service = build('drive', 'v3', credentials=credentials)
        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [SHARED_DRIVE_FOLDER_ID]
        }
        # infer mimetype from file extension so HTML or PDF both upload correctly
        mtype = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        media = MediaFileUpload(file_path, mimetype=mtype)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        service.permissions().create(
            fileId=file['id'],
            body={'type': 'anyone', 'role': 'reader'},
            supportsAllDrives=True
        ).execute()
        return file['id'], file['webViewLink']

    return await asyncio.to_thread(_do_upload)


app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get("/")
async def read_root():
    return {"message": "Welcome to RPA Click for FTI Credit Analyst ver. 1.3"}
    
@app.get("/get_company")
async def get_company(
    message_id: str = "00025FTICREVI2026",
    trade_name: str = "PT Prima Tata Solusindo",
    address: str = "Gedung Graha Pena Jawa Pos Lt.5, Jl Raya Kebayoran Lama No.12",
    sub_district: str = "GROGOL UTARA",
    district: str = "KEBAYORAN LAMA",
    postal_code: str = "20146",
    business_number: str = "028822948013000",
    phone: str = "08119931126"
) -> str:
    playwright = None
    browser = None
    context = None
    page = None   
    max_retries = 3
    base_delay = 5
    last_error = None
    pdf_filename = None
      
    for attempt in range(0, max_retries):
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=HEADLESS)
            context = await browser.new_context()
            page = await context.new_page()
            
            # --- RPA steps ---
            await page.goto(LOGIN_URL)
            await page.wait_for_load_state("load")
            await page.get_by_role("button", name="").click()
            await page.get_by_role("link", name="English").click()

            await page.get_by_role("textbox", name="Username").fill(USERNAME)
            await page.get_by_role("textbox", name="Password").fill(PASSWORD)
            await page.get_by_role("button", name="Login").click()
            
            await page.wait_for_load_state("load")
            await page.get_by_role("link", name="Company").nth(2).click()

            await page.wait_for_load_state("load")
            await page.locator("#CompanyModel_PurposeOfEnquiry").select_option("20")
            await page.locator("#CompanyModel_CompanyDataModel_MessageID").fill(message_id)
            await page.locator("#CompanyModel_CompanyDataModel_TradeName").fill(trade_name)
            await page.get_by_role("textbox", name="FIELD 'ADDRESS' LENGTH IS NOT").fill(address)
            await page.get_by_role("textbox", name="FIELD 'SUB DISTRICT' IS").fill(sub_district)
            await page.get_by_role("textbox", name="FIELD 'DISTRICT' IS MANDATORY").fill(district)
            await page.locator("#CompanyModel_AddressDataModel_City").select_option("0394")
            await page.get_by_role("textbox", name="FIELD 'POSTAL CODE' IS").fill(postal_code)
            await page.locator("#CompanyModel_AddressDataModel_Country").select_option("ID")
            await page.locator("#CompanyModel_IdentificationCodeModel_BusniessNumber").fill(business_number)
            await page.get_by_role("textbox", name="AT LEAST ONE BETWEEN 'PHONE").fill(phone)

            await page.wait_for_load_state("load")
            await page.get_by_text("Next").click()

            await page.wait_for_load_state("load")
            await page.locator("#ContractModel_IndividualRole").select_option("B")
            await page.locator("#operationCombo").select_option("[[N99,F01],F01]")
            await page.locator("#ContractModel_ContractDataModelCredit_ApplicationAmount").fill("100000000")
            await page.get_by_text("Submit").click()

            await page.wait_for_load_state("load")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            pdf_filename = f"{message_id}_company_{timestamp}.pdf"

            # --- PDF Download ---
            page.set_default_timeout(120000)
            async with page.expect_download() as download_info:
                await page.get_by_role("link", name=" View PDF").click()
            
            download = await download_info.value
            await download.save_as(pdf_filename)
            logger.info(f"PDF successfully saved locally as: {pdf_filename}")
            
            # --- CALL GOOGLE DRIVE UPLOAD ---
            file_id, web_link = await upload_to_drive(pdf_filename, message_id)
            
            # --- Cleanup ---
            if os.path.exists(pdf_filename):
                os.remove(pdf_filename)
                logger.info(f"Local file {pdf_filename} removed.")
                
            await context.close()
            await browser.close()
            await playwright.stop()
            
            logger.info(f"Attempt {attempt+1} succeeded")
            return f"Company RPA & Drive upload completed successfully on attempt #{attempt+1}. Drive Link: {web_link}"

        except Exception as e:
            last_error = e
            logger.error(f"Attempt {attempt+1} failed: {str(e)}")
            
            # --- Cleanup on failure ---
            if page:
                await page.screenshot(path=f"ss-comp-error-attempt{attempt+1}.png")
            if context:
                await context.close()
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
            
            # --- Retry logic ---
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
            
            # Clean up local PDF if it was created before failure
            if pdf_filename and os.path.exists(pdf_filename):
                os.remove(pdf_filename)
                logger.info(f"Local file {pdf_filename} removed after failure.")
    
    # If all attempts failed
    logger.error("All retry attempts on Company report failed")
    raise HTTPException(
        status_code=500, 
        detail=f"Company report failed after {max_retries} attempts. Last error: {str(last_error)}"
    )

@app.get("/get_individual")
async def get_individual(
    message_id: str = "00026FTICREVI2026",
    name: str = "Tri Wahyudin",
    birth_date: str = "1977/11/26",
    gender: str = "L",
    address: str = "JL RAYA PKP GRAHA ARJUNA NO G",
    sub_district: str = "KELAPA DUA WETAN",
    district: str = "CIRACAS",
    city: str = "0395",
    postal_code: str = "13730",
    country: str = "ID",
    identity_type: str = "1",
    id_number: str = "3276052611770004",
    phone_number: str = "08119931126"
) -> str:
    playwright = None
    browser = None
    context = None
    page = None   
    max_retries = 3
    base_delay = 5 
    last_error = None
    pdf_filename = None
    
    for attempt in range(0, max_retries):
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=HEADLESS)
            context = await browser.new_context()
            page = await context.new_page()
            
            # --- RPA steps ---
            await page.goto(LOGIN_URL)
            await page.wait_for_load_state("load")
            await page.get_by_role("button", name="").click()
            await page.get_by_role("link", name="English").click()

            await page.get_by_role("textbox", name="Username").fill(USERNAME)
            await page.get_by_role("textbox", name="Password").fill(PASSWORD)
            await page.get_by_role("button", name="Login").click()

            await page.wait_for_load_state("load")
            await page.get_by_role("link", name="Individual").first.click()

            await page.wait_for_load_state("load")
            await page.locator("#IndividualModel_PurposeOfEnquiry").select_option("20")
            await page.locator("#IndividualModel_IndividualDataModel_MessageID").fill(message_id)
            await page.locator("#IndividualModel_IndividualDataModel_NameAsId").fill(name)
            await page.get_by_role("textbox", name="YYYY/MM/DD").fill(birth_date)
            await page.get_by_role("textbox", name="YYYY/MM/DD").press("Enter")
            await page.locator("#IndividualModel_IndividualDataModel_GenderCode").select_option(gender)
            await page.get_by_role("textbox", name="FIELD 'ADDRESS' LENGTH IS NOT").fill(address)
            await page.get_by_role("textbox", name="FIELD 'SUB DISTRICT' IS").fill(sub_district)
            await page.get_by_role("textbox", name="FIELD 'DISTRICT' IS MANDATORY").fill(district)
            await page.locator("#IndividualModel_AddressDataModel_City").select_option(city)
            await page.get_by_role("textbox", name="FIELD 'POSTAL CODE' IS").fill(postal_code)
            await page.locator("#IndividualModel_AddressDataModel_Country").select_option(country)
            await page.locator("#IndividualModel_IdentificationCodeDataModel_Type").select_option(identity_type)
            await page.locator("#IndividualModel_IdentificationCodeDataModel_Id").fill(id_number)
            await page.locator("#IndividualModel_ContactDataModel_PhoneNumber").fill(phone_number)
            await page.get_by_text("Next").click()

            await page.wait_for_load_state("load")
            await page.locator("#ContractModel_IndividualRole").select_option("B")
            await page.locator("#operationCombo").select_option("[[P99,F01],F01]")
            await page.locator("#ContractModel_ContractDataModelCredit_ApplicationAmount").fill("100000000")
            await page.get_by_text("Submit").click()

            await page.wait_for_load_state("load")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            html_filename = f"{message_id}_individual_{timestamp}.html"

            # --- Save current HTML view ---
            await page.wait_for_load_state("load")
            html_content = await page.content()
            with open(html_filename, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"HTML successfully saved locally as: {html_filename}")

            # --- CALL GOOGLE DRIVE UPLOAD ---
            file_id, web_link = await upload_to_drive(html_filename, message_id)

            # --- Cleanup ---
            if os.path.exists(html_filename):
                os.remove(html_filename)
                logger.info(f"Local file {html_filename} removed.")

            await context.close()
            await browser.close()
            await playwright.stop()
            
            logger.info(f"Attempt {attempt+1} succeeded")
            return f"Individual RPA & Drive upload completed successfully on attempt #{attempt+1}. Drive Link: {web_link}"

        except Exception as e:
            last_error = e
            logger.error(f"Attempt {attempt+1} failed: {str(e)}")
            
            if page:
                await page.screenshot(path=f"ss-indv-error-attempt{attempt+1}.png")
            if context:
                await context.close()
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
            
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
                
            # Clean up local PDF if it was created before failure
            if pdf_filename and os.path.exists(pdf_filename):
                os.remove(pdf_filename)
                logger.info(f"Local file {pdf_filename} removed after failure.")
    
    # If all attempts failed
    logger.error("All retry attempts on Individual report failed")
    raise HTTPException(
        status_code=500, 
        detail=f"Individual report failed after {max_retries} attempts. Last error: {str(last_error)}"
    )

DB_NAME = "clik_data.db"

# --- Pydantic Model for Response Only ---
class MessageIdResponse(BaseModel):
    message_id: str
    is_new: bool

# --- Database Setup ---
def init_db():
    with closing(sqlite3.connect(DB_NAME)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS id_mappings (
                    submission_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS counter_state (
                    id INTEGER PRIMARY KEY,
                    last_val INTEGER NOT NULL
                )
            """)
            cursor.execute("INSERT OR IGNORE INTO counter_state (id, last_val) VALUES (1, 0)")
            conn.commit()



# --- Core Logic (Changed to GET) ---
@app.get("/generate-id", response_model=MessageIdResponse)
def get_or_create_message_id(submission_id):
    
    clean_submission_id = submission_id.strip()
    
    if not clean_submission_id:
        raise HTTPException(status_code=400, detail="Submission ID cannot be empty")

    with closing(sqlite3.connect(DB_NAME)) as conn:
        with closing(conn.cursor()) as cursor:
            
            # 1. CHECK
            cursor.execute("SELECT message_id FROM id_mappings WHERE submission_id = ?", (clean_submission_id,))
            row = cursor.fetchone()
            
            if row:
                return MessageIdResponse(message_id=row[0], is_new=False)
            
            # 2. CREATE
            try:
                cursor.execute("SELECT last_val FROM counter_state WHERE id = 1")
                current_val = cursor.fetchone()[0]
                
                next_val = (current_val % 99999) + 1
                
                counter_string = f"{next_val:05d}"
                now = datetime.now()
                month = now.strftime("%m")
                year = now.strftime("%Y")
                type_code = "FTICLI"
                
                new_message_id = f"{counter_string}{type_code}{month}{year}"
                
                cursor.execute("UPDATE counter_state SET last_val = ? WHERE id = 1", (next_val,))
                cursor.execute("INSERT INTO id_mappings (submission_id, message_id) VALUES (?, ?)", 
                               (clean_submission_id, new_message_id))
                conn.commit()
                
                return MessageIdResponse(message_id=new_message_id, is_new=True)
                
            except Exception as e:
                print(e)
                conn.rollback()
                raise HTTPException(status_code=500, detail=str(e))


# ---= Experimental section =---
# ---  API-Key Security ---
API_KEY = "supersecret098"
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME)

def require_api_key(key: str = Depends(api_key_header)):
    if key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API Key"
        )

# --- Schema for Validation ---
class ConfigModel(BaseModel):
    LOGIN_URL: str
    USERNAME: str
    PASSWORD: str
    BASE_URL: str
    HEADLESS: bool

# --- FastAPI App Setup ---
templates = Jinja2Templates(directory="templates")

@app.get(
    "/config",
    response_model=ConfigModel,
)
def get_config():
    # Initialize DB on startup
    init_db()
    return load_settings()

@app.put(
    "/config",
    response_model=ConfigModel,
)
def put_config(cfg: ConfigModel):
    update_env(cfg.dict())
    return cfg

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    cfg = load_settings()
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "config": cfg
    })

if __name__ == "__main__":
    uvicorn.run(
        "test-html:app",        
        host="0.0.0.0",
        port=8000,
        reload=True
    )