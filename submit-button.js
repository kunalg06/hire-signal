// Inject submit button into code-server UI
(function() {
  const LINK_ID = new URLSearchParams(window.location.search).get('link_id') ||
                   localStorage.getItem('assignment_link_id') ||
                   window.LINK_ID;

  if (!LINK_ID) {
    console.warn('No LINK_ID found for submission');
    return;
  }

  // Create submit button container
  const container = document.createElement('div');
  container.id = 'submit-btn-container';
  container.style.cssText = `
    position: fixed;
    top: 10px;
    right: 10px;
    z-index: 10000;
    display: flex;
    gap: 10px;
    font-family: system-ui, -apple-system, sans-serif;
  `;

  // Create submit button
  const submitBtn = document.createElement('button');
  submitBtn.innerHTML = '📤 Submit Solution';
  submitBtn.id = 'submit-assignment-btn';
  submitBtn.style.cssText = `
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    padding: 12px 20px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    transition: all 0.3s ease;
  `;

  submitBtn.onmouseover = () => {
    submitBtn.style.transform = 'translateY(-2px)';
    submitBtn.style.boxShadow = '0 6px 16px rgba(102, 126, 234, 0.6)';
  };

  submitBtn.onmouseout = () => {
    submitBtn.style.transform = 'translateY(0)';
    submitBtn.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.4)';
  };

  submitBtn.onclick = async () => {
    await submitSolution();
  };

  container.appendChild(submitBtn);
  document.body.appendChild(container);

  // Submission handler
  async function submitSolution() {
    const btn = submitBtn;
    const originalText = btn.innerHTML;

    try {
      btn.disabled = true;
      btn.innerHTML = '⏳ Submitting...';

      // Get link_id from query params or environment
      const linkId = LINK_ID;
      if (!linkId) {
        throw new Error('No link ID found');
      }

      // Submit the code
      const response = await fetch(`http://localhost:8000/api/submit-code/${linkId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.statusText}`);
      }

      const result = await response.json();

      btn.innerHTML = `✅ Score: ${result.score}/100`;
      btn.style.background = 'linear-gradient(135deg, #28a745 0%, #20c997 100%)';

      // Show results modal
      showResultsModal(result);

      // Close container after 5 seconds
      setTimeout(() => {
        fetch(`http://localhost:8000/api/close-container/${linkId}`, { method: 'POST' })
          .then(() => {
            alert('Container closed. Your submission has been saved.');
            btn.innerHTML = originalText;
            btn.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
          });
      }, 5000);

    } catch (error) {
      btn.innerHTML = '❌ Error';
      btn.style.background = '#dc3545';
      console.error('Submission error:', error);
      alert('Error submitting: ' + error.message);
      btn.disabled = false;
      btn.innerHTML = originalText;
      btn.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
    }
  }

  function showResultsModal(result) {
    const modal = document.createElement('div');
    modal.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: white;
      padding: 30px;
      border-radius: 12px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      z-index: 10001;
      max-width: 500px;
      font-family: system-ui, -apple-system, sans-serif;
    `;

    const scoreColor = result.score >= 70 ? '#28a745' : result.score >= 50 ? '#ffc107' : '#dc3545';

    modal.innerHTML = `
      <h2 style="color: #333; margin-bottom: 20px;">Evaluation Results</h2>
      <div style="background: ${scoreColor}; color: white; padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 20px;">
        <div style="font-size: 48px; font-weight: bold;">${result.score}</div>
        <div style="font-size: 14px;">/ 100</div>
      </div>
      <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
        <strong>Feedback:</strong>
        <p style="margin-top: 10px; color: #666; white-space: pre-wrap; word-wrap: break-word;">${result.feedback}</p>
      </div>
      <button onclick="this.parentElement.remove()" style="width: 100%; padding: 12px; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">Close</button>
    `;

    document.body.appendChild(modal);
  }
})();
