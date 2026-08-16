import os
import warnings
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

# Suppress the langchain-community deprecation warning
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_community")

from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langchain_community.agent_toolkits import create_sql_agent

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="DataLens API")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows all origins (good for local testing)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to the database
db = SQLDatabase.from_uri("sqlite:///datalens_sandbox.db")

# Initialize LLM using AIMLAPI
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    api_key=os.environ.get("AIMLAPI_API_KEY"),
    base_url="https://api.aimlapi.com/v1"
)

# Custom prefix (system prompt) for the agent
system_prefix = """You are DataLens, an AI Data Tutor. When you run a SQL query, you must briefly explain the logic of the query in simple English to the user. Always end your response by suggesting one smart follow-up question they could ask."""

# Initialize the SQL agent
agent = create_sql_agent(
    llm=llm,
    db=db,
    agent_type="tool-calling",
    prefix=system_prefix,
    verbose=True
)

# Pydantic model for the request body
class ChatRequest(BaseModel):
    user_message: str

@app.get("/")
async def root():
    return {"status": "success", "message": "DataLens API is running. Ready for queries!"}

@app.post("/chat")
async def chat(request: ChatRequest):
    # Invoke the agent with the user's message
    response = agent.invoke({"input": request.user_message})
    return {"output": response.get("output")}
