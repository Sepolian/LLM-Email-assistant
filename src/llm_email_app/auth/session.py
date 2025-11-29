from starlette.requests import Request
from starlette.responses import RedirectResponse
from llm_email_app.auth.google_oauth import get_web_flow, TOKEN_DIR, DEFAULT_SCOPES
import json
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
] + DEFAULT_SCOPES


async def login(request: Request):
    flow = get_web_flow(scopes=SCOPES)
    authorization_url, state = flow.authorization_url(
        access_type="offline", prompt="consent"
    )
    request.session["state"] = state
    return RedirectResponse(authorization_url)


async def auth_callback(request: Request):
    print("In auth_callback")
    try:
        state = request.session["state"]
        print(f"Session state: {state}")
        
        flow = get_web_flow(scopes=SCOPES)
        print("Fetching token...")
        flow.fetch_token(authorization_response=str(request.url))
        print("Token fetched.")

        credentials = flow.credentials
        request.session["credentials"] = credentials.to_json()
        print("Credentials stored in session.")

        if credentials.id_token:
            print("ID token found in credentials.")
            try:
                id_info = id_token.verify_oauth2_token(
                    credentials.id_token, google_requests.Request(), flow.client_config["client_id"]
                )
                print(f"ID token verified. User info: {id_info}")
                request.session["user"] = {
                    "name": id_info.get("name"),
                    "email": id_info.get("email"),
                    "picture": id_info.get("picture"),
                }
                print("User info stored in session.")
            except ValueError as e:
                print(f"Error verifying token: {e}")
        else:
            print("ID token not found in credentials.")

        # Save credentials to a file
        with open(TOKEN_DIR / "google_token.json", "w") as f:
            f.write(credentials.to_json())
        print("Credentials saved to file.")

        print("Redirecting to /")
        return RedirectResponse(url="/")
    except Exception as e:
        print(f"An error occurred in auth_callback: {e}")
        import traceback
        traceback.print_exc()
        # Still redirect, but the frontend will likely fail to log in.
        return RedirectResponse(url="/")


def get_credentials(request: Request):
    if "credentials" not in request.session:
        # Check if token file exists
        token_file = TOKEN_DIR / "google_token.json"
        if token_file.exists():
            with open(token_file, "r") as f:
                creds_json_str = f.read()
                request.session["credentials"] = creds_json_str
                return json.loads(creds_json_str)
        return None

    creds_json = json.loads(request.session["credentials"])
    return creds_json
