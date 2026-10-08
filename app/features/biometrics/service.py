import cv2
import numpy as np

try:
    import torch
    import torch.nn.functional as F
    from deepface import DeepFace
    from deepface.modules import modeling
    from deepface.models.spoofing.FasNetUtils import crop
    from deepface.models.spoofing.pytorch.FasNet import Compose, ToTensor
    HAS_DEEPFACE = True
except Exception as e:
    print(f"[biometrics] Warning: DeepFace import skipped: {e}")
    torch = None
    F = None
    DeepFace = None
    modeling = None
    crop = None
    Compose = None
    ToTensor = None
    HAS_DEEPFACE = False

# ArcFace cosine distance threshold (standard is 0.68; 0.65 is recommended for stricter authentication)
COSINE_THRESHOLD = 0.65

# Lazy-loaded singleton for MiniFASNet model
_FASNET_MODEL = None

def get_fasnet_model():
    global _FASNET_MODEL
    if not HAS_DEEPFACE:
        return None
    if _FASNET_MODEL is None and modeling is not None:
        _FASNET_MODEL = modeling.build_model(task="spoofing", model_name="Fasnet")
    return _FASNET_MODEL

def decode_image(file_bytes: bytes) -> np.ndarray:
    """Decodes raw image bytes into an OpenCV BGR image matrix."""
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image file: unable to decode bytes.")
    return img

