/**
 * Face Attendance System - Client-side scripts
 */

// --- 1. THEME SWITCHER ---
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    const themeBtn = document.getElementById('themeToggleBtn');
    if (themeBtn) {
        themeBtn.innerHTML = savedTheme === 'dark' 
            ? '<i class="fas fa-sun text-warning"></i>' 
            : '<i class="fas fa-moon text-secondary"></i>';
    }
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    const themeBtn = document.getElementById('themeToggleBtn');
    if (themeBtn) {
        themeBtn.innerHTML = next === 'dark' 
            ? '<i class="fas fa-sun text-warning"></i>' 
            : '<i class="fas fa-moon text-secondary"></i>';
    }
}

// --- 2. TOAST NOTIFICATIONS ---
function showToast(title, message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toastId = 'toast-' + Date.now();
    const bgMap = {
        'success': '#10b981',
        'danger': '#ef4444',
        'warning': '#f59e0b',
        'info': '#2563eb'
    };
    const iconMap = {
        'success': 'fa-check-circle',
        'danger': 'fa-exclamation-circle',
        'warning': 'fa-exclamation-triangle',
        'info': 'fa-info-circle'
    };

    const color = bgMap[type] || bgMap['info'];
    const icon = iconMap[type] || iconMap['info'];

    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = 'card-custom shadow-lg mb-2 p-3 text-white';
    toast.style.background = color;
    toast.style.minWidth = '280px';
    toast.style.maxWidth = '380px';
    toast.style.animation = 'fadeIn 0.3s ease';

    toast.innerHTML = `
        <div class="d-flex align-items-center justify-content-between">
            <strong class="d-flex align-items-center gap-2">
                <i class="fas ${icon}"></i> ${title}
            </strong>
            <button type="button" class="btn-close btn-close-white btn-sm" onclick="document.getElementById('${toastId}').remove()"></button>
        </div>
        <div class="mt-1 small">${message}</div>
    `;

    container.appendChild(toast);
    setTimeout(() => {
        if (toast && toast.parentNode) {
            toast.remove();
        }
    }, 4500);
}

// --- 3. WEB AUDIO SYNTH CHIME ---
let audioMuted = false;
function playSuccessChime() {
    if (audioMuted) return;
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
        osc.frequency.exponentialRampToValueAtTime(880.00, audioCtx.currentTime + 0.15); // A5

        gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.35);

        osc.connect(gain);
        gain.connect(audioCtx.destination);

        osc.start();
        osc.stop(audioCtx.currentTime + 0.35);
    } catch (e) {
        // AudioContext not allowed before user gesture
    }
}

// --- 4. ATTENDANCE MONITOR POLLING ---
let attendancePoller = null;
let lastSeenTimestamp = '';

function startAttendanceMonitoring() {
    const statusPill = document.getElementById('cameraStatusPill');
    const detectionMsg = document.getElementById('latestDetectionMsg');
    const recentFeed = document.getElementById('attendanceLiveFeed');

    if (!statusPill) return;

    attendancePoller = setInterval(async () => {
        try {
            const resp = await fetch('/api/attendance_status');
            if (!resp.ok) return;
            const data = await resp.json();

            // Update Camera Status Pill
            if (statusPill) {
                if (data.camera_connected) {
                    statusPill.innerHTML = '<span class="pulse-dot"></span> Camera Active & Connected';
                    statusPill.className = 'badge bg-success-subtle text-success p-2 px-3 rounded-pill';
                } else {
                    statusPill.innerHTML = '<i class="fas fa-video-slash"></i> Camera Unavailable';
                    statusPill.className = 'badge bg-warning-subtle text-warning p-2 px-3 rounded-pill';
                }
            }

            // Update Latest Detection
            if (detectionMsg && data.latest_status) {
                detectionMsg.textContent = data.latest_status;
            }

            // Check for new event
            if (data.recent_events && data.recent_events.length > 0) {
                const latest = data.recent_events[0];
                const eventKey = `${latest.student_id}-${latest.timestamp}`;
                if (eventKey !== lastSeenTimestamp) {
                    lastSeenTimestamp = eventKey;
                    
                    if (latest.status === 'marked') {
                        playSuccessChime();
                        showToast('Attendance Marked', `${latest.name} (${latest.student_id}) marked present!`, 'success');
                    } else if (latest.status === 'already_marked') {
                        showToast('Already Marked', `${latest.name} was already marked present today.`, 'info');
                    }

                    // Add row to recentFeed if container exists
                    if (recentFeed) {
                        const newRow = document.createElement('tr');
                        newRow.className = 'table-success-subtle';
                        newRow.innerHTML = `
                            <td><strong class="text-primary">${latest.student_id}</strong></td>
                            <td>${latest.name}</td>
                            <td><span class="badge bg-secondary-subtle text-secondary">${latest.course}</span></td>
                            <td>${latest.timestamp}</td>
                            <td><span class="badge-present"><i class="fas fa-check"></i> Present</span></td>
                        `;
                        recentFeed.insertBefore(newRow, recentFeed.firstChild);
                        // Limit to 10 rows
                        while (recentFeed.children.length > 10) {
                            recentFeed.removeChild(recentFeed.lastChild);
                        }
                    }
                }
            }
        } catch (err) {
            console.error('Polling error:', err);
        }
    }, 1500);
}

// --- 5. STUDENT REGISTRATION FACE CAPTURE ---
async function captureFaceSample() {
    const btn = document.getElementById('btnTriggerCapture');
    const feedback = document.getElementById('captureFeedback');
    const encodingInput = document.getElementById('face_encoding');
    const previewContainer = document.getElementById('captureResultCard');
    const submitBtn = document.getElementById('btnSubmitRegistration');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Analyzing Facial Features...';
    }

    if (feedback) {
        feedback.innerHTML = '<div class="alert alert-info py-2"><i class="fas fa-spinner fa-spin me-2"></i> Capturing camera frames and extracting 256-D feature vectors...</div>';
    }

    try {
        const resp = await fetch('/api/capture_face', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const res = await resp.json();

        if (res.success) {
            playSuccessChime();
            if (encodingInput) encodingInput.value = JSON.stringify(res.encoding);
            if (feedback) {
                feedback.innerHTML = `
                    <div class="alert alert-success py-2">
                        <i class="fas fa-check-circle text-success me-2"></i>
                        <strong>${res.message}</strong> (${res.dimensions}-D facial biometric embedding extracted).
                    </div>
                `;
            }
            if (previewContainer) {
                previewContainer.classList.remove('d-none');
            }
            if (submitBtn) {
                submitBtn.disabled = false;
            }
            showToast('Biometrics Ready', 'Facial features extracted successfully!', 'success');
        } else {
            if (feedback) {
                feedback.innerHTML = `
                    <div class="alert alert-danger py-2">
                        <i class="fas fa-exclamation-circle text-danger me-2"></i>
                        ${res.message}
                    </div>
                `;
            }
            showToast('Face Capture Failed', res.message, 'danger');
        }
    } catch (err) {
        if (feedback) {
            feedback.innerHTML = `<div class="alert alert-danger py-2">Network or camera error: ${err.message}</div>`;
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-camera me-2"></i> Retake Face Capture';
        }
    }
}

// Initialize on DOM Load
document.addEventListener('DOMContentLoaded', () => {
    initTheme();

    const themeToggleBtn = document.getElementById('themeToggleBtn');
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', toggleTheme);
    }

    if (document.getElementById('attendanceLiveFeed') || document.getElementById('cameraStatusPill')) {
        startAttendanceMonitoring();
    }
});
