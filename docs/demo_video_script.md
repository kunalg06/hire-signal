# hire-signal — 3-Minute Leadership Review (Demo Video Script)

**Audience:** internal management/directors.
**Format:** 3-minute video, live single-take — one continuous screen recording,
narrated in real time (or dubbed after in one pass), no cuts.
**Status:** dry-run walkthrough completed 2026-07-19 against the real local
app (`http://localhost:8000`). All click-path steps below were verified
live in a real browser, not assumed. One blocking bug found during the dry
run (flagged candidates were invisible in the UI) has since been fixed and
re-verified — see "Fixed since the dry run" at the bottom.

Structure (Problem → Flow → Trust) converged on independently by three
`/bmad-party-mode` reviewers (Sally/UX, John/PM, Paige/Tech-Writer).

---

## Pre-recording checklist (do NOT do these on camera)

1. **Seed the demo data first.** Run `python scripts/seed_demo_candidates.py <assignment_id>`
   against a real, published "Token Bucket Rate Limiter" catalog challenge
   (hand-authored in `scripts/seed_challenges.py` — do NOT use a freshly
   AI-generated challenge; one was tried and abandoned mid-session because
   its auto-generated bug comments were factually wrong and tanked every
   candidate's score regardless of fix quality). This produces 6 candidates
   spanning every tier the script needs — see table below.
2. **Confirm which candidate is which** before recording (composite scores
   are real Gemini output and will vary slightly run to run):
   - One clean, un-flagged, high-scoring candidate (`hire` tier) — reserved,
     do NOT flag or override it ahead of time. This is overridden **live**
     during the recording (the strongest beat in the video).
   - One candidate with a real code fix but zero AI session logs — this one
     auto-flags itself (`no_ai_engagement`), nothing to set up manually.
   - One candidate with the assignment's starter code submitted completely
     unchanged — scores a hard 0, also automatic.
   - Optionally, one candidate with a **pre-existing** override already
     applied, as a secondary "historical audit trail" example independent
     of the live-override beat.
3. **Pick a recording base URL and don't switch mid-take.** `http://localhost:8000`
   is recommended over the EC2 deployment — no security-group dependency,
   no cold-container risk on a small instance.
4. **Pre-stage the first click-heavy transition.** The candidate-view gate
   (see Beat 2 below) requires two throwaway clicks (Start Assessment, then
   the VS Code trust dialog) before the real workspace is visible. Time
   these to land during the tail end of the previous line's narration, not
   after — the driver's clicks don't have to wait for the narrator to
   finish talking.
5. Have `ffmpeg` available if you plan to burn in subtitles afterward
   (installed via `winget install --id Gyan.FFmpeg -e --source winget` on
   this machine already). Generate subtitles from the actual recorded
   audio track (Whisper, or DaVinci Resolve/Premiere's built-in
   speech-to-text) — not from this script's planned timestamps, which will
   drift from a live take's actual pacing.

---

## Script

| Timestamp | Narration (read at natural pace) | Screen / UI action | Verified notes |
|---|---|---|---|
| **0:00–0:20** | "Resumes and take-homes tell you if someone can code alone in a room. They don't tell you the thing every one of our engineers now does all day: work *with* AI. hire-signal watches that instead, and turns it into a number you can defend. Let me show you the real flow, live, no cuts." | Load `http://localhost:8000/`, click **📚 Challenge Catalog** tab. Idle on the grid. | Confirmed: default landing tab is "Generate Challenge" (a form — weak opening shot), so the Catalog click is a required first action, not optional framing. |
| **0:20–0:36** | "This is the challenge catalog. Employers either generate a new challenge — Gemini authors it against a problem statement and difficulty — or reuse a published one, like this one." | Click the **Token Bucket Rate Limiter** card. | Confirmed: click fires a toast — *"Assignment created from 'Token Bucket Rate Limiter'. Go to Student Link tab to generate a link."* — and creates a **new, throwaway** assignment (separate from the seeded one used later). This is expected; don't be alarmed by the extra assignment appearing in "Saved Assignments." |
| **0:36–0:52** | "From a challenge we create an assignment, and generating a candidate link spins up an isolated Docker container — browser-based VS Code, Gemini CLI pre-installed. The candidate does everything in that browser tab. We never touch their machine." | Click **🔗 Student Link** tab (assignment ID is pre-filled) → click **🔗 Generate Link**. | Confirmed: real container provisions in ~3–5 seconds; the "Student Access Link" panel shows the candidate URL, port, and expiry. Real, not simulated. |
| **0:52–1:15** | "Here's what the candidate actually sees." *(pause for the two gate clicks below, then continue)* "Full VS Code — and Gemini as a collaborator, working right in the terminal." | Open the Student Access Link in a new tab. Click **Start Assessment** (intro/gate screen). Click **Yes, I trust the authors** (VS Code trust dialog). Open the integrated terminal (`` Ctrl+` ``). | **Corrected from the original draft.** There are TWO gate screens before the real IDE is visible, not zero: (1) a "Before you start... Start Assessment" landing page, (2) a VS Code "Do you trust the authors" modal. Both are real and unavoidable on every fresh container — budget the clicks, don't skip past them in the plan. |
| **1:15–1:25** | "Gemini isn't a sidebar gimmick here — it's the same CLI a candidate would actually reach for." | Type `gemini` in the terminal (or reference it verbally without a live query, to stay on time budget). | **Corrected — important.** The right-hand "CHAT" panel visible in the IDE is a generic, unconfigured VS Code AI panel — **not** connected to Gemini in any way. Do not click into it or reference it as "the Gemini panel." The real integration is exclusively the terminal; confirmed `gemini` CLI v0.49.0 installed and working there. |
| **1:25–1:45** | "Once they submit, Gemini scores eight dimensions — problem decomposition, debugging with AI, token efficiency, and five more — and produces a composite. Here's a real one." | Switch to the main dashboard tab → **📊 Results** tab → select the seeded assignment → click the **top-ranked candidate's** `Detail` button → scroll down to reveal the score card and radar chart. | **Corrected.** State the *actual* composite score shown on screen, not a placeholder number — it's real Gemini output and won't be exactly the same every run. Also corrected: the Detail panel renders **below** the grid, not as an overlay — the scroll-down is a required step, not optional. |
| **1:45–2:00** | "The radar chart shows exactly where that number came from, dimension by dimension. Every candidate on this challenge lands on one ranked list — and a candidate who hasn't been evaluated yet always sorts last, never disappears. Score affects rank. It never hides anyone from you." | Point at the radar chart. Click **← Back to grid**. | |
| **2:00–2:20** | "And we just closed a real gap: submitting the starter code completely untouched used to score around fifty. Now it correctly scores zero. We also auto-flag any submission with real code changes but zero evidence of AI collaboration — because that's a case for a human's eyes, not an algorithm's guess." | Open the zero-score candidate's Detail. Back to grid. Open the flagged candidate's Detail — point at the 🚩 badge in the grid row and the orange "Flagged for review" banner in the Detail panel. | **Now fully working** — this beat was blocked in the original dry run (flag data existed but nothing rendered it anywhere in the UI, on any endpoint) and has since been fixed: a 🚩 badge now shows in the grid row, and a banner with the full reason renders in the Detail panel. Confirmed live: *"🚩 Flagged for review by system: Zero Gemini session logs recorded despite a real code change — composite reflects code quality only, not AI-collaboration signal. Needs human judgment on whether this is disqualifying."* |
| **2:20–2:42** | "The AI score is an input, never a verdict. Anyone on this team can flag a submission or override its recommendation, right here." | Back to grid → open the **reserved clean candidate's** Detail (scroll down) → click **✏️ Override Decision** → pick a recommendation from the dropdown → type a one-line rationale → click **Apply Override**, live. | Confirmed: form opens inline exactly as scripted — dropdown defaults to "Strong Hire," rationale placeholder reads "Why does your judgment differ from the AI?" This is the strongest beat — do it for real, don't fake it with a pre-existing override. |
| **2:42–2:55** | "That override is logged permanently, append-only, alongside the original AI score — which is never rewritten after the fact." | Stay on the same Detail panel; the override you just applied is now visible on screen (recommendation changed, original composite still shown unchanged). | |
| **2:55–3:05** | "Thresholds are enforced in code, not trusted from the model's own output. Human judgment stays in charge. That's hire-signal, end to end." | Return to the ranked grid as the closing frame. | |

Total runtime: ~3:05, a few seconds over the original 3:00 target due to the
two extra gate clicks in Beat 2 — trim narration pauses elsewhere if a hard
3:00 cutoff matters, don't rush the trust-dialog/Start Assessment clicks
themselves (they need real page-load time regardless of pacing).

---

## Known cosmetic bug — not fixed, worth knowing before recording

The "EVALUATION CRITERIA" panel on both the "Preview as Student" screen and
the real assessment intro screen renders the rubric as **raw, unparsed
JSON** (literal `{"criteria": [...]}` text) instead of a formatted list.
It's visible during Beat 2's gate screens. Don't let the driver's cursor
linger there or zoom in on it — narrate over it quickly, same as any other
transitional screen. This is a pre-existing display bug, unrelated to any
of this session's changes; fixing it is a separate, small frontend task if
it's worth doing before the actual recording.

---

## Fixed since the dry run (2026-07-19)

`get_candidates_for_assignment()` (`app/services/database_service.py`) was
missing `is_flagged`/`flag_reason` in its query entirely — a genuinely
flagged submission was invisible to the Results tab and Compare Candidates
tab (both navigate by assignment_id), even though the data existed and the
challenge-scoped sibling endpoint already selected it correctly. Beyond the
backend gap, **no frontend code anywhere rendered a flag indicator**, on
either endpoint — so even the challenge-scoped path was silently dead data
until now. Fixed: backend parity (both endpoints now return
`is_flagged`/`flag_reason`), plus new frontend rendering — a 🚩 badge in
both candidate grids and a reason banner in the Detail panel. 2 new tests,
full suite 211/211 passing. Live-reverified in the browser against the
seeded demo data before writing this script.
