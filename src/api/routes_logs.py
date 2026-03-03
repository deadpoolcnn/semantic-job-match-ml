"""
Logs viewer endpoint for monitoring application activity.
"""
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

router = APIRouter(prefix="/logs", tags=["Logs"])

LOG_FILE = Path("/var/log/semantic-job-match/app.log")


@router.get("/view", response_class=HTMLResponse)
async def view_logs_html():
    """
    HTML page for viewing logs in browser.
    """
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Application Logs</title>
        <meta charset="utf-8">
        <style>
            body {
                font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
                background: #1e1e1e;
                color: #d4d4d4;
                margin: 0;
                padding: 20px;
            }
            h1 {
                color: #4ec9b0;
                font-size: 24px;
                margin-bottom: 10px;
            }
            .controls {
                margin-bottom: 20px;
                padding: 15px;
                background: #252526;
                border-radius: 5px;
            }
            button {
                background: #0e639c;
                color: white;
                border: none;
                padding: 8px 16px;
                margin-right: 10px;
                border-radius: 3px;
                cursor: pointer;
                font-size: 14px;
            }
            button:hover {
                background: #1177bb;
            }
            select, input {
                padding: 6px 10px;
                margin-right: 10px;
                border-radius: 3px;
                border: 1px solid #3c3c3c;
                background: #3c3c3c;
                color: #d4d4d4;
                font-size: 14px;
            }
            #logs {
                background: #1e1e1e;
                border: 1px solid #3c3c3c;
                padding: 15px;
                border-radius: 5px;
                white-space: pre-wrap;
                word-wrap: break-word;
                max-height: 70vh;
                overflow-y: auto;
                font-size: 13px;
                line-height: 1.5;
            }
            .error { color: #f48771; }
            .warning { color: #dcdcaa; }
            .info { color: #4ec9b0; }
            .timestamp { color: #858585; }
            #status {
                display: inline-block;
                margin-left: 10px;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 12px;
            }
            #status.loading {
                background: #1177bb;
                color: white;
            }
            #status.success {
                background: #4ec9b0;
                color: #1e1e1e;
            }
        </style>
    </head>
    <body>
        <h1>📋 Application Logs</h1>
        <div class="controls">
            <label>Lines: 
                <select id="lines">
                    <option value="50">50</option>
                    <option value="100" selected>100</option>
                    <option value="200">200</option>
                    <option value="500">500</option>
                    <option value="1000">1000</option>
                    <option value="all">All</option>
                </select>
            </label>
            
            <label>Filter: 
                <input type="text" id="filter" placeholder="e.g., ERROR, WARNING">
            </label>
            
            <button onclick="fetchLogs()">🔄 Refresh</button>
            <button onclick="clearLogs()">🗑️ Clear Display</button>
            <button onclick="startAutoRefresh()">▶️ Auto-refresh (5s)</button>
            <button onclick="stopAutoRefresh()">⏸️ Stop</button>
            
            <span id="status"></span>
        </div>
        
        <div id="logs">Loading...</div>
        
        <script>
            let autoRefreshInterval = null;
            
            async function fetchLogs() {
                const lines = document.getElementById('lines').value;
                const filter = document.getElementById('filter').value;
                const status = document.getElementById('status');
                
                status.className = 'loading';
                status.textContent = 'Loading...';
                
                try {
                    let url = `/logs/raw?lines=${lines}`;
                    if (filter) url += `&filter=${encodeURIComponent(filter)}`;
                    
                    const response = await fetch(url);
                    const text = await response.text();
                    
                    const logsDiv = document.getElementById('logs');
                    logsDiv.innerHTML = highlightLogs(text || 'No logs available');
                    logsDiv.scrollTop = logsDiv.scrollHeight;
                    
                    status.className = 'success';
                    status.textContent = `✓ Updated ${new Date().toLocaleTimeString()}`;
                } catch (error) {
                    document.getElementById('logs').textContent = 'Error loading logs: ' + error;
                    status.className = '';
                    status.textContent = '✗ Error';
                }
            }
            
            function highlightLogs(text) {
                return text
                    .replace(/ERROR/g, '<span class="error">ERROR</span>')
                    .replace(/WARNING/g, '<span class="warning">WARNING</span>')
                    .replace(/INFO/g, '<span class="info">INFO</span>')
                    .replace(/\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}/g, 
                             '<span class="timestamp">$&</span>');
            }
            
            function clearLogs() {
                document.getElementById('logs').textContent = '';
            }
            
            function startAutoRefresh() {
                if (autoRefreshInterval) return;
                fetchLogs();
                autoRefreshInterval = setInterval(fetchLogs, 5000);
            }
            
            function stopAutoRefresh() {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                    autoRefreshInterval = null;
                }
            }
            
            // Initial load
            fetchLogs();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/raw", response_class=PlainTextResponse)
async def get_logs_raw(
    lines: Optional[str] = Query("100", description="Number of lines (or 'all')"),
    filter: Optional[str] = Query(None, description="Filter logs containing this text"),
):
    """
    Return raw log file content.
    
    Query params:
    - lines: Number of lines to return from end of file (default 100, or 'all')
    - filter: Only return lines containing this text (case-insensitive)
    """
    if not LOG_FILE.exists():
        return "Log file not found. Logs may not be configured or no activity yet."
    
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        # Apply filter if specified
        if filter:
            all_lines = [line for line in all_lines if filter.lower() in line.lower()]
        
        # Return requested number of lines
        if lines == "all":
            return "".join(all_lines)
        else:
            n = int(lines)
            return "".join(all_lines[-n:])
    
    except Exception as e:
        return f"Error reading logs: {str(e)}"


@router.delete("/clear")
async def clear_logs():
    """
    Clear the log file (admin operation).
    """
    try:
        if LOG_FILE.exists():
            LOG_FILE.write_text("")
            return {"status": "success", "message": "Log file cleared"}
        return {"status": "success", "message": "Log file does not exist"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
