import html as html_module

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
        .eval-spinner {{
            width: 40px; height: 40px;
            border: 4px solid #f0f2ff;
            border-top-color: #667eea;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 20px;
        }}
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
                Work in the VS Code environment that opens. Use Gemini AI freely to help you solve the
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
<!-- SUBMITTED SCREEN                                       -->
<!-- ══════════════════════════════════════════════════════ -->
<div id="submitted" style="display:none; height:100vh; align-items:center; justify-content:center; background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); flex-direction:column; gap:24px;">
    <div id="submittedCard" style="background:white; border-radius:16px; padding:48px 52px; max-width:520px; width:90%; text-align:center; box-shadow:0 24px 64px rgba(0,0,0,0.2);"></div>
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
            <button class="btn-submit" id="submitBtn" onclick="openNudgeModal()">
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

<!-- Verification Nudge Modal -->
<div class="modal-overlay" id="nudgeModal">
    <div class="modal">
        <h3>Before you submit:</h3>
        <p>Did you run the code?<br>Did you test edge cases?</p>
        <div class="modal-actions">
            <button class="btn-cancel" onclick="closeNudgeModal()">Not yet</button>
            <button class="btn-confirm" onclick="closeNudgeModal(); openSubmitModal()">Looks good, continue</button>
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
        const warmupEl = document.getElementById('warmup');
        warmupEl.style.display = 'flex';
        const frame = document.getElementById('vsCodeFrame');

        const MAX_WAIT_MS   = 45000;
        const POLL_INTERVAL = 1500;
        const deadline = Date.now() + MAX_WAIT_MS;
        let serverReady = false;

        while (Date.now() < deadline) {{
            try {{
                // no-cors fetch throws only on network error (connection refused)
                await fetch(VSCODE_URL, {{ mode: 'no-cors', cache: 'no-store' }});
                serverReady = true;
                break;
            }} catch (_) {{
                await new Promise(r => setTimeout(r, POLL_INTERVAL));
            }}
        }}

        warmupEl.style.display = 'none';

        if (!serverReady) {{
            // Container is gone (submitted or expired) — show a clear message
            document.getElementById('landing').style.display = 'none';
            document.getElementById('submitted').style.display = 'flex';
            // Rewrite the submitted card to reflect "session ended" not "just submitted"
            document.querySelector('#submitted div').innerHTML = `
                <div style="font-size:3em; margin-bottom:16px;">session ended</div>
                <h2 style="color:#333; font-size:1.5em; margin-bottom:12px;">This Session Has Ended</h2>
                <p style="color:#666; line-height:1.7; margin-bottom:24px; font-size:0.95em;">
                    The VS Code environment for this link is no longer running.<br>
                    This happens after submission or when the session expires.<br>
                    Contact your employer if you need a new session link.
                </p>
                <div style="background:#fff3e0; border-radius:8px; padding:14px 18px; font-size:0.85em; color:#e65100; font-weight:600;">
                    You may close this tab.
                </div>
            `;
            return;
        }}

        // Server is up — load the iframe
        frame.src = VSCODE_URL;
        document.getElementById('assessment').style.display = 'flex';
    }}

    // ── Nudge modal ────────────────────────────────────────────────────
    function openNudgeModal()   {{ document.getElementById('nudgeModal').classList.add('show'); }}
    function closeNudgeModal()  {{ document.getElementById('nudgeModal').classList.remove('show'); }}

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

            // Safely parse JSON — server errors may return HTML
            let data = {{}};
            const ct = res.headers.get('content-type') || '';
            if (ct.includes('application/json')) {{
                data = await res.json();
            }} else {{
                const text = await res.text();
                console.error('Non-JSON response from server:', res.status, text.slice(0, 200));
                data = {{ detail: `Server error ${{res.status}} — check Flask logs` }};
            }}

            closeSubmitModal();

            if (res.ok || res.status === 202) {{
                // Remove iframe first so code-server stops reconnecting to the now-dead container
                const frame = document.getElementById('vsCodeFrame');
                if (frame) frame.src = 'about:blank';
                startPolling(data.submission_id);
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

    // ── Submission result helpers ──────────────────────────────────────
    function escHtml(s) {{
        return String(s || '').replace(/[&<>"]/g, function(c) {{
            return ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c];
        }});
    }}

    function showSubmittedPolling() {{
        document.getElementById('submittedCard').innerHTML =
            '<div style="font-size:3em;margin-bottom:16px;">submitted</div>' +
            '<h2 style="color:#333;font-size:1.5em;margin-bottom:16px;">Assessment Submitted</h2>' +
            '<div class="eval-spinner"></div>' +
            '<p style="color:#667eea;font-weight:600;margin-bottom:8px;">Evaluating your submission...</p>' +
            '<p style="color:#666;font-size:0.88em;margin-bottom:24px;">Analysis usually takes <strong>20–40 seconds</strong>.</p>' +
            '<div style="background:#f0f2ff;border-radius:8px;padding:14px 18px;font-size:0.85em;color:#667eea;font-weight:600;">' +
            'You can close this tab — your employer will be notified when results are ready.</div>';
    }}

    function showSubmittedResults(data) {{
        const rec       = (data.hire_evaluation && data.hire_evaluation.hire_recommendation) || 'unknown';
        const rawScore  = data.hire_evaluation != null && data.hire_evaluation.composite_score != null ? data.hire_evaluation.composite_score : (data.score || 0);
        const score     = Number.isFinite(Number(rawScore)) ? Math.round(Number(rawScore)) : 0;
        const fb     = escHtml(data.feedback || '');
        const colors = {{ strong_hire:'#2e7d32', hire:'#1565c0', select:'#e65100', pass:'#795548' }};
        const labels = {{ strong_hire:'Strong Hire', hire:'Hire', select:'Select', pass:'Pass' }};
        const color  = colors[rec] || '#9e9e9e';
        const label  = escHtml(labels[rec] || rec);
        document.getElementById('submittedCard').innerHTML =
            '<div style="font-size:3em;margin-bottom:16px;">complete</div>' +
            '<h2 style="color:#333;font-size:1.5em;margin-bottom:20px;">Evaluation Complete</h2>' +
            '<div style="display:flex;justify-content:center;gap:16px;margin-bottom:20px;">' +
                '<div style="text-align:center;padding:16px 24px;border:2px solid #667eea;border-radius:8px;">' +
                    '<div style="font-size:0.72em;font-weight:700;color:#667eea;letter-spacing:.06em;margin-bottom:4px;">SCORE</div>' +
                    '<div style="font-size:2.5em;font-weight:800;color:#333;">' + score + '</div>' +
                '</div>' +
                '<div style="text-align:center;padding:16px 24px;border:2px solid ' + color + ';border-radius:8px;">' +
                    '<div style="font-size:0.72em;font-weight:700;color:#667eea;letter-spacing:.06em;margin-bottom:4px;">RESULT</div>' +
                    '<div style="font-size:1.15em;font-weight:800;color:' + color + ';margin-top:4px;">' + label + '</div>' +
                '</div>' +
            '</div>' +
            (fb ? '<p style="color:#555;line-height:1.65;font-size:0.9em;text-align:left;margin-bottom:16px;padding:12px 14px;background:#f8f9fc;border-radius:8px;">' + fb + '</p>' : '') +
            '<div style="background:#f0f2ff;border-radius:8px;padding:14px 18px;font-size:0.85em;color:#667eea;font-weight:600;">' +
            'Your employer has been notified. You may close this tab.</div>';
    }}

    function showSubmittedTimeout() {{
        document.getElementById('submittedCard').innerHTML =
            '<div style="font-size:3em;margin-bottom:16px;">submitted</div>' +
            '<h2 style="color:#333;font-size:1.5em;margin-bottom:12px;">Assessment Submitted</h2>' +
            '<p style="color:#666;line-height:1.7;margin-bottom:24px;font-size:0.95em;">' +
            'Evaluation is taking longer than expected.<br>' +
            'Your employer will be notified when results are ready.</p>' +
            '<div style="background:#fff8e1;border-radius:8px;padding:14px 18px;font-size:0.85em;color:#5d4037;font-weight:600;">' +
            'You may close this tab.</div>';
    }}

    async function startPolling(submissionId) {{
        if (!submissionId) {{
            document.getElementById('assessment').style.display = 'none';
            document.getElementById('submitted').style.display  = 'flex';
            showSubmittedTimeout();
            return;
        }}

        document.getElementById('assessment').style.display = 'none';
        document.getElementById('submitted').style.display  = 'flex';
        showSubmittedPolling();

        const POLL_MS  = 3000;
        const TIMEOUT  = 60000;
        const deadline = Date.now() + TIMEOUT;

        while (Date.now() < deadline) {{
            await new Promise(r => setTimeout(r, POLL_MS));
            try {{
                const res  = await fetch('/api/submission/' + submissionId);
                if (res.ok) {{
                    const data = await res.json();
                    if (data.hire_evaluation && data.hire_evaluation.evaluated_at) {{
                        showSubmittedResults(data);
                        return;
                    }}
                }}
            }} catch (_) {{
                // network hiccup - keep polling
            }}
        }}

        showSubmittedTimeout();
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


@student_bp.route('/student/preview/<challenge_id>')
def student_preview(challenge_id):
    # Previews the challenge TEMPLATE (challenges table), not a specific
    # generated assignment. If an employer edits an assignment after
    # generating it from this challenge, this preview will not reflect
    # that drift — see Story 6.4 Review Findings for the follow-up story.
    row = db_service.get_challenge(challenge_id)
    if not row:
        return jsonify({"detail": "Challenge not found"}), 404

    _, title, domain, description, evaluation_rubric_json, starter_code, \
        challenge_type, skill_area, difficulty, ai_assistance_mode, \
        is_published, created_at = row

    safe_title = html_module.escape(title or 'Untitled Challenge')
    safe_description = html_module.escape(description or '')
    safe_criteria = html_module.escape(
        str(evaluation_rubric_json) if evaluation_rubric_json
        else 'Evaluation criteria set by employer.'
    )
    safe_code = html_module.escape(
        starter_code or '# No starter code provided for this challenge.'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[Preview] {safe_title} — hire-signal</title>
    <style>
        *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}

        /* ── Preview banner ── */
        .preview-banner {{
            position: fixed;
            top: 0; left: 0; right: 0;
            z-index: 999;
            background: #fff3cd;
            border-bottom: 2px solid #ffc107;
            color: #856404;
            font-size: 0.85em;
            font-weight: 700;
            text-align: center;
            padding: 10px 16px;
            letter-spacing: 0.03em;
        }}

        /* ── Landing screen ── */
        #landing {{
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 64px 20px 32px;
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
        .landing-body {{ padding: 36px 40px; }}
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

        /* ── Assessment screen ── */
        #assessment {{
            display: none;
            flex-direction: column;
            height: 100vh;
            padding-top: 42px;
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
            max-width: 60%;
        }}
        .assess-actions {{ display: flex; gap: 8px; align-items: center; }}
        .btn-submit-disabled {{
            background: white;
            color: #667eea;
            border: none;
            border-radius: 6px;
            padding: 7px 18px;
            font-weight: 700;
            font-size: 0.88em;
            cursor: not-allowed;
            opacity: 0.45;
        }}

        /* ── Starter code viewer ── */
        .preview-code-viewer {{
            flex: 1;
            overflow: auto;
            background: #1e1e2e;
            color: #cdd6f4;
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.88em;
            line-height: 1.6;
            padding: 24px 28px;
            margin: 0;
            white-space: pre;
        }}
    </style>
