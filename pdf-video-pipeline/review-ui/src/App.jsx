import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const initialForm = {
  reviewerId: 'creative.approver',
  status: 'approved',
  editedLookAndFeelPrompt: '',
  editedPalette: '',
  reviewerNotes: '',
}

function App() {
  const [reviews, setReviews] = useState([])
  const [selectedReviewId, setSelectedReviewId] = useState('')
  const [tooling, setTooling] = useState(null)
  const [mvp, setMvp] = useState(null)
  const [form, setForm] = useState(initialForm)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [isDragActive, setIsDragActive] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isStartingWorkflow, setIsStartingWorkflow] = useState(false)
  const [startingReviewId, setStartingReviewId] = useState('')

  const selectedReview = useMemo(
    () => reviews.find((review) => review.review_id === selectedReviewId) ?? reviews[0] ?? null,
    [reviews, selectedReviewId],
  )

  async function fetchJson(path, options) {
    const response = await fetch(`${API_BASE_URL}${path}`, options)
    if (!response.ok) {
      const responseText = await response.text()
      if (responseText) {
        let payload = null
        try {
          payload = JSON.parse(responseText)
        } catch {}
        if (typeof payload?.detail === 'string' && payload.detail) {
          throw new Error(payload.detail)
        }
        throw new Error(responseText)
      }
      throw new Error(`Request failed: ${response.status}`)
    }
    return response.json()
  }

  async function uploadPdf(file) {
    if (!file) {
      return
    }
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please drop a PDF document.')
      return
    }

    const body = new FormData()
    body.append('file', file)
    body.append('requested_look_and_feel', 'hero design')
    body.append('requested_by', 'review-ui-drag-drop')

    try {
      setError('')
      setMessage('')
      setIsUploading(true)
      const response = await fetch(`${API_BASE_URL}/reviews/upload-pdf`, {
        method: 'POST',
        body,
      })
      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status}`)
      }
      const review = await response.json()
      setReviews((current) => [review, ...current.filter((entry) => entry.review_id !== review.review_id)])
      setSelectedReviewId(review.review_id)
      setMessage(`Added ${file.name} to pending reviews.`)
    } catch (uploadError) {
      setError(uploadError.message)
    } finally {
      setIsUploading(false)
      setIsDragActive(false)
    }
  }

  async function loadData() {
    try {
      setError('')
      const [pendingReviews, toolingProfile, mvpProfile] = await Promise.all([
        fetchJson('/reviews?status=pending'),
        fetchJson('/tooling/profile'),
        fetchJson('/mvp'),
      ])
      setReviews(pendingReviews)
      setSelectedReviewId((current) => current || pendingReviews[0]?.review_id || '')
      setTooling(toolingProfile)
      setMvp(mvpProfile)
    } catch (loadError) {
      setError(loadError.message)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    setMessage('')
    setForm(initialForm)
  }, [selectedReviewId])

  async function submitDecision(event) {
    event.preventDefault()

    if (!selectedReview) {
      setError('Select a review before submitting a decision.')
      return
    }

    const payload = {
      review_id: selectedReview.review_id,
      job_id: selectedReview.creative_brief.job_id,
      status: form.status,
      reviewer_id: form.reviewerId,
      reviewer_notes: form.reviewerNotes,
      edited_look_and_feel_prompt: form.editedLookAndFeelPrompt || null,
      edited_palette: form.editedPalette
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean),
      structured_delta: {
        style_direction:
          form.status === 'changes_requested' ? 'rework requested by creative reviewer' : undefined,
      },
    }

    try {
      setError('')
      const updatedReview = await fetchJson(`/reviews/${selectedReview.review_id}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      setReviews((currentReviews) =>
        currentReviews.map((review) =>
          review.review_id === updatedReview.review_id ? updatedReview : review,
        ),
      )
      setMessage(`Submitted ${payload.status.replace('_', ' ')} decision for ${selectedReview.review_id}.`)
    } catch (submitError) {
      setError(submitError.message)
    }
  }

  async function startWorkflow() {
    if (!selectedReview) {
      setError('Select a review before starting a workflow.')
      return
    }

    try {
      setError('')
      setMessage('')
      setIsStartingWorkflow(true)
      setStartingReviewId(selectedReview.review_id)
      const updatedReview = await fetchJson(`/reviews/${selectedReview.review_id}/start-workflow`, {
        method: 'POST',
      })
      setReviews((currentReviews) =>
        currentReviews.map((review) =>
          review.review_id === updatedReview.review_id ? updatedReview : review,
        ),
      )
      setMessage(
        `Started ${updatedReview.workflow_name} for ${selectedReview.creative_brief.summary}.`,
      )
    } catch (startError) {
      setError(startError.message)
    } finally {
      setIsStartingWorkflow(false)
      setStartingReviewId('')
    }
  }

  async function startWorkflowForReview(review) {
    setSelectedReviewId(review.review_id)
    if (selectedReview?.review_id === review.review_id) {
      await startWorkflow()
      return
    }

    try {
      setError('')
      setMessage('')
      setIsStartingWorkflow(true)
      setStartingReviewId(review.review_id)
      const updatedReview = await fetchJson(`/reviews/${review.review_id}/start-workflow`, {
        method: 'POST',
      })
      setReviews((currentReviews) =>
        currentReviews.map((entry) =>
          entry.review_id === updatedReview.review_id ? updatedReview : entry,
        ),
      )
      setMessage(`Started ${updatedReview.workflow_name} for ${review.creative_brief.summary}.`)
    } catch (startError) {
      setError(startError.message)
    } finally {
      setIsStartingWorkflow(false)
      setStartingReviewId('')
    }
  }

  function handleDragOver(event) {
    event.preventDefault()
    setIsDragActive(true)
  }

  function handleDragLeave(event) {
    if (event.currentTarget.contains(event.relatedTarget)) {
      return
    }
    setIsDragActive(false)
  }

  function handleDrop(event) {
    event.preventDefault()
    const file = event.dataTransfer.files?.[0]
    void uploadPdf(file)
  }

  function handleFileChange(event) {
    const file = event.target.files?.[0]
    void uploadPdf(file)
    event.target.value = ''
  }

  function getPacketUrl(review) {
    return review.packet_url ?? `${API_BASE_URL}/reviews/${review.review_id}/packet`
  }

  function workflowButtonLabel(review) {
    if (review.workflow_status === 'started') {
      return 'Workflow started'
    }
    if (review.workflow_status === 'starting') {
      return 'Starting workflow...'
    }
    if (isStartingWorkflow && review.review_id === startingReviewId) {
      return 'Starting workflow...'
    }
    return 'Start workflow'
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Conductor OSS HITL</p>
          <h1>PDF-to-video style review</h1>
          <p className="lede">
            Review the generated creative brief, adjust the look-and-feel prompt, and send a
            structured decision back to the pipeline.
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={loadData}>
          Refresh
        </button>
      </header>

      {error ? <p className="banner error">{error}</p> : null}
      {message ? <p className="banner success">{message}</p> : null}

      <section className="grid">
        <aside className="panel review-list">
          <h2>Pending reviews</h2>
          <label
            className={`upload-dropzone ${isDragActive ? 'drag-active' : ''} ${
              isUploading ? 'uploading' : ''
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <input type="file" accept="application/pdf,.pdf" onChange={handleFileChange} />
            <strong>{isUploading ? 'Uploading PDF...' : 'Drag and drop a PDF here'}</strong>
            <span>Or click to browse and create a pending review from the uploaded document.</span>
          </label>
          {reviews.length === 0 ? (
            <p className="empty-state">
              No pending reviews yet. Drop a PDF here or create one through the backend or Conductor workflow.
            </p>
          ) : (
            reviews.map((review) => (
              <article
                key={review.review_id}
                className={`review-card ${
                  review.review_id === selectedReview?.review_id ? 'selected' : ''
                }`}
              >
                <button
                  type="button"
                  className="review-select"
                  onClick={() => setSelectedReviewId(review.review_id)}
                >
                  <strong>{review.creative_brief.summary}</strong>
                  <span>{review.review_id}</span>
                  <span>Status: {review.status}</span>
                </button>
                <button
                  type="button"
                  className="review-start-button"
                  disabled={
                    isStartingWorkflow ||
                    review.workflow_status === 'started' ||
                    review.workflow_status === 'starting'
                  }
                  onClick={() => {
                    void startWorkflowForReview(review)
                  }}
                >
                  {workflowButtonLabel(review)}
                </button>
                <a
                  className="review-packet-button"
                  href={getPacketUrl(review)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open review packet
                </a>
                <a
                  className="packet-url"
                  href={getPacketUrl(review)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {getPacketUrl(review)}
                </a>
              </article>
            ))
          )}
        </aside>

        <section className="panel brief-panel">
          <h2>Creative brief</h2>
          {selectedReview ? (
            <>
              <div className="workflow-cta">
                <div>
                  <span className="label">Processing state</span>
                  <p>
                    {selectedReview.workflow_status === 'started'
                      ? `Workflow started${selectedReview.workflow_id ? `: ${selectedReview.workflow_id}` : ''}`
                      : selectedReview.workflow_status === 'starting'
                        ? 'Workflow launch in progress. Please wait before clicking again.'
                        : 'Staged only, not yet processing'}
                  </p>
                </div>
                <button
                  type="button"
                  className="primary-button"
                  disabled={
                    isStartingWorkflow ||
                    selectedReview.workflow_status === 'started' ||
                    selectedReview.workflow_status === 'starting'
                  }
                  onClick={() => {
                    void startWorkflow()
                  }}
                >
                  {workflowButtonLabel(selectedReview)}
                </button>
              </div>
              <div className="review-packet-inline">
                <span className="label">Review packet</span>
                <a
                  className="secondary-button review-packet-inline-link"
                  href={getPacketUrl(selectedReview)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open review packet
                </a>
                <a
                  className="packet-url"
                  href={getPacketUrl(selectedReview)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {getPacketUrl(selectedReview)}
                </a>
              </div>
              <div className="brief-meta">
                <div>
                  <span className="label">Style prompt</span>
                  <p>{selectedReview.creative_brief.look_and_feel_prompt}</p>
                </div>
                <div>
                  <span className="label">Pacing</span>
                  <p>{selectedReview.creative_brief.pacing}</p>
                </div>
                <div>
                  <span className="label">Palette</span>
                  <p>{selectedReview.creative_brief.palette.join(', ')}</p>
                </div>
                <div>
                  <span className="label">Aspect ratio</span>
                  <p>{selectedReview.creative_brief.aspect_ratio}</p>
                </div>
              </div>

              <h3>Scenes</h3>
              <div className="scene-list">
                {selectedReview.creative_brief.scenes.map((scene) => (
                  <article key={scene.scene_number} className="scene-card">
                    <header>
                      <strong>
                        {scene.scene_number}. {scene.title}
                      </strong>
                      <span>{scene.duration_seconds}s</span>
                    </header>
                    <p>{scene.narration}</p>
                    <p className="mono">{scene.visual_prompt}</p>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <p className="empty-state">Select a review to inspect its creative brief.</p>
          )}
        </section>

        <section className="panel decision-panel">
          <h2>Submit decision</h2>
          <form onSubmit={submitDecision}>
            <label>
              Reviewer ID
              <input
                value={form.reviewerId}
                onChange={(event) => setForm((current) => ({ ...current, reviewerId: event.target.value }))}
              />
            </label>

            <label>
              Decision
              <select
                value={form.status}
                onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}
              >
                <option value="approved">Approved</option>
                <option value="changes_requested">Changes requested</option>
                <option value="rejected">Rejected</option>
              </select>
            </label>

            <label>
              Edited look-and-feel prompt
              <textarea
                rows="3"
                value={form.editedLookAndFeelPrompt}
                placeholder="Example: hero design with brighter product lighting and slower text reveals"
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    editedLookAndFeelPrompt: event.target.value,
                  }))
                }
              />
            </label>

            <label>
              Edited palette
              <input
                value={form.editedPalette}
                placeholder="#0F172A, #2563EB, #FBBF24"
                onChange={(event) => setForm((current) => ({ ...current, editedPalette: event.target.value }))}
              />
            </label>

            <label>
              Notes
              <textarea
                rows="4"
                value={form.reviewerNotes}
                placeholder="Describe what should change or why the brief is approved."
                onChange={(event) => setForm((current) => ({ ...current, reviewerNotes: event.target.value }))}
              />
            </label>

            <button type="submit" className="primary-button">
              Send decision
            </button>
          </form>
        </section>
      </section>

      <section className="grid secondary-grid">
        <section className="panel">
          <h2>Selected tooling</h2>
          {tooling ? (
            <dl className="tool-grid">
              <div>
                <dt>Parser</dt>
                <dd>{tooling.pdf_parser.name}</dd>
              </div>
              <div>
                <dt>Inference</dt>
                <dd>{tooling.inference_runtime.name}</dd>
              </div>
              <div>
                <dt>Review surface</dt>
                <dd>{tooling.review_surface.name}</dd>
              </div>
              <div>
                <dt>Video backend</dt>
                <dd>{tooling.video_generation.name}</dd>
              </div>
            </dl>
          ) : (
            <p className="empty-state">Tooling profile unavailable.</p>
          )}
        </section>

        <section className="panel">
          <h2>MVP guardrails</h2>
          {mvp ? (
            <>
              <p>Document classes: {mvp.supported_document_classes.join(', ')}</p>
              <p>Outputs: {mvp.output_formats.join(', ')}</p>
              <p>Primary backend: {mvp.primary_video_backend}</p>
            </>
          ) : (
            <p className="empty-state">MVP profile unavailable.</p>
          )}
        </section>
      </section>
    </main>
  )
}

export default App
