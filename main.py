import os
import warnings
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path

# Suppress the langchain-community deprecation warning
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*langchain-community.*")

from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

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
system_prefix = """You are DataLens, an AI Data Tutor. When you run a SQL query, you must briefly explain the logic of the query in simple English to the user. 
If the user asks for a graph, chart, or visualization, you must FIRST query the database to get the actual data, and then generate a Mermaid.js chart enclosed in ```mermaid ... ``` blocks. 
IMPORTANT: Use valid Mermaid syntax. Do NOT use the dummy data from the examples below; you MUST use the real data you queried from the database.
For bar or line charts, use the `xychart-beta` type. The `x-axis` MUST contain the array of category labels (e.g. dates or regions). The `y-axis` MUST be a single string representing the value label (e.g. "Sales"). Use `bar [...]` for bar charts and `line [...]` for line charts. 
CRITICAL LIMITATIONS: 
1. If there are more than 10-12 data points, you MUST aggregate the data (e.g., group by month) or limit the results (e.g., top 10) so the x-axis labels do not overlap and remain readable!
2. The `xychart-beta` library ONLY supports ONE data series. It does NOT support grouped bar charts, multiple colors, or multiple data series. If the user asks for multiple colors or grouped data, explain this limitation politely and provide a standard single-color chart instead.
Syntax example:
```mermaid
xychart-beta
    title "YOUR ACTUAL TITLE"
    x-axis ["Category 1", "Category 2", "Category 3"]
    y-axis "Y Axis Label"
    bar [10, 20, 30]
```
For pie charts, use `pie`. Syntax example:
```mermaid
pie title "YOUR ACTUAL TITLE"
    "Category1" : 40
    "Category2" : 60
```
Always end your response by suggesting one smart follow-up question they could ask. 
CRITICAL CONVERSATIONAL RULE: If the user replies with just a chart type (e.g., "bar chart", "pie chart"), you MUST apply that chart type to the data from your PREVIOUS message. Do NOT assume they are answering your suggested follow-up question unless they explicitly mention the topic of the follow-up question."""

# Extract tools for the graph
toolkit = SQLDatabaseToolkit(db=db, llm=llm)
tools = toolkit.get_tools()

# Initialize checkpointer
memory = MemorySaver()

# Initialize the LangGraph SQL agent
agent = create_react_agent(
    llm,
    tools,
    prompt=system_prefix,
    checkpointer=memory
)

# Pydantic model for the request body
class ChatRequest(BaseModel):
    user_message: str

# Serve the frontend
@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

@app.post("/chat")
async def chat(request: ChatRequest):
    # Invoke the agent with the user's message and a fixed thread_id for conversation history
    config = {"configurable": {"thread_id": "1"}}
    response = agent.invoke({"messages": [("user", request.user_message)]}, config)
    return {"reply": response["messages"][-1].content}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
