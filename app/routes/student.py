from flask import Blueprint, jsonify
from app.services.database_service import DatabaseService

student_bp = Blueprint('student', __name__)
db_service = DatabaseService()


@student_bp.route('/student/<link_id>')
def student_dashboard(link_id):
    row = db_service.get_session_link(link_id)

    if not row:
        return jsonify({"detail": "Session not found"}), 404

    assignment_id, port, title, description, criteria, starter_code, expires_at = row

    docker_available = port is not None
    vscode_url = f"http://localhost:{port}/?folder=/workspace" if docker_available else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — hire-signal Assessment</title>
    <style>
        *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}

        /* ── Landing screen ── */
        #landing {{
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 32px 20px;
        }}
        .landing-card {{
            background: white;
            border-radius: 16px;
            box-shadow: 0 24px 64px rgba(0,0,0,0.18);
            max-width: 780px;
            width: 100%;
            overflow: hidden;
        }}
        .landing-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 36px 40px;
            color: white;
        }}
        .landing-header .badge {{
            display: inline-block;
            background: rgba(255,255,255,0.2);
            border: 1px solid rgba(255,255,255,0.4);
            border-radius: 20px;
            padding: 4px 14px;
            font-size: 0.78em;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin-bottom: 14px;
        }}
        .landing-header h1 {{
            font-size: 1.9em;
            font-weight: 800;
            line-height: 1.25;
            margin-bottom: 8px;
        }}
        .landing-header .meta {{
            font-size: 0.88em;
            opacity: 0.85;
        }}
        .landing-body {{
            padding: 36px 40px;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 28px;
        }}
        @media (max-width: 600px) {{ .info-grid {{ grid-template-columns: 1fr; }} }}
        .info-box {{
            background: #f8f9fc;
            border-left: 4px solid #667eea;
            border-radius: 8px;
            padding: 18px 20px;
        }}
        .info-box h3 {{
            color: #667eea;
            font-size: 0.8em;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 10px;
        }}
        .info-box p {{
            color: #444;
            line-height: 1.65;
            font-size: 0.9em;
            white-space: pre-wrap;
        }}
        .notice-box {{
            background: #fff8e1;
            border: 1px solid #ffe082;
            border-radius: 8px;
            padding: 14px 18px;
            margin-bottom: 28px;
            font-size: 0.86em;
            color: #5d4037;
            line-height: 1.6;
        }}
        .notice-box strong {{ color: #e65100; }}
        .timer-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 24px;
            padding: 14px 18px;
            background: #f0f2ff;
            border-radius: 8px;
            font-size: 0.9em;
        }}
        .timer-label {{ color: #667eea; font-weight: 600; }}
        .timer-value {{ color: #333; font-weight: 700; font-family: monospace; font-size: 1.05em; }}
        .btn-start {{
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1.1em;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
            letter-spacing: 0.02em;
        }}
        .btn-start:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(102,126,234,0.45);
        }}
        {''.join([f"""
        .docker-warn {{
            background: #fff3e0;
            border: 1px solid #ffcc80;
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 20px;
            font-size: 0.88em;
            color: #5d4037;
        }}
        .docker-warn code {{ background: #ffe0b2; padding: 2px 6px; border-radius: 3px; font-size: 0.95em; }}
        """ if not docker_available else ''])}

        /* ── Assessment screen ── */
        #assessment {{
            display: none;
            flex-direction: column;
            height: 100vh;
        }}
        .assess-topbar {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 0 20px;
            height: 52px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            gap: 12px;
        }}
        .assess-title {{
            font-weight: 700;
            font-size: 0.95em;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 40%;
        }}
        .assess-center {{
            display: flex;
            align-items: center;
            gap: 16px;
            font-size: 0.85em;
        }}
        .assess-timer {{
            font-family: monospace;
            font-size: 1em;
            background: rgba(255,255,255,0.15);
            padding: 4px 12px;
            border-radius: 20px;
        }}
        .assess-actions {{ display: flex; gap: 8px; align-items: center; }}
        .btn-submit {{
            background: white;
            color: #667eea;
            border: none;
            border-radius: 6px;
            padding: 7px 18px;
            font-weight: 700;
            font-size: 0.88em;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .btn-submit:hover {{ background: #f0f2ff; }}
        .btn-submit:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        /* ── Warmup screen ── */
        #warmup {{
            display: none;
            flex-direction: column;
            height: 100vh;
            align-items: center;
            justify-content: center;
            background: #1e1e2e;
            color: #cdd6f4;
            gap: 24px;
        }}
        .warmup-spinner {{
            width: 48px; height: 48px;
            border: 4px solid rgba(255,255,255,0.1);
            border-top-color: #667eea;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .warmup-msg {{ font-size: 1em; color: #a6adc8; }}
        .warmup-dots::after {{
            content: '';
            animation: dots 1.5s steps(4, end) infinite;
        }}
        @keyframes dots {{
            0%  {{ content: ''; }}
            25% {{ content: '.'; }}
            50% {{ content: '..'; }}
            75% {{ content: '...'; }}
        }}

        .assess-iframe {{
            flex: 1;
            border: none;
            width: 100%;
        }}

        /* ── Modal ── */
        .modal-overlay {{
            display: none;
            position: fixed; inset: 0;
            background: rgba(0,0,0,0.5);
            z-index: 100;
            align-items: center;
            justify-content: center;
        }}
        .modal-overlay.show {{ display: flex; }}
        .modal {{
            background: white;
            border-radius: 12px;
            padding: 32px;
            max-width: 440px;
            width: 90%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        .modal h3 {{ color: #333; margin-bottom: 12px; font-size: 1.15em; }}
        .modal p {{ color: #666; line-height: 1.6; margin-bottom: 24px; font-size: 0.93em; }}
        .modal-actions {{ display: flex; gap: 10px; justify-content: flex-end; }}
        .btn-cancel {{
            padding: 9px 20px; background: #f5f5f5; color: #555;
            border: none; border-radius: 6px; cursor: pointer; font-weight: 600;
        }}
        .btn-confirm {{
            padding: 9px 20px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white; border: none; border-radius: 6px;
            cursor: pointer; font-weight: 600;
        }}

        /* ── Toast ── */
        .toast {{
            position: fixed; bottom: 24px; right: 24px;
            background: #333; color: white;
            padding: 12px 20px; border-radius: 8px;
            font-size: 0.88em; z-index: 200;
            opacity: 0; transition: opacity 0.3s;
            max-width: 340px; line-height: 1.5;
        }}
        .toast.show {{ opacity: 1; }}
        .toast.success {{ background: #2e7d32; }}
        .toast.error   {{ background: #c62828; }}
    </style>
</head>
<body>

<!-- ══════════════════════════════════════════════════════ -->
<!-- LANDING SCREEN                                         -->
<!-- ══════════════════════════════════════════════════════ -->
<div id="landing">
    <div class="landing-card">
        <div class="landing-header">
            <div class="badge">hire-signal · Assessment</div>
            <h1>{title}</h1>
            <div class="meta">Complete the challenge below · Your session is timed</div>
        </div>

        <div class="landing-body">
            {'<div class="docker-warn">⚠️ <strong>Docker environment unavailable.</strong> The browser-based VS Code IDE requires Docker Desktop to be running with the <code>coding-platform-student:latest</code> image built. You can still submit — evaluation will run on whatever is in the workspace.</div>' if not docker_available else ''}

            <div class="notice-box">
                <strong>Before you start:</strong> Once you click Start Assessment, your session begins.
                Work in the VS Code environment that opens. Use Claude AI freely to help you solve the
                challenge — you are being evaluated on <em>how well you collaborate with AI</em>,
                not on writing code without it. Click <strong>Submit Assessment</strong> in the
                top bar when you are done.
            </div>

            <div class="info-grid">
                <div class="info-box">
                    <h3>Challenge Description</h3>
                    <p>{description}</p>
                </div>
                <div class="info-box">
                    <h3>Evaluation Criteria</h3>
                    <p>{criteria}</p>
                </div>
            </div>

            <div class="timer-row">
                <span class="timer-label">⏱ Session expires in</span>
                <span class="timer-value" id="landingTimer">calculating...</span>
            </div>

            <button class="btn-start" onclick="startAssessment()">
                {'🚀 Start Assessment' if docker_available else '⚠️ Start (No IDE — Docker unavailable)'}
            </button>
        </div>
    </div>
</div>

<!-- ══════════════════════════════════════════════════════ -->
<!-- WARMUP SCREEN                                          -->
<!-- ══════════════════════════════════════════════════════ -->
<div id="warmup">
    <div class="warmup-spinner"></div>
    <div class="warmup-msg">Starting your VS Code environment<span class="warmup-dots"></span></div>
    <div style="font-size:0.8em; color:#585b70;">This usually takes 5–15 seconds</div>
</div>

<!-- ══════════════════════════════════════════════════════ -->
<!-- ASSESSMENT SCREEN                                      -->
<!-- ══════════════════════════════════════════════════════ -->
<div id="assessment">
    <div class="assess-topbar">
        <div class="assess-title">📋 {title}</div>
        <div class="assess-center">
            <span class="assess-timer" id="assessTimer">--:--:--</span>
        </div>
        <div class="assess-actions">
            <button class="btn-submit" id="submitBtn" onclick="openSubmitModal()">
                📤 Submit Assessment
            </button>
        </div>
    </div>
    {'<iframe id="vsCodeFrame" class="assess-iframe" allow="clipboard-read; clipboard-write; microphone; camera; fullscreen"></iframe>' if docker_available else '<div style="flex:1; display:flex; align-items:center; justify-content:center; background:#1e1e2e; color:#888; flex-direction:column; gap:12px;"><div style="font-size:2em;">🐳</div><div>Docker environment not available — submit when ready to evaluate</div></div>'}
</div>

<!-- Submit Confirmation Modal -->
<div class="modal-overlay" id="submitModal">
    <div class="modal">
        <h3>Submit Assessment?</h3>
        <p>This will capture your entire workspace and begin AI evaluation. Make sure you have saved all your files in the VS Code editor before submitting.</p>
        <div class="modal-actions">
            <button class="btn-cancel" onclick="closeSubmitModal()">Go Back</button>
            <button class="btn-confirm" id="confirmBtn" onclick="submitAssessment()">Yes, Submit</button>
        </div>
    </div>
</div>

<!-- Toast notification -->
<div class="toast" id="toast"></div>

<script>
    const LINK_ID    = "{link_id}";
    const EXPIRES_AT = new Date('{expires_at}');

    // ── Timer ──────────────────────────────────────────────────────────
    function formatRemaining() {{
        const diff = EXPIRES_AT - Date.now();
        if (diff <= 0) return 'Expired';
        const h = Math.floor(diff / 3600000);
        const m = Math.floor((diff % 3600000) / 60000);
        const s = Math.floor((diff % 60000) / 1000);
        return `${{h}}:${{String(m).padStart(2,'0')}}:${{String(s).padStart(2,'0')}}`;
    }}

    function tickTimer() {{
        const t = formatRemaining();
        const lt = document.getElementById('landingTimer');
        const at = document.getElementById('assessTimer');
        if (lt) lt.textContent = t;
        if (at) at.textContent = t;
    }}
    tickTimer();
    setInterval(tickTimer, 1000);

    // ── Start assessment ───────────────────────────────────────────────
    const VSCODE_URL = "{vscode_url}";
    const DOCKER_AVAILABLE = {'true' if docker_available else 'false'};

    async function startAssessment() {{
        document.getElementById('landing').style.display = 'none';

        if (!DOCKER_AVAILABLE) {{
            document.getElementById('assessment').style.display = 'flex';
            return;
        }}

        // Show warmup screen, poll until code-server responds
        document.getElementById('warmup').style.display = 'flex';
        const frame = document.getElementById('vsCodeFrame');

        const MAX_WAIT_MS  = 45000;
        const POLL_INTERVAL = 1500;
        const deadline = Date.now() + MAX_WAIT_MS;

        while (Date.now() < deadline) {{
            try {{
                // no-cors fetch throws only on network error (connection refused)
                await fetch(VSCODE_URL, {{ mode: 'no-cors', cache: 'no-store' }});
                // Reached here → server is up
                break;
            }} catch (_) {{
                await new Promise(r => setTimeout(r, POLL_INTERVAL));
            }}
        }}

        // Load the iframe (whether we confirmed ready or timed out)
        frame.src = VSCODE_URL;

        document.getElementById('warmup').style.display    = 'none';
        document.getElementById('assessment').style.display = 'flex';
    }}

    // ── Submit modal ───────────────────────────────────────────────────
    function openSubmitModal()  {{ document.getElementById('submitModal').classList.add('show'); }}
    function closeSubmitModal() {{ document.getElementById('submitModal').classList.remove('show'); }}

    // ── Submit ─────────────────────────────────────────────────────────
    async function submitAssessment() {{
        const confirmBtn = document.getElementById('confirmBtn');
        const submitBtn  = document.getElementById('submitBtn');
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Submitting...';
        submitBtn.disabled = true;

        try {{
            const res  = await fetch(`/api/submit-with-files/${{LINK_ID}}`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }}
            }});
            const data = await res.json();

            closeSubmitModal();

            if (res.ok || res.status === 202) {{
                showToast('✅ Submitted! Evaluation is running — you will receive results shortly.', 'success', 8000);
                submitBtn.textContent = '✅ Submitted';
            }} else {{
                showToast('❌ ' + (data.detail || 'Submission failed — please try again.'), 'error');
            }}
        }} catch (err) {{
            closeSubmitModal();
            showToast('❌ Network error: ' + err.message, 'error');
        }} finally {{
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Yes, Submit';
        }}
    }}

    // ── Toast ──────────────────────────────────────────────────────────
    function showToast(msg, type = '', duration = 5000) {{
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.className = `toast show ${{type}}`;
        setTimeout(() => t.className = 'toast', duration);
    }}
</script>
</body>
</html>"""

    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
