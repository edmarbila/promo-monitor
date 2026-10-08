import os
from dotenv import load_dotenv
load_dotenv()
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "control_api:app",
        host=os.environ.get("CONTROL_API_HOST", "0.0.0.0"),
        port=int(os.environ.get("CONTROL_API_PORT", "8787")),
        reload=False,
    )
