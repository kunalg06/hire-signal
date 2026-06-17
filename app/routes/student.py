from flask import Blueprint, jsonify
from app.services.database_service import DatabaseService

student_bp = Blueprint('student', __name__)
db_service = DatabaseService()

@student_bp.route('/student/<link_id>')
def student_dashboard(link_id):
    """Serve student dashboard with embedded code-server"""
    row = db_service.get_session_link(link_id)

    if not row:
        return jsonify({"detail": "Session not found"}), 404

    assignment_id, port, title, description, criteria, starter_code, expires_at = row

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - AI Engineering Assessment & Evaluation Platform</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                font-size: 32px;
                margin-bottom: 10px;
            }}
            .content {{
                padding: 40px;
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 40px;
            }}
            .section {{
                background: #f8f9fa;
                padding: 25px;
                border-radius: 8px;
                border-left: 4px solid #667eea;
            }}
            .section h2 {{
                color: #667eea;
                margin-bottom: 15px;
                font-size: 20px;
            }}
            .section p {{
                color: #555;
                line-height: 1.6;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            .editor-section {{
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                min-height: 600px;
            }}
            .editor-section iframe {{
                width: 100%;
                height: 600px;
                border: none;
            }}
            .btn {{
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                cursor: pointer;
                transition: all 0.3s ease;
                font-weight: 600;
            }}
            .btn-primary {{
                background: #667eea;
                color: white;
                width: 100%;
                margin-top: 15px;
            }}
            .btn-primary:hover {{
                background: #5568d3;
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
            }}
            .status {{
                padding: 15px;
                border-radius: 6px;
                text-align: center;
                font-weight: 600;
                display: none;
                margin-top: 15px;
            }}
            .status.success {{
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }}
            .status.error {{
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }}
            .status.loading {{
                background: #e2e3e5;
                color: #383d41;
            }}
            #results {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                max-height: 400px;
                overflow-y: auto;
                margin-top: 20px;
                display: none;
            }}
            #sessionLogsList {{
                font-size: 13px;
                color: #666;
            }}
            .log-entry {{
                background: #f5f5f5;
                padding: 10px;
                margin: 5px 0;
                border-radius: 4px;
                border-left: 3px solid #667eea;
            }}
            .timer {{
                text-align: center;
                padding: 15px;
                background: #fff3cd;
                border-radius: 6px;
                color: #856404;
                font-weight: 600;
                margin-top: 15px;
            }}
            @media (max-width: 768px) {{
                .content {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 {title}</h1>
                <p>AI Engineering Assessment & Evaluation Platform</p>
            </div>

            <div class="content">
                <div>
                    <div class="section">
                        <h2>📋 Assignment</h2>
                        <p>{description}</p>
                    </div>

                    <div class="section" style="margin-top: 20px;">
                        <h2>✅ Evaluation Criteria</h2>
                        <p>{criteria}</p>
                    </div>

                    <button id="submitBtn" class="btn btn-primary">📤 Submit Solution</button>
                    <div id="status" class="status"></div>

                    <div id="results">
                        <h3 style="color: #667eea; margin-bottom: 15px;">✅ Evaluation Results</h3>
                        <div id="scoreDisplay" style="font-size: 18px; font-weight: bold; margin: 15px 0; color: #667eea;">Score: <span id="scoreValue">--</span>/100</div>
                        <div id="feedbackDisplay" style="color: #555; line-height: 1.6; white-space: pre-wrap; word-break: break-word;"></div>
                        <div id="sessionLogsPanel" style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd;">
                            <h4 style="color: #667eea; margin-bottom: 10px;">📝 Claude Session Logs</h4>
                            <div id="sessionLogsList" style="font-size: 13px; color: #666;"></div>
                        </div>
                    </div>

                    <div class="timer">
                        ⏰ Session Expires: <span id="timer">--:--:--</span>
                    </div>
                </div>

                <div>
                    <div class="editor-section">
                        <iframe src="http://localhost:{port}/?folder=/workspace" allow="clipboard-read; clipboard-write" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-presentation"></iframe>
                    </div>
                </div>
            </div>
        </div>

        <script>
            const LINK_ID = "{link_id}";

            function updateTimer() {{
                const expiresAt = new Date('{expires_at}').getTime();
                if (expiresAt > 0) {{
                    const now = new Date().getTime();
                    const remaining = expiresAt - now;

                    if (remaining <= 0) {{
                        document.getElementById('timer').textContent = 'Expired';
                    }} else {{
                        const hours = Math.floor((remaining % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                        const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
                        const seconds = Math.floor((remaining % (1000 * 60)) / 1000);
                        document.getElementById('timer').textContent =
                            `${{hours}}:${{String(minutes).padStart(2, '0')}}:${{String(seconds).padStart(2, '0')}}`;
                    }}
                }}
            }}

            setInterval(updateTimer, 1000);
            updateTimer();

            document.getElementById('submitBtn').addEventListener('click', async () => {{
                const submitBtn = document.getElementById('submitBtn');
                const statusDiv = document.getElementById('status');

                submitBtn.disabled = true;
                statusDiv.textContent = '⏳ Submitting...';
                statusDiv.className = 'status loading';
                statusDiv.style.display = 'block';

                try {{
                    const response = await fetch(`/api/submit-with-files/${{LINK_ID}}`, {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}}
                    }});

                    const data = await response.json();

                    if (response.ok || response.status === 202) {{
                        statusDiv.textContent = '⏳ Evaluating...';
                        statusDiv.className = 'status loading';

                        await new Promise(r => setTimeout(r, 2000));

                        const resultRes = await fetch(`/api/submission/${{data.submission_id}}`);
                        const resultData = await resultRes.json();

                        const logsRes = await fetch(`/api/session-logs/${{data.submission_id}}`);
                        const logsData = logsRes.ok ? await logsRes.json() : {{'logs': []}};

                        displayResults(resultData, logsData);

                        statusDiv.textContent = '✅ Submission successful!';
                        statusDiv.className = 'status success';
                    }} else {{
                        statusDiv.textContent = '❌ ' + (data.detail || 'Submission failed');
                        statusDiv.className = 'status error';
                    }}
                }} catch (error) {{
                    statusDiv.textContent = '❌ Error: ' + error.message;
                    statusDiv.className = 'status error';
                }} finally {{
                    submitBtn.disabled = false;
                }}
            }});

            function displayResults(submission, sessionLogs) {{
                const scoreValue = submission.score ? submission.score.toFixed(1) : '0';
                document.getElementById('scoreValue').textContent = scoreValue;
                document.getElementById('feedbackDisplay').textContent = submission.feedback || 'No feedback available';

                const logs = sessionLogs.logs || [];
                const logsList = document.getElementById('sessionLogsList');

                if (logs.length === 0) {{
                    logsList.innerHTML = '<p>No Claude interactions recorded</p>';
                }} else {{
                    logsList.innerHTML = logs.map(log => `
                        <div class="log-entry">
                            <strong>${{log.timestamp}}</strong><br/>
                            <strong>Prompt:</strong> ${{log.prompt}}<br/>
                            <strong>Response:</strong> ${{log.response_summary}}<br/>
                            <strong>Files Changed:</strong> ${{log.file_changes_count}}
                        </div>
                    `).join('');
                }}

                document.getElementById('results').style.display = 'block';
            }}
        </script>
    </body>
    </html>
    """

    return html_content, 200, {'Content-Type': 'text/html'}
