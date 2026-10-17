"use client";

/** Last-resort boundary: replaces the root layout when it fails to render, so it carries its own html and body. */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", background: "#0f1216", color: "#e6e8eb", margin: 0 }}>
        <main role="alert" style={{ maxWidth: "60ch", margin: "0 auto", padding: "4rem 1rem" }}>
          <h1 style={{ fontSize: "1.25rem", fontWeight: 600 }}>KEP Brain could not start this page</h1>
          <p style={{ color: "#a3a9b3" }}>
            The application shell failed to render. Reload the page; if it keeps failing, the digest below identifies the error in
            the server logs.
          </p>
          {error.digest ? <p style={{ fontFamily: "monospace", fontSize: "0.75rem", color: "#7d8591" }}>digest {error.digest}</p> : null}
          <button
            type="button"
            onClick={reset}
            style={{ marginTop: "1rem", padding: "0.5rem 1rem", borderRadius: 6, border: "1px solid #3a4250", background: "#1a1f27", color: "inherit" }}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
