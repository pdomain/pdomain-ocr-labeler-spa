export function CudaSetupGuidance() {
  return (
    <section
      data-testid="cuda-setup-guidance"
      aria-labelledby="cuda-setup-heading"
      style={{
        marginTop: "12px",
        paddingTop: "12px",
        borderTop: "1px solid var(--border)",
      }}
    >
      <h3 key="heading" id="cuda-setup-heading" style={{ margin: "0 0 6px", fontSize: "0.95rem" }}>
        CUDA setup
      </h3>
      <p key="summary" style={{ fontSize: "0.85em", margin: "0 0 6px" }}>
        NVIDIA GPU can be detected even when CUDA is not usable by PyTorch. Hardware detection only
        means a GPU is present; GPU OCR needs the NVIDIA driver and a CUDA-enabled PyTorch build
        visible to this app.
      </p>
      <ol
        key="steps"
        style={{
          margin: "0 0 8px",
          paddingLeft: "1.2rem",
          fontSize: "0.85em",
        }}
      >
        <li key="driver">
          Run <code key="driver-command">nvidia-smi</code> and confirm it prints your GPU and
          driver.
        </li>
        <li key="torch">
          Run{" "}
          <code key="torch-command">
            python -c "import torch; print(torch.cuda.is_available())"
          </code>{" "}
          in the same environment that starts <code key="app-command">pdomain-ocr-labeler-ui</code>.
        </li>
        <li key="install">
          If <code key="install-driver-command">nvidia-smi</code> works but{" "}
          <code key="install-torch-command">torch.cuda.is_available()</code> is false, install a
          CUDA-enabled PyTorch build.
        </li>
      </ol>
      <a
        key="selector-link"
        href="https://pytorch.org/get-started/locally/"
        target="_blank"
        rel="noopener noreferrer"
      >
        PyTorch selector
      </a>
    </section>
  );
}
