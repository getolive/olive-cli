# cli/olive/tools/shell/mcp.py
from fastapi import FastAPI, Request
from tools.shell import run_shell_tool

app = FastAPI()

@app.post("/tools/shell")
async def mcp_shell(request: Request):
    body = await request.json()
    input = body.get("input", {})
    result = run_shell_tool(input)
    return {"output": result}
