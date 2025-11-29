import uvicorn
from llm_email_app.config import settings

if __name__ == '__main__':
    uvicorn.run("llm_email_app.api:app", host="0.0.0.0", port=settings.BACKEND_PORT, reload=True)