def cosine_distance(source_vector: list, test_vector: list) -> float:
    """Computes the cosine distance between two feature vectors."""
    a = np.array(source_vector, dtype=np.float32)
    b = np.array(test_vector, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return float(1.0 - (np.dot(a, b) / (norm_a * norm_b)))

def analyze_liveness_probabilities(img: np.ndarray, facial_area: tuple) -> dict:
    """
    Computes normalized probability distribution across MiniFASNet classes:
      - Class 0: 2D attack (paper / printout)
      - Class 1: Genuine human face
      - Class 2: 2D attack (digital screen replay)
    """
    model = get_fasnet_model()
    x, y, w, h = facial_area
    first_img = crop(img, (x, y, w, h), 2.7, 80, 80)
    second_img = crop(img, (x, y, w, h), 4, 80, 80)

    test_transform = Compose([ToTensor()])
    t1 = test_transform(first_img).unsqueeze(0).to(model.device)
    t2 = test_transform(second_img).unsqueeze(0).to(model.device)

    with torch.no_grad():
        r1 = F.softmax(model.first_model.forward(t1), dim=1).cpu().numpy()
        r2 = F.softmax(model.second_model.forward(t2), dim=1).cpu().numpy()

    prediction = (r1 + r2) / 2.0  # Normalized (sum = 1.0)
    paper_prob = float(prediction[0][0])
    real_prob = float(prediction[0][1])
    screen_prob = float(prediction[0][2])
    spoof_prob = paper_prob + screen_prob
    dominant_class = int(np.argmax(prediction[0]))

    return {
        "real_prob": round(real_prob, 4),
        "spoof_prob": round(spoof_prob, 4),
        "paper_prob": round(paper_prob, 4),
        "screen_prob": round(screen_prob, 4),
        "dominant_class": dominant_class
    }

def normalize_facial_area_to_square(facial_area: tuple, img_shape: tuple) -> tuple:
    """
    MiniFASNet was trained on square bounding boxes (w == h).
    Detectors like SSD return tall rectangular boxes (h >> w) which severely
    distorts MiniFASNet's contextual 2.7x and 4.0x crops, triggering false spoofs.
    This normalizes the bounding box to a square centered on the face.
    """
    img_h, img_w = img_shape[:2]
    x, y, w, h = facial_area
    side = max(w, h)
    cx = x + w // 2
    cy = y + h // 2

    sq_x = max(0, cx - side // 2)
    sq_y = max(0, cy - side // 2)
    sq_w = min(img_w - sq_x, side)
    sq_h = min(img_h - sq_y, side)
    return (int(sq_x), int(sq_y), int(sq_w), int(sq_h))

def evaluate_liveness(img: np.ndarray, facial_area: tuple, mode: str = "balanced") -> tuple[bool, str, dict]:
    """
    Evaluates face liveness based on the selected tolerance mode:
      - 'strict': High security. Requires dominant_class == 1 and real_prob >= 0.55
      - 'balanced': Default for webcams. Accepts if dominant_class == 1, real_prob >= 0.25, or spoof_prob <= 0.75
      - 'lenient': Accommodates poor webcam lighting, reflections, glasses. Accepts if dominant_class == 1 or spoof_prob <= 0.88
      - 'off': Completely bypasses anti-spoofing
    """
    mode = (mode or "balanced").lower().strip()
    if mode in ("off", "disabled", "false", "none", "0"):
        return True, "Anti-spoofing bypassed (mode: off)", {
            "real_prob": 1.0, "spoof_prob": 0.0, "paper_prob": 0.0, "screen_prob": 0.0, "mode": "off"
        }

    # Normalize face bounding box to a square for MiniFASNet
    sq_area = normalize_facial_area_to_square(facial_area, img.shape)
    probs = analyze_liveness_probabilities(img, sq_area)
    probs["mode"] = mode
    probs["original_box"] = list(facial_area)
    probs["squared_box"] = list(sq_area)
    real_p = probs["real_prob"]
    spoof_p = probs["spoof_prob"]
    dominant = probs["dominant_class"]

    if mode == "strict":
        if dominant == 1 and real_p >= 0.55:
            return True, f"Genuine face verified (confidence: {real_p:.1%})", probs
        else:
            return False, f"Spoof attempt detected (mode: strict, spoof: {spoof_p:.1%}, real: {real_p:.1%})", probs

    elif mode == "lenient":
        if dominant == 1 or real_p >= 0.15 or spoof_p <= 0.88:
            return True, f"Genuine face verified (mode: lenient, real: {real_p:.1%}, spoof: {spoof_p:.1%})", probs
        else:
            return False, f"Definite presentation attack detected (spoof: {spoof_p:.1%})", probs

    else:  # 'balanced' (default)
        if dominant == 1 or real_p >= 0.25 or spoof_p <= 0.75:
            return True, f"Genuine face verified (confidence: {real_p:.1%})", probs
        else:
            return False, f"Spoof attempt detected (screen/photo/paper: {spoof_p:.1%}, real: {real_p:.1%})", probs

def process_live_frame(
    img: np.ndarray, 
    detector: str = "opencv", 
    liveness_mode: str = "balanced"
) -> tuple[list | None, str | None, dict]:
    """
    Two-stage face authentication pipeline:
    1. Detects face and runs configurable MiniFASNet passive liveness detection.
    2. Extracts ArcFace 512-dimensional embedding for genuine faces.
    
    Returns:
        tuple (embedding: list | None, error_message: str | None, details: dict)
    """
    try:
        # Step 1: Detect face (prefer requested detector, fallback to opencv if needed)
        face_objs = None
        chosen_detector = detector or "opencv"
        try:
            face_objs = DeepFace.extract_faces(
                img_path=img,
                detector_backend=chosen_detector,
                enforce_detection=True
            )
        except Exception:
            if chosen_detector != "opencv":
                try:
                    face_objs = DeepFace.extract_faces(
                        img_path=img,
                        detector_backend="opencv",
                        enforce_detection=True
                    )
                    chosen_detector = "opencv"
                except Exception:
                    pass

        if not face_objs:
            return None, "No face detected in the frame. Please look directly at the camera.", {}

        face_data = face_objs[0]
        fa = face_data.get("facial_area", {})
        if isinstance(fa, dict):
            facial_tuple = (fa.get("x", 0), fa.get("y", 0), fa.get("w", 0), fa.get("h", 0))
        elif isinstance(fa, (list, tuple)) and len(fa) == 4:
            facial_tuple = tuple(fa)
        else:
            h, w = img.shape[:2]
            facial_tuple = (0, 0, w, h)

        # Step 2: Configurable Liveness Gate
        is_real, liveness_msg, liveness_details = evaluate_liveness(img, facial_tuple, mode=liveness_mode)
        liveness_details["detector"] = chosen_detector

        if not is_real:
            return None, liveness_msg, liveness_details

        # Step 3: ArcFace 512-d feature extraction
        reps = DeepFace.represent(
            img_path=img,
            model_name="ArcFace",
            detector_backend=chosen_detector,
            enforce_detection=False
        )

        if not reps:
            return None, "Failed to extract face embedding representation.", liveness_details

        return reps[0]["embedding"], None, liveness_details

    except Exception as e:
        return None, f"Inference error: {str(e)}", {}
