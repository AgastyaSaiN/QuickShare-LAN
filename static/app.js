const socket = io();
const fileInput = document.querySelector("#fileInput");
const uploadForm = document.querySelector("#uploadForm");
const dropZone = document.querySelector("#dropZone");
const fileList = document.querySelector("#fileList");
const fileCount = document.querySelector("#fileCount");
const progress = document.querySelector("#uploadProgress");
const progressBar = document.querySelector("#progressBar");
const refreshButton = document.querySelector("#refreshButton");
const pad = document.querySelector("#sharedPad");
const saveStatus = document.querySelector("#saveStatus");
const characterCount = document.querySelector("#characterCount");
const copyButton = document.querySelector("#copyButton");
const statusDot = document.querySelector("#statusDot");
const connectionText = document.querySelector("#connectionText");
const toast = document.querySelector("#toast");

let padTimer;
let applyingRemoteUpdate = false;
let toastTimer;

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2600);
}

function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), 3);
  return `${(bytes / (1024 ** unitIndex)).toFixed(unitIndex ? 1 : 0)} ${units[unitIndex]}`;
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value;
  return element.innerHTML;
}

function fileExtension(name) {
  const parts = name.split(".");
  return parts.length > 1 ? parts.pop().slice(0, 4) : "file";
}

async function loadFiles() {
  try {
    const response = await fetch("/api/files");
    const files = await response.json();
    fileCount.textContent = `${files.length} ${files.length === 1 ? "file" : "files"}`;

    if (!files.length) {
      fileList.innerHTML = '<div class="empty-state">No files yet. Upload one for the LAN.</div>';
      return;
    }

    fileList.innerHTML = files.map((file) => `
      <div class="file-row">
        <span class="file-icon">${escapeHtml(fileExtension(file.name))}</span>
        <div class="file-meta">
          <div class="file-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</div>
          <div class="file-details">${formatBytes(file.size)} · ${new Date(file.modified).toLocaleString()}</div>
        </div>
        <div class="file-actions">
          <a class="download-link" href="/files/${encodeURIComponent(file.name)}">Download</a>
          <button class="delete-button" type="button" data-filename="${escapeHtml(file.name)}">Delete</button>
        </div>
      </div>
    `).join("");
  } catch (_error) {
    fileList.innerHTML = '<div class="empty-state">Could not load files.</div>';
  }
}

function uploadFiles(files) {
  if (!files.length) return;

  const formData = new FormData();
  [...files].forEach((file) => formData.append("files", file));
  const request = new XMLHttpRequest();

  progress.hidden = false;
  progressBar.style.width = "0%";
  request.upload.addEventListener("progress", (event) => {
    if (event.lengthComputable) {
      progressBar.style.width = `${Math.round((event.loaded / event.total) * 100)}%`;
    }
  });
  request.addEventListener("load", () => {
    progress.hidden = true;
    fileInput.value = "";
    if (request.status >= 200 && request.status < 300) {
      showToast("Upload complete");
      loadFiles();
    } else {
      let message = "Upload failed";
      try {
        message = JSON.parse(request.responseText).error || message;
      } catch (_error) {
        // Keep the generic message for non-JSON errors.
      }
      showToast(message);
    }
  });
  request.addEventListener("error", () => {
    progress.hidden = true;
    showToast("Upload failed: server unreachable");
  });
  request.open("POST", "/api/upload");
  request.send(formData);
}

uploadForm.addEventListener("submit", (event) => event.preventDefault());
fileInput.addEventListener("change", () => uploadFiles(fileInput.files));
refreshButton.addEventListener("click", loadFiles);
fileList.addEventListener("click", async (event) => {
  const button = event.target.closest(".delete-button");
  if (!button) return;

  const filename = button.dataset.filename;
  if (!window.confirm(`Delete "${filename}" for everyone?`)) return;

  button.disabled = true;
  try {
    const response = await fetch(`/api/files/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.error || "Delete failed");
    }
    showToast(`Deleted ${filename}`);
    loadFiles();
  } catch (error) {
    button.disabled = false;
    showToast(error.message);
  }
});

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
});

dropZone.addEventListener("drop", (event) => uploadFiles(event.dataTransfer.files));

function updateCharacterCount() {
  characterCount.textContent = `${pad.value.length.toLocaleString()} characters`;
}

pad.addEventListener("input", () => {
  if (applyingRemoteUpdate) return;
  updateCharacterCount();
  saveStatus.textContent = "Typing";
  clearTimeout(padTimer);
  padTimer = setTimeout(() => {
    socket.emit("pad_update", { text: pad.value });
    saveStatus.textContent = "Synced";
  }, 120);
});

copyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(pad.value);
    showToast("Pad copied");
  } catch (_error) {
    pad.select();
    document.execCommand("copy");
    showToast("Pad copied");
  }
});

socket.on("connect", () => {
  statusDot.classList.add("online");
  connectionText.textContent = "Live on LAN";
});

socket.on("disconnect", () => {
  statusDot.classList.remove("online");
  connectionText.textContent = "Reconnecting";
});

socket.on("pad_update", (data) => {
  const cursorStart = pad.selectionStart;
  const cursorEnd = pad.selectionEnd;
  applyingRemoteUpdate = true;
  pad.value = data.text || "";
  pad.setSelectionRange(
    Math.min(cursorStart, pad.value.length),
    Math.min(cursorEnd, pad.value.length)
  );
  applyingRemoteUpdate = false;
  saveStatus.textContent = "Synced";
  updateCharacterCount();
});

socket.on("files_changed", loadFiles);

loadFiles();
updateCharacterCount();
