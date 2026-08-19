import os
import re
import warnings
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass # In production (Railway), env vars are injected directly, so dotenv isn't strictly required
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path
from fastapi import File, UploadFile, HTTPException
import shutil
import pandas as pd

# Suppress the langchain-community deprecation warning
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*langchain-community.*")

# Auto-install psycopg2-binary for Supabase if missing
try:
    import psycopg2
except ImportError:
    import subprocess
    import sys
    print("Auto-installing psycopg2-binary into current environment...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
    import psycopg2

from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# Environment variables are loaded at the top of the file

# Initialize FastAPI app
app = FastAPI(title="DataLens API")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://data-lens-ivory-seven.vercel.app",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fetch the Supabase URL from the environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Dynamic connection state
ACTIVE_DB_URI = DATABASE_URL
agent = None
db = None

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

# Initialize checkpointer
memory = MemorySaver()

def initialize_agent(db_uri):
    global agent, db
    try:
        db = SQLDatabase.from_uri(db_uri)
        toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        tools = toolkit.get_tools()
        agent = create_react_agent(
            llm,
            tools,
            prompt=system_prefix,
            checkpointer=memory
        )
    except Exception as e:
        print(f"Failed to initialize agent: {e}")

if ACTIVE_DB_URI:
    initialize_agent(ACTIVE_DB_URI)

# Pydantic model for the request body
class ChatRequest(BaseModel):
    user_message: str

# API Root / Healthcheck
@app.get("/")
async def root():
    return {"message": "DataLens API is running", "status": "ok"}

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

@app.post("/chat")
async def chat(request: ChatRequest):
    if not agent:
        raise HTTPException(status_code=500, detail="Database agent not initialized")
    config = {"configurable": {"thread_id": "1"}}
    response = agent.invoke({"messages": [("user", request.user_message)]}, config)
    return {"reply": response["messages"][-1].content}

class ConnectRequest(BaseModel):
    db_url: str

class CustomDBRequest(BaseModel):
    db_type: str
    host: str
    port: str
    db_name: str
    username: str
    password: str

class SpreadsheetRequest(BaseModel):
    url: str

class AnalyzeRequest(BaseModel):
    table_name: str

@app.get("/api/insights")
async def get_insights(table: str = None):
    global ACTIVE_DB_URI, agent
    if not agent:
        raise HTTPException(status_code=500, detail="Database agent not initialized")
    
    target = f"the '{table}' table" if table else "the connected database"
    prompt = f"""
    You are an expert Business and HR Data Analyst. Analyze {target} and determine 4 actionable, business-critical Key Performance Indicators (KPIs) that best summarize the core business value of this dataset. 
    
    CRITICAL RULE: DO NOT return generic database metadata. You MUST NOT return metrics like "Total Records", "Total Rows", "Number of Columns", "Null Values", or "Total Countries". 
    Instead, think about what a Manager, Executive, or HR Director would actually want to see. For example, if it's sales data, show "Total Revenue", "Average Order Value", "Top Selling Product". If it's HR data, show "Average Salary", "Turnover Rate", "Total Employees", etc.
    
    You MUST write and execute SQL queries to calculate the real numerical values for these 4 business KPIs from the data.
    After you have the real values, return your final answer STRICTLY as a valid JSON array of 4 objects. Do not include any other text or markdown formatting in your final response other than the JSON array.
    Each object must have the following keys:
    - "title": A short name for the business metric (e.g. "Total Revenue", "Avg Salary", "Active Employees").
    - "value": The actual number you queried, formatted nicely (e.g. "$1.2M", "14.5%", "1,248").
    - "icon": Choose the most appropriate icon name from this list ONLY: ["users", "briefcase", "trending", "cash"].
    - "trend": A short 3-5 word description providing context (e.g. "across all departments", "highest monthly value").
    - "positive": a boolean true or false indicating if this is a good thing.
    """
    try:
        config = {"configurable": {"thread_id": "insights"}}
        response = agent.invoke({"messages": [("user", prompt)]}, config)
        reply = response["messages"][-1].content
        
        # Extract JSON array from the reply using regex
        import re
        import json
        match = re.search(r'\[\s*\{.*?\}\s*\]', reply, re.DOTALL)
        if match:
            json_str = match.group(0)
            stats = json.loads(json_str)
            return {"stats": stats}
        else:
            print("Failed to parse JSON from agent:", reply)
            # Fallback stats
            return {"stats": [
                {"title": "Data Analyzed", "value": "100%", "icon": "trending", "trend": "Ready for queries", "positive": True}
            ]}
    except Exception as e:
        print(f"Insights error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze-dataset")
async def analyze_dataset(request: AnalyzeRequest):
    global ACTIVE_DB_URI, agent
    if not ACTIVE_DB_URI:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        from sqlalchemy import create_engine
        import pandas as pd
        import numpy as np
        import json
        import re

        engine = create_engine(ACTIVE_DB_URI)
        
        # Load data (with limit for safety)
        query = f'SELECT * FROM "{request.table_name}" LIMIT 50000'
        df = pd.read_sql_query(query, engine)
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Table is empty")
        
        # Profiling
        row_count, col_count = df.shape
        
        # Missing values & Quality Score
        total_cells = row_count * col_count
        missing_cells = int(df.isnull().sum().sum())
        data_quality_score = max(0, min(100, int(100 * (1 - (missing_cells / total_cells)))))
        
        # Data types
        col_types = {}
        for col, dtype in df.dtypes.items():
            if pd.api.types.is_numeric_dtype(dtype):
                col_types[col] = "Numerical"
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                col_types[col] = "Datetime"
            else:
                col_types[col] = "Categorical"
                
        # Statistical & Outlier Engine
        numeric_cols = [c for c, t in col_types.items() if t == "Numerical"]
        stats_summary = {}
        outliers_detected = {}
        
        for col in numeric_cols:
            col_data = df[col].dropna()
            if len(col_data) == 0:
                continue
                
            stats_summary[col] = {
                "mean": float(col_data.mean()),
                "median": float(col_data.median()),
                "min": float(col_data.min()),
                "max": float(col_data.max()),
                "std": float(col_data.std())
            }
            
            # IQR Outliers
            Q1 = col_data.quantile(0.25)
            Q3 = col_data.quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            outliers = col_data[(col_data < lower_bound) | (col_data > upper_bound)]
            outliers_detected[col] = len(outliers)
            
        # Prepare structured summary for LLM
        summary_payload = {
            "table_name": request.table_name,
            "rows": row_count,
            "columns": col_count,
            "data_quality_score": data_quality_score,
            "missing_cells": missing_cells,
            "column_types": col_types,
            "numeric_stats": stats_summary,
            "outlier_counts": outliers_detected
        }
        
        # Construct prompt
        prompt = f"""
        You are an expert data strategist and executive analyst. 
        I have automatically profiled the '{request.table_name}' table and generated the following statistical summary:
        
        {json.dumps(summary_payload, indent=2)}
        
        Based on this statistical summary, generate an executive insights report.
        You MUST return your answer STRICTLY as a valid JSON object. Do not include markdown formatting or any other text.
        
        The JSON object must have EXACTLY the following structure:
        {{
            "data_quality_score": {data_quality_score},
            "hygiene_notes": ["<note 1 about missing values or data types>", "<note 2 about statistical outliers>"],
            "key_insights": ["<top business finding 1 derived from the stats>", "<top finding 2>", "<top finding 3>"],
            "suggested_queries": ["<a specific SQL question the user could ask to investigate outliers>", "<another analytical question>", "<a third question>"]
        }}
        """
        
        # Invoke Agent
        config = {"configurable": {"thread_id": "analyze"}}
        response = agent.invoke({"messages": [("user", prompt)]}, config)
        reply = response["messages"][-1].content
        
        # Parse JSON
        match = re.search(r'\{.*?\}', reply, re.DOTALL)
        if match:
            try:
                result_json = json.loads(match.group(0))
                return result_json
            except json.JSONDecodeError:
                pass
                
        # Fallback if parsing fails
        return {
            "data_quality_score": data_quality_score,
            "hygiene_notes": [f"Missing values: {missing_cells}", "Outliers detected in numeric columns"],
            "key_insights": ["Dataset analyzed successfully", f"Rows: {row_count}, Columns: {col_count}"],
            "suggested_queries": ["Show me the summary stats", "What are the outliers?"]
        }
        
    except Exception as e:
        print(f"Analyze error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/connect-spreadsheet")
async def connect_spreadsheet(request: SpreadsheetRequest):
    global ACTIVE_DB_URI
    try:
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', request.url)
        if not match:
            raise Exception("Invalid Google Sheets URL. Could not extract Spreadsheet ID.")
        sheet_id = match.group(1)
        csv_export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        
        df = pd.read_csv(csv_export_url)
        
        import os
        from sqlalchemy import create_engine
        
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise Exception("DATABASE_URL environment variable is missing")
            
        engine = create_engine(database_url)
        table_name = f"sheet_{sheet_id[:8]}"
        df.to_sql(table_name, engine, if_exists="replace", index=False)
        
        ACTIVE_DB_URI = database_url
        initialize_agent(ACTIVE_DB_URI)
        
        from sqlalchemy import create_engine, inspect
        engine = create_engine(ACTIVE_DB_URI)
        inspector = inspect(engine)
        schema = {}
        for t_name in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns(t_name)]
            schema[t_name] = columns
            
        return {"status": "success", "schema": schema}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Spreadsheet connection failed: {str(e)}")

