
from pathlib import Path
import json
import shutil
import time
from .config import FACE_DISTANCE_THRESHOLD


class FaceIdentity:
    def __init__(self, root):
        self.root = Path(root) / 'biometrics'
        self.root.mkdir(exist_ok=True)

    def _cv(self):
        try:
            import cv2
            if not hasattr(cv2, 'face'):
                raise ImportError()
            return cv2
        except ImportError:
            raise ValueError('Face login needs opencv-contrib-python. Install requirements-face.txt in your virtual environment.') from None

    def _capture(self, enrollment):
        cv = self._cv()
        detector = cv.CascadeClassifier(cv.data.haarcascades + 'haarcascade_frontalface_default.xml')
        camera = cv.VideoCapture(0)
        if not camera.isOpened():
            camera.release()
            raise ValueError('Cannot open webcam. Check camera access and close other camera apps.')
        samples, positions = [], []
        start = time.monotonic()
        last = start
        window = 'BookNest face enrollment' if enrollment else 'BookNest face login'
        try:
            while time.monotonic() - start < 20:
                ok, frame = camera.read()
                if not ok:
                    continue
                gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
                faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
                if len(faces) == 1:
                    x, y, w, h = faces[0]
                    crop = cv.equalizeHist(cv.resize(gray[y:y+h, x:x+w], (160, 160)))
                    cv.rectangle(frame, (x, y), (x+w, y+h), (80, 210, 110), 2)
                    if time.monotonic() - last >= .33 and cv.Laplacian(crop, cv.CV_64F).var() > 40:
                        samples.append(crop)
                        positions.append((x+w/2) / frame.shape[1])
                        last = time.monotonic()
                cv.putText(frame, 'Move gently left/right; look up/down. ESC cancels.', (10, 30), cv.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
                cv.putText(frame, f'Usable samples: {len(samples)}', (10, 55), cv.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 1)
                cv.imshow(window, frame)
                if cv.waitKey(1) & 0xff == 27:
                    raise ValueError('Camera capture cancelled.')
                needed = 30 if enrollment else 10
                if len(samples) >= needed and max(positions)-min(positions) >= .035:
                    break
            if len(samples) < (20 if enrollment else 8):
                raise ValueError('Not enough clear face samples. Improve lighting and retry.')
            if max(positions)-min(positions) < .035:
                raise ValueError('Movement was not detected. Move gently left and right and retry.')
            return samples
        finally:
            camera.release()
            cv.destroyAllWindows()

    def enroll(self, uid):
        samples = self._capture(True)
        cv = self._cv()
        directory = self.root / uid
        directory.mkdir(exist_ok=True)
        for i, sample in enumerate(samples):
            cv.imwrite(str(directory / f'{i:03}.png'), sample)
        self.retrain()

    def retrain(self):
        cv = self._cv()
        import numpy as np
        samples, labels, users = [], [], []
        for folder in sorted(self.root.iterdir()):
            if not folder.is_dir():
                continue
            images = sorted(folder.glob('*.png'))
            if not images:
                continue
            label = len(users)
            users.append(folder.name)
            for path in images:
                image = cv.imread(str(path), cv.IMREAD_GRAYSCALE)
                if image is not None:
                    samples.append(image)
                    labels.append(label)
        modelpath = self.root / 'face-model.yml'
        if not samples:
            modelpath.unlink(missing_ok=True)
            (self.root / 'labels.json').unlink(missing_ok=True)
            return
        model = cv.face.LBPHFaceRecognizer_create()
        model.train(samples, np.array(labels, dtype=np.int32))
        model.write(str(modelpath))
        (self.root / 'labels.json').write_text(json.dumps(users), encoding='utf-8')

    def identify(self):
        cv = self._cv()
        modelpath = self.root / 'face-model.yml'
        if not modelpath.exists():
            raise ValueError('No enrolled faces. Register or ask the administrator to enroll first.')
        model = cv.face.LBPHFaceRecognizer_create()
        model.read(str(modelpath))
        users = json.loads((self.root / 'labels.json').read_text(encoding='utf-8'))
        votes = []
        for sample in self._capture(False):
            label, distance = model.predict(sample)
            if distance < FACE_DISTANCE_THRESHOLD and 0 <= label < len(users):
                votes.append((label, distance))
        from collections import Counter
        if not votes:
            raise ValueError("We couldn't recognize you. Please retry.")
        label, count = Counter(v[0] for v in votes).most_common(1)[0]
        if count < 6:
            raise ValueError('Recognition was inconsistent. Please retry.')
        return users[label], sum(d for l, d in votes if l == label) / count

    def delete(self, uid):
        shutil.rmtree(self.root / uid, ignore_errors=True)
        self.retrain()
