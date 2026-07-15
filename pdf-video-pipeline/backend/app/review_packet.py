from __future__ import annotations

from html import escape

from .schemas import DocumentProfile, ReviewRecord


def render_review_packet(review: ReviewRecord, document: DocumentProfile) -> str:
    brief = review.creative_brief
    scenes_markup = "".join(
        f"""
        <section class="scene">
          <div class="scene-meta">Scene {scene.scene_number} · {scene.duration_seconds}s</div>
          <h3>{escape(scene.title)}</h3>
          <p>{escape(scene.narration)}</p>
          <div class="prompt">{escape(scene.visual_prompt)}</div>
          <div class="motion">Motion direction: {escape(scene.motion_direction)}</div>
        </section>
        """
        for scene in brief.scenes
    )
    key_messages = "".join(f"<li>{escape(message)}</li>" for message in brief.key_messages)
    visual_references = "".join(
        f"<li>{escape(reference)}</li>" for reference in brief.visual_references
    )
    entities = "".join(f"<li>{escape(entity)}</li>" for entity in document.entities[:8])

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Review Packet · {escape(document.filename)}</title>
    <style>
      body {{
        margin: 0;
        font-family: Inter, Arial, sans-serif;
        background: #f8fafc;
        color: #0f172a;
      }}
      .page {{
        max-width: 980px;
        margin: 0 auto;
        padding: 40px 28px 64px;
      }}
      .hero {{
        background: linear-gradient(135deg, #0f172a, #1d4ed8);
        color: white;
        border-radius: 24px;
        padding: 32px;
        margin-bottom: 28px;
      }}
      .eyebrow {{
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font-size: 12px;
        opacity: 0.82;
      }}
      h1, h2, h3, p {{
        margin-top: 0;
      }}
      .lede {{
        max-width: 60ch;
        color: #dbeafe;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 18px;
        margin-bottom: 24px;
      }}
      .card {{
        background: white;
        border: 1px solid #dbe4f0;
        border-radius: 18px;
        padding: 20px;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
      }}
      ul {{
        margin: 0;
        padding-left: 18px;
      }}
      .packet-quote {{
        font-size: 20px;
        line-height: 1.5;
        color: #1e3a8a;
        padding: 18px 20px;
        border-left: 4px solid #60a5fa;
        background: #eff6ff;
        border-radius: 12px;
        margin-bottom: 24px;
      }}
      .scene-list {{
        display: grid;
        gap: 16px;
      }}
      .scene {{
        background: white;
        border-radius: 18px;
        padding: 20px;
        border: 1px solid #dbe4f0;
      }}
      .scene-meta {{
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748b;
        margin-bottom: 8px;
      }}
      .prompt, .motion {{
        margin-top: 12px;
        border-radius: 12px;
        background: #f8fafc;
        padding: 12px 14px;
      }}
      .footer {{
        margin-top: 28px;
        color: #475569;
      }}
      @media (max-width: 720px) {{
        .grid {{
          grid-template-columns: 1fr;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="page">
      <section class="hero">
        <div class="eyebrow">Human Review Packet</div>
        <h1>{escape(brief.summary)}</h1>
        <p class="lede">
          This packet exists to help the reviewer make a humane, creative, and decisive call:
          is this document becoming the right video, with the right emotional weight, for the
          right audience?
        </p>
      </section>

      <div class="packet-quote">
        The heart of this piece is <strong>{escape(brief.look_and_feel_prompt)}</strong>:
        a {escape(brief.style_direction)} treatment intended to leave the audience feeling that
        the source document matters now, not later.
      </div>

      <section class="grid">
        <article class="card">
          <h2>Source Document</h2>
          <p><strong>Filename:</strong> {escape(document.filename)}</p>
          <p><strong>Document type:</strong> {escape(document.document_type.value)}</p>
          <p><strong>Pages:</strong> {document.page_count}</p>
          <p><strong>Extraction confidence:</strong> {document.extraction_confidence:.0%}</p>
          <p><strong>Parser:</strong> {escape(document.parser_used)}</p>
          <p>{escape(document.summary)}</p>
        </article>

        <article class="card">
          <h2>Creative Direction</h2>
          <p><strong>Look and feel:</strong> {escape(brief.look_and_feel_prompt)}</p>
          <p><strong>Pacing:</strong> {escape(brief.pacing)}</p>
          <p><strong>Aspect ratio:</strong> {escape(brief.aspect_ratio)}</p>
          <p><strong>Palette:</strong> {escape(", ".join(brief.palette))}</p>
          <p><strong>Typography:</strong> {escape(", ".join(brief.typography))}</p>
          <p><strong>Camera language:</strong> {escape(", ".join(brief.camera_language))}</p>
        </article>

        <article class="card">
          <h2>Key Messages</h2>
          <ul>{key_messages or "<li>No key messages extracted yet.</li>"}</ul>
        </article>

        <article class="card">
          <h2>Visual Signals</h2>
          <ul>{visual_references or "<li>No visual references extracted yet.</li>"}</ul>
        </article>

        <article class="card">
          <h2>Detected Entities</h2>
          <ul>{entities or "<li>No entities extracted yet.</li>"}</ul>
        </article>

        <article class="card">
          <h2>Reviewer Checklist</h2>
          <ul>
            <li>Does the emotional tone feel aligned with the source document?</li>
            <li>Does the visual style elevate the document instead of merely restating it?</li>
            <li>Would a viewer understand why this story deserves motion treatment?</li>
            <li>Is the CTA credible, clear, and appropriate for the audience?</li>
          </ul>
        </article>
      </section>

      <section>
        <h2>Scene Plan</h2>
        <div class="scene-list">{scenes_markup}</div>
      </section>

      <p class="footer">
        Review ID: {escape(str(review.review_id))} · Workflow: {escape(review.workflow_name or "not started")}
      </p>
    </main>
  </body>
</html>
"""