@app.post("/api/connect")
async def connect_db(request: ConnectRequest):
    global ACTIVE_DB_URI
    try:
        from sqlalchemy import create_engine
        engine = create_engine(request.db_url)
        with engine.connect() as conn:
            pass # Validate connection
        ACTIVE_DB_URI = request.db_url
        initialize_agent(ACTIVE_DB_URI)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/connect-custom-db")
async def connect_custom_db(request: CustomDBRequest):
    global ACTIVE_DB_URI
    
    if request.db_type.lower() == "postgresql":
        uri = f"postgresql+psycopg2://{request.username}:{request.password}@{request.host}:{request.port}/{request.db_name}"
    elif request.db_type.lower() == "mysql":
        uri = f"mysql+pymysql://{request.username}:{request.password}@{request.host}:{request.port}/{request.db_name}"
    else:
        raise HTTPException(status_code=400, detail="Unsupported database type. Use PostgreSQL or MySQL.")
        
    try:
        from sqlalchemy import create_engine, inspect
        engine = create_engine(uri)
        with engine.connect() as conn:
            pass # Validate connection
            
        ACTIVE_DB_URI = uri
        initialize_agent(ACTIVE_DB_URI)
        
        # Return schema 
        inspector = inspect(engine)
        schema = {}
        for table_name in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns(table_name)]
            schema[table_name] = columns
            
        return {"status": "success", "schema": schema}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    global ACTIVE_DB_URI
    try:
        file_location = f"uploaded_{file.filename}"
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
        
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(file_location)
        elif file.filename.lower().endswith('.xlsx'):
            try:
                df = pd.read_excel(file_location)
            except Exception as e:
                if 'openpyxl' in str(e).lower():
                    import subprocess
                    import sys
                    print("Auto-installing openpyxl into current environment...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
                    df = pd.read_excel(file_location)
                else:
                    raise e
        else:
            raise Exception("Unsupported format. Use .csv or .xlsx")
            
        import os
        from sqlalchemy import create_engine
        
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise Exception("DATABASE_URL environment variable is missing")
            
        engine = create_engine(database_url)
        table_name = file.filename.split('.')[0].replace(" ", "_").replace("-", "_").lower()
        df.to_sql(table_name, engine, if_exists="replace", index=False)
        
        ACTIVE_DB_URI = database_url
        initialize_agent(ACTIVE_DB_URI)
        
        # Clean up the temporary local file
        if os.path.exists(file_location):
            os.remove(file_location)
            
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/schema")
async def get_schema():
    global ACTIVE_DB_URI
    if not ACTIVE_DB_URI:
        return {}
        
    try:
        from sqlalchemy import create_engine, inspect
        engine = create_engine(ACTIVE_DB_URI)
        inspector = inspect(engine)
        schema = {}
        for table_name in inspector.get_table_names():
            if not table_name.startswith('sqlite_'):
                columns = [col['name'] for col in inspector.get_columns(table_name)]
                schema[table_name] = columns
        return schema
    except Exception as e:
        print(f"Error fetching schema: {e}")
        return {}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
# Triggering reload to pick up openpyxl dependency
