import os
from pathlib import Path
from dotenv import load_dotenv

print("Running from folder:", os.getcwd())
print(".env exists here?", Path(".env").exists())

# force it to load the .env sitting next to this script
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

key = os.getenv("GROQ_API_KEY")
if key:
    print("Groq key loaded: YES  (starts with", key[:7], ", length", len(key), ")")
else:
    print("Groq key loaded: NO")