</head>
<body>

<!-- Preview banner (fixed, visible on all screens) -->
<div class="preview-banner">Preview Mode — No session data is recorded</div>

<!-- ══════════════════════════════════════════════════════ -->
<!-- LANDING SCREEN                                         -->
<!-- ══════════════════════════════════════════════════════ -->
<div id="landing">
    <div class="landing-card">
        <div class="landing-header">
            <div class="badge">hire-signal · Preview</div>
            <h1>{safe_title}</h1>
            <div class="meta">Preview Mode · Candidate view · No data recorded</div>
        </div>
        <div class="landing-body">
            <div class="info-grid">
                <div class="info-box">
                    <h3>Challenge Description</h3>
                    <p>{safe_description}</p>
                </div>
                <div class="info-box">
                    <h3>Evaluation Criteria</h3>
                    <p>{safe_criteria}</p>
                </div>
            </div>
            <button class="btn-start" onclick="startPreview()">
                Start Preview
            </button>
        </div>
    </div>
</div>

<!-- ══════════════════════════════════════════════════════ -->
<!-- ASSESSMENT SCREEN                                      -->
<!-- ══════════════════════════════════════════════════════ -->
<div id="assessment">
    <div class="assess-topbar">
        <div class="assess-title">[Preview] {safe_title}</div>
        <div class="assess-actions">
            <button class="btn-submit-disabled" disabled title="Disabled in preview">
                Submit Assessment
            </button>
        </div>
    </div>
    <pre class="preview-code-viewer">{safe_code}</pre>
</div>

<script>
    function startPreview() {{
        document.getElementById('landing').style.display = 'none';
        document.getElementById('assessment').style.display = 'flex';
    }}
</script>
</body>
</html>"""

    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
